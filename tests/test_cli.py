import json
import zipfile
from pathlib import Path

from pytest import CaptureFixture, MonkeyPatch

from desktop_agent.actuation import ActuationProfile, DryRunActuator
from desktop_agent.cli import (
    _benchmark_exit_code,
    _benchmark_monitoring_failures,
    _benchmark_monitoring_status,
    _perception_engine_for_mode,
    _screen_observer_for_mode,
    main,
)
from desktop_agent.config import RuntimeConfig
from desktop_agent.goal_planning import (
    GoalModelRanking,
    GoalPlan,
    GoalPlanCandidate,
)
from desktop_agent.goal_reporting import write_goal_plan_trace
from desktop_agent.local_models import LocalModelInfo, LocalModelStatus
from desktop_agent.ocr import OcrTextBlock
from desktop_agent.perception import DryRunPerceptionEngine, ElementCandidate
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
                "    checkpoint:",
                "      type: visible_text",
                "      text: Submit",
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


def test_cli_dry_run_accepts_activity_profile(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    task_path = tmp_path / "task.yaml"
    write_task(task_path)

    status = main(
        [
            "dry-run",
            str(task_path),
            "--allowed-window",
            "DeskPilot Fixture",
            "--activity-profile",
            "focused",
        ],
    )

    output = capsys.readouterr().out
    assert status == 0
    assert "execution profile: focused (persona normal)" in output
    assert "timing: action 0.080-0.250s" in output


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
    assert "safety: local_mutation; mutation local; mutates state yes" in output
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


def test_cli_local_model_status_reports_disabled_default(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    output_path = tmp_path / "local-model-status.json"

    status = main(["local-model", "status", "--output", str(output_path)])

    output = capsys.readouterr().out
    assert status == 0
    assert "status: disabled" in output
    assert "available: False" in output
    assert "report:" in output
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert report["status"] == "disabled"
    assert report["model_count"] == 0


def test_cli_local_model_list_probes_and_prints_models(
    monkeypatch: MonkeyPatch,
    capsys: CaptureFixture[str],
) -> None:
    class FakeOllamaProvider:
        def __init__(self, config: object) -> None:
            self.config = config

        def status(self, *, probe_when_disabled: bool = False) -> LocalModelStatus:
            assert probe_when_disabled is True
            return LocalModelStatus(
                enabled=False,
                provider="ollama",
                endpoint="http://127.0.0.1:11434",
                status="available",
                available=True,
                models=(LocalModelInfo(name="llama3.2:latest"),),
            )

    monkeypatch.setattr(
        "desktop_agent.cli.OllamaLocalModelProvider",
        FakeOllamaProvider,
    )

    status = main(["local-model", "list"])

    output = capsys.readouterr().out
    assert status == 0
    assert output == "llama3.2:latest\n"


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
    monkeypatch.setattr(
        "desktop_agent.cli._perception_engine_for_mode",
        lambda _dry_run: DryRunPerceptionEngine(),
    )

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
    monkeypatch.setattr(
        "desktop_agent.cli._perception_engine_for_mode",
        lambda _dry_run: DryRunPerceptionEngine(),
    )

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
        record_video: bool,
        video_fps: int,
        ffmpeg_path: str,
    ) -> MouseDemoReport:
        assert trace_root == tmp_path
        assert random_seed == 7
        assert movement_smoothness == 0.5
        assert keyboard_text == "typed by test"
        assert countdown_seconds == 0
        assert record_video is True
        assert video_fps == 24
        assert ffmpeg_path == "ffmpeg-test"
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
            "--record-video",
            "--video-fps",
            "24",
            "--ffmpeg-path",
            "ffmpeg-test",
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
        record_video: bool,
        video_fps: int,
        ffmpeg_path: str,
    ) -> MouseDemoReport:
        _ = trace_root, random_seed, movement_smoothness, keyboard_text
        assert countdown_seconds == 0
        assert record_video is False
        assert video_fps == 15
        assert ffmpeg_path == "ffmpeg"
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


def test_cli_video_policy_disabled_blocks_record_video(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    from desktop_agent.mouse_demo import MouseDemoReport

    def fake_run_input_demo(
        *,
        trace_root: Path,
        random_seed: int,
        movement_smoothness: float,
        keyboard_text: str,
        countdown_seconds: float,
        record_video: bool,
        video_fps: int,
        ffmpeg_path: str,
    ) -> MouseDemoReport:
        _ = (
            trace_root,
            random_seed,
            movement_smoothness,
            keyboard_text,
            countdown_seconds,
            video_fps,
            ffmpeg_path,
        )
        assert record_video is False
        return MouseDemoReport(
            status="passed",
            trace_dir=tmp_path / "trace",
            report_path=tmp_path / "trace" / "input-demo-report.json",
            steps=(),
        )

    monkeypatch.setattr("desktop_agent.cli.run_input_demo", fake_run_input_demo)

    status = main(
        [
            "demo-input",
            "--trace-root",
            str(tmp_path),
            "--countdown-seconds",
            "0",
            "--record-video",
            "--video-policy",
            "disabled",
        ],
    )

    assert status == 0


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
        record_video: bool,
        video_fps: int,
        ffmpeg_path: str,
    ) -> MouseDemoReport:
        assert trace_root == tmp_path
        assert random_seed == 13
        assert movement_smoothness == 0.4
        assert countdown_seconds == 0
        assert url == "https://www.linkedin.com/"
        assert find_text == "LinkedIn"
        assert page_load_seconds == 0
        assert record_video is False
        assert video_fps == 15
        assert ffmpeg_path == "ffmpeg"
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


