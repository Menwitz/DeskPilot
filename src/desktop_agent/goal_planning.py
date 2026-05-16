"""Goal-to-routine planning schemas for local routine selection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, cast

from desktop_agent.routines import RoutineCatalog, RoutineDefinition
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
class GoalRoutineIndexResult:
    """Routine index hit prepared for goal-plan candidate ranking."""

    routine: RoutineDefinition
    candidate: GoalPlanCandidate
    schedule_eligible: bool
    schedule_reason: str

    def metadata(self) -> dict[str, object]:
        return {
            **self.candidate.metadata(),
            "schedule_eligible": self.schedule_eligible,
            "schedule_reason": self.schedule_reason,
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
    )
    validate_goal_plan(plan)
    return plan


def search_routine_index_for_goal(
    catalog: RoutineCatalog,
    query: str,
    *,
    now: datetime | None = None,
    require_schedule_eligible: bool = False,
    limit: int = 20,
) -> tuple[GoalRoutineIndexResult, ...]:
    """Search routine metadata and attach goal-planning eligibility fields."""
    results: list[GoalRoutineIndexResult] = []
    for result in catalog.search(query, limit=limit):
        schedule_eligible, schedule_reason = _schedule_eligibility(
            result.routine,
            now,
        )
        if require_schedule_eligible and not schedule_eligible:
            continue
        results.append(
            GoalRoutineIndexResult(
                routine=result.routine,
                candidate=GoalPlanCandidate(
                    routine_id=result.routine.id,
                    routine_name=result.routine.name,
                    score=float(result.score),
                    matched_fields=result.matched_fields,
                    safety_class=result.routine.safety_class,
                    approval_policy=result.routine.approval_policy,
                ),
                schedule_eligible=schedule_eligible,
                schedule_reason=schedule_reason,
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
) -> GoalPlan:
    """Select the best known routine using deterministic router rules."""
    validate_goal_routing_request(request)
    indexed_results = search_routine_index_for_goal(
        catalog,
        request.normalized_intent or request.user_goal,
        now=request.now,
        require_schedule_eligible=True,
        limit=100,
    )
    ranked_candidates = _rank_goal_candidates(indexed_results, request)
    selected = ranked_candidates[0] if ranked_candidates else None
    missing_inputs = (
        _missing_inputs(catalog, selected.routine_id, request.provided_inputs)
        if selected is not None
        else ()
    )
    approvals = _approval_requirements(catalog, selected.routine_id) if selected else ()
    execution_status: GoalExecutionStatus = "ready"
    explanation = "Selected routine by deterministic ranking."
    selected_routine_id = selected.routine_id if selected else None
    if selected is None:
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
    return score


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
