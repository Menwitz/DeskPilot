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

SUPPORTED_GOAL_EXECUTION_STATUSES: frozenset[str] = frozenset(
    {"draft", "blocked", "ready", "running", "completed", "failed", "canceled"},
)


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
class GoalRoutineIndexResult:
    """Routine index hit prepared for goal-plan candidate ranking."""

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
