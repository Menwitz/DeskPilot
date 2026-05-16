from desktop_agent.actuation import (
    ActuationGuardBlocked,
    ActuationProfile,
    DesktopActuator,
    FakeInputBackend,
    FittsLawPointerTimingModel,
    PointerTimingContext,
    SmoothMovementPlanner,
    _keyboard_input,
    _mouse_button_input,
    _mouse_wheel_input,
    _normalize_absolute_mouse_point,
    _relative_mouse_move_input,
    _virtual_key,
    actuation_profile_from_runtime_config,
)
from desktop_agent.config import ExecutionProfile, RuntimeConfig
from desktop_agent.perception import ElementCandidate
from desktop_agent.safety import StaticEmergencyStopMonitor
from desktop_agent.screen import Bounds, MonitorInfo, ScreenObservation
from desktop_agent.task_dsl import TaskRegion, TaskStep


class SequenceEmergencyStopMonitor:
    def __init__(self, states: tuple[bool, ...]) -> None:
        self._states = states
        self.calls = 0

    def is_triggered(self, config: RuntimeConfig) -> bool:
        _ = config
        index = min(self.calls, len(self._states) - 1)
        self.calls += 1
        return self._states[index]


class SequenceActiveWindowBackend(FakeInputBackend):
    """Fake backend that can change foreground titles between guard checks."""

    def __init__(self, titles: tuple[str | None, ...]) -> None:
        super().__init__(
            start_position=(0, 0),
            active_window_title=titles[0] if titles else None,
        )
        self._titles = titles
        self.active_window_calls = 0

    def active_window_title(self) -> str | None:
        if not self._titles:
            return None
        index = min(self.active_window_calls, len(self._titles) - 1)
        self.active_window_calls += 1
        return self._titles[index]


def test_desktop_actuator_clicks_converted_target_center() -> None:
    backend = FakeInputBackend(
        start_position=(0, 0),
        active_window_title="DeskPilot Fixture",
    )
    actuator = DesktopActuator(backend, _instant_profile())
    target = ElementCandidate(
        id="target-1",
        source="ocr",
        label="Submit",
        bounds=Bounds(x=10, y=20, width=30, height=10),
        confidence=0.95,
    )
    observation = ScreenObservation(
        monitor=MonitorInfo(
            left=100,
            top=200,
            width=800,
            height=600,
            scale_x=2.0,
            scale_y=2.0,
        ),
    )

    result = actuator.execute(
        TaskStep(id="click-submit", action="click_text", target="Submit"),
        target,
        observation,
        RuntimeConfig(allowed_windows=("DeskPilot Fixture",)),
    )

    assert result.success is True
    assert result.metadata["point"] == [150, 250]
    assert result.metadata["pointer_timing_model"] == "fitts_law"
    assert result.metadata["pointer_effective_target_width_pixels"] == 20.0
    assert result.metadata["pointer_path_model"] == "minimum_jerk_quadratic_bezier"
    assert result.metadata["overshoot_applied"] is False
    assert backend.events[-2].kind == "mouse_down"
    assert backend.events[-2].point == (150, 250)
    assert backend.events[-1].kind == "mouse_up"
    assert backend.events[-1].point == (150, 250)


def test_windows_absolute_mouse_points_are_normalized_for_sendinput() -> None:
    assert _normalize_absolute_mouse_point((0, 0), (0, 0, 1920, 1080)) == (0, 0)
    assert _normalize_absolute_mouse_point((1919, 1079), (0, 0, 1920, 1080)) == (
        65535,
        65535,
    )
    assert _normalize_absolute_mouse_point((960, 540), (0, 0, 1920, 1080)) == (
        32785,
        32798,
    )


def test_windows_absolute_mouse_points_support_virtual_screen_offsets() -> None:
    assert _normalize_absolute_mouse_point((-1280, 0), (-1280, 0, 3200, 1080)) == (
        0,
        0,
    )
    assert _normalize_absolute_mouse_point((1919, 1079), (-1280, 0, 3200, 1080)) == (
        65535,
        65535,
    )


def test_windows_relative_mouse_input_uses_delta_move_events() -> None:
    input_record = _relative_mouse_move_input((12, -7))

    assert input_record.type == 0
    assert input_record.data.mi.dx == 12
    assert input_record.data.mi.dy == -7
    assert input_record.data.mi.dwFlags == 0x0001


