import json
from pathlib import Path

from pytest import CaptureFixture, MonkeyPatch

from desktop_agent.cli import main
from desktop_agent.config import RuntimeConfig
from desktop_agent.ocr import OcrTextBlock
from desktop_agent.perception import ElementCandidate
from desktop_agent.screen import Bounds, ScreenObservation, ScreenUnavailableError


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


def test_cli_dry_run_plans_scroll_until_without_live_screen(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    task_path = tmp_path / "task.yaml"
    trace_root = tmp_path / "traces"
    task_path.write_text(
        "\n".join(
            [
                "name: dry-run-scroll",
                "allowed_windows:",
                "  - DeskPilot Fixture",
                "timeout_seconds: 30",
                "config:",
                f"  trace_root: {trace_root}",
                "steps:",
                "  - id: scroll-to-submit",
                "    action: scroll_until",
                "    target: Submit",
                "    region:",
                "      x: 0",
                "      y: 0",
                "      width: 640",
                "      height: 480",
                "",
            ],
        ),
        encoding="utf-8",
    )

    status = main(["dry-run", str(task_path)])

    output = capsys.readouterr().out
    assert status == 0
    assert "status: passed" in output
    assert "step scroll-to-submit: passed" in output


def test_cli_run_fails_when_platform_actuation_is_unavailable(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    task_path = tmp_path / "task.yaml"
    write_task(task_path)

    status = main(["run", str(task_path), "--allowed-window", "DeskPilot Fixture"])

    output = capsys.readouterr().out
    assert status == 1
    assert "desktop actuation is unavailable on this platform" in output


class FixtureScreenObserver:
    def observe(self, config: RuntimeConfig) -> ScreenObservation:
        return ScreenObservation(
            screenshot_path=config.trace_root / "screenshots" / "screen.png",
            size=(640, 480),
            warnings=(
                "multiple monitors detected; v1 is using the primary monitor only",
            ),
            metadata={"monitor_count": 2},
        )


class FailingScreenObserver:
    def observe(self, config: RuntimeConfig) -> ScreenObservation:
        _ = config
        raise ScreenUnavailableError("desktop session appears locked or unavailable")


class FixtureOcrProvider:
    def extract_text(self, screenshot_path: Path) -> tuple[OcrTextBlock, ...]:
        _ = screenshot_path
        return (
            OcrTextBlock(
                text="Submit",
                bounds=Bounds(x=10, y=20, width=80, height=24),
                confidence=0.93,
            ),
        )


class FixtureUiaAdapter:
    def tree_snapshot(self) -> dict[str, object]:
        return {
            "active_window": {"title": "DeskPilot Fixture"},
            "elements": [{"name": "Submit", "control_type": "Button"}],
        }

    def candidates(self) -> tuple[ElementCandidate, ...]:
        return (
            ElementCandidate(
                id="uia-submit",
                source="uia",
                label="Submit",
                bounds=Bounds(x=120, y=20, width=90, height=28),
                confidence=0.95,
            ),
        )


def test_cli_inspect_screen_writes_success_report(
    tmp_path: Path,
    capsys: CaptureFixture[str],
    monkeypatch: MonkeyPatch,
) -> None:
    output_dir = tmp_path / "trace"
    monkeypatch.setattr("desktop_agent.cli.MssScreenObserver", FixtureScreenObserver)
    monkeypatch.setattr("desktop_agent.cli.TesseractOcrProvider", FixtureOcrProvider)
    monkeypatch.setattr("desktop_agent.cli.WindowsUiaAdapter", FixtureUiaAdapter)

    status = main(["inspect-screen", "--output", str(output_dir)])

    output = capsys.readouterr().out
    report = json.loads((output_dir / "inspect-screen.json").read_text())
    assert status == 0
    assert report["status"] == "passed"
    assert report["size"] == [640, 480]
    assert report["metadata"]["monitor_count"] == 2
    assert report["ocr"]["status"] == "passed"
    assert report["ocr"]["blocks"][0]["text"] == "Submit"
    assert report["uia"]["status"] == "passed"
    assert report["uia"]["tree"]["active_window"]["title"] == "DeskPilot Fixture"
    assert report["candidates"][0]["id"] == "uia-submit"
    assert report["candidate_rankings"][0]["source"] == "uia"
    assert (output_dir / "uia-tree.json").exists()
    assert "status: passed" in output


def test_cli_inspect_screen_writes_failure_report(
    tmp_path: Path,
    capsys: CaptureFixture[str],
    monkeypatch: MonkeyPatch,
) -> None:
    output_dir = tmp_path / "trace"
    monkeypatch.setattr("desktop_agent.cli.MssScreenObserver", FailingScreenObserver)

    status = main(["inspect-screen", "--output", str(output_dir)])

    output = capsys.readouterr().out
    report = json.loads((output_dir / "inspect-screen.json").read_text())
    assert status == 1
    assert report["status"] == "failed"
    assert "locked or unavailable" in output


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


def test_cli_benchmark_run_writes_metrics_and_report(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    task_path = tmp_path / "task.yaml"
    output_dir = tmp_path / "benchmark"
    write_task(task_path)

    status = main(
        [
            "benchmark-run",
            str(task_path),
            "--iterations",
            "2",
            "--output",
            str(output_dir),
        ],
    )

    output = capsys.readouterr().out
    report = json.loads((output_dir / "benchmark-report.json").read_text())
    metrics = (output_dir / "runs.jsonl").read_text().splitlines()
    assert status == 0
    assert report["iterations"] == 2
    assert len(metrics) == 2
    assert "metrics:" in output
    assert "report:" in output
