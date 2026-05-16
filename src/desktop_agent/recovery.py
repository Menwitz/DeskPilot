"""Recovery policy selection for bounded planner retries."""

from __future__ import annotations

from dataclasses import dataclass

from desktop_agent.actuation import ActionResult
from desktop_agent.perception import ElementCandidate
from desktop_agent.screen import ScreenObservation
from desktop_agent.task_dsl import RecoveryRule, TaskStep


@dataclass(frozen=True)
class RecoveryPolicy:
    """Named recovery plan emitted into traces before retrying or stopping."""

    name: str
    reason: str
    actions: tuple[str, ...]
    backoff_strategy: str = "bounded_linear"

    def metadata(self) -> dict[str, object]:
        return {
            "recovery_policy": self.name,
            "recovery_reason": self.reason,
            "recovery_actions": list(self.actions),
            "recovery_backoff_strategy": self.backoff_strategy,
        }


@dataclass(frozen=True)
class ConstrainedRecoveryPolicy:
    """Recovery policy after applying task-authored allowed recovery actions."""

    policy: RecoveryPolicy
    rule: RecoveryRule | None = None
    rejected_actions: tuple[str, ...] = ()

    @property
    def chosen_action(self) -> str:
        """Return the concrete recovery action used before retrying."""

        for action in self.policy.actions:
            if action != "abort_with_trace":
                return action
        return "abort_with_trace"

    def metadata(self) -> dict[str, object]:
        metadata = self.policy.metadata()
        metadata["recovery_chosen_action"] = self.chosen_action
        metadata["recovery_rejected_policy_actions"] = list(self.rejected_actions)
        if self.rule is not None:
            metadata["recovery_allowed_actions"] = list(self.rule.actions)
            metadata["recovery_rule_next_step"] = self.rule.next_step
            metadata["recovery_actions_constrained"] = True
        return metadata


@dataclass(frozen=True)
class RecoveryTreeAction:
    """One executable node in a bounded recovery tree."""

    action: str
    phase: str
    requires_operator: bool = False

    def metadata(self) -> dict[str, object]:
        return {
            "action": self.action,
            "phase": self.phase,
            "requires_operator": self.requires_operator,
        }


@dataclass(frozen=True)
class RecoveryTreeExecution:
    """Concrete recovery tree emitted before retry or handoff."""

    reason: str
    chosen_action: str
    actions: tuple[RecoveryTreeAction, ...]
    failed_attempt: int | None = None
    next_attempt: int | None = None

    @property
    def requires_operator(self) -> bool:
        return any(action.requires_operator for action in self.actions)

    @property
    def can_retry(self) -> bool:
        return (
            self.chosen_action != "abort_with_trace"
            and not self.requires_operator
            and self.next_attempt is not None
        )

    def metadata(self) -> dict[str, object]:
        return {
            "recovery_tree_reason": self.reason,
            "recovery_tree_chosen_action": self.chosen_action,
            "recovery_tree_actions": [action.metadata() for action in self.actions],
            "recovery_tree_action_count": len(self.actions),
            "recovery_tree_requires_operator": self.requires_operator,
            "recovery_tree_can_retry": self.can_retry,
            "recovery_tree_failed_attempt": self.failed_attempt,
            "recovery_tree_next_attempt": self.next_attempt,
        }


