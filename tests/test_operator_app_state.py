from pathlib import Path

import pytest

from desktop_agent.operator_app_shell import (
    ApprovalDialogState,
    RecorderReviewPanelState,
    TraceViewerTimelineState,
)
from desktop_agent.operator_app_state import (
    OperatorAppController,
    OperatorAppStateError,
)
from desktop_agent.operator_services import OperatorRunStartResult
from desktop_agent.routines import RoutineExecutionGate


def test_operator_app_controller_transitions_run_state_with_fake_runner() -> None:
    controller = OperatorAppController(
        _FakeRunnerService(
            {
                "browser.search": RoutineExecutionGate(
                    routine_id="browser.search",
                    allowed=True,
                    reason="validated_catalog_routine",
                ),
            },
        ),
    )

    running = controller.start_routine("browser.search")
    paused = controller.pause_run()
    resumed = controller.resume_run()
    canceled = controller.cancel_run()

    assert running.current_page_id == "dashboard"
    assert running.live_run.run_id == "run-0001"
    assert running.live_run.current_routine_id == "browser.search"
    assert running.live_run.status == "running"
    assert running.live_run.next_action == "observe_screen"
    assert paused.live_run.status == "paused"
    assert resumed.live_run.status == "running"
    assert canceled.live_run.status == "canceled"
    assert canceled.live_run.next_action == "none"


def test_operator_app_controller_blocks_run_when_fake_gate_rejects() -> None:
    controller = OperatorAppController(
        _FakeRunnerService(
            {
                "browser.unknown": RoutineExecutionGate(
                    routine_id="browser.unknown",
                    allowed=False,
                    reason="unknown_routine_id",
                ),
            },
        ),
    )

    state = controller.start_routine("browser.unknown")

    assert state.live_run.current_routine_id == "browser.unknown"
    assert state.live_run.status == "blocked"
    assert state.live_run.next_action == "unknown_routine_id"


def test_operator_app_controller_selects_pages_and_rejects_unknown_page() -> None:
    controller = OperatorAppController(_FakeRunnerService({}))

    state = controller.select_page("trace_viewer")

    assert state.current_page_id == "trace_viewer"
    with pytest.raises(OperatorAppStateError, match="unknown app page"):
        controller.select_page("missing")


def test_operator_app_controller_resolves_approval_dialog() -> None:
    controller = OperatorAppController(_FakeRunnerService({}))
    dialog = ApprovalDialogState(
        routine_id="social.publish",
        step_id="submit-post",
        risk_class="high",
        checkpoint_evidence="checkpoint screenshot present",
        content_fingerprint="sha256:abc123",
    )

    pending = controller.request_approval(dialog)
    approved = controller.resolve_approval("approve")

    assert pending.current_page_id == "approvals"
    assert pending.approval_dialog is not None
    assert pending.approval_dialog.status == "pending"
    assert approved.approval_dialog is not None
    assert approved.approval_dialog.status == "approve"
    with pytest.raises(OperatorAppStateError, match="unsupported approval action"):
        controller.resolve_approval("maybe")


def test_operator_app_controller_tracks_recorder_review_state() -> None:
    controller = OperatorAppController(_FakeRunnerService({}))
    review = RecorderReviewPanelState(
        generated_yaml="name: Recorded routine\nsteps: []\n",
        selected_targets=("Submit", "Done"),
        verification_suggestions=("visible_text: Done",),
        status="ready_for_save",
    )

    state = controller.review_recording(review)
    metadata = state.metadata()

    assert state.current_page_id == "record"
    assert state.recorder_review == review
    assert metadata["recorder_review"] == review.metadata()


def test_operator_app_controller_tracks_trace_viewer_state(tmp_path: Path) -> None:
    controller = OperatorAppController(_FakeRunnerService({}))
    timeline = TraceViewerTimelineState(
        video_path=tmp_path / "proof-video.mp4",
        screenshot_paths=(tmp_path / "screenshots" / "after.png",),
        action_log_path=tmp_path / "action-log.jsonl",
        candidate_reasoning=("selected candidate-1",),
        state_delta=("visible text added Success",),
        final_report_path=tmp_path / "final-report.json",
        status="loaded",
    )

    state = controller.view_trace(timeline)
    metadata = state.metadata()

    assert state.current_page_id == "trace_viewer"
    assert state.trace_viewer == timeline
    assert metadata["trace_viewer"] == timeline.metadata()


class _FakeRunnerService:
    def __init__(self, gates: dict[str, RoutineExecutionGate]) -> None:
        self._gates = gates

    def execution_gate(self, routine_id: str) -> RoutineExecutionGate:
        return self._gates.get(
            routine_id,
            RoutineExecutionGate(
                routine_id=routine_id,
                allowed=False,
                reason="unknown_routine_id",
            ),
        )

    def start_routine(self, routine_id: str) -> OperatorRunStartResult:
        gate = self.execution_gate(routine_id)
        if not gate.allowed:
            return OperatorRunStartResult(
                run_id=None,
                routine_id=routine_id,
                status="blocked",
                reason=gate.reason,
                next_action=None,
                execution_gate=gate,
            )
        return OperatorRunStartResult(
            run_id="run-0001",
            routine_id=routine_id,
            status="running",
            reason="operator_app_start",
            next_action="observe_screen",
            execution_gate=gate,
        )