def test_windows_mouse_button_and_wheel_inputs_use_sendinput_records() -> None:
    down_record = _mouse_button_input(0x0002)
    wheel_record = _mouse_wheel_input(-3)

    assert down_record.type == 0
    assert down_record.data.mi.dwFlags == 0x0002
    assert wheel_record.type == 0
    assert wheel_record.data.mi.dwFlags == 0x0800
    assert wheel_record.data.mi.mouseData & 0xFFFFFFFF == (-360 & 0xFFFFFFFF)


def test_windows_keyboard_inputs_use_sendinput_records() -> None:
    down_record = _keyboard_input(0x41, key_down=True)
    up_record = _keyboard_input(0x41, key_down=False)

    assert down_record.type == 1
    assert down_record.data.ki.wVk == 0x41
    assert down_record.data.ki.dwFlags == 0
    assert up_record.type == 1
    assert up_record.data.ki.wVk == 0x41
    assert up_record.data.ki.dwFlags == 0x0002


def test_windows_key_aliases_include_global_desktop_modifier() -> None:
    assert _virtual_key("win") == 0x5B
    assert _virtual_key("windows") == 0x5B
    assert _virtual_key("meta") == 0x5B


def test_desktop_actuator_types_text_and_key_chords() -> None:
    backend = FakeInputBackend(active_window_title="DeskPilot Fixture")
    actuator = DesktopActuator(backend, _instant_profile())

    typed = actuator.execute(
        TaskStep(id="type-name", action="type_text", text="hello"),
        None,
        ScreenObservation(),
        RuntimeConfig(allowed_windows=("DeskPilot Fixture",)),
    )
    pressed = actuator.execute(
        TaskStep(id="save", action="press_key", text="ctrl+s"),
        None,
        ScreenObservation(),
        RuntimeConfig(allowed_windows=("DeskPilot Fixture",)),
    )

    assert typed.success is True
    assert pressed.success is True
    assert [event.kind for event in backend.events] == [
        "type_text",
        "key_down",
        "press_key",
        "key_up",
    ]
    assert backend.events[0].text == "hello"
    assert backend.events[1].key == "ctrl"
    assert backend.events[2].key == "s"


def test_keyboard_cadence_never_changes_typed_text() -> None:
    backend = FakeInputBackend(active_window_title="DeskPilot Fixture")
    actuator = DesktopActuator(
        backend,
        ActuationProfile(
            movement_duration_seconds=(0.1, 0.2),
            timing_variation_seconds=(0.01, 0.02),
            movement_steps=3,
            movement_smoothness=0.5,
            random_seed=9,
        ),
    )
    text = "Hello, qa@example.test!\nNext line: 123"

    result = actuator.execute(
        TaskStep(id="type-note", action="type_text", text=text),
        None,
        ScreenObservation(),
        RuntimeConfig(allowed_windows=("DeskPilot Fixture",)),
    )

    assert result.success is True
    assert result.metadata["text_length"] == len(text)
    assert [event.kind for event in backend.events] == ["type_text"]
    assert backend.events[0].text == text


def test_keyboard_cadence_profiles_type_same_text_with_intervals() -> None:
    backend = FakeInputBackend(active_window_title="DeskPilot Fixture")
    actuator = DesktopActuator(
        backend,
        ActuationProfile(
            movement_duration_seconds=(0.0, 0.0),
            timing_variation_seconds=(0.0, 0.0),
            keyboard_interval_seconds=(0.01, 0.01),
            random_seed=9,
        ),
    )

    result = actuator.execute(
        TaskStep(id="type-code", action="type_text", text="abc"),
        None,
        ScreenObservation(),
        RuntimeConfig(allowed_windows=("DeskPilot Fixture",)),
    )

    typed_text = "".join(
        event.text or "" for event in backend.events if event.kind == "type_text"
    )
    sleep_durations = [
        event.duration_seconds for event in backend.events if event.kind == "sleep"
    ]
    assert result.success is True
    assert typed_text == "abc"
    assert [event.kind for event in backend.events] == [
        "type_text",
        "sleep",
        "type_text",
        "sleep",
        "type_text",
    ]
    assert sleep_durations == [0.01, 0.01]
    assert result.metadata["keyboard_cadence_applied"] is True
    assert result.metadata["keyboard_interval_count"] == 2


