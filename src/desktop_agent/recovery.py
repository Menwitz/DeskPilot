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

    def metadata(self) -> dict[str, object]:
        return {
            "recovery_policy": self.name,
            "recovery_reason": self.reason,
            "recovery_actions": list(self.actions),
        }


@dataclass(frozen=True)
class ConstrainedRecoveryPolicy:
    """Recovery policy after applying task-authored allowed recovery actions."""

    policy: RecoveryPolicy
    rule: RecoveryRule | None = None

    def metadata(self) -> dict[str, object]:
        metadata = self.policy.metadata()
        if self.rule is not None:
            metadata["recovery_allowed_actions"] = list(self.rule.actions)
            metadata["recovery_rule_next_step"] = self.rule.next_step
            metadata["recovery_actions_constrained"] = True
        return metadata


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
    ),
    "occluded_control": RecoveryPolicy(
        name="recover_occluded_control",
        reason="occluded_control",
        actions=("refocus_allowed_window", "scroll_search_region", "abort_with_trace"),
    ),
    "transient_loading": RecoveryPolicy(
        name="wait_for_transient_loading",
        reason="transient_loading",
        actions=("wait_for_loading", "reobserve_screen", "abort_with_trace"),
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
}


def recovery_policy_for_selection(
    observation: ScreenObservation,
    candidates: tuple[ElementCandidate, ...],
    target: ElementCandidate | None,
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
    return RECOVERY_POLICIES["missed_target"]


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
    if not allowed:
        allowed = ("abort_with_trace",)
    return ConstrainedRecoveryPolicy(
        RecoveryPolicy(
            name=policy.name,
            reason=policy.reason,
            actions=allowed,
        ),
        rule,
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