def test_cli_proof_browser_fixture_prints_trace_report(
    tmp_path: Path,
    capsys: CaptureFixture[str],
    monkeypatch: MonkeyPatch,
) -> None:
    from desktop_agent.mouse_demo import MouseDemoReport, MouseDemoStep

    def fake_run_browser_fixture(
        *,
        trace_root: Path,
        random_seed: int,
        movement_smoothness: float,
        countdown_seconds: float,
        fixture_text: str,
        result_text: str,
        page_load_seconds: float,
        record_video: bool,
        video_fps: int,
        ffmpeg_path: str,
    ) -> MouseDemoReport:
        assert trace_root == tmp_path
        assert random_seed == 34
        assert movement_smoothness == 0.7
        assert countdown_seconds == 0
        assert fixture_text == "typed fixture"
        assert result_text == "fixture submitted"
        assert page_load_seconds == 0
        assert record_video is False
        assert video_fps == 15
        assert ffmpeg_path == "ffmpeg"
        return MouseDemoReport(
            status="passed",
            trace_dir=tmp_path / "trace",
            report_path=tmp_path / "trace" / "browser-fixture-report.json",
            proof_manifest_path=tmp_path / "trace" / "proof-manifest.json",
            steps=(
                MouseDemoStep(
                    "focus-browser-fixture-input",
                    "click",
                    {
                        "movement_points": 8,
                        "movement_duration_seconds": 0.25,
                    },
                ),
            ),
        )

    monkeypatch.setattr(
        "desktop_agent.cli.run_browser_fixture",
        fake_run_browser_fixture,
    )

    status = main(
        [
            "proof",
            "browser-fixture",
            "--trace-root",
            str(tmp_path),
            "--random-seed",
            "34",
            "--movement-smoothness",
            "0.7",
            "--countdown-seconds",
            "0",
            "--fixture-text",
            "typed fixture",
            "--result-text",
            "fixture submitted",
            "--page-load-seconds",
            "0",
        ]
    )

    output = capsys.readouterr().out
    assert status == 0
    assert "status: passed" in output
    assert f"manifest: {tmp_path / 'trace' / 'proof-manifest.json'}" in output
    assert "step focus-browser-fixture-input: click (8 points, 0.250s)" in output


def test_cli_proof_native_fixture_prints_trace_report(
    tmp_path: Path,
    capsys: CaptureFixture[str],
    monkeypatch: MonkeyPatch,
) -> None:
    from desktop_agent.mouse_demo import MouseDemoReport, MouseDemoStep

    def fake_run_native_fixture(
        *,
        trace_root: Path,
        random_seed: int,
        movement_smoothness: float,
        countdown_seconds: float,
        initial_text: str,
        replacement_text: str,
        record_video: bool,
        video_fps: int,
        ffmpeg_path: str,
    ) -> MouseDemoReport:
        assert trace_root == tmp_path
        assert random_seed == 55
        assert movement_smoothness == 0.8
        assert countdown_seconds == 0
        assert initial_text == "first"
        assert replacement_text == "second"
        assert record_video is False
        assert video_fps == 15
        assert ffmpeg_path == "ffmpeg"
        return MouseDemoReport(
            status="passed",
            trace_dir=tmp_path / "trace",
            report_path=tmp_path / "trace" / "native-fixture-report.json",
            proof_manifest_path=tmp_path / "trace" / "proof-manifest.json",
            steps=(
                MouseDemoStep(
                    "replace-native-fixture-text",
                    "type_text",
                    {},
                ),
            ),
        )

    monkeypatch.setattr(
        "desktop_agent.cli.run_native_fixture",
        fake_run_native_fixture,
    )

    status = main(
        [
            "proof",
            "native-fixture",
            "--trace-root",
            str(tmp_path),
            "--random-seed",
            "55",
            "--movement-smoothness",
            "0.8",
            "--countdown-seconds",
            "0",
            "--initial-text",
            "first",
            "--replacement-text",
            "second",
        ]
    )

    output = capsys.readouterr().out
    assert status == 0
    assert "status: passed" in output
    assert f"manifest: {tmp_path / 'trace' / 'proof-manifest.json'}" in output
    assert "step replace-native-fixture-text: type_text" in output


def test_cli_proof_mixed_fixture_prints_trace_report(
    tmp_path: Path,
    capsys: CaptureFixture[str],
    monkeypatch: MonkeyPatch,
) -> None:
    from desktop_agent.mouse_demo import MouseDemoReport, MouseDemoStep

    def fake_run_mixed_fixture(
        *,
        trace_root: Path,
        random_seed: int,
        movement_smoothness: float,
        countdown_seconds: float,
        native_text: str,
        browser_find_text: str,
        page_load_seconds: float,
        record_video: bool,
        video_fps: int,
        ffmpeg_path: str,
    ) -> MouseDemoReport:
        assert trace_root == tmp_path
        assert random_seed == 89
        assert movement_smoothness == 0.9
        assert countdown_seconds == 0
        assert native_text == "handoff"
        assert browser_find_text == "browser marker"
        assert page_load_seconds == 0
        assert record_video is False
        assert video_fps == 15
        assert ffmpeg_path == "ffmpeg"
        return MouseDemoReport(
            status="passed",
            trace_dir=tmp_path / "trace",
            report_path=tmp_path / "trace" / "mixed-fixture-report.json",
            proof_manifest_path=tmp_path / "trace" / "proof-manifest.json",
            steps=(
                MouseDemoStep(
                    "switch-back-to-browser",
                    "press_chord",
                    {},
                ),
            ),
        )

    monkeypatch.setattr(
        "desktop_agent.cli.run_mixed_fixture",
        fake_run_mixed_fixture,
    )

    status = main(
        [
            "proof",
            "mixed-fixture",
            "--trace-root",
            str(tmp_path),
            "--random-seed",
            "89",
            "--movement-smoothness",
            "0.9",
            "--countdown-seconds",
            "0",
            "--native-text",
            "handoff",
            "--browser-find-text",
            "browser marker",
            "--page-load-seconds",
            "0",
        ]
    )

    output = capsys.readouterr().out
    assert status == 0
    assert "status: passed" in output
    assert f"manifest: {tmp_path / 'trace' / 'proof-manifest.json'}" in output
    assert "step switch-back-to-browser: press_chord" in output