def test_desktop_actuator_drags_to_destination_region() -> None:
    backend = FakeInputBackend(active_window_title="DeskPilot Fixture")
    actuator = DesktopActuator(backend, _instant_profile())
    target = ElementCandidate(
        id="tile-1",
        source="uia",
        label="Tile",
        bounds=Bounds(x=10, y=10, width=20, height=20),
        confidence=0.9,
    )
    step = TaskStep(
        id="drag-tile",
        action="drag",
        target="Tile",
        region=TaskRegion(x=100, y=100, width=40, height=20),
    )

    result = actuator.execute(
        step,
        target,
        ScreenObservation(),
        RuntimeConfig(allowed_windows=("DeskPilot Fixture",)),
    )

    assert result.success is True
    assert result.metadata["start"] == [20, 20]
    assert result.metadata["end"] == [120, 110]
    assert any(event.kind == "mouse_down" for event in backend.events)
    assert backend.events[-1].kind == "mouse_up"
    assert backend.events[-1].point == (120, 110)


def test_desktop_actuator_scrolls_at_region_when_no_target_exists() -> None:
    backend = FakeInputBackend(active_window_title="DeskPilot Fixture")
    actuator = DesktopActuator(backend, _instant_profile())
    step = TaskStep(
        id="scroll-list",
        action="scroll",
        text="-5",
        region=TaskRegion(x=20, y=30, width=100, height=40),
    )

    result = actuator.execute(
        step,
        None,
        ScreenObservation(),
        RuntimeConfig(allowed_windows=("DeskPilot Fixture",)),
    )

    assert result.success is True
    assert backend.events[-1].kind == "scroll"
    assert backend.events[-1].point == (70, 50)
    assert backend.events[-1].clicks == -5


def test_scroll_cadence_profiles_preserve_total_scroll_clicks() -> None:
    backend = FakeInputBackend(active_window_title="DeskPilot Fixture")
    actuator = DesktopActuator(
        backend,
        ActuationProfile(
            movement_duration_seconds=(0.0, 0.0),
            timing_variation_seconds=(0.0, 0.0),
            scroll_interval_seconds=(0.02, 0.02),
            movement_steps=1,
            random_seed=11,
        ),
    )
    step = TaskStep(
        id="scroll-feed",
        action="scroll",
        text="-3",
        region=TaskRegion(x=20, y=30, width=100, height=40),
    )

    result = actuator.execute(
        step,
        None,
        ScreenObservation(),
        RuntimeConfig(allowed_windows=("DeskPilot Fixture",)),
    )

    scroll_clicks = [event.clicks for event in backend.events if event.kind == "scroll"]
    sleep_durations = [
        event.duration_seconds for event in backend.events if event.kind == "sleep"
    ]
    assert result.success is True
    assert scroll_clicks == [-1, -1, -1]
    assert sum(click for click in scroll_clicks if click is not None) == -3
    assert sleep_durations == [0.02, 0.02]
    assert result.metadata["scroll_cadence_applied"] is True
    assert result.metadata["scroll_step_count"] == 3


def test_desktop_actuator_blocks_disallowed_active_window() -> None:
    backend = FakeInputBackend(active_window_title="Unexpected Window")
    actuator = DesktopActuator(backend, _instant_profile())
    target = ElementCandidate(
        id="target-1",
        source="uia",
        label="Submit",
        bounds=Bounds(x=0, y=0, width=10, height=10),
        confidence=0.9,
    )

    result = actuator.execute(
        TaskStep(id="click-submit", action="click_text", target="Submit"),
        target,
        ScreenObservation(),
        RuntimeConfig(allowed_windows=("DeskPilot Fixture",)),
    )

    assert result.success is False
    assert "allowed_windows" in result.message
    assert result.metadata["actuation_guard"] == "active_window"
    assert backend.events == []


