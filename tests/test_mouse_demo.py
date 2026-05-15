from pathlib import Path
from typing import cast

import pytest
from pytest import MonkeyPatch

from desktop_agent.actuation import ActuationProfile, FakeInputBackend
from desktop_agent.config import RuntimeConfig
from desktop_agent.mouse_demo import (
    MouseDemoError,
    MouseDemoStep,
    PostActionEvidenceRecorder,
    RealInputController,
    _demo_actuation_profile,
    _run_linkedin_sequence,
    _run_windows_smoke_sequence,
    _write_report,
    run_input_demo,
    run_linkedin_demo,
    run_mouse_demo,
    run_windows_smoke_checklist,
)
from desktop_agent.screen import ScreenObservation


def test_demo_actuation_profile_uses_visible_human_like_motion() -> None:
    profile = _demo_actuation_profile(123, 0.75)

    assert profile.movement_duration_seconds == (0.90, 1.80)
    assert profile.movement_steps == 72
    assert profile.movement_smoothness == 0.75
    assert profile.overshoot_probability == 0.35
    assert profile.scroll_interval_seconds == (0.08, 0.18)
    assert profile.random_seed == 123


def test_real_input_controller_records_cursor_readback_frames() -> None:
    backend = FakeInputBackend(start_position=(0, 0))
    controller = RealInputController(backend, _instant_demo_profile())

    step = controller.move_to("move-proof", (80, 40), target_size_pixels=(20, 20))

    frames = cast(list[dict[str, object]], step.metadata["cursor_frames"])
    assert step.action == "move"
    assert len(frames) == 4
    assert step.metadata["cursor_frame_count"] == 4
    assert frames[-1]["planned"] == [80, 40]
    assert frames[-1]["actual"] == [80, 40]
    assert step.metadata["max_drift_pixels"] == 0.0
    assert [event.kind for event in backend.events] == ["move", "move", "move", "move"]


def test_real_input_controller_drag_records_down_move_up_order() -> None:
    backend = FakeInputBackend(start_position=(0, 0))
    controller = RealInputController(backend, _instant_demo_profile())

    step = controller.drag("desktop-drag", (10, 10), (60, 40))

    event_kinds = [event.kind for event in backend.events]
    down_index = event_kinds.index("mouse_down")
    up_index = event_kinds.index("mouse_up")
    button_events = cast(list[dict[str, object]], step.metadata["button_events"])
    assert down_index < up_index
    assert "move" in event_kinds[down_index + 1 : up_index]
    assert [event["event"] for event in button_events] == ["mouse_down", "mouse_up"]
    assert step.metadata["start"] == [10, 10]
    assert step.metadata["end"] == [60, 40]


def test_real_input_controller_scroll_records_wheel_events() -> None:
    backend = FakeInputBackend(start_position=(0, 0))
    controller = RealInputController(backend, _instant_demo_profile())

    step = controller.scroll("scroll-proof", (20, 30), -3)

    scroll_events = cast(list[dict[str, object]], step.metadata["scroll_events"])
    assert [event.clicks for event in backend.events if event.kind == "scroll"] == [
        -1,
        -1,
        -1,
    ]
    assert [event["event"] for event in scroll_events] == ["wheel", "wheel", "wheel"]
    assert step.metadata["requested_clicks"] == -3


def test_real_input_controller_keyboard_cadence_preserves_exact_text() -> None:
    backend = FakeInputBackend(start_position=(0, 0))
    controller = RealInputController(backend, _instant_demo_profile())
    text = "DeskPilot controlled input"

    step = controller.type_text("type-notepad-text", text)

    typed_text = "".join(
        event.text or "" for event in backend.events if event.kind == "type_text"
    )
    intervals = cast(list[float], step.metadata["keyboard_interval_seconds"])
    assert typed_text == text
    assert step.metadata["typed_text_reconstructed"] == text
    assert intervals == [0.01] * (len(text) - 1)


def test_post_action_evidence_recorder_attaches_screenshot_and_focus(
    tmp_path: Path,
) -> None:
    backend = FakeInputBackend(start_position=(12, 14), active_window_title="Fallback")
    observer = FakeScreenObserver(active_window_title="Observed Window")
    recorder = PostActionEvidenceRecorder(
        backend=backend,
        trace_dir=tmp_path,
        observer=observer,
    )

    step = recorder.attach(MouseDemoStep("after-click", "click", {}))

    evidence = cast(dict[str, object], step.metadata["post_action_evidence"])
    assert evidence["status"] == "passed"
    assert evidence["active_window_title"] == "Observed Window"
    assert evidence["screenshot_size"] == [640, 480]
    assert evidence["cursor_position"] == [12, 14]
    assert str(evidence["screenshot_path"]).endswith("shot-1.png")


def test_demo_report_writes_monitoring_action_log(tmp_path: Path) -> None:
    step = MouseDemoStep(
        "scroll-page",
        "scroll",
        {
            "post_action_evidence": {
                "status": "passed",
                "active_window_title": "LinkedIn - Edge",
            },
        },
    )

    report_path = _write_report(
        tmp_path,
        (step,),
        "passed",
        None,
        report_name="linkedin-demo-report.json",
    )

    action_log_path = tmp_path / "action-log.jsonl"
    assert report_path.exists()
    assert action_log_path.exists()
    assert "LinkedIn - Edge" in action_log_path.read_text(encoding="utf-8")
    assert "action_log_path" in report_path.read_text(encoding="utf-8")


