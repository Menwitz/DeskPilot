import tomllib
from pathlib import Path

from pytest import CaptureFixture

from desktop_agent.operator_app import main
from desktop_agent.operator_app_shell import (
    ApprovalDialogState,
    LiveRunPanelState,
    default_live_run_panel_state,
    operator_app_shell_spec,
    render_approval_dialog_text,
    render_live_run_panel_text,
    render_operator_app_shell_text,
)


def test_pyproject_exposes_deskpilot_app_entry_point() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["scripts"]["deskpilot-app"] == (
        "desktop_agent.operator_app:main"
    )


def test_operator_app_check_mode_reports_entry_point(
    capsys: CaptureFixture[str],
) -> None:
    status = main(["--check"])

    output = capsys.readouterr().out
    assert status == 0
    assert "deskpilot-app entry point: ok" in output
    assert "PySide6:" in output


def test_operator_app_shell_exposes_required_pages() -> None:
    shell = operator_app_shell_spec()

    assert shell.default_page_id == "dashboard"
    assert [page.page_id for page in shell.pages] == [
        "dashboard",
        "routine_library",
        "record",
        "run_queue",
        "approvals",
        "trace_viewer",
        "settings",
        "help",
    ]
    assert shell.pages[0].panel_ids == ("live_run",)
    approvals_page = next(page for page in shell.pages if page.page_id == "approvals")
    assert approvals_page.panel_ids == ("approval_dialog",)
    assert shell.metadata()["pages"]


def test_operator_app_describe_shell_prints_pages(
    capsys: CaptureFixture[str],
) -> None:
    status = main(["--describe-shell"])

    output = capsys.readouterr().out
    assert status == 0
    assert "DeskPilot Operator" in output
    assert "Dashboard (default)" in output
    assert "panel: live_run" in output
    assert "Routine Library" in output
    assert "Trace Viewer" in output
    assert output == render_operator_app_shell_text()


def test_live_run_panel_state_tracks_run_status_fields(tmp_path: Path) -> None:
    state = LiveRunPanelState(
        current_routine_id="browser.search",
        current_step_id="type-query",
        screenshot_path=tmp_path / "screen.png",
        selected_target="Search box",
        next_action="type_text",
        elapsed_seconds=12.5,
        status="running",
    )

    metadata = state.metadata()
    text = render_live_run_panel_text(state)

    assert metadata["current_routine_id"] == "browser.search"
    assert metadata["current_step_id"] == "type-query"
    assert metadata["screenshot_path"] == str(tmp_path / "screen.png")
    assert metadata["selected_target"] == "Search box"
    assert metadata["next_action"] == "type_text"
    assert metadata["elapsed_seconds"] == 12.5
    assert metadata["status"] == "running"
    assert metadata["stop_controls"] == [
        "pause",
        "resume",
        "cancel",
        "emergency_stop",
    ]
    assert "Screenshot preview" in text
    assert "Stop controls: pause, resume, cancel, emergency_stop" in text


def test_live_run_panel_defaults_to_idle() -> None:
    state = default_live_run_panel_state()

    assert state.status == "idle"
    assert state.current_routine_id is None


def test_approval_dialog_state_tracks_required_review_fields() -> None:
    state = ApprovalDialogState(
        routine_id="social.publish",
        step_id="submit-post",
        risk_class="high",
        checkpoint_evidence="checkpoint screenshot present",
        content_fingerprint="sha256:abc123",
    )

    metadata = state.metadata()
    text = render_approval_dialog_text(state)

    assert metadata["routine_id"] == "social.publish"
    assert metadata["step_id"] == "submit-post"
    assert metadata["risk_class"] == "high"
    assert metadata["checkpoint_evidence"] == "checkpoint screenshot present"
    assert metadata["content_fingerprint"] == "sha256:abc123"
    assert metadata["actions"] == ["approve", "deny"]
    assert "Actions: approve, deny" in text
