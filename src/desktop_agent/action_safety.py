"""Resolved safety metadata for task actions."""

from __future__ import annotations

from dataclasses import dataclass

from desktop_agent.task_dsl import TaskRegion, TaskStep, step_category

READ_ONLY_ACTIONS: frozenset[str] = frozenset(
    {"wait_for", "assert_visible", "branch_if_visible"},
)
MESSAGE_OR_PUBLISH_CATEGORIES: frozenset[str] = frozenset(
    {"publish", "comment", "message"},
)


@dataclass(frozen=True)
class ActionSafetyProfile:
    """Reportable safety classification for one resolved task action."""

    safety_class: str
    mutation_risk: str
    mutates_state: bool
    approval_required: bool
    approval_reason: str | None
    reversibility: str
    reversible: bool
    idempotent: bool
    app_scope: str
    window_scope: tuple[str, ...]
    allowed_region: TaskRegion | None
    sensitive_category: str | None

    def metadata(self) -> dict[str, object]:
        metadata: dict[str, object] = {
            "action_safety_class": self.safety_class,
            "mutation_risk": self.mutation_risk,
            "mutates_state": self.mutates_state,
            "approval_required": self.approval_required,
            "approval_reason": self.approval_reason,
            "reversibility": self.reversibility,
            "reversible": self.reversible,
            "idempotent": self.idempotent,
            "app_scope": self.app_scope,
            "window_scope": list(self.window_scope),
            "allowed_region": _region_metadata(self.allowed_region),
        }
        if self.sensitive_category is not None:
            metadata["sensitive_category"] = self.sensitive_category
        return metadata


def action_safety_profile(
    step: TaskStep,
    *,
    allowed_windows: tuple[str, ...] = (),
) -> ActionSafetyProfile:
    """Resolve mutation, approval, reversibility, and scope for an action."""

    safety_class = _safety_class(step)
    mutation_risk = _mutation_risk(safety_class)
    mutates_state = safety_class != "read_only"
    approval_reason = _approval_reason(step)
    return ActionSafetyProfile(
        safety_class=safety_class,
        mutation_risk=mutation_risk,
        mutates_state=mutates_state,
        approval_required=approval_reason is not None,
        approval_reason=approval_reason,
        reversibility=_reversibility(safety_class),
        reversible=safety_class not in {"credential", "payment", "delete"},
        idempotent=not mutates_state,
        app_scope="effective_allowed_windows" if allowed_windows else "task_scope",
        window_scope=allowed_windows,
        allowed_region=step.region,
        sensitive_category=_sensitive_category(step),
    )


def action_safety_metadata(
    step: TaskStep,
    *,
    allowed_windows: tuple[str, ...] = (),
) -> dict[str, object]:
    """Return JSON-safe action safety metadata for traces and previews."""

    return action_safety_profile(step, allowed_windows=allowed_windows).metadata()


def _safety_class(step: TaskStep) -> str:
    sensitive_category = _sensitive_category(step)
    if sensitive_category in MESSAGE_OR_PUBLISH_CATEGORIES:
        return "message_or_publish"
    if sensitive_category == "delete":
        return "delete"
    if sensitive_category == "transaction":
        return "payment"
    if sensitive_category == "login":
        return "credential"
    if sensitive_category is not None or step_category(step) == "submission":
        return "external_mutation"
    if step.action in READ_ONLY_ACTIONS:
        return "read_only"
    return "local_mutation"


def _mutation_risk(safety_class: str) -> str:
    if safety_class == "read_only":
        return "none"
    if safety_class == "local_mutation":
        return "local"
    if safety_class in {"credential", "payment", "delete", "message_or_publish"}:
        return "sensitive_external"
    return "external"


def _approval_reason(step: TaskStep) -> str | None:
    if step.requires_confirmation:
        return "requires_confirmation"
    if step_category(step) == "submission":
        return "submission_category"
    return None


def _reversibility(safety_class: str) -> str:
    if safety_class == "read_only":
        return "not_applicable"
    if safety_class == "local_mutation":
        return "usually_reversible"
    if safety_class in {"credential", "payment", "delete"}:
        return "irreversible"
    return "operator_dependent"


def _sensitive_category(step: TaskStep) -> str | None:
    value = step.metadata.get("site_sensitive_category")
    return value if isinstance(value, str) else None


def _region_metadata(region: TaskRegion | None) -> dict[str, int] | None:
    if region is None:
        return None
    return {
        "x": region.x,
        "y": region.y,
        "width": region.width,
        "height": region.height,
    }