def test_cli_proof_recovery_fixture_prints_recovery_summary(
    tmp_path: Path,
    capsys: CaptureFixture[str],
    monkeypatch: MonkeyPatch,
) -> None:
    from desktop_agent.mouse_demo import MouseDemoReport, MouseDemoStep

    def fake_run_recovery_fixture(
        *,
        trace_root: Path,
        random_seed: int,
        movement_smoothness: float,
        countdown_seconds: float,
        page_load_seconds: float,
        ready_delay_seconds: float,
        recovery_wait_seconds: float,
        result_text: str,
        record_video: bool,
        video_fps: int,
        ffmpeg_path: str,
    ) -> MouseDemoReport:
        assert trace_root == tmp_path
        assert random_seed == 144
        assert movement_smoothness == 0.65
        assert countdown_seconds == 0
        assert page_load_seconds == 0
        assert ready_delay_seconds == 0.5
        assert recovery_wait_seconds == 0.75
        assert result_text == "clicked"
        assert record_video is False
        assert video_fps == 15
        assert ffmpeg_path == "ffmpeg"
        return MouseDemoReport(
            status="passed",
            trace_dir=tmp_path / "trace",
            report_path=tmp_path / "trace" / "recovery-fixture-report.json",
            proof_manifest_path=tmp_path / "trace" / "proof-manifest.json",
            steps=(
                MouseDemoStep(
                    "retry-recovery-target",
                    "click",
                    {
                        "recovery": {
                            "reason": "disabled_control",
                            "action": "retry_after_wait",
                        },
                    },
                ),
            ),
        )

    monkeypatch.setattr(
        "desktop_agent.cli.run_recovery_fixture",
        fake_run_recovery_fixture,
    )

    status = main(
        [
            "proof",
            "recovery-fixture",
            "--trace-root",
            str(tmp_path),
            "--random-seed",
            "144",
            "--movement-smoothness",
            "0.65",
            "--countdown-seconds",
            "0",
            "--page-load-seconds",
            "0",
            "--ready-delay-seconds",
            "0.5",
            "--recovery-wait-seconds",
            "0.75",
            "--result-text",
            "clicked",
        ]
    )

    output = capsys.readouterr().out
    assert status == 0
    assert "status: passed" in output
    assert f"manifest: {tmp_path / 'trace' / 'proof-manifest.json'}" in output
    assert (
        "recovery retry-recovery-target: disabled_control (retry_after_wait)"
        in output
    )


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
        record_video: bool,
        video_fps: int,
        ffmpeg_path: str,
    ) -> MouseDemoReport:
        assert trace_root == tmp_path
        assert random_seed == 21
        assert movement_smoothness == 0.6
        assert countdown_seconds == 0
        assert keyboard_text == "smoke"
        assert edge_url == "about:blank"
        assert record_video is False
        assert video_fps == 15
        assert ffmpeg_path == "ffmpeg"
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
    caption_output = output_dir / "screen-caption-review.json"
    monkeypatch.setattr("desktop_agent.cli.MssScreenObserver", FixtureScreenObserver)
    monkeypatch.setattr("desktop_agent.cli.TesseractOcrProvider", FixtureOcrProvider)
    monkeypatch.setattr("desktop_agent.cli.WindowsUiaAdapter", FixtureUiaAdapter)

    status = main(
        [
            "inspect-screen",
            "--output",
            str(output_dir),
            "--caption-output",
            str(caption_output),
        ],
    )

    output = capsys.readouterr().out
    report = json.loads((output_dir / "inspect-screen.json").read_text())
    caption = json.loads(caption_output.read_text(encoding="utf-8"))
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
    assert caption["review_only"] is True
    assert caption["direct_action_allowed"] is False
    assert caption["prompt"]["prompt_class"] == "screen_summary"
    assert "status: passed" in output
    assert "caption report:" in output


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


