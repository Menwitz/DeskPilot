from desktop_agent.actuation import ActionResult
from desktop_agent.perception import CandidateSource, ElementCandidate
from desktop_agent.recovery import (
    RECOVERY_POLICIES,
    RECOVERY_TREE_ACTIONS,
    build_recovery_tree_execution,
    constrain_recovery_policy,
    recovery_policy_for_action_result,
    recovery_policy_for_selection,
)
from desktop_agent.screen import Bounds, ScreenObservation
from desktop_agent.task_dsl import RecoveryRule, TaskStep


def candidate(
    *,
    source: CandidateSource = "uia",
    enabled: bool = True,
    visible: bool = True,
    state: str | None = None,
) -> ElementCandidate:
    metadata: dict[str, object] = {}
    if state is not None:
        metadata["state"] = state
    return ElementCandidate(
        id="candidate-1",
        source=source,
        label="Submit",
        bounds=Bounds(x=0, y=0, width=10, height=10),
        confidence=0.95,
        enabled=enabled,
        visible=visible,
        metadata=metadata,
    )


def test_recovery_policy_classifies_stale_observation() -> None:
    policy = recovery_policy_for_selection(
        ScreenObservation(warnings=("stale snapshot",)),
        (),
        None,
    )

    assert policy.reason == "stale_observation"
    assert "reobserve_screen" in policy.actions


def test_recovery_policy_classifies_disabled_and_occluded_controls() -> None:
    disabled = recovery_policy_for_selection(
        ScreenObservation(),
        (candidate(enabled=False),),
        None,
    )
    occluded = recovery_policy_for_selection(
        ScreenObservation(),
        (candidate(visible=False),),
        None,
    )

    assert disabled.reason == "disabled_control"
    assert occluded.reason == "occluded_control"


def test_recovery_policy_classifies_loading_and_missed_targets() -> None:
    loading = recovery_policy_for_selection(
        ScreenObservation(metadata={"state": "loading"}),
        (),
        None,
    )
    missed = recovery_policy_for_selection(ScreenObservation(), (), None)

    assert loading.reason == "transient_loading"
    assert missed.reason == "missed_target"


def test_recovery_policy_classifies_layout_change_from_candidate_families() -> None:
    policy = recovery_policy_for_selection(
        ScreenObservation(),
        (
            candidate(source="uia"),
            candidate(source="ocr"),
        ),
        None,
    )

    assert policy.reason == "layout_change"
    assert policy.actions[0] == "retry_alternate_selector_family"


def test_recovery_policy_classifies_transient_action_failure() -> None:
    policy = recovery_policy_for_action_result(
        ScreenObservation(),
        (),
        ActionResult(False, "transient failure"),
        verification_passed=False,
    )

    assert policy.reason == "transient_loading"
    assert "wait_for_loading" in policy.actions


def test_recovery_policy_declares_focus_loss_refocus_tree() -> None:
    tree = build_recovery_tree_execution(
        TaskStep(id="click-submit", action="click_text", target="Submit"),
        RECOVERY_POLICIES["focus_loss"],
        failed_attempt=1,
        next_attempt=2,
    )

    assert tree.chosen_action == "refocus_allowed_window"
    assert [action.action for action in tree.actions] == [
        "refocus_allowed_window",
        "reobserve_screen",
    ]
    assert tree.metadata()["recovery_tree_can_retry"] is True


def test_recovery_policy_constrains_actions_from_task_rule() -> None:
    step = TaskStep(
        id="click-submit",
        action="click_text",
        target="Submit",
        recovery=(
            RecoveryRule(
                reason="transient_loading",
                actions=("wait_for_loading", "abort_with_trace"),
            ),
        ),
    )

    constrained = constrain_recovery_policy(
        step,
        RECOVERY_POLICIES["transient_loading"],
    )

    assert constrained.policy.actions == ("wait_for_loading", "abort_with_trace")
    assert constrained.chosen_action == "wait_for_loading"
    assert constrained.metadata()["recovery_chosen_action"] == "wait_for_loading"
    assert constrained.metadata()["recovery_actions_constrained"] is True


def test_recovery_tree_covers_supported_execution_actions() -> None:
    expected_actions = {
        "refocus_allowed_window",
        "reobserve_screen",
        "retry_alternate_candidate",
        "retry_alternate_selector_family",
        "scroll_search_region",
        "wait_for_enabled",
        "wait_for_loading",
        "reopen_surface",
        "manual_handoff",
    }

    assert expected_actions <= set(RECOVERY_TREE_ACTIONS)


def test_recovery_tree_execution_records_retry_and_operator_handoff() -> None:
    retry_tree = build_recovery_tree_execution(
        TaskStep(id="click-submit", action="click_text", target="Submit"),
        RECOVERY_POLICIES["transient_loading"],
        failed_attempt=1,
        next_attempt=2,
    )
    handoff_tree = build_recovery_tree_execution(
        TaskStep(
            id="verify-result",
            action="assert_visible",
            target="Success",
            recovery=(
                RecoveryRule(
                    reason="verification_inconclusive",
                    actions=("manual_handoff", "abort_with_trace"),
                ),
            ),
        ),
        RECOVERY_POLICIES["verification_inconclusive"],
        failed_attempt=1,
        next_attempt=2,
    )

    retry_metadata = retry_tree.metadata()
    handoff_metadata = handoff_tree.metadata()

    assert retry_tree.chosen_action == "wait_for_loading"
    assert [action.action for action in retry_tree.actions] == [
        "wait_for_loading",
        "reobserve_screen",
    ]
    assert retry_metadata["recovery_tree_can_retry"] is True
    assert handoff_tree.chosen_action == "manual_handoff"
    assert handoff_tree.requires_operator is True
    assert handoff_metadata["recovery_tree_requires_operator"] is True
    assert handoff_metadata["recovery_tree_can_retry"] is False