def test_desktop_actuator_rechecks_active_window_before_low_level_input() -> None:
    backend = SequenceActiveWindowBackend(
        ("DeskPilot Fixture", "Unexpected Window"),
    )
    actuator = DesktopActuator(
        backend,
        ActuationProfile(
            movement_duration_seconds=(0.0, 0.0),
            timing_variation_seconds=(0.0, 0.0),
            movement_steps=1,
            movement_smoothness=0.0,
        ),
    )
    target = ElementCandidate(
        id="target-1",
        source="uia",
        label="Submit",
        bounds=Bounds(x=10, y=10, width=10, height=10),
        confidence=0.9,
    )

    result = actuator.execute(
        TaskStep(id="click-submit", action="click_text", target="Submit"),
        target,
        ScreenObservation(),
        RuntimeConfig(allowed_windows=("DeskPilot Fixture",)),
    )

    assert result.success is False
    assert result.metadata["actuation_guard"] == "active_window"
    assert result.metadata["active_window_title"] == "Unexpected Window"
    assert [event.kind for event in backend.events] == ["move"]


def test_desktop_actuator_allows_case_insensitive_contains_window_match() -> None:
    backend = FakeInputBackend(active_window_title="LinkedIn - Google Chrome")
    actuator = DesktopActuator(backend, _instant_profile())

    result = actuator.execute(
        TaskStep(id="press-tab", action="press_key", text="tab"),
        None,
        ScreenObservation(),
        RuntimeConfig(allowed_windows=("linkedin",)),
    )

    assert result.success is True
    assert [event.kind for event in backend.events] == ["press_key"]


def test_desktop_actuator_allows_regex_window_match() -> None:
    backend = FakeInputBackend(active_window_title="Medium - Brave")
    actuator = DesktopActuator(backend, _instant_profile())

    result = actuator.execute(
        TaskStep(id="press-tab", action="press_key", text="tab"),
        None,
        ScreenObservation(),
        RuntimeConfig(allowed_windows=("regex:^medium\\b",)),
    )

    assert result.success is True
    assert [event.kind for event in backend.events] == ["press_key"]


def test_desktop_actuator_blocks_target_outside_step_region() -> None:
    backend = FakeInputBackend(active_window_title="DeskPilot Fixture")
    actuator = DesktopActuator(backend, _instant_profile())
    target = ElementCandidate(
        id="outside-region",
        source="uia",
        label="Submit",
        bounds=Bounds(x=180, y=20, width=30, height=10),
        confidence=0.9,
    )

    result = actuator.execute(
        TaskStep(
            id="click-submit",
            action="click_text",
            target="Submit",
            region=TaskRegion(x=0, y=0, width=100, height=100),
        ),
        target,
        ScreenObservation(),
        RuntimeConfig(allowed_windows=("DeskPilot Fixture",)),
    )

    assert result.success is False
    assert "step region" in result.message
    assert result.metadata["actuation_guard"] == "allowed_region"
    assert backend.events == []


def test_desktop_actuator_blocks_low_level_point_outside_allowed_region() -> None:
    backend = FakeInputBackend(active_window_title="DeskPilot Fixture")
    actuator = DesktopActuator(
        backend,
        ActuationProfile(
            movement_duration_seconds=(0.0, 0.0),
            timing_variation_seconds=(0.0, 0.0),
            movement_steps=1,
            movement_smoothness=0.0,
        ),
    )

    try:
        actuator.click(
            (30, 30),
            allowed_region=Bounds(x=0, y=0, width=20, height=20),
            config=RuntimeConfig(allowed_windows=("DeskPilot Fixture",)),
        )
    except ActuationGuardBlocked as exc:
        result = exc.result
    else:
        raise AssertionError("expected final allowed-region guard to block input")

    assert result.success is False
    assert result.metadata["actuation_guard"] == "allowed_region"
    assert result.metadata["input_point"] == [30, 30]
    assert [event.kind for event in backend.events] == ["move"]


def test_desktop_actuator_blocks_emergency_stop_before_input() -> None:
    backend = FakeInputBackend(active_window_title="DeskPilot Fixture")
    actuator = DesktopActuator(
        backend,
        _instant_profile(),
        StaticEmergencyStopMonitor(triggered=True),
    )
    target = ElementCandidate(
        id="target-1",
        source="uia",
        label="Submit",
        bounds=Bounds(x=0, y=0, width=10, height=10),
        confidence=0.9,
    )

    result = actuator.execute(
        TaskStep(id="click-submit", action="click_text", target="Submit"),
        target,
        ScreenObservation(),
        RuntimeConfig(allowed_windows=("DeskPilot Fixture",)),
    )

    assert result.success is False
    assert result.metadata["actuation_guard"] == "emergency_stop"
    assert result.metadata["emergency_stop_triggered"] is True
    assert backend.events == []


