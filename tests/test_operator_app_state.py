import pytest

from desktop_agent.operator_app_shell import ApprovalDialogState
from desktop_agent.operator_app_state import (
    OperatorAppController,
    OperatorAppStateError,
)
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
