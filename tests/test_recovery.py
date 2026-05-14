from desktop_agent.actuation import ActionResult
from desktop_agent.perception import ElementCandidate
from desktop_agent.recovery import (
    recovery_policy_for_action_result,
    recovery_policy_for_selection,
)
from desktop_agent.screen import Bounds, ScreenObservation


def candidate(
    *,
    enabled: bool = True,
    visible: bool = True,
    state: str | None = None,
) -> ElementCandidate:
    metadata: dict[str, object] = {}
    if state is not None:
        metadata["state"] = state
    return ElementCandidate(
        id="candidate-1",
        source="uia",
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


def test_recovery_policy_classifies_transient_action_failure() -> None:
    policy = recovery_policy_for_action_result(
        ScreenObservation(),
        (),
        ActionResult(False, "transient failure"),
        verification_passed=False,
    )

    assert policy.reason == "transient_loading"
    assert "wait_for_loading" in policy.actions