def test_desktop_actuator_checks_emergency_stop_between_pointer_events() -> None:
    backend = FakeInputBackend(
        start_position=(0, 0),
        active_window_title="DeskPilot Fixture",
    )
    actuator = DesktopActuator(
        backend,
        ActuationProfile(
            movement_duration_seconds=(0.0, 0.0),
            timing_variation_seconds=(0.0, 0.0),
            movement_steps=4,
            movement_smoothness=0.0,
        ),
        SequenceEmergencyStopMonitor((False, False, True)),
    )
    target = ElementCandidate(
        id="target-1",
        source="uia",
        label="Submit",
        bounds=Bounds(x=20, y=20, width=10, height=10),
        confidence=0.9,
    )

    result = actuator.execute(
        TaskStep(id="click-submit", action="click_text", target="Submit"),
        target,
        ScreenObservation(),
        RuntimeConfig(allowed_windows=("DeskPilot Fixture",)),
    )

    assert result.success is False
    assert result.metadata["emergency_stop_boundary"] == "movement_path"
    assert [event.kind for event in backend.events] == ["move"]


def test_desktop_actuator_releases_drag_on_emergency_stop_between_path_points() -> None:
    backend = FakeInputBackend(
        start_position=(0, 0),
        active_window_title="DeskPilot Fixture",
    )
    actuator = DesktopActuator(
        backend,
        ActuationProfile(
            movement_duration_seconds=(0.0, 0.0),
            timing_variation_seconds=(0.0, 0.0),
            movement_steps=1,
            movement_smoothness=0.0,
        ),
        SequenceEmergencyStopMonitor((False, False, False, True)),
    )
    target = ElementCandidate(
        id="tile-1",
        source="uia",
        label="Tile",
        bounds=Bounds(x=0, y=0, width=10, height=10),
        confidence=0.9,
    )

    result = actuator.execute(
        TaskStep(
            id="drag-tile",
            action="drag",
            target="Tile",
            region=TaskRegion(x=100, y=100, width=10, height=10),
        ),
        target,
        ScreenObservation(),
        RuntimeConfig(allowed_windows=("DeskPilot Fixture",)),
    )

    assert result.success is False
    assert result.metadata["emergency_stop_boundary"] == "movement_path"
    assert [event.kind for event in backend.events] == [
        "move",
        "mouse_down",
        "mouse_up",
    ]
    assert backend.events[-1].point == backend.events[0].point


def test_desktop_actuator_checks_emergency_stop_between_scroll_chunks() -> None:
    backend = FakeInputBackend(active_window_title="DeskPilot Fixture")
    actuator = DesktopActuator(
        backend,
        ActuationProfile(
            movement_duration_seconds=(0.0, 0.0),
            timing_variation_seconds=(0.0, 0.0),
            scroll_interval_seconds=(0.01, 0.01),
            movement_steps=1,
            movement_smoothness=0.0,
        ),
        SequenceEmergencyStopMonitor((False, False, False, False, True)),
    )

    result = actuator.execute(
        TaskStep(
            id="scroll-results",
            action="scroll",
            region=TaskRegion(x=10, y=10, width=20, height=20),
            text="-3",
        ),
        None,
        ScreenObservation(),
        RuntimeConfig(allowed_windows=("DeskPilot Fixture",)),
    )

    assert result.success is False
    assert result.metadata["emergency_stop_boundary"] == "scroll"
    assert [event.kind for event in backend.events] == ["move", "scroll", "sleep"]
    assert backend.events[1].clicks == -1


