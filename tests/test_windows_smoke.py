"""Opt-in smoke tests for real input on an owned unlocked Windows desktop."""

import json
import os
import sys
import zipfile
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

    preflight_exit_code = main(
        [
            "proof",
            "preflight",
            "--trace-root",
            str(trace_root),
            "--video-policy",
            "disabled",
            "--write-report",
        ],
    )
    assert preflight_exit_code == 0, "proof suite preflight failed"

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
            "--require-preflight",
            "--write-report",
            "--write-status-json",
            "--write-runbook",
            "--write-archive",
            "--write-review-template",
        ],
    )

    assert validation_exit_code == 0, "proof suite validation failed"
    assert (trace_root / "proof-preflight.json").exists()
    assert (trace_root / "proof-suite-report.md").exists()
    assert (trace_root / "proof-suite-status.json").exists()
    assert (trace_root / "proof-suite-next-actions.md").exists()
    assert (trace_root / "proof-suite-review.md").exists()

    review_path = trace_root / "proof-suite-review.md"
    _complete_smoke_review_template(review_path)
    review_exit_code = main(
        [
            "proof",
            "validate-review",
            str(review_path),
            "--write-status-json",
        ],
    )
    assert review_exit_code == 0, "proof suite review validation failed"

    promotion_exit_code = main(
        [
            "proof",
            "promote-suite",
            str(trace_root),
            "--allow-missing-video",
            "--write-status-json",
            "--write-archive",
        ],
    )
    assert promotion_exit_code == 0, "proof suite review-gated promotion failed"
    verification_exit_code = main(
        [
            "proof",
            "verify-promotion",
            str(trace_root / "proof-suite-promotion.json"),
        ],
    )
    assert verification_exit_code == 0, "proof promotion digest verification failed"
    promotion_payload = json.loads(
        (trace_root / "proof-suite-promotion.json").read_text(encoding="utf-8"),
    )
    status_payload = json.loads(
        (trace_root / "proof-suite-status.json").read_text(encoding="utf-8"),
    )
    assert promotion_payload["promotion_ready"] is True
    assert status_payload["status"] == "passed"
    assert status_payload["review_status_path"] == str(
        trace_root / "proof-suite-review-status.json",
    )
    assert (trace_root / "proof-suite-artifacts.zip").exists()
    with zipfile.ZipFile(trace_root / "proof-suite-artifacts.zip") as archive:
        names = set(archive.namelist())
    assert "proof-suite-review-status.json" in names
    assert "proof-suite-promotion.json" in names


def _complete_smoke_review_template(review_path: Path) -> None:
    # The opt-in smoke test completes the generated template only to exercise
    # review-gated promotion mechanics; final proof acceptance still requires a
    # real human review of the collected Windows video and trace bundle.
    lines = []
    for line in review_path.read_text(encoding="utf-8").splitlines():
        if line == "- Reviewer:":
            lines.append("- Reviewer: Windows smoke pipeline")
        elif line == "- Review date:":
            lines.append("- Review date: 2026-05-16")
        elif line == "- [ ] Pass":
            lines.append("- [x] Pass")
        elif line.startswith("- [ ] ") and line != "- [ ] Fail":
            lines.append(line.replace("- [ ] ", "- [x] ", 1))
        else:
            lines.append(line)
    review_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _require_windows_smoke() -> None:
    # The environment gate prevents real desktop input from running in CI or dev
    # shells unless the operator has prepared the local Windows fixture session.
    if os.environ.get(SMOKE_ENV) != "1":
        pytest.skip(f"set {SMOKE_ENV}=1 on an owned Windows desktop to run")
    if sys.platform != "win32":
        pytest.skip("Windows smoke tests require an unlocked Windows desktop")
