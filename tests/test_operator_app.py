import tomllib
from pathlib import Path

from pytest import CaptureFixture

from desktop_agent.operator_app import main


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
