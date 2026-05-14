"""Opt-in smoke tests for real input on an owned unlocked Windows desktop."""

import json
import os
import sys
from pathlib import Path

import pytest

from desktop_agent.cli import main

SMOKE_ENV = "DESKPILOT_WINDOWS_SMOKE"

pytestmark = pytest.mark.windows_smoke


def test_windows_smoke_inspect_screen_writes_unlocked_desktop_report(
    tmp_path: Path,
) -> None:
    _require_windows_smoke()
    output_dir = tmp_path / "inspect-screen"

    exit_code = main(["inspect-screen", "--output", str(output_dir)])

    report_path = output_dir / "inspect-screen.json"
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert payload["status"] == "passed"
    assert payload["screenshot_path"] is not None
    assert Path(str(payload["screenshot_path"])).exists()


@pytest.mark.parametrize(
    ("task_path", "fixture_name", "confirmed_step"),
    [
        (Path("examples/browser-task.yaml"), "browser fixture", "click-submit"),
        (
            Path("examples/native-task.yaml"),
            "native fixture",
            "click-native-submit",
        ),
    ],
)
def test_windows_smoke_fixture_run_passes_on_owned_desktop(
    task_path: Path,
    fixture_name: str,
    confirmed_step: str,
) -> None:
    _require_windows_smoke()
    config_path = Path("packaging/default-config.yaml")

    exit_code = main(
        [
            "run",
            str(task_path),
            "--config",
            str(config_path),
            "--confirm-step",
            confirmed_step,
        ]
    )

    assert exit_code == 0, f"{fixture_name} smoke run failed"


def _require_windows_smoke() -> None:
    # The environment gate prevents real desktop input from running in CI or dev
    # shells unless the operator has prepared the local Windows fixture session.
    if os.environ.get(SMOKE_ENV) != "1":
        pytest.skip(f"set {SMOKE_ENV}=1 on an owned Windows desktop to run")
    if sys.platform != "win32":
        pytest.skip("Windows smoke tests require an unlocked Windows desktop")
