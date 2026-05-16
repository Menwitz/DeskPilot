import json
from pathlib import Path

from pytest import CaptureFixture, MonkeyPatch

from desktop_agent.actuation import ActuationProfile, DryRunActuator
from desktop_agent.cli import (
    _perception_engine_for_mode,
    _screen_observer_for_mode,
    main,
)
from desktop_agent.config import RuntimeConfig
from desktop_agent.ocr import OcrTextBlock
from desktop_agent.perception import ElementCandidate
from desktop_agent.safety import EmergencyStopMonitor
from desktop_agent.screen import (
    Bounds,
    MssScreenObserver,
    ScreenObservation,
    ScreenUnavailableError,
    StaticScreenObserver,
)
from desktop_agent.task_dsl import TaskStep


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


def write_proof_manifest(trace_dir: Path) -> dict[str, Path]:
    trace_dir.mkdir()
    screenshot_dir = trace_dir / "screenshots"
    screenshot_dir.mkdir()
    report_path = trace_dir / "linkedin-demo-report.json"
    action_log_path = trace_dir / "action-log.jsonl"
    manifest_path = trace_dir / "proof-manifest.json"
    screenshot_path = screenshot_dir / "shot-1.png"
    video_path = trace_dir / "missing-video.mp4"
    report_path.write_text("{}", encoding="utf-8")
    action_log_path.write_text("", encoding="utf-8")
    screenshot_path.write_bytes(b"png")
    manifest = {
        "schema_version": 1,
        "proof_name": "linkedin-demo",
        "command": ["desktop-agent", "demo-linkedin", "--trace-root", "traces"],
        "status": "passed",
        "started_at": "2026-05-16T00:00:00+00:00",
        "completed_at": "2026-05-16T00:00:01+00:00",
        "executable_version": "0.1.0",
        "python_version": "3.12.0",
        "platform": "win32",
        "artifacts": {
            "trace_dir": str(trace_dir),
            "report_path": str(report_path),
            "action_log_path": str(action_log_path),
            "proof_manifest_path": str(manifest_path),
            "screenshots": [str(screenshot_path)],
            "video_path": str(video_path),
        },
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return {
        "trace_dir": trace_dir,
        "report_path": report_path,
        "action_log_path": action_log_path,
        "proof_manifest_path": manifest_path,
        "screenshot_path": screenshot_path,
        "video_path": video_path,
    }


def _write_submission_task(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "name: cli-submission",
                "allowed_windows:",
                "  - DeskPilot Fixture",
                "timeout_seconds: 30",
                "steps:",
                "  - id: click-submit",
                "    action: press_key",
                "    text: enter",
                "    category: submission",
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
    assert "dry-run preview:" in output
    assert "task: cli-fixture" in output
    assert "status: passed" in output


def test_cli_dry_run_preview_shows_timing_bounds_and_recovery_paths(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    task_path = tmp_path / "task.yaml"
    task_path.write_text(
        "\n".join(
            [
                "name: preview-cli",
                "allowed_windows:",
                "  - DeskPilot Fixture",
                "timeout_seconds: 30",
                "config:",
                "  execution_profile:",
                "    enabled: true",
                "    action_delay_seconds: [0.05, 0.25]",
                "    retry_delay_seconds: [0.10, 0.30]",
                "steps:",
                "  - id: click-submit",
                "    action: click_text",
                "    target: Submit",
                "    recovery:",
                "      - reason: missed_target",
                "        actions:",
                "          - wait_and_reobserve",
                "          - abort_with_trace",
                "",
            ],
        ),
        encoding="utf-8",
    )

    status = main(["dry-run", str(task_path), "--allowed-window", "DeskPilot Fixture"])

    output = capsys.readouterr().out
    assert status == 0
    assert "timing: action 0.050-0.250s x2" in output
    assert "retry 0.100-0.300s x1" in output
    assert "recovery: missed_target -> wait_and_reobserve -> abort_with_trace" in output
    assert "chosen wait_and_reobserve constrained" in output


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
    trace_root = tmp_path / "traces"
    task_path.write_text(
        "\n".join(
            [
                "name: cli-fixture",
                "allowed_windows:",
                "  - DeskPilot Fixture",
                "timeout_seconds: 30",
                "config:",
                f"  trace_root: {trace_root}",
                "steps:",
                "  - id: click-submit",
                "    action: click_text",
                "    target: Submit",
                "",
            ],
        ),
        encoding="utf-8",
    )

    status = main(["run", str(task_path), "--allowed-window", "DeskPilot Fixture"])

    output = capsys.readouterr().out
    assert status == 1
    assert "desktop actuation is unavailable on this platform" in output
    assert "missed_target" not in output
    report_paths = tuple(trace_root.glob("*/final-report.json"))
    assert len(report_paths) == 1
    report = json.loads(report_paths[0].read_text(encoding="utf-8"))
    assert report["status"] == "aborted"
    assert (
        report["abort_reason"]
        == "desktop actuation is unavailable on this platform; use dry-run"
    )
    phases = [event["phase"] for event in report["events"]]
    assert phases == ["platform_preflight"]
    assert report["events"][0]["metadata"]["deep_search_skipped"] is True


def test_cli_run_stops_when_operator_denies_submission_approval(
    tmp_path: Path,
    capsys: CaptureFixture[str],
    monkeypatch: MonkeyPatch,
) -> None:
    task_path = tmp_path / "task.yaml"
    _write_submission_task(task_path)
    monkeypatch.setattr("builtins.input", lambda _prompt: "no")

    def create_actuator(
        profile: ActuationProfile | None = None,
        emergency_stop_monitor: EmergencyStopMonitor | None = None,
    ) -> DryRunActuator:
        _ = profile, emergency_stop_monitor
        return DryRunActuator()

    monkeypatch.setattr("desktop_agent.cli.create_platform_actuator", create_actuator)

    status = main(["run", str(task_path), "--allowed-window", "DeskPilot Fixture"])

    output = capsys.readouterr().out
    assert status == 1
    assert "step click-submit not approved" in output
    assert (
        "step click-submit: failed (step click-submit requires operator approval)"
        in output
    )


def test_cli_run_uses_operator_approval_for_submission_steps(
    tmp_path: Path,
    capsys: CaptureFixture[str],
    monkeypatch: MonkeyPatch,
) -> None:
    task_path = tmp_path / "task.yaml"
    _write_submission_task(task_path)
    monkeypatch.setattr("builtins.input", lambda _prompt: "click-submit")

    def create_actuator(
        profile: ActuationProfile | None = None,
        emergency_stop_monitor: EmergencyStopMonitor | None = None,
    ) -> DryRunActuator:
        _ = profile, emergency_stop_monitor
        return DryRunActuator()

    monkeypatch.setattr("desktop_agent.cli.create_platform_actuator", create_actuator)

    status = main(["run", str(task_path), "--allowed-window", "DeskPilot Fixture"])

    output = capsys.readouterr().out
    assert status == 0
    assert "step click-submit: passed" in output


def test_cli_demo_input_prints_trace_report(
    tmp_path: Path,
    capsys: CaptureFixture[str],
    monkeypatch: MonkeyPatch,
) -> None:
    from desktop_agent.mouse_demo import MouseDemoReport, MouseDemoStep

    def fake_run_input_demo(
        *,
        trace_root: Path,
        random_seed: int,
        movement_smoothness: float,
        keyboard_text: str,
        countdown_seconds: float,
    ) -> MouseDemoReport:
        assert trace_root == tmp_path
        assert random_seed == 7
        assert movement_smoothness == 0.5
        assert keyboard_text == "typed by test"
        assert countdown_seconds == 0
        return MouseDemoReport(
            status="passed",
            trace_dir=tmp_path / "trace",
            report_path=tmp_path / "trace" / "input-demo-report.json",
            steps=(
                MouseDemoStep(
                    "desktop-waypoint-1",
                    "move",
                    {
                        "movement_points": 32,
                        "movement_duration_seconds": 0.75,
                    },
                ),
            ),
        )

    monkeypatch.setattr("desktop_agent.cli.run_input_demo", fake_run_input_demo)

    status = main(
        [
            "demo-input",
            "--trace-root",
            str(tmp_path),
            "--random-seed",
            "7",
            "--movement-smoothness",
            "0.5",
            "--keyboard-text",
            "typed by test",
            "--countdown-seconds",
            "0",
        ],
    )

    output = capsys.readouterr().out
    assert status == 0
    assert "status: passed" in output
    assert "step desktop-waypoint-1: move (32 points, 0.750s)" in output


def test_cli_demo_mouse_alias_uses_input_demo(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    from desktop_agent.mouse_demo import MouseDemoReport

    calls: list[str] = []

    def fake_run_input_demo(
        *,
        trace_root: Path,
        random_seed: int,
        movement_smoothness: float,
        keyboard_text: str,
        countdown_seconds: float,
    ) -> MouseDemoReport:
        _ = trace_root, random_seed, movement_smoothness, keyboard_text
        assert countdown_seconds == 0
        calls.append("called")
        return MouseDemoReport(
            status="passed",
            trace_dir=tmp_path / "trace",
            report_path=tmp_path / "trace" / "input-demo-report.json",
            steps=(),
        )

    monkeypatch.setattr("desktop_agent.cli.run_input_demo", fake_run_input_demo)

    status = main(
        ["demo-mouse", "--trace-root", str(tmp_path), "--countdown-seconds", "0"]
    )

    assert status == 0
    assert calls == ["called"]


def test_cli_demo_linkedin_prints_trace_report(
    tmp_path: Path,
    capsys: CaptureFixture[str],
    monkeypatch: MonkeyPatch,
) -> None:
    from desktop_agent.mouse_demo import MouseDemoReport, MouseDemoStep

    def fake_run_linkedin_demo(
        *,
        trace_root: Path,
        random_seed: int,
        movement_smoothness: float,
        countdown_seconds: float,
        url: str,
        find_text: str,
        page_load_seconds: float,
    ) -> MouseDemoReport:
        assert trace_root == tmp_path
        assert random_seed == 13
        assert movement_smoothness == 0.4
        assert countdown_seconds == 0
        assert url == "https://www.linkedin.com/"
        assert find_text == "LinkedIn"
        assert page_load_seconds == 0
        return MouseDemoReport(
            status="passed",
            trace_dir=tmp_path / "trace",
            report_path=tmp_path / "trace" / "linkedin-demo-report.json",
            steps=(
                MouseDemoStep(
                    "scroll-linkedin-page",
                    "scroll",
                    {
                        "movement_points": 12,
                        "movement_duration_seconds": 0.5,
                    },
                ),
            ),
        )

    monkeypatch.setattr("desktop_agent.cli.run_linkedin_demo", fake_run_linkedin_demo)

    status = main(
        [
            "demo-linkedin",
            "--trace-root",
            str(tmp_path),
            "--random-seed",
            "13",
            "--movement-smoothness",
            "0.4",
            "--countdown-seconds",
            "0",
            "--page-load-seconds",
            "0",
        ]
    )

    output = capsys.readouterr().out
    assert status == 0
    assert "status: passed" in output
    assert "step scroll-linkedin-page: scroll (12 points, 0.500s)" in output


def test_cli_windows_smoke_checklist_prints_checks(
    tmp_path: Path,
    capsys: CaptureFixture[str],
    monkeypatch: MonkeyPatch,
) -> None:
    from desktop_agent.mouse_demo import MouseDemoReport, MouseDemoStep

    def fake_run_windows_smoke_checklist(
        *,
        trace_root: Path,
        random_seed: int,
        movement_smoothness: float,
        countdown_seconds: float,
        keyboard_text: str,
        edge_url: str,
    ) -> MouseDemoReport:
        assert trace_root == tmp_path
        assert random_seed == 21
        assert movement_smoothness == 0.6
        assert countdown_seconds == 0
        assert keyboard_text == "smoke"
        assert edge_url == "about:blank"
        return MouseDemoReport(
            status="passed",
            trace_dir=tmp_path / "trace",
            report_path=tmp_path / "trace" / "windows-smoke-checklist-report.json",
            steps=(
                MouseDemoStep(
                    "cursor-readback-check",
                    "cursor_readback",
                    {"smoke_check": {"check_id": "cursor_readback"}},
                ),
            ),
        )

    monkeypatch.setattr(
        "desktop_agent.cli.run_windows_smoke_checklist",
        fake_run_windows_smoke_checklist,
    )

    status = main(
        [
            "windows-smoke-checklist",
            "--trace-root",
            str(tmp_path),
            "--random-seed",
            "21",
            "--movement-smoothness",
            "0.6",
            "--countdown-seconds",
            "0",
            "--keyboard-text",
            "smoke",
        ]
    )

    output = capsys.readouterr().out
    assert status == 0
    assert "status: passed" in output
    assert "checklist:" in output
    assert "check cursor_readback: cursor_readback" in output


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


class EmptyOcrProvider:
    def extract_text(self, screenshot_path: Path) -> tuple[OcrTextBlock, ...]:
        _ = screenshot_path
        return ()


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


class AmbiguousUiaAdapter:
    def tree_snapshot(self) -> dict[str, object]:
        return {"active_window": {"title": "DeskPilot Fixture"}, "elements": []}

    def candidates(self) -> tuple[ElementCandidate, ...]:
        return (
            ElementCandidate(
                id="uia-submit-1",
                source="uia",
                label="Submit",
                bounds=Bounds(x=10, y=20, width=90, height=28),
                confidence=0.95,
            ),
            ElementCandidate(
                id="uia-submit-2",
                source="uia",
                label="Submit",
                bounds=Bounds(x=180, y=20, width=90, height=28),
                confidence=0.94,
            ),
        )


class FixtureUiaPerceptionEngine:
    def detect(
        self,
        step: TaskStep,
        observation: ScreenObservation,
        config: RuntimeConfig,
    ) -> tuple[ElementCandidate, ...]:
        _ = step, observation, config
        return (
            ElementCandidate(
                id="uia-submit",
                source="uia",
                label="Submit",
                bounds=Bounds(x=10, y=20, width=90, height=28),
                confidence=0.95,
            ),
        )


class EmptyPerceptionEngine:
    def detect(
        self,
        step: TaskStep,
        observation: ScreenObservation,
        config: RuntimeConfig,
    ) -> tuple[ElementCandidate, ...]:
        _ = step, observation, config
        return ()


class FixtureOcrPerceptionEngine:
    def detect(
        self,
        step: TaskStep,
        observation: ScreenObservation,
        config: RuntimeConfig,
    ) -> tuple[ElementCandidate, ...]:
        _ = step, observation, config
        return (
            ElementCandidate(
                id="ocr-submit",
                source="ocr",
                label="Submit",
                bounds=Bounds(x=120, y=20, width=90, height=28),
                confidence=0.91,
            ),
        )


def test_real_mode_perception_includes_uia_source(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "desktop_agent.cli.WindowsUiaPerceptionEngine",
        FixtureUiaPerceptionEngine,
    )
    monkeypatch.setattr("desktop_agent.cli.OcrPerceptionEngine", EmptyPerceptionEngine)
    monkeypatch.setattr(
        "desktop_agent.cli.OpenCvTemplatePerceptionEngine",
        EmptyPerceptionEngine,
    )

    candidates = _perception_engine_for_mode(False).detect(
        TaskStep(id="click-submit", action="click_text", target="Submit"),
        ScreenObservation(),
        RuntimeConfig(confidence_threshold=0.8),
    )

    assert [candidate.source for candidate in candidates] == ["uia"]


def test_real_mode_perception_keeps_ocr_fallback_when_uia_empty(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "desktop_agent.cli.WindowsUiaPerceptionEngine",
        EmptyPerceptionEngine,
    )
    monkeypatch.setattr(
        "desktop_agent.cli.OcrPerceptionEngine",
        FixtureOcrPerceptionEngine,
    )
    monkeypatch.setattr(
        "desktop_agent.cli.OpenCvTemplatePerceptionEngine",
        EmptyPerceptionEngine,
    )

    candidates = _perception_engine_for_mode(False).detect(
        TaskStep(id="click-submit", action="click_text", target="Submit"),
        ScreenObservation(),
        RuntimeConfig(confidence_threshold=0.8),
    )

    assert [candidate.source for candidate in candidates] == ["ocr"]


def test_real_windows_mode_uses_live_screen_observer(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr("desktop_agent.cli.sys.platform", "win32")

    observer = _screen_observer_for_mode(False, object())

    assert isinstance(observer, MssScreenObserver)


def test_dry_run_mode_keeps_static_screen_observer(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr("desktop_agent.cli.sys.platform", "win32")

    observer = _screen_observer_for_mode(True, object())

    assert isinstance(observer, StaticScreenObserver)


def test_dry_run_actuator_keeps_static_screen_observer_on_windows(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr("desktop_agent.cli.sys.platform", "win32")

    observer = _screen_observer_for_mode(False, DryRunActuator())

    assert isinstance(observer, StaticScreenObserver)


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


def test_cli_calibrate_target_writes_selected_report(
    tmp_path: Path,
    capsys: CaptureFixture[str],
    monkeypatch: MonkeyPatch,
) -> None:
    task_path = tmp_path / "task.yaml"
    output_dir = tmp_path / "calibration"
    write_task(task_path)
    monkeypatch.setattr("desktop_agent.cli.MssScreenObserver", FixtureScreenObserver)
    monkeypatch.setattr("desktop_agent.cli.TesseractOcrProvider", FixtureOcrProvider)
    monkeypatch.setattr("desktop_agent.cli.WindowsUiaAdapter", FixtureUiaAdapter)

    status = main(
        [
            "calibrate-target",
            str(task_path),
            "--output",
            str(output_dir),
            "--allowed-window",
            "DeskPilot Fixture",
        ],
    )

    output = capsys.readouterr().out
    report = json.loads((output_dir / "target-calibration.json").read_text())
    assert status == 0
    assert report["status"] == "selected"
    assert report["selected_candidate_id"] == "uia-submit"
    assert report["ui_state_snapshot"]["selected_candidate"]["id"] == "uia-submit"
    assert "selected: uia-submit" in output


def test_cli_calibrate_target_writes_rejected_report(
    tmp_path: Path,
    capsys: CaptureFixture[str],
    monkeypatch: MonkeyPatch,
) -> None:
    task_path = tmp_path / "task.yaml"
    output_dir = tmp_path / "calibration"
    write_task(task_path)
    monkeypatch.setattr("desktop_agent.cli.MssScreenObserver", FixtureScreenObserver)
    monkeypatch.setattr("desktop_agent.cli.TesseractOcrProvider", EmptyOcrProvider)
    monkeypatch.setattr("desktop_agent.cli.WindowsUiaAdapter", AmbiguousUiaAdapter)

    status = main(
        [
            "calibrate-target",
            str(task_path),
            "--output",
            str(output_dir),
            "--confidence-threshold",
            "0.8",
        ],
    )

    output = capsys.readouterr().out
    report = json.loads((output_dir / "target-calibration.json").read_text())
    assert status == 1
    assert report["status"] == "rejected"
    assert report["rejection_reason"] == "confidence_or_ambiguity_gate"
    assert "reason: confidence_or_ambiguity_gate" in output


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


def test_cli_replay_points_to_proof_replay_for_manifest_trace(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    trace_dir = tmp_path / "trace"
    trace_dir.mkdir()
    (trace_dir / "proof-manifest.json").write_text("{}", encoding="utf-8")

    status = main(["replay", str(trace_dir)])

    output = capsys.readouterr().out
    assert status == 1
    assert f"hint: use desktop-agent proof replay {trace_dir}" in output


def test_cli_proof_replay_summarizes_manifest_and_artifacts(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    trace_dir = tmp_path / "trace"
    manifest = write_proof_manifest(trace_dir)

    status = main(["proof", "replay", str(trace_dir)])

    output = capsys.readouterr().out
    assert status == 0
    assert "proof: linkedin-demo" in output
    assert "command: desktop-agent demo-linkedin --trace-root traces" in output
    assert "status: passed" in output
    assert "started_at: 2026-05-16T00:00:00+00:00" in output
    assert f"artifact report_path: {manifest['report_path']}" in output
    assert f"artifact screenshot_1: {manifest['screenshot_path']}" in output


def test_cli_proof_replay_opens_existing_artifacts_when_requested(
    tmp_path: Path,
    capsys: CaptureFixture[str],
    monkeypatch: MonkeyPatch,
) -> None:
    trace_dir = tmp_path / "trace"
    manifest = write_proof_manifest(trace_dir)
    opened: list[Path] = []
    monkeypatch.setattr("desktop_agent.cli._open_path", opened.append)

    status = main(["proof", "replay", str(trace_dir), "--open-artifacts"])

    output = capsys.readouterr().out
    assert status == 0
    assert manifest["trace_dir"] in opened
    assert manifest["report_path"] in opened
    assert manifest["action_log_path"] in opened
    assert manifest["proof_manifest_path"] in opened
    assert manifest["screenshot_path"] in opened
    assert manifest["video_path"] not in opened
    assert f"artifact video_path: {manifest['video_path']} (missing)" in output
    assert f"opened artifact: {trace_dir}" in output


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
    assert report["summary"]["success_rate"] == 1.0
    assert report["summary"]["step_count"] > 0
    assert report["summary"]["action_count"] > 0
    assert report["acceptance"]["configured"] is False
    assert report["acceptance"]["status"] == "not_configured"
    assert report["baseline_comparison"]["safety_not_reduced"] is True
    assert (output_dir / "variance-report.json").exists()
    assert (output_dir / "baseline-runs.jsonl").exists()
    assert (output_dir / "baseline-comparison.json").exists()
    assert (output_dir / "pointer-timing-comparison.json").exists()
    assert len(metrics) == 2
    assert "metrics:" in output
    assert "baseline metrics:" in output
    assert "variance:" in output
    assert "baseline comparison:" in output
    assert "baseline status:" in output
    assert "pointer timing:" in output
    assert "acceptance: not_configured" in output
    assert "report:" in output
