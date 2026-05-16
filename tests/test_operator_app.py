import tomllib
from pathlib import Path

from pytest import CaptureFixture

from desktop_agent.operator_app import main
from desktop_agent.operator_app_shell import (
    operator_app_shell_spec,
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
    assert shell.metadata()["pages"]


def test_operator_app_describe_shell_prints_pages(
    capsys: CaptureFixture[str],
) -> None:
    status = main(["--describe-shell"])

    output = capsys.readouterr().out
    assert status == 0
    assert "DeskPilot Operator" in output
    assert "Dashboard (default)" in output
    assert "Routine Library" in output
    assert "Trace Viewer" in output
    assert output == render_operator_app_shell_text()
