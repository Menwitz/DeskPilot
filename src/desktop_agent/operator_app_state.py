"""State transitions for the native operator app shell."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from desktop_agent.operator_app_shell import (
    ApprovalDialogState,
    LiveRunPanelState,
    OperatorAppShell,
    RecorderReviewPanelState,
    TraceHealthPanelState,
    TraceViewerTimelineState,
    operator_app_shell_spec,
    trace_health_panel_from_metadata,
    trace_viewer_timeline_from_report,
)
from desktop_agent.operator_services import ApprovalService, RunnerService, TraceService


class OperatorAppStateError(ValueError):
    """Raised when an app state transition is not allowed."""


@dataclass(frozen=True)
class OperatorAppState:
    """Mutable-in-the-UI state represented as immutable testable data."""

    shell: OperatorAppShell
    current_page_id: str
    live_run: LiveRunPanelState
    trace_health: TraceHealthPanelState | None = None
    approval_dialog: ApprovalDialogState | None = None
    recorder_review: RecorderReviewPanelState | None = None
    trace_viewer: TraceViewerTimelineState | None = None

    def metadata(self) -> dict[str, object]:
        return {
            "current_page_id": self.current_page_id,
            "live_run": self.live_run.metadata(),
            "trace_health": (
                None if self.trace_health is None else self.trace_health.metadata()
            ),
            "approval_dialog": (
                None
                if self.approval_dialog is None
                else self.approval_dialog.metadata()
            ),
            "recorder_review": (
                None
                if self.recorder_review is None
                else self.recorder_review.metadata()
            ),
            "trace_viewer": (
                None if self.trace_viewer is None else self.trace_viewer.metadata()
            ),
        }


class OperatorAppController:
    """Small UI controller for testing app transitions with fake services."""

    def __init__(
        self,
        runner: RunnerService,
        *,
        approvals: ApprovalService | None = None,
        traces: TraceService | None = None,
        shell: OperatorAppShell | None = None,
        state: OperatorAppState | None = None,
    ) -> None:
        self._runner = runner
        self._approvals = approvals
        self._traces = traces
        active_shell = shell or operator_app_shell_spec()
        self.state = state or OperatorAppState(
            shell=active_shell,
            current_page_id=active_shell.default_page_id,
            live_run=LiveRunPanelState(),
        )

    def select_page(self, page_id: str) -> OperatorAppState:
        if page_id not in {page.page_id for page in self.state.shell.pages}:
            raise OperatorAppStateError(f"unknown app page: {page_id}")
        self.state = replace(self.state, current_page_id=page_id)
        return self.state

    def start_routine(self, routine_id: str) -> OperatorAppState:
        run = self._runner.start_routine(routine_id)
        if run.status != "running":
            self.state = replace(
                self.state,
                current_page_id="dashboard",
                live_run=LiveRunPanelState(
                    run_id=run.run_id,
                    current_routine_id=routine_id,
                    status=run.status,
                    next_action=run.reason,
                ),
            )
            return self.state
        self.state = replace(
            self.state,
            current_page_id="dashboard",
            live_run=LiveRunPanelState(
                run_id=run.run_id,
                current_routine_id=routine_id,
                status=run.status,
                next_action=run.next_action,
            ),
        )
        return self.state

    def dry_run_routine(self, routine_id: str) -> OperatorAppState:
        dry_run = self._runner.dry_run_routine(routine_id)
        self.state = replace(
            self.state,
            current_page_id="routine_library",
            live_run=LiveRunPanelState(
                current_routine_id=routine_id,
                current_step_id=(
                    "compiled_task" if dry_run.compiled_task else None
                ),
                status=f"dry_run_{dry_run.status}",
                next_action=dry_run.reason,
            ),
        )
        return self.state

    def pause_run(self) -> OperatorAppState:
        run_id = self._active_run_id()
        run = self._runner.pause_run(run_id)
        self.state = replace(
            self.state,
            live_run=replace(
                self.state.live_run,
                status=run.status,
                next_action=run.next_action,
            ),
        )
        return self.state

    def resume_run(self) -> OperatorAppState:
        run_id = self._active_run_id()
        run = self._runner.resume_run(run_id)
        self.state = replace(
            self.state,
            live_run=replace(
                self.state.live_run,
                status=run.status,
                next_action=run.next_action,
            ),
        )
        return self.state

    def cancel_run(self) -> OperatorAppState:
        run_id = self._active_run_id()
        run = self._runner.cancel_run(run_id)
        self.state = replace(
            self.state,
            live_run=replace(
                self.state.live_run,
                status=run.status,
                next_action=run.next_action,
            ),
        )
        return self.state

    def stop_run(self) -> OperatorAppState:
        run_id = self._active_run_id()
        run = self._runner.stop_run(run_id)
        self.state = replace(
            self.state,
            live_run=replace(
                self.state.live_run,
                status=run.status,
                next_action=run.next_action,
            ),
        )
        return self.state

    def emergency_stop_run(self) -> OperatorAppState:
        run_id = self._active_run_id()
        run = self._runner.emergency_stop_run(run_id)
        self.state = replace(
            self.state,
            live_run=replace(
                self.state.live_run,
                status=run.status,
                next_action=run.next_action,
            ),
        )
        return self.state

    def request_approval(self, dialog: ApprovalDialogState) -> OperatorAppState:
        self.state = replace(
            self.state,
            current_page_id="approvals",
            approval_dialog=dialog,
        )
        return self.state

    def resolve_approval(
        self,
        action: str,
        *,
        approver: str = "local-operator",
        reason: str = "operator app decision",
    ) -> OperatorAppState:
        if self.state.approval_dialog is None:
            raise OperatorAppStateError("approval dialog is not active")
        if action not in self.state.approval_dialog.actions:
            raise OperatorAppStateError(f"unsupported approval action: {action}")
        decision = None
        if self._approvals is not None:
            dialog = self.state.approval_dialog
            decision = self._approvals.resolve_step_approval(
                routine_id=dialog.routine_id,
                step_id=dialog.step_id,
                action=action,
                risk_class=dialog.risk_class,
                checkpoint_evidence=dialog.checkpoint_evidence,
                content_fingerprint=dialog.content_fingerprint,
                approver=approver,
                reason=reason,
            )
        self.state = replace(
            self.state,
            approval_dialog=replace(
                self.state.approval_dialog,
                status=action,
                approver=None if decision is None else decision.approver,
                reason=None if decision is None else decision.reason,
                decided_at=None if decision is None else decision.decided_at,
            ),
        )
        return self.state

    def review_recording(
        self,
        review: RecorderReviewPanelState,
    ) -> OperatorAppState:
        self.state = replace(
            self.state,
            current_page_id="record",
            recorder_review=review,
        )
        return self.state

    def view_trace(self, timeline: TraceViewerTimelineState) -> OperatorAppState:
        self.state = replace(
            self.state,
            current_page_id="trace_viewer",
            trace_viewer=timeline,
        )
        return self.state

    def view_trace_report(self, trace_dir: Path) -> OperatorAppState:
        if self._traces is None:
            raise OperatorAppStateError("trace service is not configured")
        report = self._traces.read_report(trace_dir)
        summary = self._traces.trace_summary(trace_dir)
        return self.view_trace(
            trace_viewer_timeline_from_report(
                report,
                report_path=summary.report_path,
            ),
        )

    def refresh_trace_health(self) -> OperatorAppState:
        if self._traces is None:
            raise OperatorAppStateError("trace service is not configured")
        self.state = replace(
            self.state,
            current_page_id="dashboard",
            trace_health=trace_health_panel_from_metadata(
                self._traces.trace_health(),
            ),
        )
        return self.state

    def _require_started_run(self) -> None:
        if self.state.live_run.current_routine_id is None:
            raise OperatorAppStateError("no active run")

    def _active_run_id(self) -> str:
        self._require_started_run()
        if self.state.live_run.run_id is None:
            raise OperatorAppStateError("active run is missing a run id")
        return self.state.live_run.run_id