def test_cli_trace_health_summarizes_trace_counts(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    trace_root = tmp_path / "traces"
    run_trace = trace_root / "20260516T000000Z-run"
    proof_trace = trace_root / "20260516T010000Z-proof"
    run_trace.mkdir(parents=True)
    proof_trace.mkdir()
    (run_trace / "final-report.json").write_text(
        json.dumps({"status": "failed"}),
        encoding="utf-8",
    )
    replay_summary_path = run_trace / "replay-summary.md"
    replay_summary_path.write_text("# Replay Summary\n", encoding="utf-8")
    (proof_trace / "proof-finalization-status.json").write_text(
        json.dumps({"status": "passed"}),
        encoding="utf-8",
    )

    status = main(["trace-health", "--trace-root", str(trace_root)])

    output = capsys.readouterr().out
    assert status == 0
    assert f"trace_root: {trace_root}" in output
    assert "health_status: attention" in output
    assert "trace_count: 2" in output
    assert "- proof_suite: 1" in output
    assert "- run: 1" in output
    assert "- passed: 1" in output
    assert "- failed: 1" in output
    assert "attention_statuses: failed" in output
    assert f"- {run_trace} (run/failed)" in output
    assert f"summary {replay_summary_path}" in output


def test_cli_trace_health_writes_json(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    trace_root = tmp_path / "traces"
    trace_dir = trace_root / "20260516T000000Z-goal"
    trace_dir.mkdir(parents=True)
    (trace_dir / "goal-plan-report.json").write_text(
        json.dumps({"status": "ready"}),
        encoding="utf-8",
    )

    status = main(["trace-health", "--trace-root", str(trace_root), "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert status == 0
    assert payload["trace_count"] == 1
    assert payload["by_kind"] == {"goal_plan": 1}
    assert payload["by_status"] == {"ready": 1}
    assert payload["health_status"] == "ok"
    assert payload["attention_traces"] == []


def test_cli_trace_health_writes_report_file(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    trace_root = tmp_path / "traces"
    trace_dir = trace_root / "20260516T000000Z-run"
    trace_dir.mkdir(parents=True)
    (trace_dir / "final-report.json").write_text(
        json.dumps({"status": "passed"}),
        encoding="utf-8",
    )
    output_path = tmp_path / "reports" / "trace-health.json"

    status = main(
        [
            "trace-health",
            "--trace-root",
            str(trace_root),
            "--output",
            str(output_path),
        ],
    )

    output = capsys.readouterr().out
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert status == 0
    assert f"report: {output_path}" in output
    assert payload["trace_count"] == 1
    assert payload["by_kind"] == {"run": 1}
    assert payload["by_status"] == {"passed": 1}
    assert payload["health_status"] == "ok"


def test_cli_trace_health_writes_markdown_summary(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    trace_root = tmp_path / "traces"
    trace_dir = trace_root / "20260516T000000Z-run"
    trace_dir.mkdir(parents=True)
    (trace_dir / "final-report.json").write_text(
        json.dumps({"status": "failed"}),
        encoding="utf-8",
    )
    replay_summary_path = trace_dir / "replay-summary.md"
    replay_summary_path.write_text("# Replay Summary\n", encoding="utf-8")
    output_path = tmp_path / "reports" / "trace-health.md"

    status = main(
        [
            "trace-health",
            "--trace-root",
            str(trace_root),
            "--markdown-output",
            str(output_path),
        ],
    )

    output = capsys.readouterr().out
    summary = output_path.read_text(encoding="utf-8")
    assert status == 0
    assert f"summary: {output_path}" in output
    assert "# Trace Health" in summary
    assert "- Health status: `attention`" in summary
    assert f"`{trace_dir}`" in summary
    assert f"summary `{replay_summary_path}`" in summary


def test_cli_trace_health_json_output_stays_parseable_with_report_file(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    trace_root = tmp_path / "traces"
    trace_dir = trace_root / "20260516T000000Z-run"
    trace_dir.mkdir(parents=True)
    (trace_dir / "final-report.json").write_text(
        json.dumps({"status": "passed"}),
        encoding="utf-8",
    )
    output_path = tmp_path / "reports" / "trace-health.json"
    summary_path = tmp_path / "reports" / "trace-health.md"

    status = main(
        [
            "trace-health",
            "--trace-root",
            str(trace_root),
            "--json",
            "--output",
            str(output_path),
            "--markdown-output",
            str(summary_path),
        ],
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert status == 0
    assert f"report: {output_path}" in captured.err
    assert f"summary: {summary_path}" in captured.err
    assert payload["trace_count"] == 1
    assert output_path.exists()
    assert summary_path.exists()


def test_cli_trace_health_can_fail_on_attention(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    trace_root = tmp_path / "traces"
    trace_dir = trace_root / "20260516T000000Z-run"
    trace_dir.mkdir(parents=True)
    (trace_dir / "final-report.json").write_text(
        json.dumps({"status": "failed"}),
        encoding="utf-8",
    )

    status = main(
        ["trace-health", "--trace-root", str(trace_root), "--fail-on-attention"],
    )

    output = capsys.readouterr().out
    assert status == 1
    assert "health_status: attention" in output


def test_cli_replay_summarizes_goal_plan_trace(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    plan = GoalPlan(
        user_goal="Search the web",
        normalized_intent="browser search",
        candidate_routines=(
            GoalPlanCandidate(
                routine_id="browser.search-web",
                routine_name="Browser web search",
                score=10,
                matched_fields=("tags", "outputs"),
                safety_class="low",
                approval_policy="none",
            ),
        ),
        selected_routine_id="browser.search-web",
        expected_evidence=("search results",),
        abort_conditions=("browser signed out",),
        explanation="The browser search routine matches the goal.",
        execution_status="ready",
        model_ranking=GoalModelRanking(
            provider="ollama",
            model="llama3.1",
            enabled=True,
            attempted=True,
            status="applied",
            selected_routine_id="browser.search-web",
            candidate_order=("browser.search-web",),
            output_hash="abc123",
            affected_selection=False,
        ),
    )
    trace_dir = write_goal_plan_trace(plan, tmp_path / "traces")

    status = main(["replay", str(trace_dir), "--write-summary"])

    output = capsys.readouterr().out
    summary_path = trace_dir / "replay-summary.md"
    summary = summary_path.read_text(encoding="utf-8")
    assert status == 0
    assert f"trace: {trace_dir}" in output
    assert "goal plan: Search the web" in output
    assert "status: ready" in output
    assert "selected: browser.search-web" in output
    assert (
        "candidate: browser.search-web score=10 matched=tags, outputs "
        "safety=low approval=none"
        in output
    )
    assert "expected_evidence: search results" in output
    assert "abort_conditions: browser signed out" in output
    assert (
        "- goal_plan: goal plan ready [selected browser.search-web candidates 1 "
        "expected_evidence 1 abort_conditions 1]"
        in output
    )
    assert (
        "- model_assistance: model assistance applied "
        "[model ollama/llama3.1 status applied affected_selection False]"
        in output
    )
    assert f"summary: {summary_path}" in output
    assert "# DeskPilot Goal Plan Replay Summary" in summary
    assert "- Desktop input required: `False`" in summary
    assert "- Expected evidence: `search results`" in summary
    assert "- Abort conditions: `browser signed out`" in summary
    assert (
        "`browser.search-web` score `10` matched `tags, outputs` safety `low` "
        "approval `none`"
    ) in summary


def test_cli_replay_summarizes_proof_suite_finalization(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    trace_dir = tmp_path / "proof-suite"
    trace_dir.mkdir()
    status_path = trace_dir / "proof-finalization-status.json"
    status_path.write_text(
        json.dumps(
            {
                "status": "passed",
                "gates": {
                    "suite_validation": "passed",
                    "promotion_verification": "passed",
                    "archive_verification": "passed",
                },
                "artifacts": {
                    "promotion": str(trace_dir / "proof-suite-promotion.json"),
                },
                "errors": [],
            },
        ),
        encoding="utf-8",
    )

    status = main(["replay", str(trace_dir), "--write-summary"])

    output = capsys.readouterr().out
    summary_path = trace_dir / "replay-summary.md"
    summary = summary_path.read_text(encoding="utf-8")
    assert status == 0
    assert f"trace: {trace_dir}" in output
    assert "proof suite: finalization" in output
    assert "status: passed" in output
    assert "- suite_validation: passed" in output
    assert f"summary: {summary_path}" in output
    assert "# DeskPilot Proof Suite Replay Summary" in summary
    assert "- `promotion`: `" in summary


def test_cli_replay_summarizes_benchmark_report(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    trace_dir = tmp_path / "benchmark"
    trace_dir.mkdir()
    (trace_dir / "benchmark-report.json").write_text(
        json.dumps(
            {
                "task_path": "tasks/demo.yaml",
                "trace_health_path": str(trace_dir / "trace-health.json"),
                "iterations": 1,
                "summary": {
                    "success_rate": 1.0,
                    "grounding_accuracy": 1.0,
                    "ambiguity_rate": 0.0,
                    "recovery_rate": 0.0,
                    "operator_intervention_rate": 0.0,
                },
                "acceptance": {"status": "passed"},
                "baseline_comparison": {"status": "neutral"},
                "observability_contract": {
                    "configured": True,
                    "benchmark_task_id": "demo",
                    "pipeline_modes": ["dry-run", "replay"],
                    "deep_search_sources": ["trace_events", "final_report"],
                    "required_trace_phases": ["observe_screen"],
                    "required_report_fields": ["status"],
                    "required_metrics": ["success_rate"],
                },
                "monitoring_coverage": {
                    "configured": True,
                    "passed": True,
                    "observed_trace_phases": ["observe_screen"],
                    "missing_trace_phases": [],
                    "observed_report_fields": ["status"],
                    "missing_report_fields": [],
                },
                "runs": [
                    {
                        "iteration": 1,
                        "status": "passed",
                        "trace_dir": str(trace_dir / "traces" / "run-1"),
                        "task_time_seconds": 0.25,
                        "step_count": 2,
                        "action_count": 1,
                    },
                ],
            },
        ),
        encoding="utf-8",
    )

    status = main(["replay", str(trace_dir), "--write-summary"])

    output = capsys.readouterr().out
    summary_path = trace_dir / "replay-summary.md"
    summary = summary_path.read_text(encoding="utf-8")
    assert status == 0
    assert f"trace: {trace_dir}" in output
    assert "benchmark: tasks/demo.yaml" in output
    assert "status: passed" in output
    assert "baseline: neutral" in output
    assert "monitoring coverage: passed" in output
    assert "pipeline_modes: dry-run, replay" in output
    assert "deep_search_sources: trace_events, final_report" in output
    assert "observed_trace_phases: observe_screen" in output
    assert "missing_trace_phases: none" in output
    assert "run 1: passed" in output
    assert f"summary: {summary_path}" in output
    assert "# DeskPilot Benchmark Replay Summary" in summary
    assert "- Pipeline modes: `dry-run, replay`" in summary
    assert "- Deep-search sources: `trace_events, final_report`" in summary
    assert "- Monitoring coverage: `passed`" in summary
    assert "- Observed trace phases: `observe_screen`" in summary
    assert "- Missing trace phases: `none`" in summary
    assert "run 1: passed" in summary


def test_cli_analyze_failed_run_writes_review_artifacts(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    trace_dir = tmp_path / "trace"
    trace_dir.mkdir()
    (trace_dir / "final-report.json").write_text(
        json.dumps(
            {
                "task_name": "Browser search",
                "status": "failed",
                "steps": [
                    {
                        "step_id": "click-submit",
                        "status": "failed",
                        "metadata": {"failure_category": "selection_ambiguity"},
                    },
                ],
            },
        ),
        encoding="utf-8",
    )

    status = main(["analyze-failed-run", str(trace_dir)])

    output = capsys.readouterr().out
    analysis = json.loads((trace_dir / "failed-run-analysis.json").read_text())
    assert status == 0
    assert "proposals: 1" in output
    assert "diagnostic ready: false" in output
    assert analysis["proposals"][0]["review_required"] is True
    assert analysis["proposals"][0]["applies_automatically"] is False
    assert (trace_dir / "failed-run-analysis.md").exists()


def test_cli_replay_prints_step_timeline(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    trace_dir = tmp_path / "trace"
    trace_dir.mkdir()
    (trace_dir / "final-report.json").write_text(
        json.dumps(
            {
                "status": "passed",
                "steps": [
                    {
                        "step_id": "click-submit",
                        "action": "click_text",
                        "status": "passed",
                        "attempts": 1,
                    },
                ],
                "events": [
                    {
                        "phase": "observe_screen",
                        "message": "screen observed",
                        "metadata": {
                            "step_id": "click-submit",
                            "observation_role": "pre_action",
                        },
                    },
                    {
                        "phase": "select_target",
                        "message": "target selected",
                        "metadata": {
                            "step_id": "click-submit",
                            "candidate_id": "candidate-submit",
                        },
                    },
                    {
                        "phase": "verify_result",
                        "message": "verified",
                        "metadata": {
                            "step_id": "click-submit",
                            "verification_outcome": "passed",
                        },
                    },
                ],
            },
        ),
        encoding="utf-8",
    )

    status = main(["replay", str(trace_dir)])

    output = capsys.readouterr().out
    assert status == 0
    assert "timeline:" in output
    assert "- step click-submit (click_text) passed after 1 attempt(s)" in output
    assert "1. observe_screen: screen observed [observation pre_action]" in output
    assert "2. select_target: target selected [candidate candidate-submit]" in output
    assert "3. verify_result: verified [outcome passed]" in output


def test_cli_replay_writes_markdown_summary(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    trace_dir = tmp_path / "trace"
    trace_dir.mkdir()
    before = trace_dir / "screenshots" / "before.png"
    after = trace_dir / "screenshots" / "after.png"
    (trace_dir / "final-report.json").write_text(
        json.dumps(
            {
                "task_name": "fixture",
                "status": "passed",
                "steps": [
                    {
                        "step_id": "click-submit",
                        "action": "click_text",
                        "status": "passed",
                        "attempts": 1,
                        "metadata": {
                            "success_evidence": {
                                "success_evidence_type": "passed_action",
                                "action_message": "clicked",
                                "verification_outcome": "passed",
                                "post_action_evidence": {
                                    "screenshot_path": str(after),
                                    "active_window_title": (
                                        "DeskPilot Fixture - Done"
                                    ),
                                },
                                "state_delta": {
                                    "visible_text_added": ["Success"],
                                    "target_appeared": True,
                                },
                            },
                        },
                    },
                ],
                "events": [
                    {
                        "phase": "observe_screen",
                        "message": "screen observed",
                        "metadata": {
                            "step_id": "click-submit",
                            "pre_action_evidence": {
                                "screenshot_path": str(before),
                                "active_window_title": "DeskPilot Fixture",
                            },
                        },
                    },
                    {
                        "phase": "observe_after_action",
                        "message": "screen observed after action",
                        "metadata": {
                            "step_id": "click-submit",
                            "post_action_evidence": {
                                "screenshot_path": str(after),
                                "active_window_title": "DeskPilot Fixture - Done",
                            },
                        },
                    },
                    {
                        "phase": "state_delta",
                        "message": "visual state delta summarized",
                        "metadata": {
                            "step_id": "click-submit",
                            "visible_text_added": ["Success"],
                            "target_appeared": True,
                        },
                    },
                ],
            },
        ),
        encoding="utf-8",
    )

    status = main(["replay", str(trace_dir), "--write-summary"])

    output = capsys.readouterr().out
    summary_path = trace_dir / "replay-summary.md"
    summary = summary_path.read_text(encoding="utf-8")
    assert status == 0
    assert f"summary: {summary_path}" in output
    assert "# DeskPilot Replay Summary" in summary
    assert "- step click-submit (click_text) passed after 1 attempt(s)" in summary
    assert f"Screenshot: `{before}`" in summary
    assert f"Screenshot: `{after}`" in summary
    assert "Visible text added: `['Success']`" in summary
    assert "Target appeared: `True`" in summary
    assert "step `click-submit` `success_evidence`" in summary
    assert "Success evidence type: `passed_action`" in summary
    assert "Post active window: `DeskPilot Fixture - Done`" in summary


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


def test_cli_proof_validate_reports_bundle_errors(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    trace_dir = tmp_path / "trace"
    write_proof_manifest(trace_dir)

    status = main(["proof", "validate", str(trace_dir)])

    output = capsys.readouterr().out
    assert status == 1
    assert "validation: failed" in output
    assert "error: artifact video_path does not exist" in output
    assert "error: action_log_path is empty" in output


def test_cli_proof_preflight_reports_non_windows_failure(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    status = main(
        [
            "proof",
            "preflight",
            "--trace-root",
            str(tmp_path / "traces"),
            "--video-policy",
            "disabled",
        ],
    )

    output = capsys.readouterr().out
    assert status == 1
    assert "preflight: failed" in output
    assert "check windows-platform: failed" in output
    assert "check trace-root: passed" in output
    assert "check video-capture: warning" in output


def test_cli_proof_preflight_writes_report(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    report_path = tmp_path / "review" / "preflight.json"

    status = main(
        [
            "proof",
            "preflight",
            "--trace-root",
            str(tmp_path / "traces"),
            "--video-policy",
            "disabled",
            "--write-report",
            "--report-path",
            str(report_path),
        ],
    )

    output = capsys.readouterr().out
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert status == 1
    assert f"report: {report_path}" in output
    assert payload["status"] == "failed"
    assert payload["trace_root"] == str(tmp_path / "traces")


def test_cli_proof_validate_suite_reports_missing_bundles(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    trace_dir = tmp_path / "trace"
    write_proof_manifest(trace_dir)

    status = main(["proof", "validate-suite", str(tmp_path)])

    output = capsys.readouterr().out
    assert status == 1
    assert "suite: failed" in output
    assert (
        "expected: browser-fixture, native-fixture, mixed-fixture, recovery-fixture"
        in output
    )
    assert "error: missing proof bundle: browser-fixture" in output
    assert "error: missing proof bundle: native-fixture" in output


def test_cli_proof_validate_suite_can_require_preflight(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    trace_dir = tmp_path / "trace"
    write_proof_manifest(trace_dir)

    status = main(["proof", "validate-suite", str(tmp_path), "--require-preflight"])

    output = capsys.readouterr().out
    assert status == 1
    assert "suite: failed" in output
    assert "error: proof preflight report not found" in output


def test_cli_proof_validate_suite_can_require_review(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    trace_dir = tmp_path / "trace"
    write_proof_manifest(trace_dir)

    status = main(["proof", "validate-suite", str(tmp_path), "--require-review"])

    output = capsys.readouterr().out
    assert status == 1
    assert "suite: failed" in output
    assert "error: proof review status not found" in output


def test_cli_proof_validate_suite_writes_report(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    trace_dir = tmp_path / "trace"
    report_path = tmp_path / "review" / "suite.md"
    write_proof_manifest(trace_dir)

    status = main(
        [
            "proof",
            "validate-suite",
            str(tmp_path),
            "--write-report",
            "--report-path",
            str(report_path),
        ],
    )

    output = capsys.readouterr().out
    report = report_path.read_text(encoding="utf-8")
    assert status == 1
    assert f"report: {report_path}" in output
    assert "# DeskPilot Windows Proof Suite Report" in report
    assert "- Status: `failed`" in report


def test_cli_proof_validate_suite_writes_status_json(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    trace_dir = tmp_path / "trace"
    status_path = tmp_path / "monitoring" / "suite-status.json"
    write_proof_manifest(trace_dir)

    status = main(
        [
            "proof",
            "validate-suite",
            str(tmp_path),
            "--write-status-json",
            "--status-json-path",
            str(status_path),
        ],
    )

    output = capsys.readouterr().out
    payload = json.loads(status_path.read_text(encoding="utf-8"))
    assert status == 1
    assert f"status_json: {status_path}" in output
    assert payload["status"] == "failed"
    assert "browser-fixture" in payload["missing_proofs"]


def test_cli_proof_validate_suite_writes_runbook(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    trace_dir = tmp_path / "trace"
    runbook_path = tmp_path / "review" / "next-actions.md"
    write_proof_manifest(trace_dir)

    status = main(
        [
            "proof",
            "validate-suite",
            str(tmp_path),
            "--allow-missing-video",
            "--write-runbook",
            "--runbook-path",
            str(runbook_path),
        ],
    )

    output = capsys.readouterr().out
    runbook = runbook_path.read_text(encoding="utf-8")
    assert status == 1
    assert f"runbook: {runbook_path}" in output
    assert "# DeskPilot Windows Proof Suite Next Actions" in runbook
    assert "desktop-agent proof browser-fixture" in runbook
    assert (
        "--allow-missing-video --require-preflight --require-review --write-report"
        in runbook
    )


def test_cli_proof_validate_suite_writes_archive(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    trace_dir = tmp_path / "trace"
    archive_path = tmp_path / "review" / "suite.zip"
    write_proof_manifest(trace_dir)

    status = main(
        [
            "proof",
            "validate-suite",
            str(tmp_path),
            "--allow-missing-video",
            "--write-archive",
            "--archive-path",
            str(archive_path),
        ],
    )

    output = capsys.readouterr().out
    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
    assert status == 1
    assert f"archive: {archive_path}" in output
    assert "proof-suite-report.md" in names
    assert "proof-suite-status.json" in names
    assert "proof-suite-next-actions.md" in names


def test_cli_proof_validate_suite_writes_review_template(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    trace_dir = tmp_path / "trace"
    review_path = tmp_path / "review" / "suite-review.md"
    write_proof_manifest(trace_dir)

    status = main(
        [
            "proof",
            "validate-suite",
            str(tmp_path),
            "--allow-missing-video",
            "--write-review-template",
            "--review-template-path",
            str(review_path),
        ],
    )

    output = capsys.readouterr().out
    review = review_path.read_text(encoding="utf-8")
    assert status == 1
    assert f"review_template: {review_path}" in output
    assert "# DeskPilot Windows Proof Suite Review" in review
    assert "- [ ] Pass" in review


def test_cli_proof_promote_suite_writes_promotion_json(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    trace_dir = tmp_path / "trace"
    promotion_path = tmp_path / "monitoring" / "promotion.json"
    write_proof_manifest(trace_dir)

    status = main(
        [
            "proof",
            "promote-suite",
            str(tmp_path),
            "--allow-missing-video",
            "--promotion-path",
            str(promotion_path),
        ],
    )

    output = capsys.readouterr().out
    payload = json.loads(promotion_path.read_text(encoding="utf-8"))
    assert status == 1
    assert "promotion: failed" in output
    assert f"promotion_json: {promotion_path}" in output
    assert payload["status"] == "failed"
    assert payload["promotion_ready"] is False
    assert isinstance(payload["artifact_digests"], list)
    assert "proof preflight report not found" in "\n".join(payload["errors"])
    assert "proof review status not found" in "\n".join(payload["errors"])


def test_cli_proof_finalize_suite_writes_complete_evidence_pack(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    trace_dir = tmp_path / "trace"
    write_proof_manifest(trace_dir)

    status = main(
        [
            "proof",
            "finalize-suite",
            str(tmp_path),
            "--allow-missing-video",
        ],
    )

    output = capsys.readouterr().out
    assert status == 1
    assert "suite: failed" in output
    assert f"report: {tmp_path / 'proof-suite-report.md'}" in output
    assert f"promotion_json: {tmp_path / 'proof-suite-promotion.json'}" in output
    assert "promotion_verification: failed" in output
    assert "archive_verification: failed" in output
    assert (
        f"finalization_status_json: {tmp_path / 'proof-finalization-status.json'}"
        in output
    )
    for artifact_name in (
        "proof-suite-report.md",
        "proof-suite-status.json",
        "proof-suite-next-actions.md",
        "proof-suite-promotion.json",
        "proof-promotion-verification.json",
        "proof-suite-artifacts.zip",
        "proof-archive-verification.json",
        "proof-finalization-status.json",
    ):
        assert (tmp_path / artifact_name).exists()


def test_cli_proof_verify_promotion_reports_failed_record(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    trace_dir = tmp_path / "trace"
    promotion_path = tmp_path / "promotion.json"
    write_proof_manifest(trace_dir)
    main(
        [
            "proof",
            "promote-suite",
            str(tmp_path),
            "--allow-missing-video",
            "--promotion-path",
            str(promotion_path),
        ],
    )
    capsys.readouterr()

    status_path = tmp_path / "promotion-verification.json"

    status = main(
        [
            "proof",
            "verify-promotion",
            str(promotion_path),
            "--write-status-json",
            "--status-json-path",
            str(status_path),
        ],
    )

    output = capsys.readouterr().out
    payload = json.loads(status_path.read_text(encoding="utf-8"))
    assert status == 1
    assert "promotion_verification: failed" in output
    assert f"status_json: {status_path}" in output
    assert payload["status"] == "failed"
    assert "error: proof suite promotion status is not passed: failed" in output


def test_cli_proof_verify_archive_reports_missing_promotion(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    archive_path = tmp_path / "empty-proof-suite.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("placeholder.txt", "empty")

    status_path = tmp_path / "archive-verification.json"

    status = main(
        [
            "proof",
            "verify-archive",
            str(archive_path),
            "--write-status-json",
            "--status-json-path",
            str(status_path),
        ],
    )

    output = capsys.readouterr().out
    payload = json.loads(status_path.read_text(encoding="utf-8"))
    assert status == 1
    assert "archive_verification: failed" in output
    assert f"status_json: {status_path}" in output
    assert payload["status"] == "failed"
    assert "error: proof suite archive missing proof-suite-promotion.json" in output


def test_cli_proof_validate_review_writes_status(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    review_path = tmp_path / "proof-suite-review.md"
    status_path = tmp_path / "proof-suite-review-status.json"
    review_path.write_text(
        "\n".join(
            [
                "# DeskPilot Windows Proof Suite Review",
                "- Reviewer: Ada",
                "- Review date: 2026-05-16",
                "- [x] Pass",
                "- [ ] Fail",
                "- [x] The run happened on an owned, unlocked Windows desktop or VM.",
                "",
            ],
        ),
        encoding="utf-8",
    )

    status = main(
        [
            "proof",
            "validate-review",
            str(review_path),
            "--write-status-json",
            "--status-json-path",
            str(status_path),
        ],
    )

    output = capsys.readouterr().out
    payload = json.loads(status_path.read_text(encoding="utf-8"))
    assert status == 0
    assert "review_validation: passed" in output
    assert f"status_json: {status_path}" in output
    assert payload["status"] == "passed"


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
    assert report["observability_contract"]["configured"] is False
    assert report["monitoring_coverage"]["configured"] is False
    assert report["acceptance"]["configured"] is False
    assert report["acceptance"]["status"] == "not_configured"
    assert report["baseline_comparison"]["safety_not_reduced"] is True
    assert (output_dir / "trace-health.json").exists()
    assert (output_dir / "variance-report.json").exists()
    assert (output_dir / "benchmark-summary.md").exists()
    assert (output_dir / "baseline-runs.jsonl").exists()
    assert (output_dir / "baseline-comparison.json").exists()
    assert (output_dir / "pointer-timing-comparison.json").exists()
    assert len(metrics) == 2
    assert "metrics:" in output
    assert "baseline metrics:" in output
    assert "trace health:" in output
    assert "monitoring coverage: not_configured" in output
    assert "variance:" in output
    assert "baseline comparison:" in output
    assert "baseline status:" in output
    assert "pointer timing:" in output
    assert "acceptance: not_configured" in output
    assert "report:" in output
    assert "summary:" in output


def test_cli_benchmark_exit_code_can_fail_on_monitoring_gap() -> None:
    healthy = {"configured": True, "passed": True}
    missing = {"configured": True, "passed": False}
    ad_hoc = {"configured": False}

    assert (
        _benchmark_exit_code(
            ("passed",),
            acceptance_passed=True,
            monitoring_coverage=healthy,
            fail_on_monitoring_gap=True,
        )
        == 0
    )
    assert (
        _benchmark_exit_code(
            ("passed",),
            acceptance_passed=True,
            monitoring_coverage=missing,
            fail_on_monitoring_gap=True,
        )
        == 1
    )
    assert (
        _benchmark_exit_code(
            ("passed",),
            acceptance_passed=True,
            monitoring_coverage=ad_hoc,
            fail_on_monitoring_gap=True,
        )
        == 0
    )
    assert _benchmark_monitoring_status(missing) == "failed"


def test_cli_benchmark_monitoring_failures_explain_gaps() -> None:
    coverage = {
        "configured": True,
        "passed": False,
        "missing_trace_phases": ["select_target", "verify_result"],
        "missing_report_fields": ["trace_dir"],
    }

    assert _benchmark_monitoring_failures(coverage) == (
        "missing trace phases: select_target, verify_result",
        "missing report fields: trace_dir",
    )
