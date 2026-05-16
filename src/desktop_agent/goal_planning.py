"""Goal-to-routine planning schemas for local routine selection."""

from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Literal, Protocol, cast

from desktop_agent.config import LocalModelConfig
from desktop_agent.local_model_prompts import (
    PROMPT_CLASS_ROUTINE_RANKING,
    build_routine_ranking_prompt,
)
from desktop_agent.local_model_validation import validate_routine_ranking_response
from desktop_agent.routines import (
    RoutineCatalog,
    RoutineDefinition,
    RoutineDefinitionError,
    RoutineFailureCounters,
    require_validated_routine_for_execution,
)
from desktop_agent.scheduler import select_schedule_time

GoalExecutionStatus = Literal[
    "draft",
    "blocked",
    "ready",
    "running",
    "completed",
    "failed",
    "canceled",
]
GoalMissingPromptKind = Literal["routine_input", "session_state"]
GoalModelRankingStatus = Literal[
    "disabled",
    "skipped",
    "applied",
    "failed",
    "rejected",
]

SUPPORTED_GOAL_EXECUTION_STATUSES: frozenset[str] = frozenset(
    {"draft", "blocked", "ready", "running", "completed", "failed", "canceled"},
)
GOAL_ROUTER_SAFETY_RANK: dict[str, int] = {
    "low": 0,
    "medium": 1,
    "high": 2,
    "sensitive": 3,
}


class GoalPlanError(ValueError):
    """Raised when a goal plan fails schema validation."""


@dataclass(frozen=True)
class GoalPlanCandidate:
    """Candidate routine considered for a user goal."""

    routine_id: str
    routine_name: str
    score: float
    matched_fields: tuple[str, ...] = ()
    safety_class: str = "low"
    approval_policy: str = "none"

    def metadata(self) -> dict[str, object]:
        return {
            "routine_id": self.routine_id,
            "routine_name": self.routine_name,
            "score": self.score,
            "matched_fields": list(self.matched_fields),
            "safety_class": self.safety_class,
            "approval_policy": self.approval_policy,
        }


