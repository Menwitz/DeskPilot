from desktop_agent.actuation import (
    ActuationProfile,
    DesktopActuator,
    FakeInputBackend,
    FittsLawPointerTimingModel,
    PointerTimingContext,
    SmoothMovementPlanner,
)
from desktop_agent.config import RuntimeConfig
from desktop_agent.perception import ElementCandidate
from desktop_agent.screen import Bounds, MonitorInfo, ScreenObservation
from desktop_agent.task_dsl import TaskRegion, TaskStep


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
    assert backend.events[-2].kind == "mouse_down"
    assert backend.events[-2].point == (150, 250)
    assert backend.events[-1].kind == "mouse_up"
    assert backend.events[-1].point == (150, 250)


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
    assert backend.events == []


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


def _instant_profile() -> ActuationProfile:
    return ActuationProfile(
        movement_duration_seconds=(0.0, 0.0),
        timing_variation_seconds=(0.0, 0.0),
        movement_steps=3,
        movement_smoothness=0.0,
        random_seed=1,
    )
