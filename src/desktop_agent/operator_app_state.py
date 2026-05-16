"""State transitions for the native operator app shell."""

from __future__ import annotations

from dataclasses import dataclass, replace

from desktop_agent.operator_app_shell import (
    ApprovalDialogState,
    LiveRunPanelState,
    OperatorAppShell,
    operator_app_shell_spec,
)
from desktop_agent.operator_services import RunnerService


class OperatorAppStateError(ValueError):
    """Raised when an app state transition is not allowed."""


@dataclass(frozen=True)
class OperatorAppState:
    """Mutable-in-the-UI state represented as immutable testable data."""

    shell: OperatorAppShell
    current_page_id: str
    live_run: LiveRunPanelState
    approval_dialog: ApprovalDialogState | None = None

    def metadata(self) -> dict[str, object]:
        return {
            "current_page_id": self.current_page_id,
            "live_run": self.live_run.metadata(),
            "approval_dialog": (
                None
                if self.approval_dialog is None
                else self.approval_dialog.metadata()
            ),
        }


class OperatorAppController:
    """Small UI controller for testing app transitions with fake services."""

    def __init__(
        self,
        runner: RunnerService,
        *,
        shell: OperatorAppShell | None = None,
        state: OperatorAppState | None = None,
    ) -> None:
        self._runner = runner
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
        gate = self._runner.execution_gate(routine_id)
        if not gate.allowed:
            self.state = replace(
                self.state,
                current_page_id="dashboard",
                live_run=LiveRunPanelState(
                    current_routine_id=routine_id,
                    status="blocked",
                    next_action=gate.reason,
                ),
            )
            return self.state
        self.state = replace(
            self.state,
            current_page_id="dashboard",
            live_run=LiveRunPanelState(
                current_routine_id=routine_id,
                status="running",
                next_action="observe_screen",
            ),
        )
        return self.state

    def pause_run(self) -> OperatorAppState:
        self._require_started_run()
        self.state = replace(
            self.state,
            live_run=replace(self.state.live_run, status="paused"),
        )
        return self.state

    def resume_run(self) -> OperatorAppState:
        self._require_started_run()
        self.state = replace(
            self.state,
            live_run=replace(self.state.live_run, status="running"),
        )
        return self.state

    def cancel_run(self) -> OperatorAppState:
        self._require_started_run()
        self.state = replace(
            self.state,
            live_run=replace(
                self.state.live_run,
                status="canceled",
                next_action="none",
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

    def resolve_approval(self, action: str) -> OperatorAppState:
        if self.state.approval_dialog is None:
            raise OperatorAppStateError("approval dialog is not active")
        if action not in self.state.approval_dialog.actions:
            raise OperatorAppStateError(f"unsupported approval action: {action}")
        self.state = replace(
            self.state,
            approval_dialog=replace(
                self.state.approval_dialog,
                status=action,
            ),
        )
        return self.state

    def _require_started_run(self) -> None:
        if self.state.live_run.current_routine_id is None:
            raise OperatorAppStateError("no active run")