def test_desktop_actuator_checks_emergency_stop_between_typed_characters() -> None:
    backend = FakeInputBackend(active_window_title="DeskPilot Fixture")
    actuator = DesktopActuator(
        backend,
        _instant_profile(),
        SequenceEmergencyStopMonitor((False, False, True)),
    )

    result = actuator.execute(
        TaskStep(id="type-query", action="type_text", text="abc"),
        None,
        ScreenObservation(),
        RuntimeConfig(allowed_windows=("DeskPilot Fixture",)),
    )

    typed = [event.text for event in backend.events if event.kind == "type_text"]
    assert result.success is False
    assert result.metadata["emergency_stop_boundary"] == "type_character"
    assert typed == ["a"]


def test_pointer_path_is_not_emitted_for_disallowed_active_window() -> None:
    backend = FakeInputBackend(active_window_title="Unexpected Window")
    actuator = DesktopActuator(
        backend,
        ActuationProfile(
            movement_duration_seconds=(0.0, 0.0),
            timing_variation_seconds=(0.0, 0.0),
            movement_steps=4,
            movement_smoothness=0.0,
            overshoot_probability=1.0,
            overshoot_pixels=(8.0, 8.0),
            random_seed=1,
        ),
    )
    target = ElementCandidate(
        id="target-1",
        source="uia",
        label="Submit",
        bounds=Bounds(x=10, y=20, width=30, height=10),
        confidence=0.9,
    )

    result = actuator.execute(
        TaskStep(id="click-submit", action="click_text", target="Submit"),
        target,
        ScreenObservation(),
        RuntimeConfig(allowed_windows=("DeskPilot Fixture",)),
    )

    assert result.success is False
    assert all(event.kind != "move" for event in backend.events)


def test_pointer_path_stays_inside_allowed_monitor_bounds() -> None:
    monitor = MonitorInfo(left=100, top=100, width=800, height=600)
    backend = FakeInputBackend(
        start_position=(120, 250),
        active_window_title="DeskPilot Fixture",
    )
    actuator = DesktopActuator(
        backend,
        ActuationProfile(
            movement_duration_seconds=(0.0, 0.0),
            timing_variation_seconds=(0.0, 0.0),
            movement_steps=8,
            movement_smoothness=0.0,
            overshoot_probability=1.0,
            overshoot_pixels=(40.0, 40.0),
            random_seed=1,
        ),
    )
    target = ElementCandidate(
        id="target-1",
        source="uia",
        label="Submit",
        bounds=Bounds(x=760, y=130, width=30, height=30),
        confidence=0.9,
    )

    result = actuator.execute(
        TaskStep(id="click-submit", action="click_text", target="Submit"),
        target,
        ScreenObservation(monitor=monitor),
        RuntimeConfig(allowed_windows=("DeskPilot Fixture",)),
    )

    move_points = [event.point for event in backend.events if event.kind == "move"]
    assert result.success is True
    assert move_points
    assert all(point is not None for point in move_points)
    assert all(100 <= point[0] <= 900 for point in move_points if point)
    assert all(100 <= point[1] <= 700 for point in move_points if point)


def test_drag_pointer_path_stays_inside_allowed_window_and_monitor() -> None:
    monitor = MonitorInfo(left=100, top=100, width=800, height=600)
    backend = FakeInputBackend(
        start_position=(120, 120),
        active_window_title="DeskPilot Fixture",
    )
    actuator = DesktopActuator(
        backend,
        ActuationProfile(
            movement_duration_seconds=(0.0, 0.0),
            timing_variation_seconds=(0.0, 0.0),
            movement_steps=8,
            movement_smoothness=0.0,
            overshoot_probability=1.0,
            overshoot_pixels=(60.0, 60.0),
            random_seed=3,
        ),
    )
    target = ElementCandidate(
        id="tile-1",
        source="uia",
        label="Tile",
        bounds=Bounds(x=5, y=5, width=30, height=30),
        confidence=0.9,
    )
    step = TaskStep(
        id="drag-tile",
        action="drag",
        target="Tile",
        region=TaskRegion(x=760, y=560, width=30, height=30),
    )

    result = actuator.execute(
        step,
        target,
        ScreenObservation(monitor=monitor),
        RuntimeConfig(allowed_windows=("DeskPilot Fixture",)),
    )

    pointer_points = [
        event.point
        for event in backend.events
        if event.kind in {"move", "mouse_down", "mouse_up"}
    ]
    assert result.success is True
    assert pointer_points
    assert all(point is not None for point in pointer_points)
    assert all(100 <= point[0] <= 900 for point in pointer_points if point)
    assert all(100 <= point[1] <= 700 for point in pointer_points if point)


