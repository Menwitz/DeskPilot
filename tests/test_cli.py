import json
from pathlib import Path

from pytest import CaptureFixture

from desktop_agent.cli import main


def write_task(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "name: cli-fixture",
                "allowed_windows:",
                "  - DeskPilot Fixture",
                "timeout_seconds: 30",
                "steps:",
                "  - id: click-submit",
                "    action: click_text",
                "    target: Submit",
                "",
            ],
        ),
        encoding="utf-8",
    )


def test_cli_dry_run_validates_and_reports_success(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    task_path = tmp_path / "task.yaml"
    write_task(task_path)

    status = main(["dry-run", str(task_path), "--allowed-window", "DeskPilot Fixture"])

    output = capsys.readouterr().out
    assert status == 0
    assert "task: cli-fixture" in output
    assert "status: passed" in output


def test_cli_run_fails_until_actuation_adapter_exists(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    task_path = tmp_path / "task.yaml"
    write_task(task_path)

    status = main(["run", str(task_path), "--allowed-window", "DeskPilot Fixture"])

    output = capsys.readouterr().out
    assert status == 1
    assert "desktop actuation is not implemented yet" in output


def test_cli_inspect_screen_writes_failure_report(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    output_dir = tmp_path / "trace"

    status = main(["inspect-screen", "--output", str(output_dir)])

    output = capsys.readouterr().out
    report = json.loads((output_dir / "inspect-screen.json").read_text())
    assert status == 1
    assert report["status"] == "failed"
    assert "not implemented yet" in output


def test_cli_replay_summarizes_final_report(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    trace_dir = tmp_path / "trace"
    trace_dir.mkdir()
    (trace_dir / "final-report.json").write_text(
        json.dumps({"status": "failed", "abort_reason": "fixture"}),
        encoding="utf-8",
    )

    status = main(["replay", str(trace_dir)])

    output = capsys.readouterr().out
    assert status == 0
    assert "status: failed" in output
    assert "reason: fixture" in output
