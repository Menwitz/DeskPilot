"""Opt-in smoke tests for real input on an owned unlocked Windows desktop."""

import json
import os
import sys
from pathlib import Path

import pytest

from desktop_agent.cli import main

SMOKE_ENV = "DESKPILOT_WINDOWS_SMOKE"
PROOF_SUITE_COMMANDS = (
    ("proof", "browser-fixture"),
    ("proof", "native-fixture"),
    ("proof", "mixed-fixture"),
    ("proof", "recovery-fixture"),
)

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


@pytest.mark.parametrize(
    "command",
    [
        ("windows-smoke-checklist",),
        *PROOF_SUITE_COMMANDS,
    ],
)
def test_windows_smoke_proof_command_passes_on_owned_desktop(
    tmp_path: Path,
    command: tuple[str, ...],
) -> None:
    _require_windows_smoke()
    trace_root = tmp_path / "-".join(command)

    exit_code = main(
        [
            *command,
            "--trace-root",
            str(trace_root),
            "--countdown-seconds",
            "0",
            "--video-policy",
            "disabled",
        ]
    )

    manifests = sorted(trace_root.glob("*/proof-manifest.json"))
    assert exit_code == 0, f"{' '.join(command)} smoke command failed"
    assert manifests, f"{' '.join(command)} did not write a proof manifest"
    validation_exit_code = main(
        [
            "proof",
            "validate",
            str(manifests[0].parent),
            "--allow-missing-video",
        ]
    )
    assert validation_exit_code == 0, (
        f"{' '.join(command)} proof bundle validation failed"
    )


def test_windows_smoke_proof_suite_validates_owned_desktop(tmp_path: Path) -> None:
    _require_windows_smoke()
    trace_root = tmp_path / "proof-suite"

    for command in PROOF_SUITE_COMMANDS:
        exit_code = main(
            [
                *command,
                "--trace-root",
                str(trace_root),
                "--countdown-seconds",
                "0",
                "--video-policy",
                "disabled",
            ],
        )
        assert exit_code == 0, f"{' '.join(command)} suite command failed"

    validation_exit_code = main(
        [
            "proof",
            "validate-suite",
            str(trace_root),
            "--allow-missing-video",
            "--write-report",
        ],
    )

    assert validation_exit_code == 0, "proof suite validation failed"
    assert (trace_root / "proof-suite-report.md").exists()


def _require_windows_smoke() -> None:
    # The environment gate prevents real desktop input from running in CI or dev
    # shells unless the operator has prepared the local Windows fixture session.
    if os.environ.get(SMOKE_ENV) != "1":
        pytest.skip(f"set {SMOKE_ENV}=1 on an owned Windows desktop to run")
    if sys.platform != "win32":
        pytest.skip("Windows smoke tests require an unlocked Windows desktop")