def test_linkedin_sequence_opens_edge_navigates_and_finds_text() -> None:
    backend = FakeInputBackend(start_position=(0, 0))
    controller = RealInputController(backend, _instant_demo_profile())
    observer = FakeScreenObserver(active_window_title="LinkedIn - Edge")
    recorder = PostActionEvidenceRecorder(
        backend=backend,
        trace_dir=Path("trace"),
        observer=observer,
    )

    steps = _run_linkedin_sequence(
        controller,
        (0, 0, 1280, 720),
        url="https://www.linkedin.com/",
        find_text="LinkedIn",
        page_load_seconds=0,
        evidence_recorder=recorder,
        launch_edge=lambda initial_url: MouseDemoStep(
            "open-edge",
            "launch_application",
            {"initial_url": initial_url},
        ),
    )

    typed_text = "".join(
        event.text or "" for event in backend.events if event.kind == "type_text"
    )
    assert [step.step_id for step in steps] == [
        "open-edge",
        "focus-edge-address-bar",
        "type-linkedin-url",
        "submit-linkedin-url",
        "scroll-linkedin-page",
        "open-browser-find",
        "type-find-text",
        "confirm-find-text",
        "close-browser-find",
        "final-cursor-readback",
    ]
    assert "https://www.linkedin.com/" in typed_text
    assert typed_text.endswith("LinkedIn")
    assert any(event.kind == "scroll" for event in backend.events)
    assert all("post_action_evidence" in step.metadata for step in steps)
    assert observer.observe_count == len(steps)


def test_windows_smoke_sequence_checks_cursor_notepad_edge_and_trace() -> None:
    backend = FakeInputBackend(start_position=(0, 0))
    controller = RealInputController(backend, _instant_demo_profile())
    observer = FakeScreenObserver(active_window_title="Smoke Window")
    recorder = PostActionEvidenceRecorder(
        backend=backend,
        trace_dir=Path("trace"),
        observer=observer,
    )

    steps = _run_windows_smoke_sequence(
        controller,
        keyboard_text="smoke text",
        edge_url="about:blank",
        evidence_recorder=recorder,
        launch_notepad=lambda: MouseDemoStep(
            "open-notepad",
            "launch_application",
            {"application": "notepad.exe"},
        ),
        launch_edge=lambda url: MouseDemoStep(
            "open-edge",
            "launch_application",
            {"url": url},
        ),
    )

    check_ids = [
        cast(dict[str, object], step.metadata["smoke_check"])["check_id"]
        for step in steps
    ]
    typed_text = "".join(
        event.text or "" for event in backend.events if event.kind == "type_text"
    )
    assert check_ids == [
        "cursor_readback",
        "notepad_launch",
        "notepad_typing",
        "edge_launch",
        "final_cursor_readback",
    ]
    assert typed_text == "smoke text"
    assert all("post_action_evidence" in step.metadata for step in steps)
    assert observer.observe_count == len(steps)


def test_run_input_demo_requires_windows(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr("desktop_agent.mouse_demo.sys.platform", "darwin")

    with pytest.raises(MouseDemoError, match="demo-input requires Windows"):
        run_input_demo(trace_root=tmp_path)


def test_run_linkedin_demo_requires_windows(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr("desktop_agent.mouse_demo.sys.platform", "darwin")

    with pytest.raises(MouseDemoError, match="demo-linkedin requires Windows"):
        run_linkedin_demo(trace_root=tmp_path)


def test_run_windows_smoke_checklist_requires_windows(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr("desktop_agent.mouse_demo.sys.platform", "darwin")

    with pytest.raises(MouseDemoError, match="requires Windows"):
        run_windows_smoke_checklist(trace_root=tmp_path)


def test_run_mouse_demo_alias_requires_windows(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr("desktop_agent.mouse_demo.sys.platform", "darwin")

    with pytest.raises(MouseDemoError, match="demo-input requires Windows"):
        run_mouse_demo(trace_root=tmp_path)


def _instant_demo_profile() -> ActuationProfile:
    return ActuationProfile(
        movement_duration_seconds=(0.0, 0.0),
        timing_variation_seconds=(0.0, 0.0),
        keyboard_interval_seconds=(0.01, 0.01),
        scroll_interval_seconds=(0.0, 0.0),
        movement_steps=4,
        movement_smoothness=0.5,
        random_seed=12,
    )


class FakeScreenObserver:
    def __init__(self, *, active_window_title: str) -> None:
        self._active_window_title = active_window_title
        self.observe_count = 0

    def observe(self, config: RuntimeConfig) -> ScreenObservation:
        trace_root = config.trace_root
        self.observe_count += 1
        screenshot_dir = trace_root / "screenshots"
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = screenshot_dir / f"shot-{self.observe_count}.png"
        screenshot_path.write_bytes(b"png")
        return ScreenObservation(
            screenshot_path=screenshot_path,
            size=(640, 480),
            active_window_title=self._active_window_title,
            warnings=("fake warning",),
            metadata={"observe_count": self.observe_count},
        )