def test_smooth_movement_planner_uses_eased_multi_point_path() -> None:
    planner = SmoothMovementPlanner(
        ActuationProfile(
            movement_duration_seconds=(0.2, 0.2),
            timing_variation_seconds=(0.01, 0.01),
            movement_steps=4,
            movement_smoothness=0.5,
            random_seed=3,
        ),
    )

    plan = planner.plan((0, 0), (100, 0))

    assert len(plan.points) == 4
    assert plan.points[-1] == (100, 0)
    assert plan.duration_seconds == 0.21000000000000002
    assert plan.points[0][0] < plan.points[1][0] < plan.points[2][0]
    assert plan.timing_estimate is not None
    assert plan.timing_estimate.model == "fitts_law"
    assert plan.path_model == "minimum_jerk_quadratic_bezier"


def test_movement_planner_replays_all_random_choices_with_seed() -> None:
    profile = ActuationProfile(
        movement_duration_seconds=(0.2, 0.2),
        timing_variation_seconds=(0.01, 0.02),
        movement_steps=6,
        movement_smoothness=0.7,
        overshoot_probability=1.0,
        overshoot_pixels=(3.0, 7.0),
        settle_duration_seconds=(0.01, 0.02),
        random_seed=17,
    )

    first = SmoothMovementPlanner(profile).plan(
        (0, 0),
        (120, 20),
        target_size_pixels=(30, 20),
    )
    second = SmoothMovementPlanner(profile).plan(
        (0, 0),
        (120, 20),
        target_size_pixels=(30, 20),
    )
    different_seed = SmoothMovementPlanner(
        ActuationProfile(
            movement_duration_seconds=(0.2, 0.2),
            timing_variation_seconds=(0.01, 0.02),
            movement_steps=6,
            movement_smoothness=0.7,
            overshoot_probability=1.0,
            overshoot_pixels=(3.0, 7.0),
            settle_duration_seconds=(0.01, 0.02),
            random_seed=18,
        ),
    ).plan((0, 0), (120, 20), target_size_pixels=(30, 20))

    assert first == second
    assert first != different_seed
    assert first.random_seed == 17
    assert [record.label for record in first.sample_records] == [
        "actuation.settle_duration",
        "actuation.timing_variation",
        "actuation.overshoot",
        "actuation.overshoot_pixels",
        "actuation.control_direction",
        "actuation.control_direction",
    ]


def test_movement_planner_uses_minimum_jerk_progression() -> None:
    planner = SmoothMovementPlanner(
        ActuationProfile(
            movement_duration_seconds=(0.2, 0.2),
            timing_variation_seconds=(0.0, 0.0),
            movement_steps=6,
            movement_smoothness=0.0,
            random_seed=3,
        ),
    )

    plan = planner.plan((0, 0), (120, 0), target_size_pixels=(20, 20))
    x_positions = [0, *(point[0] for point in plan.points)]
    deltas = [
        x_positions[index + 1] - x_positions[index]
        for index in range(len(x_positions) - 1)
    ]

    assert plan.points[-1] == (120, 0)
    assert deltas[0] < max(deltas)
    assert deltas[-1] < max(deltas)


def test_actuation_profile_uses_enabled_execution_smoothness() -> None:
    base_profile = ActuationProfile(movement_smoothness=0.2, random_seed=4)
    config = RuntimeConfig(
        execution_profile=ExecutionProfile(
            enabled=True,
            movement_smoothness=0.9,
            keyboard_interval_seconds=(0.02, 0.03),
            scroll_interval_seconds=(0.04, 0.05),
        ),
    )

    profile = actuation_profile_from_runtime_config(config, base_profile)

    assert profile.movement_smoothness == 0.9
    assert profile.keyboard_interval_seconds == (0.02, 0.03)
    assert profile.scroll_interval_seconds == (0.04, 0.05)
    assert profile.random_seed == 4


def test_actuation_profile_preserves_default_when_execution_profile_disabled() -> None:
    base_profile = ActuationProfile(movement_smoothness=0.7)
    config = RuntimeConfig(
        execution_profile=ExecutionProfile(
            enabled=False,
            movement_smoothness=0.1,
        ),
    )

    profile = actuation_profile_from_runtime_config(config, base_profile)

    assert profile.movement_smoothness == 0.7


