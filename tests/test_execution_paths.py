from desktop_agent.config import ExecutionProfile, RuntimeConfig
from desktop_agent.execution_paths import choose_execution_path
from desktop_agent.perception import ElementCandidate
from desktop_agent.screen import Bounds
from desktop_agent.task_dsl import TaskStep


def test_fast_path_accepts_stable_high_confidence_target() -> None:
    step = TaskStep(id="open-menu", action="click_text", target="Menu")
    candidate = _candidate(confidence=0.98)

    decision = choose_execution_path(
        step,
        (candidate,),
        candidate,
        RuntimeConfig(confidence_threshold=0.8),
        attempt=1,
    )

    assert decision.fast
    assert decision.reason == "stable_high_confidence_segment"
    assert decision.metadata()["fast_path_timing_policy"] == "lower_bound"


def test_fast_path_rejects_sensitive_or_unstable_segments() -> None:
    candidate = _candidate(confidence=0.98)
    submission = TaskStep(
        id="submit",
        action="click_text",
        target="Submit",
        category="submission",
    )
    low_confidence = _candidate(confidence=0.9)
    loading = _candidate(confidence=0.98, state="loading")
    careful_config = RuntimeConfig(
        confidence_threshold=0.8,
        execution_profile=ExecutionProfile(enabled=True, persona="careful"),
    )

    assert (
        choose_execution_path(
            submission,
            (candidate,),
            candidate,
            RuntimeConfig(confidence_threshold=0.8),
            attempt=1,
        ).reason
        == "submission_requires_checkpoint"
    )
    assert (
        choose_execution_path(
            TaskStep(id="next", action="click_text", target="Next"),
            (low_confidence,),
            low_confidence,
            RuntimeConfig(confidence_threshold=0.8),
            attempt=1,
        ).reason
        == "target_below_fast_path_confidence"
    )
    assert (
        choose_execution_path(
            TaskStep(id="refresh", action="click_text", target="Refresh"),
            (loading,),
            loading,
            RuntimeConfig(confidence_threshold=0.8),
            attempt=1,
        ).reason
        == "unstable_candidate_state"
    )
    assert (
        choose_execution_path(
            TaskStep(id="open", action="click_text", target="Open"),
            (candidate,),
            candidate,
            careful_config,
            attempt=1,
        ).reason
        == "careful_persona"
    )


def _candidate(confidence: float, *, state: str | None = None) -> ElementCandidate:
    metadata: dict[str, object] = {}
    if state is not None:
        metadata["state"] = state
    return ElementCandidate(
        id="candidate-1",
        source="uia",
        label="Menu",
        bounds=Bounds(x=10, y=20, width=100, height=30),
        confidence=confidence,
        metadata=metadata,
    )