RECOVERY_POLICIES: dict[str, RecoveryPolicy] = {
    "stale_observation": RecoveryPolicy(
        name="refresh_stale_observation",
        reason="stale_observation",
        actions=(
            "reobserve_screen",
            "retry_with_fresh_candidates",
            "abort_with_trace",
        ),
    ),
    "missed_target": RecoveryPolicy(
        name="recover_missed_target",
        reason="missed_target",
        actions=(
            "wait_and_reobserve",
            "retry_alternate_candidate",
            "abort_with_trace",
        ),
    ),
    "disabled_control": RecoveryPolicy(
        name="wait_for_enabled_control",
        reason="disabled_control",
        actions=("wait_for_enabled", "reobserve_screen", "abort_with_trace"),
        backoff_strategy="bounded_exponential",
    ),
    "occluded_control": RecoveryPolicy(
        name="recover_occluded_control",
        reason="occluded_control",
        actions=("refocus_allowed_window", "scroll_search_region", "abort_with_trace"),
    ),
    "focus_loss": RecoveryPolicy(
        name="recover_focus_loss",
        reason="focus_loss",
        actions=("refocus_allowed_window", "reobserve_screen", "abort_with_trace"),
    ),
    "layout_change": RecoveryPolicy(
        name="recover_layout_change",
        reason="layout_change",
        actions=(
            "retry_alternate_selector_family",
            "reobserve_screen",
            "abort_with_trace",
        ),
    ),
    "transient_loading": RecoveryPolicy(
        name="wait_for_transient_loading",
        reason="transient_loading",
        actions=("wait_for_loading", "reobserve_screen", "abort_with_trace"),
        backoff_strategy="bounded_exponential",
    ),
    "verification_failure": RecoveryPolicy(
        name="recover_verification_failure",
        reason="verification_failure",
        actions=(
            "wait_and_reobserve",
            "retry_alternate_candidate",
            "abort_with_trace",
        ),
    ),
    "verification_inconclusive": RecoveryPolicy(
        name="recover_verification_inconclusive",
        reason="verification_inconclusive",
        actions=(
            "wait_and_reobserve",
            "manual_handoff",
            "abort_with_trace",
        ),
    ),
}


RECOVERY_TREE_ACTIONS: dict[str, tuple[RecoveryTreeAction, ...]] = {
    "refocus_allowed_window": (
        RecoveryTreeAction("refocus_allowed_window", "prepare"),
        RecoveryTreeAction("reobserve_screen", "observe"),
    ),
    "reobserve_screen": (
        RecoveryTreeAction("reobserve_screen", "observe"),
    ),
    "retry_alternate_candidate": (
        RecoveryTreeAction("retry_alternate_candidate", "select"),
        RecoveryTreeAction("reobserve_screen", "observe"),
    ),
    "retry_alternate_selector_family": (
        RecoveryTreeAction("retry_alternate_selector_family", "select"),
        RecoveryTreeAction("reobserve_screen", "observe"),
    ),
    "retry_with_fresh_candidates": (
        RecoveryTreeAction("reobserve_screen", "observe"),
        RecoveryTreeAction("retry_with_fresh_candidates", "select"),
    ),
    "scroll_search_region": (
        RecoveryTreeAction("scroll_search_region", "act"),
        RecoveryTreeAction("reobserve_screen", "observe"),
    ),
    "wait_and_reobserve": (
        RecoveryTreeAction("wait_and_reobserve", "wait"),
        RecoveryTreeAction("reobserve_screen", "observe"),
    ),
    "wait_for_enabled": (
        RecoveryTreeAction("wait_for_enabled", "wait"),
        RecoveryTreeAction("reobserve_screen", "observe"),
    ),
    "wait_for_loading": (
        RecoveryTreeAction("wait_for_loading", "wait"),
        RecoveryTreeAction("reobserve_screen", "observe"),
    ),
    "reopen_surface": (
        RecoveryTreeAction("reopen_surface", "act"),
        RecoveryTreeAction("reobserve_screen", "observe"),
    ),
    "manual_handoff": (
        RecoveryTreeAction("manual_handoff", "handoff", requires_operator=True),
    ),
    "abort_with_trace": (
        RecoveryTreeAction("abort_with_trace", "abort"),
    ),
}


def recovery_policy_for_selection(
    observation: ScreenObservation,
    candidates: tuple[ElementCandidate, ...],
    target: ElementCandidate | None,
    *,
    confidence_threshold: float = 0.8,
) -> RecoveryPolicy:
    """Classify why target selection could not safely produce an action target."""

    if target is not None:
        return RECOVERY_POLICIES["verification_failure"]
    if _observation_has_state(observation, "stale"):
        return RECOVERY_POLICIES["stale_observation"]
    if _observation_has_state(observation, "loading") or _candidates_have_state(
        candidates,
        "loading",
    ):
        return RECOVERY_POLICIES["transient_loading"]
    if candidates and all(not candidate.enabled for candidate in candidates):
        return RECOVERY_POLICIES["disabled_control"]
    if candidates and all(not candidate.visible for candidate in candidates):
        return RECOVERY_POLICIES["occluded_control"]
    if _has_multiple_candidate_families(candidates, confidence_threshold):
        return RECOVERY_POLICIES["layout_change"]
    return RECOVERY_POLICIES["missed_target"]