@dataclass(frozen=True)
class GoalPlanApproval:
    """Approval requirement that must be satisfied before execution."""

    policy: str
    required: bool
    satisfied: bool = False
    reason: str = ""

    def metadata(self) -> dict[str, object]:
        return {
            "policy": self.policy,
            "required": self.required,
            "satisfied": self.satisfied,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class GoalMissingInputPrompt:
    """Operator prompt for a missing routine input or session state."""

    key: str
    prompt: str
    kind: GoalMissingPromptKind
    required: bool = True

    def metadata(self) -> dict[str, object]:
        return {
            "key": self.key,
            "prompt": self.prompt,
            "kind": self.kind,
            "required": self.required,
        }


@dataclass(frozen=True)
class GoalModelRanking:
    """Traceable summary of optional local-model goal ranking assistance."""

    provider: str = "ollama"
    model: str = ""
    prompt_class: str = PROMPT_CLASS_ROUTINE_RANKING
    enabled: bool = False
    attempted: bool = False
    status: GoalModelRankingStatus = "disabled"
    selected_routine_id: str | None = None
    candidate_order: tuple[str, ...] = ()
    input_artifact_references: tuple[str, ...] = ()
    explanation: str = ""
    output_hash: str | None = None
    affected_selection: bool = False
    error: str | None = None

    def metadata(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "model": self.model,
            "prompt_class": self.prompt_class,
            "enabled": self.enabled,
            "attempted": self.attempted,
            "status": self.status,
            "selected_routine_id": self.selected_routine_id,
            "candidate_order": list(self.candidate_order),
            "input_artifact_references": list(self.input_artifact_references),
            "explanation": self.explanation,
            "output_hash": self.output_hash,
            "affected_selection": self.affected_selection,
            "error": self.error,
        }


@dataclass(frozen=True)
class GoalModelSuggestion:
    """Validated local-model suggestion before deterministic safety checks rerun."""

    selected_routine_id: str | None = None
    candidate_order: tuple[str, ...] = ()
    explanation: str = ""
    raw_output: str = ""


class GoalModelRanker(Protocol):
    """Advisory ranker that can only speak in known routine IDs."""

    def rank_goal_candidates(self, plan: GoalPlan) -> GoalModelSuggestion: ...


@dataclass(frozen=True)
class GoalRoutineIndexResult:
    """Routine index hit prepared for goal-plan candidate ranking."""

    routine: RoutineDefinition
    candidate: GoalPlanCandidate
    schedule_eligible: bool
    schedule_reason: str
    historical_success_rate: float | None = None
    historical_total_runs: int = 0

    def metadata(self) -> dict[str, object]:
        return {
            **self.candidate.metadata(),
            "schedule_eligible": self.schedule_eligible,
            "schedule_reason": self.schedule_reason,
            "historical_success_rate": self.historical_success_rate,
            "historical_total_runs": self.historical_total_runs,
        }


@dataclass(frozen=True)
class GoalRoutingRequest:
    """Deterministic routine-router inputs derived from a user goal."""

    user_goal: str
    normalized_intent: str
    required_app: str | None = None
    required_site: str | None = None
    tags: tuple[str, ...] = ()
    provided_inputs: tuple[str, ...] = ()
    max_safety_class: str = "sensitive"
    now: datetime | None = None


@dataclass(frozen=True)
class GoalPlan:
    """Planner output that maps a user goal to candidate routines."""

    user_goal: str
    normalized_intent: str
    candidate_routines: tuple[GoalPlanCandidate, ...] = ()
    selected_routine_id: str | None = None
    missing_inputs: tuple[str, ...] = ()
    approvals: tuple[GoalPlanApproval, ...] = ()
    explanation: str = ""
    execution_status: GoalExecutionStatus = "draft"
    model_ranking: GoalModelRanking | None = None

    @property
    def selected_candidate(self) -> GoalPlanCandidate | None:
        if self.selected_routine_id is None:
            return None
        for candidate in self.candidate_routines:
            if candidate.routine_id == self.selected_routine_id:
                return candidate
        return None

    @property
    def execution_ready(self) -> bool:
        return (
            self.execution_status == "ready"
            and self.selected_candidate is not None
            and not self.missing_inputs
            and all(
                not approval.required or approval.satisfied
                for approval in self.approvals
            )
        )

    def metadata(self) -> dict[str, object]:
        return {
            "user_goal": self.user_goal,
            "normalized_intent": self.normalized_intent,
            "candidate_routines": [
                candidate.metadata() for candidate in self.candidate_routines
            ],
            "selected_routine_id": self.selected_routine_id,
            "missing_inputs": list(self.missing_inputs),
            "approvals": [approval.metadata() for approval in self.approvals],
            "explanation": self.explanation,
            "execution_status": self.execution_status,
            "execution_ready": self.execution_ready,
            "model_ranking": (
                None if self.model_ranking is None else self.model_ranking.metadata()
            ),
        }


def goal_plan_from_mapping(data: dict[str, object]) -> GoalPlan:
    """Parse a JSON/YAML-style mapping into a validated GoalPlan."""
    plan = GoalPlan(
        user_goal=_required_string(data, "user_goal"),
        normalized_intent=_required_string(data, "normalized_intent"),
        candidate_routines=_candidate_tuple(data.get("candidate_routines")),
        selected_routine_id=_optional_string(data, "selected_routine_id"),
        missing_inputs=_string_tuple(data.get("missing_inputs"), "missing_inputs"),
        approvals=_approval_tuple(data.get("approvals")),
        explanation=_optional_string(data, "explanation") or "",
        execution_status=cast(
            GoalExecutionStatus,
            _optional_string(data, "execution_status") or "draft",
        ),
        model_ranking=_model_ranking_from_value(data.get("model_ranking")),
    )
    validate_goal_plan(plan)
    return plan


class OllamaGoalRanker:
    """Minimal Ollama adapter for advisory goal-plan candidate ranking."""

    def __init__(self, config: LocalModelConfig) -> None:
        self._config = config

    def rank_goal_candidates(self, plan: GoalPlan) -> GoalModelSuggestion:
        prompt = _ollama_goal_ranking_prompt(plan)
        body = {
            "model": self._config.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
        }
        request = urllib.request.Request(
            f"{self._config.endpoint.rstrip('/')}/api/generate",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=self._config.request_timeout_seconds,
            ) as response:
                response_body = response.read().decode("utf-8")
        except urllib.error.URLError as exc:
            raise GoalPlanError(f"Ollama request failed: {exc}") from exc

        payload = json.loads(response_body)
        if not isinstance(payload, dict):
            raise GoalPlanError("Ollama response must be a mapping")
        raw_model_output = payload.get("response")
        if not isinstance(raw_model_output, str):
            raise GoalPlanError("Ollama response field must be a string")
        return _goal_model_suggestion_from_raw(raw_model_output)


def search_routine_index_for_goal(
    catalog: RoutineCatalog,
    query: str,
    *,
    now: datetime | None = None,
    require_schedule_eligible: bool = False,
    failure_counters: Mapping[str, RoutineFailureCounters] | None = None,
    limit: int = 20,
) -> tuple[GoalRoutineIndexResult, ...]:
    """Search routine metadata and attach goal-planning eligibility fields."""
    results: list[GoalRoutineIndexResult] = []
    counters = failure_counters or {}
    for result in catalog.search(query, limit=limit):
        schedule_eligible, schedule_reason = _schedule_eligibility(
            result.routine,
            now,
        )
        if require_schedule_eligible and not schedule_eligible:
            continue
        historical_success_rate, historical_total_runs = _historical_success(
            counters.get(result.routine.id),
        )
        matched_fields = result.matched_fields
        if historical_success_rate is not None:
            matched_fields = (*matched_fields, "historical_success")
        results.append(
            GoalRoutineIndexResult(
                routine=result.routine,
                candidate=GoalPlanCandidate(
                    routine_id=result.routine.id,
                    routine_name=result.routine.name,
                    score=float(result.score),
                    matched_fields=matched_fields,
                    safety_class=result.routine.safety_class,
                    approval_policy=result.routine.approval_policy,
                ),
                schedule_eligible=schedule_eligible,
                schedule_reason=schedule_reason,
                historical_success_rate=historical_success_rate,
                historical_total_runs=historical_total_runs,
            ),
        )
    return tuple(results)


def missing_input_prompts(
    plan: GoalPlan,
    *,
    required_session_state: tuple[str, ...] = (),
) -> tuple[GoalMissingInputPrompt, ...]:
    """Build editable prompts for routine variables and session prerequisites."""
    prompts = [
        GoalMissingInputPrompt(
            key=input_name,
            prompt=f"Provide a value for routine input: {input_name}",
            kind="routine_input",
        )
        for input_name in plan.missing_inputs
    ]
    prompts.extend(
        GoalMissingInputPrompt(
            key=state_name,
            prompt=f"Confirm required session state is ready: {state_name}",
            kind="session_state",
        )
        for state_name in required_session_state
    )
    for prompt in prompts:
        validate_missing_input_prompt(prompt)
    return tuple(prompts)


def route_goal_to_routine(
    catalog: RoutineCatalog,
    request: GoalRoutingRequest,
    *,
    failure_counters: Mapping[str, RoutineFailureCounters] | None = None,
) -> GoalPlan:
    """Select the best known routine using deterministic router rules."""
    validate_goal_routing_request(request)
    indexed_results = search_routine_index_for_goal(
        catalog,
        request.normalized_intent or request.user_goal,
        now=request.now,
        require_schedule_eligible=True,
        failure_counters=failure_counters,
        limit=100,
    )
    ranked_candidates = _rank_goal_candidates(indexed_results, request)
    ambiguous_selection = _has_ambiguous_top_candidate(ranked_candidates)
    selected = (
        ranked_candidates[0] if ranked_candidates and not ambiguous_selection else None
    )
    missing_inputs = (
        _missing_inputs(catalog, selected.routine_id, request.provided_inputs)
        if selected is not None
        else ()
    )
    approvals = _approval_requirements(catalog, selected.routine_id) if selected else ()
    execution_status: GoalExecutionStatus = "ready"
    explanation = "Selected routine by deterministic ranking."
    selected_routine_id = selected.routine_id if selected else None
    if ambiguous_selection:
        execution_status = "blocked"
        explanation = "Ambiguous goal matched multiple routines; review alternatives."
    elif selected is None:
        execution_status = "blocked"
        explanation = "No eligible routine matched the goal and constraints."
    elif missing_inputs:
        execution_status = "blocked"
        explanation = "Selected routine is blocked by missing inputs."
    elif any(approval.required and not approval.satisfied for approval in approvals):
        execution_status = "blocked"
        explanation = "Selected routine is blocked by required approvals."
    plan = GoalPlan(
        user_goal=request.user_goal,
        normalized_intent=request.normalized_intent,
        candidate_routines=tuple(ranked_candidates),
        selected_routine_id=selected_routine_id,
        missing_inputs=missing_inputs,
        approvals=approvals,
        explanation=explanation,
        execution_status=execution_status,
    )
    validate_goal_plan(plan)
    return plan


def rank_goal_plan_with_optional_model(
    catalog: RoutineCatalog,
    request: GoalRoutingRequest,
    plan: GoalPlan,
    config: LocalModelConfig,
    *,
    ranker: GoalModelRanker | None = None,
) -> GoalPlan:
    """Apply opt-in local-model ranking without allowing new routine IDs."""
    validate_goal_plan(plan)
    validate_goal_routing_request(request)
    if not config.enabled or not config.use_for_goal_ranking:
        return _with_model_ranking(
            plan,
            GoalModelRanking(
                provider=config.provider,
                model=config.model,
                enabled=config.enabled,
                attempted=False,
                status="disabled",
                candidate_order=_candidate_order(plan),
                selected_routine_id=plan.selected_routine_id,
                explanation="Local model goal ranking is disabled by configuration.",
            ),
        )
    if not plan.candidate_routines:
        return _with_model_ranking(
            plan,
            GoalModelRanking(
                provider=config.provider,
                model=config.model,
                enabled=True,
                attempted=False,
                status="skipped",
                explanation="No deterministic candidates were available to rank.",
            ),
        )

    active_ranker = ranker or OllamaGoalRanker(config)
    try:
        suggestion = active_ranker.rank_goal_candidates(plan)
    except Exception as exc:
        return _with_model_ranking(
            plan,
            GoalModelRanking(
                provider=config.provider,
                model=config.model,
                enabled=True,
                attempted=True,
                status="failed",
                selected_routine_id=plan.selected_routine_id,
                candidate_order=_candidate_order(plan),
                explanation="Local model ranking failed; deterministic plan kept.",
                error=str(exc),
            ),
        )
    return _apply_model_suggestion(catalog, request, plan, config, suggestion)


def selected_routine_for_goal_execution(
    catalog: RoutineCatalog,
    plan: GoalPlan,
) -> RoutineDefinition:
    """Resolve a goal plan to an executable routine through the catalog gate."""
    validate_goal_plan(plan)
    if plan.selected_routine_id is None:
        raise GoalPlanError("goal plan has no selected routine")
    try:
        return require_validated_routine_for_execution(
            catalog,
            plan.selected_routine_id,
        )
    except RoutineDefinitionError as exc:
        raise GoalPlanError(str(exc)) from exc


def validate_missing_input_prompt(prompt: GoalMissingInputPrompt) -> None:
    """Validate prompt text before it is shown by CLI or operator UI layers."""
    errors: list[str] = []
    if not prompt.key.strip():
        errors.append("prompt key is required")
    if not prompt.prompt.strip():
        errors.append("prompt text is required")
    if prompt.kind not in {"routine_input", "session_state"}:
        errors.append("prompt kind must be routine_input or session_state")
    if errors:
        raise GoalPlanError("; ".join(errors))


def validate_goal_routing_request(request: GoalRoutingRequest) -> None:
    """Validate deterministic router constraints before scoring routines."""
    errors: list[str] = []
    if not request.user_goal.strip():
        errors.append("user_goal is required")
    if not request.normalized_intent.strip():
        errors.append("normalized_intent is required")
    if request.max_safety_class not in GOAL_ROUTER_SAFETY_RANK:
        errors.append("max_safety_class must be low, medium, high, or sensitive")
    if any(not tag.strip() for tag in request.tags):
        errors.append("tags entries must not be blank")
    if any(not item.strip() for item in request.provided_inputs):
        errors.append("provided_inputs entries must not be blank")
    if errors:
        raise GoalPlanError("; ".join(errors))


def validate_goal_plan(plan: GoalPlan) -> None:
    """Validate candidate, approval, and execution-state consistency."""
    errors: list[str] = []
    if not plan.user_goal.strip():
        errors.append("user_goal is required")
    if not plan.normalized_intent.strip():
        errors.append("normalized_intent is required")
    if plan.execution_status not in SUPPORTED_GOAL_EXECUTION_STATUSES:
        errors.append(f"unsupported execution_status: {plan.execution_status}")
    candidate_ids = [candidate.routine_id for candidate in plan.candidate_routines]
    if len(candidate_ids) != len(set(candidate_ids)):
        errors.append("candidate routine IDs must be unique")
    for candidate in plan.candidate_routines:
        errors.extend(_candidate_errors(candidate))
    if (
        plan.selected_routine_id is not None
        and plan.selected_routine_id not in candidate_ids
    ):
        errors.append("selected_routine_id must reference a candidate routine")
    if any(not item.strip() for item in plan.missing_inputs):
        errors.append("missing_inputs entries must not be blank")
    for approval in plan.approvals:
        errors.extend(_approval_errors(approval))
    if plan.model_ranking is not None:
        errors.extend(_model_ranking_errors(plan.model_ranking, set(candidate_ids)))
    if plan.execution_status == "ready" and not plan.execution_ready:
        errors.append("ready goal plans require selection, inputs, and approvals")
    if errors:
        raise GoalPlanError("; ".join(errors))


def _candidate_tuple(value: object) -> tuple[GoalPlanCandidate, ...]:
    if value is None:
        return ()
    if not isinstance(value, list | tuple):
        raise GoalPlanError("candidate_routines must be a list")
    return tuple(_candidate_from_mapping(_mapping(item)) for item in value)


def _candidate_from_mapping(data: dict[str, object]) -> GoalPlanCandidate:
    return GoalPlanCandidate(
        routine_id=_required_string(data, "routine_id"),
        routine_name=_required_string(data, "routine_name"),
        score=_required_float(data, "score"),
        matched_fields=_string_tuple(data.get("matched_fields"), "matched_fields"),
        safety_class=_optional_string(data, "safety_class") or "low",
        approval_policy=_optional_string(data, "approval_policy") or "none",
    )


def _approval_tuple(value: object) -> tuple[GoalPlanApproval, ...]:
    if value is None:
        return ()
    if not isinstance(value, list | tuple):
        raise GoalPlanError("approvals must be a list")
    return tuple(_approval_from_mapping(_mapping(item)) for item in value)


def _approval_from_mapping(data: dict[str, object]) -> GoalPlanApproval:
    return GoalPlanApproval(
        policy=_required_string(data, "policy"),
        required=_required_bool(data, "required"),
        satisfied=_optional_bool(data, "satisfied") or False,
        reason=_optional_string(data, "reason") or "",
    )


def _model_ranking_from_value(value: object) -> GoalModelRanking | None:
    if value is None:
        return None
    data = _mapping(value)
    return GoalModelRanking(
        provider=_optional_string(data, "provider") or "ollama",
        model=_optional_string(data, "model") or "",
        prompt_class=_optional_string(data, "prompt_class") or "goal_routine_ranking",
        enabled=_optional_bool(data, "enabled") or False,
        attempted=_optional_bool(data, "attempted") or False,
        status=cast(
            GoalModelRankingStatus,
            _optional_string(data, "status") or "disabled",
        ),
        selected_routine_id=_optional_string(data, "selected_routine_id"),
        candidate_order=_string_tuple(data.get("candidate_order"), "candidate_order"),
        input_artifact_references=_string_tuple(
            data.get("input_artifact_references"),
            "input_artifact_references",
        ),
        explanation=_optional_string(data, "explanation") or "",
        output_hash=_optional_string(data, "output_hash"),
        affected_selection=_optional_bool(data, "affected_selection") or False,
        error=_optional_string(data, "error"),
    )


def _candidate_errors(candidate: GoalPlanCandidate) -> list[str]:
    errors: list[str] = []
    if not candidate.routine_id.strip():
        errors.append("candidate routine_id is required")
    if not candidate.routine_name.strip():
        errors.append("candidate routine_name is required")
    if candidate.score < 0:
        errors.append("candidate score must not be negative")
    if any(not field.strip() for field in candidate.matched_fields):
        errors.append("candidate matched_fields entries must not be blank")
    return errors


def _model_ranking_errors(
    ranking: GoalModelRanking,
    candidate_ids: set[str],
) -> list[str]:
    errors: list[str] = []
    if ranking.status not in {"disabled", "skipped", "applied", "failed", "rejected"}:
        errors.append(f"unsupported model ranking status: {ranking.status}")
    if ranking.provider != "ollama":
        errors.append("model ranking provider must be ollama")
    if not ranking.prompt_class.strip():
        errors.append("model ranking prompt_class is required")
    if ranking.selected_routine_id and ranking.selected_routine_id not in candidate_ids:
        errors.append("model ranking selected_routine_id must reference a candidate")
    if len(ranking.candidate_order) != len(set(ranking.candidate_order)):
        errors.append("model ranking candidate_order entries must be unique")
    if any(not item.strip() for item in ranking.input_artifact_references):
        errors.append("model ranking input_artifact_references must not be blank")
    unknown_ids = [
        routine_id
        for routine_id in ranking.candidate_order
        if routine_id not in candidate_ids
    ]
    if unknown_ids:
        errors.append("model ranking candidate_order must reference candidates")
    return errors


def _approval_errors(approval: GoalPlanApproval) -> list[str]:
    errors: list[str] = []
    if not approval.policy.strip():
        errors.append("approval policy is required")
    if approval.required and not approval.reason.strip():
        errors.append("required approvals need a reason")
    return errors


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise GoalPlanError("entries must be mappings")
    return cast(dict[str, object], value)


def _required_string(data: dict[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise GoalPlanError(f"{key} is required")
    return value


def _optional_string(data: dict[str, object], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise GoalPlanError(f"{key} must be a string")
    return value


def _required_float(data: dict[str, object], key: str) -> float:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise GoalPlanError(f"{key} must be numeric")
    return float(value)


def _required_bool(data: dict[str, object], key: str) -> bool:
    value = data.get(key)
    if not isinstance(value, bool):
        raise GoalPlanError(f"{key} must be true or false")
    return value


def _optional_bool(data: dict[str, object], key: str) -> bool | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, bool):
        raise GoalPlanError(f"{key} must be true or false")
    return value


def _string_tuple(value: object, key: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list | tuple):
        raise GoalPlanError(f"{key} must be a list")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise GoalPlanError(f"{key} entries must be strings")
        result.append(item)
    return tuple(result)


def _rank_goal_candidates(
    indexed_results: tuple[GoalRoutineIndexResult, ...],
    request: GoalRoutingRequest,
) -> tuple[GoalPlanCandidate, ...]:
    candidates: list[GoalPlanCandidate] = []
    for result in indexed_results:
        routine_score = _router_score(result, request)
        if routine_score is None:
            continue
        candidates.append(
            GoalPlanCandidate(
                routine_id=result.candidate.routine_id,
                routine_name=result.candidate.routine_name,
                score=routine_score,
                matched_fields=result.candidate.matched_fields,
                safety_class=result.candidate.safety_class,
                approval_policy=result.candidate.approval_policy,
            ),
        )
    return tuple(sorted(candidates, key=lambda item: (-item.score, item.routine_id)))


def _has_ambiguous_top_candidate(
    ranked_candidates: tuple[GoalPlanCandidate, ...],
) -> bool:
    return (
        len(ranked_candidates) > 1
        and ranked_candidates[0].score == ranked_candidates[1].score
    )


def _router_score(
    result: GoalRoutineIndexResult,
    request: GoalRoutingRequest,
) -> float | None:
    candidate = result.candidate
    routine = result.routine
    if not _safety_allowed(candidate.safety_class, request.max_safety_class):
        return None
    if request.required_site and not _text_matches(
        routine.required_site,
        request.required_site,
    ):
        return None
    if request.required_app and not _text_matches(
        routine.required_app,
        request.required_app,
    ):
        return None
    score = candidate.score
    score += _tag_bonus(routine, request.tags)
    score += _input_bonus(routine, request.provided_inputs)
    if request.required_site:
        score += 25
    if request.required_app:
        score += 25
    if result.schedule_eligible:
        score += 5
    score += _historical_success_bonus(result)
    return score


def _historical_success(
    counters: RoutineFailureCounters | None,
) -> tuple[float | None, int]:
    if counters is None or counters.total_runs <= 0:
        return None, 0
    return counters.passed_runs / counters.total_runs, counters.total_runs


def _historical_success_bonus(result: GoalRoutineIndexResult) -> float:
    if result.historical_success_rate is None:
        return 0.0
    return result.historical_success_rate * min(result.historical_total_runs, 10)


def _safety_allowed(safety_class: str, max_safety_class: str) -> bool:
    return GOAL_ROUTER_SAFETY_RANK.get(safety_class, 99) <= GOAL_ROUTER_SAFETY_RANK[
        max_safety_class
    ]


def _tag_bonus(routine: RoutineDefinition, requested_tags: tuple[str, ...]) -> float:
    if not requested_tags:
        return 0
    routine_tags = {tag.casefold() for tag in routine.tags}
    return sum(3 for tag in requested_tags if tag.casefold() in routine_tags)


def _input_bonus(
    routine: RoutineDefinition,
    provided_inputs: tuple[str, ...],
) -> float:
    if not provided_inputs:
        return 0
    routine_inputs = {item.casefold() for item in routine.inputs}
    return float(
        sum(2 for item in provided_inputs if item.casefold() in routine_inputs)
    )


def _missing_inputs(
    catalog: RoutineCatalog,
    routine_id: str,
    provided_inputs: tuple[str, ...],
) -> tuple[str, ...]:
    routine = catalog.by_id(routine_id)
    if routine is None:
        return ()
    provided = {item.casefold() for item in provided_inputs}
    return tuple(item for item in routine.inputs if item.casefold() not in provided)


def _approval_requirements(
    catalog: RoutineCatalog,
    routine_id: str,
) -> tuple[GoalPlanApproval, ...]:
    routine = catalog.by_id(routine_id)
    if routine is None or routine.approval_policy == "none":
        return ()
    return (
        GoalPlanApproval(
            policy=routine.approval_policy,
            required=True,
            satisfied=False,
            reason="Routine approval policy requires operator review.",
        ),
    )


def _tokens(value: str) -> tuple[str, ...]:
    return tuple(value.casefold().replace("_", " ").replace("-", " ").split())


def _text_matches(value: str | None, expected: str) -> bool:
    if value is None:
        return False
    return value.casefold() == expected.casefold()


def _schedule_eligibility(
    routine: RoutineDefinition,
    now: datetime | None,
) -> tuple[bool, str]:
    if routine.schedule_policy != "scheduled":
        return True, "not_scheduled"
    if now is None:
        return True, "schedule_time_not_checked"
    if not routine.schedule.allowed_time_windows:
        return True, "no_schedule_window_declared"
    decision = select_schedule_time(routine, now=now, random_seed=0)
    if decision.lower_bound == now:
        return True, "inside_allowed_time_window"
    return False, "outside_allowed_time_window"


def _candidate_order(plan: GoalPlan) -> tuple[str, ...]:
    return tuple(candidate.routine_id for candidate in plan.candidate_routines)


def _with_model_ranking(plan: GoalPlan, ranking: GoalModelRanking) -> GoalPlan:
    updated = replace(plan, model_ranking=ranking)
    validate_goal_plan(updated)
    return updated


def _apply_model_suggestion(
    catalog: RoutineCatalog,
    request: GoalRoutingRequest,
    plan: GoalPlan,
    config: LocalModelConfig,
    suggestion: GoalModelSuggestion,
) -> GoalPlan:
    candidate_order = _candidate_order(plan)
    ordered_ids, rejected_reason = _safe_model_candidate_order(
        candidate_order,
        suggestion,
    )
    output_hash = _hash_model_output(suggestion.raw_output)
    if rejected_reason is not None:
        return _with_model_ranking(
            plan,
            GoalModelRanking(
                provider=config.provider,
                model=config.model,
                enabled=True,
                attempted=True,
                status="rejected",
                selected_routine_id=plan.selected_routine_id,
                candidate_order=candidate_order,
                explanation=(
                    "Local model ranking was rejected; deterministic plan kept."
                ),
                output_hash=output_hash,
                error=rejected_reason,
            ),
        )

    candidates_by_id = {
        candidate.routine_id: candidate for candidate in plan.candidate_routines
    }
    reranked_candidates = tuple(
        candidates_by_id[routine_id] for routine_id in ordered_ids
    )
    selected_routine_id = ordered_ids[0] if ordered_ids else plan.selected_routine_id
    missing_inputs = (
        _missing_inputs(catalog, selected_routine_id, request.provided_inputs)
        if selected_routine_id is not None
        else ()
    )
    approvals = (
        _approval_requirements(catalog, selected_routine_id)
        if selected_routine_id is not None
        else ()
    )
    status, explanation = _selection_status(
        selected_routine_id,
        missing_inputs,
        approvals,
        fallback_explanation=(
            suggestion.explanation
            or "Local model reranked deterministic routine candidates."
        ),
    )
    affected_selection = selected_routine_id != plan.selected_routine_id
    updated = GoalPlan(
        user_goal=plan.user_goal,
        normalized_intent=plan.normalized_intent,
        candidate_routines=reranked_candidates,
        selected_routine_id=selected_routine_id,
        missing_inputs=missing_inputs,
        approvals=approvals,
        explanation=explanation,
        execution_status=status,
        model_ranking=GoalModelRanking(
            provider=config.provider,
            model=config.model,
            enabled=True,
            attempted=True,
            status="applied",
            selected_routine_id=selected_routine_id,
            candidate_order=ordered_ids,
            explanation=suggestion.explanation,
            output_hash=output_hash,
            affected_selection=affected_selection,
        ),
    )
    validate_goal_plan(updated)
    return updated


def _selection_status(
    selected_routine_id: str | None,
    missing_inputs: tuple[str, ...],
    approvals: tuple[GoalPlanApproval, ...],
    *,
    fallback_explanation: str,
) -> tuple[GoalExecutionStatus, str]:
    if selected_routine_id is None:
        return "blocked", "No eligible routine matched the goal and constraints."
    if missing_inputs:
        return "blocked", "Selected routine is blocked by missing inputs."
    if any(approval.required and not approval.satisfied for approval in approvals):
        return "blocked", "Selected routine is blocked by required approvals."
    return "ready", fallback_explanation


def _safe_model_candidate_order(
    candidate_order: tuple[str, ...],
    suggestion: GoalModelSuggestion,
) -> tuple[tuple[str, ...], str | None]:
    validation = validate_routine_ranking_response(
        {
            "selected_routine_id": suggestion.selected_routine_id,
            "candidate_order": list(suggestion.candidate_order),
            "explanation": suggestion.explanation,
        },
        candidate_ids=candidate_order,
    )
    if not validation.accepted:
        return candidate_order, "; ".join(validation.errors)

    suggested_ids = list(suggestion.candidate_order)
    if (
        suggestion.selected_routine_id
        and suggestion.selected_routine_id not in suggested_ids
    ):
        suggested_ids.insert(0, suggestion.selected_routine_id)

    remaining_ids = [
        routine_id
        for routine_id in candidate_order
        if routine_id not in suggested_ids
    ]
    ordered_ids = tuple([*suggested_ids, *remaining_ids])
    return ordered_ids, None


def _goal_model_suggestion_from_raw(raw_output: str) -> GoalModelSuggestion:
    try:
        loaded = json.loads(raw_output)
    except json.JSONDecodeError as exc:
        raise GoalPlanError("model output must be JSON") from exc
    if not isinstance(loaded, dict):
        raise GoalPlanError("model output must be a mapping")
    data = cast(dict[str, object], loaded)
    return GoalModelSuggestion(
        selected_routine_id=_optional_string(data, "selected_routine_id"),
        candidate_order=_string_tuple(data.get("candidate_order"), "candidate_order"),
        explanation=_optional_string(data, "explanation") or "",
        raw_output=raw_output,
    )


def _ollama_goal_ranking_prompt(plan: GoalPlan) -> str:
    candidates = [
        {
            "routine_id": candidate.routine_id,
            "name": candidate.routine_name,
            "score": candidate.score,
            "matched_fields": list(candidate.matched_fields),
            "safety_class": candidate.safety_class,
            "approval_policy": candidate.approval_policy,
        }
        for candidate in plan.candidate_routines
    ]
    return build_routine_ranking_prompt(
        user_goal=plan.user_goal,
        normalized_intent=plan.normalized_intent,
        candidates=candidates,
    ).text


def _hash_model_output(raw_output: str) -> str | None:
    if not raw_output:
        return None
    return hashlib.sha256(raw_output.encode("utf-8")).hexdigest()
