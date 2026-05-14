from desktop_agent.config import RuntimeConfig
from desktop_agent.screen import (
    Bounds,
    MonitorInfo,
    _primary_monitor_warnings,
    physical_point_to_screenshot,
    screenshot_bounds_to_physical,
    screenshot_point_to_physical,
)


def test_coordinate_normalization_between_screenshot_and_physical_space() -> None:
    monitor = MonitorInfo(
        left=100,
        top=200,
        width=1920,
        height=1080,
        scale_x=1.5,
        scale_y=2.0,
        is_primary=True,
    )

    physical = screenshot_point_to_physical((20, 30), monitor)
    screenshot = physical_point_to_screenshot(physical, monitor)

    assert physical == (130, 260)
    assert screenshot == (20, 30)


def test_bounds_normalization_preserves_scaled_size() -> None:
    monitor = MonitorInfo(
        left=10,
        top=20,
        width=800,
        height=600,
        scale_x=1.25,
        scale_y=1.5,
    )

    physical_bounds = screenshot_bounds_to_physical(
        Bounds(x=8, y=10, width=100, height=40),
        monitor,
    )

    assert physical_bounds == Bounds(x=20, y=35, width=125, height=60)


def test_primary_monitor_warning_for_multiple_monitors() -> None:
    warnings = _primary_monitor_warnings(
        (
            MonitorInfo(left=0, top=0, width=800, height=600, is_primary=True),
            MonitorInfo(left=800, top=0, width=800, height=600),
        ),
        RuntimeConfig(primary_monitor_only=True),
    )

    assert warnings == (
        "multiple monitors detected; v1 is using the primary monitor only",
    )