def _has_multiple_candidate_families(
    candidates: tuple[ElementCandidate, ...],
    confidence_threshold: float,
) -> bool:
    families: set[str] = set()
    for candidate in candidates:
        if candidate.confidence < confidence_threshold:
            continue
        merged_sources = candidate.metadata.get("merged_sources")
        if isinstance(merged_sources, tuple | list):
            families.update(
                source for source in merged_sources if isinstance(source, str)
            )
        families.add(candidate.source)
    return len(families) > 1


def recovery_policy_for_action_result(
    observation: ScreenObservation,
    candidates: tuple[ElementCandidate, ...],
    action_result: ActionResult,
    verification_passed: bool,
) -> RecoveryPolicy:
    """Classify an actuation or verification failure for retry metadata."""

    if _message_has_state(
        action_result.message,
        "transient",
    ) or _observation_has_state(observation, "loading"):
        return RECOVERY_POLICIES["transient_loading"]
    if _observation_has_state(observation, "stale"):
        return RECOVERY_POLICIES["stale_observation"]
    if not action_result.success:
        return RECOVERY_POLICIES["missed_target"]
    if not verification_passed:
        return recovery_policy_for_selection(observation, candidates, None)
    return RECOVERY_POLICIES["verification_failure"]


def constrain_recovery_policy(
    step: TaskStep,
    policy: RecoveryPolicy,
) -> ConstrainedRecoveryPolicy:
    rule = _matching_recovery_rule(step, policy.reason)
    if rule is None:
        return ConstrainedRecoveryPolicy(policy)
    allowed = tuple(action for action in policy.actions if action in rule.actions)
    rejected = tuple(action for action in policy.actions if action not in allowed)
    if not allowed:
        allowed = ("abort_with_trace",)
        rejected = policy.actions
    return ConstrainedRecoveryPolicy(
        RecoveryPolicy(
            name=policy.name,
            reason=policy.reason,
            actions=allowed,
            backoff_strategy=policy.backoff_strategy,
        ),
        rule,
        rejected,
    )


def build_recovery_tree_execution(
    step: TaskStep,
    policy: RecoveryPolicy,
    *,
    failed_attempt: int | None = None,
    next_attempt: int | None = None,
) -> RecoveryTreeExecution:
    """Build the concrete recovery tree after task-authored constraints."""
    constrained = constrain_recovery_policy(step, policy)
    chosen_action = constrained.chosen_action
    actions = RECOVERY_TREE_ACTIONS.get(
        chosen_action,
        (RecoveryTreeAction(chosen_action, "act"),),
    )
    return RecoveryTreeExecution(
        reason=constrained.policy.reason,
        chosen_action=chosen_action,
        actions=actions,
        failed_attempt=failed_attempt,
        next_attempt=next_attempt,
    )


def _matching_recovery_rule(
    step: TaskStep,
    reason: str,
) -> RecoveryRule | None:
    for rule in step.recovery:
        if rule.reason == reason:
            return rule
    return None


def _observation_has_state(observation: ScreenObservation, state: str) -> bool:
    state = state.lower()
    warning_text = " ".join(observation.warnings).lower()
    metadata_state = str(observation.metadata.get("state", "")).lower()
    return state in warning_text or state in metadata_state


def _candidates_have_state(
    candidates: tuple[ElementCandidate, ...],
    state: str,
) -> bool:
    state = state.lower()
    return any(
        str(candidate.metadata.get("state", "")).lower() == state
        for candidate in candidates
    )


def _message_has_state(message: str, state: str) -> bool:
    return state.lower() in message.lower()