def test_movement_planner_applies_bounded_overshoot_correction_and_settle() -> None:
    planner = SmoothMovementPlanner(
        ActuationProfile(
            movement_duration_seconds=(0.2, 0.2),
            timing_variation_seconds=(0.0, 0.0),
            movement_steps=6,
            movement_smoothness=0.0,
            overshoot_probability=1.0,
            overshoot_pixels=(6.0, 6.0),
            settle_duration_seconds=(0.03, 0.03),
            random_seed=3,
        ),
    )

    plan = planner.plan((0, 0), (120, 0), target_size_pixels=(20, 20))

    assert plan.overshoot_applied is True
    assert plan.overshoot_point == (126, 0)
    assert plan.points[-1] == (120, 0)
    assert plan.path_model == "minimum_jerk_quadratic_bezier_with_correction"
    assert plan.settle_duration_seconds == 0.03
    assert round(plan.duration_seconds, 2) == 0.23


def test_movement_planner_clamps_overshoot_inside_target_width() -> None:
    planner = SmoothMovementPlanner(
        ActuationProfile(
            movement_duration_seconds=(0.2, 0.2),
            timing_variation_seconds=(0.0, 0.0),
            movement_steps=4,
            movement_smoothness=0.0,
            overshoot_probability=1.0,
            overshoot_pixels=(100.0, 100.0),
            random_seed=3,
        ),
    )

    plan = planner.plan((0, 0), (120, 0), target_size_pixels=(20, 20))

    assert plan.overshoot_point == (129, 0)
    assert 110 <= plan.overshoot_point[0] <= 130
    assert max(point[0] for point in plan.points) <= 129
    assert plan.points[-1] == (120, 0)


def test_fitts_law_pointer_timing_increases_for_far_small_targets() -> None:
    model = FittsLawPointerTimingModel(intercept_seconds=0.1, slope_seconds=0.2)

    easy = model.estimate(
        PointerTimingContext(
            start=(0, 0),
            end=(50, 0),
            target_width_pixels=100,
            target_height_pixels=100,
        )
    )
    hard = model.estimate(
        PointerTimingContext(
            start=(0, 0),
            end=(500, 0),
            target_width_pixels=10,
            target_height_pixels=10,
        )
    )

    assert hard.index_of_difficulty > easy.index_of_difficulty
    assert hard.duration_seconds > easy.duration_seconds


def test_movement_planner_clamps_fitts_duration_inside_profile_bounds() -> None:
    planner = SmoothMovementPlanner(
        ActuationProfile(
            movement_duration_seconds=(0.05, 0.5),
            timing_variation_seconds=(0.0, 0.0),
            movement_steps=2,
            movement_smoothness=0.0,
            random_seed=1,
        ),
        FittsLawPointerTimingModel(intercept_seconds=0.0, slope_seconds=0.2),
    )

    large_target = planner.plan((0, 0), (100, 0), target_size_pixels=(100, 100))
    small_target = planner.plan((0, 0), (100, 0), target_size_pixels=(5, 5))

    assert large_target.duration_seconds >= 0.05
    assert small_target.duration_seconds <= 0.5
    assert small_target.duration_seconds > large_target.duration_seconds


def test_actuation_profile_rejects_invalid_overshoot_settings() -> None:
    try:
        ActuationProfile(overshoot_probability=1.5)
    except ValueError as exc:
        assert str(exc) == "overshoot_probability must be between 0 and 1"
    else:
        raise AssertionError("expected overshoot probability validation failure")

    try:
        ActuationProfile(overshoot_pixels=(2.0, 1.0))
    except ValueError as exc:
        assert str(exc) == "overshoot_pixels lower bound must not exceed upper bound"
    else:
        raise AssertionError("expected overshoot pixel validation failure")


def _instant_profile() -> ActuationProfile:
    return ActuationProfile(
        movement_duration_seconds=(0.0, 0.0),
        timing_variation_seconds=(0.0, 0.0),
        movement_steps=3,
        movement_smoothness=0.0,
        random_seed=1,
    )
