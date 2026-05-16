"""Native operator app shell structure and optional PySide6 launcher."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any

from desktop_agent.config import RuntimeConfig


class OperatorAppUnavailableError(RuntimeError):
    """Raised when the optional native UI dependency is not installed."""


@dataclass(frozen=True)
class OperatorAppPage:
    """One top-level page in the local operator app shell."""

    page_id: str
    title: str
    purpose: str
    panel_ids: tuple[str, ...] = ()

    def metadata(self) -> dict[str, object]:
        return {
            "page_id": self.page_id,
            "title": self.title,
            "purpose": self.purpose,
            "panel_ids": list(self.panel_ids),
        }


@dataclass(frozen=True)
class OperatorAppShell:
    """Static shell contract shared by the app UI and tests."""

    title: str
    pages: tuple[OperatorAppPage, ...]
    default_page_id: str

    def metadata(self) -> dict[str, object]:
        return {
            "title": self.title,
            "default_page_id": self.default_page_id,
            "pages": [page.metadata() for page in self.pages],
        }


@dataclass(frozen=True)
class LiveRunPanelState:
    """Live run panel fields shown by the operator app."""

    current_routine_id: str | None = None
    current_step_id: str | None = None
    screenshot_path: Path | None = None
    selected_target: str | None = None
    next_action: str | None = None
    elapsed_seconds: float = 0.0
    status: str = "idle"
    stop_controls: tuple[str, ...] = (
        "pause",
        "resume",
        "cancel",
        "emergency_stop",
    )

    def metadata(self) -> dict[str, object]:
        return {
            "current_routine_id": self.current_routine_id,
            "current_step_id": self.current_step_id,
            "screenshot_path": (
                str(self.screenshot_path) if self.screenshot_path else None
            ),
            "selected_target": self.selected_target,
            "next_action": self.next_action,
            "elapsed_seconds": self.elapsed_seconds,
            "status": self.status,
            "stop_controls": list(self.stop_controls),
        }


@dataclass(frozen=True)
class ApprovalDialogState:
    """Approval dialog fields shown before high-risk local actions continue."""

    routine_id: str
    step_id: str
    risk_class: str
    checkpoint_evidence: str
    content_fingerprint: str
    status: str = "pending"
    actions: tuple[str, ...] = ("approve", "deny")

    def metadata(self) -> dict[str, object]:
        return {
            "routine_id": self.routine_id,
            "step_id": self.step_id,
            "risk_class": self.risk_class,
            "checkpoint_evidence": self.checkpoint_evidence,
            "content_fingerprint": self.content_fingerprint,
            "status": self.status,
            "actions": list(self.actions),
        }


@dataclass(frozen=True)
class RecorderReviewPanelState:
    """Recorder review fields shown before saving generated YAML."""

    generated_yaml: str
    selected_targets: tuple[str, ...] = ()
    screenshot_paths: tuple[Path, ...] = ()
    verification_suggestions: tuple[str, ...] = ()
    status: str = "draft"

    def metadata(self) -> dict[str, object]:
        return {
            "generated_yaml": self.generated_yaml,
            "selected_targets": list(self.selected_targets),
            "screenshot_paths": [str(path) for path in self.screenshot_paths],
            "verification_suggestions": list(self.verification_suggestions),
            "status": self.status,
        }


@dataclass(frozen=True)
class TraceViewerTimelineState:
    """Trace viewer timeline fields for reviewing local evidence."""

    video_path: Path | None = None
    screenshot_paths: tuple[Path, ...] = ()
    action_log_path: Path | None = None
    candidate_reasoning: tuple[str, ...] = ()
    state_delta: tuple[str, ...] = ()
    final_report_path: Path | None = None
    status: str = "empty"

    def metadata(self) -> dict[str, object]:
        return {
            "video_path": str(self.video_path) if self.video_path else None,
            "screenshot_paths": [str(path) for path in self.screenshot_paths],
            "action_log_path": (
                str(self.action_log_path) if self.action_log_path else None
            ),
            "candidate_reasoning": list(self.candidate_reasoning),
            "state_delta": list(self.state_delta),
            "final_report_path": (
                str(self.final_report_path) if self.final_report_path else None
            ),
            "status": self.status,
        }


@dataclass(frozen=True)
class SettingsPanelState:
    """Settings panel fields exposed by the operator app."""

    trace_root: Path = Path("traces")
    screenshots_enabled: bool = True
    video_capture_enabled: bool = False
    ollama_enabled: bool = False
    emergency_hotkey: str = "ctrl+alt+esc"
    default_activity_profile: str | None = None
    proof_mode: bool = False

    def metadata(self) -> dict[str, object]:
        return {
            "trace_root": str(self.trace_root),
            "screenshots_enabled": self.screenshots_enabled,
            "video_capture_enabled": self.video_capture_enabled,
            "ollama_enabled": self.ollama_enabled,
            "emergency_hotkey": self.emergency_hotkey,
            "default_activity_profile": self.default_activity_profile,
            "proof_mode": self.proof_mode,
        }


def operator_app_shell_spec() -> OperatorAppShell:
    """Return the Phase 8 native app shell page contract."""
    pages = (
        OperatorAppPage(
            page_id="dashboard",
            title="Dashboard",
            purpose="Daily status, recent runs, and next safe action.",
            panel_ids=("live_run",),
        ),
        OperatorAppPage(
            page_id="routine_library",
            title="Routine Library",
            purpose="List, search, inspect, dry-run, and run routines.",
        ),
        OperatorAppPage(
            page_id="record",
            title="Record",
            purpose="Capture a demonstrated routine and review generated YAML.",
            panel_ids=("recorder_review",),
        ),
        OperatorAppPage(
            page_id="run_queue",
            title="Run Queue",
            purpose="Monitor scheduled, running, paused, and blocked routines.",
        ),
        OperatorAppPage(
            page_id="approvals",
            title="Approvals",
            purpose="Review high-risk steps before local execution continues.",
            panel_ids=("approval_dialog",),
        ),
        OperatorAppPage(
            page_id="trace_viewer",
            title="Trace Viewer",
            purpose="Inspect screenshots, action logs, evidence, and reports.",
            panel_ids=("trace_timeline",),
        ),
        OperatorAppPage(
            page_id="settings",
            title="Settings",
            purpose="Configure local trace, safety, model, and proof options.",
            panel_ids=("settings",),
        ),
        OperatorAppPage(
            page_id="help",
            title="Help",
            purpose="Show local guidance, safety boundaries, and diagnostics.",
        ),
    )
    return OperatorAppShell(
        title="DeskPilot Operator",
        pages=pages,
        default_page_id="dashboard",
    )


def default_live_run_panel_state() -> LiveRunPanelState:
    """Return an idle live-run panel state for app startup."""
    return LiveRunPanelState()


def render_live_run_panel_text(state: LiveRunPanelState | None = None) -> str:
    """Render live-run status for CLI diagnostics and tests."""
    active_state = state or default_live_run_panel_state()
    screenshot = (
        str(active_state.screenshot_path)
        if active_state.screenshot_path is not None
        else "none"
    )
    return "\n".join(
        [
            "Live Run",
            f"- Status: {active_state.status}",
            f"- Current routine: {active_state.current_routine_id or 'none'}",
            f"- Current step: {active_state.current_step_id or 'none'}",
            f"- Screenshot preview: {screenshot}",
            f"- Selected target: {active_state.selected_target or 'none'}",
            f"- Next action: {active_state.next_action or 'none'}",
            f"- Elapsed seconds: {active_state.elapsed_seconds:g}",
            f"- Stop controls: {', '.join(active_state.stop_controls)}",
        ],
    ) + "\n"


def render_approval_dialog_text(state: ApprovalDialogState) -> str:
    """Render approval dialog details for diagnostics and tests."""
    return "\n".join(
        [
            "Approval",
            f"- Routine ID: {state.routine_id}",
            f"- Step ID: {state.step_id}",
            f"- Risk class: {state.risk_class}",
            f"- Checkpoint evidence: {state.checkpoint_evidence}",
            f"- Content fingerprint: {state.content_fingerprint}",
            f"- Status: {state.status}",
            f"- Actions: {', '.join(state.actions)}",
        ],
    ) + "\n"


def render_recorder_review_text(state: RecorderReviewPanelState) -> str:
    """Render recorder review details for diagnostics and tests."""
    screenshots = (
        ", ".join(str(path) for path in state.screenshot_paths)
        if state.screenshot_paths
        else "none"
    )
    return "\n".join(
        [
            "Recorder Review",
            f"- Status: {state.status}",
            f"- Generated YAML: {state.generated_yaml}",
            f"- Selected targets: {', '.join(state.selected_targets) or 'none'}",
            f"- Screenshots: {screenshots}",
            "- Verification suggestions: "
            f"{', '.join(state.verification_suggestions) or 'none'}",
        ],
    ) + "\n"


def render_trace_viewer_timeline_text(state: TraceViewerTimelineState) -> str:
    """Render trace timeline evidence for diagnostics and tests."""
    video = str(state.video_path) if state.video_path else "none"
    action_log = str(state.action_log_path) if state.action_log_path else "none"
    final_report = str(state.final_report_path) if state.final_report_path else "none"
    screenshots = (
        ", ".join(str(path) for path in state.screenshot_paths)
        if state.screenshot_paths
        else "none"
    )
    return "\n".join(
        [
            "Trace Timeline",
            f"- Status: {state.status}",
            f"- Video: {video}",
            f"- Screenshots: {screenshots}",
            f"- Action log: {action_log}",
            "- Candidate reasoning: "
            f"{', '.join(state.candidate_reasoning) or 'none'}",
            f"- State delta: {', '.join(state.state_delta) or 'none'}",
            f"- Final report: {final_report}",
        ],
    ) + "\n"


def settings_panel_from_runtime_config(
    config: RuntimeConfig,
    *,
    video_capture_enabled: bool = False,
    proof_mode: bool = False,
) -> SettingsPanelState:
    """Build app settings state from the shared runtime configuration."""
    return SettingsPanelState(
        trace_root=config.trace_root,
        screenshots_enabled=config.save_screenshots,
        video_capture_enabled=video_capture_enabled,
        ollama_enabled=config.local_model.enabled,
        emergency_hotkey=config.emergency_stop_hotkey,
        default_activity_profile=config.execution_profile.activity_profile,
        proof_mode=proof_mode,
    )


def render_settings_panel_text(state: SettingsPanelState) -> str:
    """Render app settings fields for diagnostics and tests."""
    return "\n".join(
        [
            "Settings",
            f"- Trace root: {state.trace_root}",
            f"- Screenshots: {state.screenshots_enabled}",
            f"- Video capture: {state.video_capture_enabled}",
            f"- Ollama: {state.ollama_enabled}",
            f"- Emergency hotkey: {state.emergency_hotkey}",
            f"- Default activity profile: {state.default_activity_profile or 'none'}",
            f"- Proof mode: {state.proof_mode}",
        ],
    ) + "\n"


def render_operator_app_shell_text(shell: OperatorAppShell | None = None) -> str:
    """Render the shell contract for CLI diagnostics and tests."""
    active_shell = shell or operator_app_shell_spec()
    lines = [active_shell.title, ""]
    for page in active_shell.pages:
        default_marker = (
            " (default)" if page.page_id == active_shell.default_page_id else ""
        )
        lines.append(f"- {page.title}{default_marker}: {page.purpose}")
        for panel_id in page.panel_ids:
            lines.append(f"  panel: {panel_id}")
    return "\n".join(lines) + "\n"


def launch_operator_app(
    argv: Sequence[str] | None = None,
    *,
    shell: OperatorAppShell | None = None,
) -> int:
    """Launch the native PySide6 shell when the optional dependency exists."""
    active_shell = shell or operator_app_shell_spec()
    qt_widgets = _qt_widgets_module()
    app = qt_widgets.QApplication(list(argv or []))
    window = _build_main_window(qt_widgets, active_shell)
    window.show()
    return int(app.exec())


def _qt_widgets_module() -> Any:
    try:
        return import_module("PySide6.QtWidgets")
    except ModuleNotFoundError as exc:
        raise OperatorAppUnavailableError(
            'PySide6 is not installed. Install DeskPilot with "deskpilot[app]".',
        ) from exc


def _build_main_window(qt_widgets: Any, shell: OperatorAppShell) -> Any:
    window = qt_widgets.QMainWindow()
    window.setWindowTitle(shell.title)
    window.resize(1180, 760)

    central = qt_widgets.QWidget()
    layout = qt_widgets.QHBoxLayout(central)
    nav = qt_widgets.QListWidget()
    stack = qt_widgets.QStackedWidget()
    for page in shell.pages:
        nav.addItem(page.title)
        stack.addWidget(_page_widget(qt_widgets, page))
    nav.setCurrentRow(0)
    nav.currentRowChanged.connect(stack.setCurrentIndex)
    layout.addWidget(nav, 1)
    layout.addWidget(stack, 4)
    window.setCentralWidget(central)
    return window


def _page_widget(qt_widgets: Any, page: OperatorAppPage) -> Any:
    widget = qt_widgets.QWidget()
    layout = qt_widgets.QVBoxLayout(widget)
    heading = qt_widgets.QLabel(page.title)
    heading.setObjectName(f"{page.page_id}_heading")
    body = qt_widgets.QLabel(page.purpose)
    body.setWordWrap(True)
    layout.addWidget(heading)
    layout.addWidget(body)
    if "live_run" in page.panel_ids:
        for line in render_live_run_panel_text().splitlines():
            layout.addWidget(qt_widgets.QLabel(line))
    if "approval_dialog" in page.panel_ids:
        layout.addWidget(qt_widgets.QLabel("Approval"))
        layout.addWidget(qt_widgets.QLabel("Routine ID: pending"))
        layout.addWidget(qt_widgets.QLabel("Step ID: pending"))
        layout.addWidget(qt_widgets.QLabel("Risk class: pending"))
        layout.addWidget(qt_widgets.QLabel("Checkpoint evidence: pending"))
        layout.addWidget(qt_widgets.QLabel("Content fingerprint: pending"))
        layout.addWidget(qt_widgets.QLabel("Actions: approve, deny"))
    if "recorder_review" in page.panel_ids:
        layout.addWidget(qt_widgets.QLabel("Recorder Review"))
        layout.addWidget(qt_widgets.QLabel("Generated YAML: pending"))
        layout.addWidget(qt_widgets.QLabel("Selected targets: pending"))
        layout.addWidget(qt_widgets.QLabel("Screenshots: pending"))
        layout.addWidget(qt_widgets.QLabel("Verification suggestions: pending"))
    if "trace_timeline" in page.panel_ids:
        layout.addWidget(qt_widgets.QLabel("Trace Timeline"))
        layout.addWidget(qt_widgets.QLabel("Video: pending"))
        layout.addWidget(qt_widgets.QLabel("Screenshots: pending"))
        layout.addWidget(qt_widgets.QLabel("Action log: pending"))
        layout.addWidget(qt_widgets.QLabel("Candidate reasoning: pending"))
        layout.addWidget(qt_widgets.QLabel("State delta: pending"))
        layout.addWidget(qt_widgets.QLabel("Final report: pending"))
    if "settings" in page.panel_ids:
        layout.addWidget(qt_widgets.QLabel("Settings"))
        layout.addWidget(qt_widgets.QLabel("Trace root: traces"))
        layout.addWidget(qt_widgets.QLabel("Screenshots: true"))
        layout.addWidget(qt_widgets.QLabel("Video capture: false"))
        layout.addWidget(qt_widgets.QLabel("Ollama: false"))
        layout.addWidget(qt_widgets.QLabel("Emergency hotkey: ctrl+alt+esc"))
        layout.addWidget(qt_widgets.QLabel("Default activity profile: none"))
        layout.addWidget(qt_widgets.QLabel("Proof mode: false"))
    layout.addStretch(1)
    return widget
