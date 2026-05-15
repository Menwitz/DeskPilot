from pathlib import Path
from typing import cast

import pytest
from pytest import MonkeyPatch

from desktop_agent.actuation import ActuationProfile, FakeInputBackend
from desktop_agent.mouse_demo import (
    MouseDemoError,
    MouseDemoStep,
    RealInputController,
    _demo_actuation_profile,
    _run_linkedin_sequence,
    run_input_demo,
    run_linkedin_demo,
    run_mouse_demo,
)


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


def test_linkedin_sequence_opens_edge_navigates_and_finds_text() -> None:
    backend = FakeInputBackend(start_position=(0, 0))
    controller = RealInputController(backend, _instant_demo_profile())

    steps = _run_linkedin_sequence(
        controller,
        (0, 0, 1280, 720),
        url="https://www.linkedin.com/",
        find_text="LinkedIn",
        page_load_seconds=0,
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
