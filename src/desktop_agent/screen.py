"""Screen observation contracts and shared geometry types."""

from __future__ import annotations

import ctypes
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path
from typing import Any, Protocol, cast

from desktop_agent.config import RuntimeConfig


@dataclass(frozen=True)
class Bounds:
    """Rectangle in screenshot coordinate space."""

    x: int
    y: int
    width: int
    height: int

    @property
    def center(self) -> tuple[int, int]:
        return (self.x + self.width // 2, self.y + self.height // 2)


@dataclass(frozen=True)
class MonitorInfo:
    """Monitor geometry and DPI scale used for coordinate normalization."""

    left: int
    top: int
    width: int
    height: int
    scale_x: float = 1.0
    scale_y: float = 1.0
    is_primary: bool = False


@dataclass(frozen=True)
class ScreenObservation:
    """Snapshot metadata returned by a screen adapter."""

    screenshot_path: Path | None = None
    size: tuple[int, int] = (0, 0)
    active_window_title: str | None = None
    monitor: MonitorInfo | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)
    metadata: dict[str, object] = field(default_factory=dict)


class ScreenUnavailableError(RuntimeError):
    """Raised when the desktop cannot be observed safely."""


class ScreenObserver(Protocol):
    """Interface for screen capture adapters."""

    def observe(self, config: RuntimeConfig) -> ScreenObservation: ...


class StaticScreenObserver(ScreenObserver):
    """Screen observer used by tests and dry architecture checks."""

    def __init__(self, observation: ScreenObservation | None = None) -> None:
        self._observation = observation or ScreenObservation()

    def observe(self, config: RuntimeConfig) -> ScreenObservation:
        _ = config
        return self._observation


class MssScreenObserver(ScreenObserver):
    """Captures primary-monitor screenshots through the local `mss` backend."""

    def observe(self, config: RuntimeConfig) -> ScreenObservation:
        ensure_desktop_available()
        monitors = self.detect_monitors()
        if not monitors:
            raise ScreenUnavailableError("no monitors were detected")

        monitor = (
            monitors[0] if config.primary_monitor_only else _combined_monitor(monitors)
        )
        warnings = _primary_monitor_warnings(monitors, config)
        screenshot_path = self.capture_region(
            Bounds(0, 0, monitor.width, monitor.height),
            monitor,
            config,
        )

        return ScreenObservation(
            screenshot_path=screenshot_path,
            size=(monitor.width, monitor.height),
            active_window_title=detect_active_window_title(),
            monitor=monitor,
            warnings=warnings,
            metadata={"monitor_count": len(monitors)},
        )

    def detect_monitors(self) -> tuple[MonitorInfo, ...]:
        mss_module = import_module("mss")
        dpi_scale = detect_windows_dpi_scale()
        with mss_module.mss() as screen_capture:
            raw_monitors = cast(list[dict[str, int]], screen_capture.monitors[1:])

        return tuple(
            MonitorInfo(
                left=monitor["left"],
                top=monitor["top"],
                width=monitor["width"],
                height=monitor["height"],
                scale_x=dpi_scale[0],
                scale_y=dpi_scale[1],
                is_primary=index == 0,
            )
            for index, monitor in enumerate(raw_monitors)
        )

    def capture_region(
        self,
        region: Bounds,
        monitor: MonitorInfo,
        config: RuntimeConfig,
    ) -> Path | None:
        if not config.save_screenshots:
            return None

        mss_module = import_module("mss")
        tools_module = import_module("mss.tools")
        to_png = cast(Any, tools_module.to_png)
        capture_box = {
            "left": monitor.left + region.x,
            "top": monitor.top + region.y,
            "width": region.width,
            "height": region.height,
        }
        try:
            with mss_module.mss() as screen_capture:
                screenshot = screen_capture.grab(capture_box)
        except Exception as exc:
            raise ScreenUnavailableError(
                "desktop session is unavailable, locked, or blocked",
            ) from exc

        screenshot_dir = config.trace_root / "screenshots"
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = screenshot_dir / _screenshot_name()
        to_png(screenshot.bgra, screenshot.size, str(screenshot_path))
        return screenshot_path

    def capture_active_window_region(
        self,
        active_window_bounds: Bounds,
        monitor: MonitorInfo,
        config: RuntimeConfig,
    ) -> Path | None:
        return self.capture_region(active_window_bounds, monitor, config)


def screenshot_point_to_physical(
    point: tuple[int, int],
    monitor: MonitorInfo,
) -> tuple[int, int]:
    # Screenshot coordinates are scaled back into physical mouse coordinates.
    return (
        monitor.left + round(point[0] * monitor.scale_x),
        monitor.top + round(point[1] * monitor.scale_y),
    )


def physical_point_to_screenshot(
    point: tuple[int, int],
    monitor: MonitorInfo,
) -> tuple[int, int]:
    # Physical mouse coordinates are normalized into screenshot pixel space.
    return (
        round((point[0] - monitor.left) / monitor.scale_x),
        round((point[1] - monitor.top) / monitor.scale_y),
    )


def screenshot_bounds_to_physical(bounds: Bounds, monitor: MonitorInfo) -> Bounds:
    left, top = screenshot_point_to_physical((bounds.x, bounds.y), monitor)
    width = round(bounds.width * monitor.scale_x)
    height = round(bounds.height * monitor.scale_y)
    return Bounds(x=left, y=top, width=width, height=height)


def detect_windows_dpi_scale() -> tuple[float, float]:
    if sys.platform != "win32":
        return (1.0, 1.0)
    try:
        user32 = ctypes.windll.user32
        dpi = int(user32.GetDpiForSystem())
    except Exception:
        return (1.0, 1.0)
    scale = dpi / 96
    return (scale, scale)


def detect_active_window_title() -> str | None:
    """Read the current Windows foreground-window title when available."""

    if sys.platform != "win32":
        return None
    try:
        user32 = ctypes.windll.user32
        foreground_window = int(user32.GetForegroundWindow())
        if foreground_window == 0:
            return None
        length = int(user32.GetWindowTextLengthW(foreground_window))
        if length <= 0:
            return None
        buffer = ctypes.create_unicode_buffer(length + 1)
        copied = int(
            user32.GetWindowTextW(foreground_window, buffer, length + 1),
        )
    except Exception:
        return None
    if copied <= 0:
        return None
    return buffer.value or None


def ensure_desktop_available() -> None:
    if sys.platform != "win32":
        return
    try:
        foreground_window = int(ctypes.windll.user32.GetForegroundWindow())
    except Exception as exc:
        raise ScreenUnavailableError(
            "unable to inspect Windows desktop session",
        ) from exc
    if foreground_window == 0:
        raise ScreenUnavailableError("desktop session appears locked or unavailable")


def _primary_monitor_warnings(
    monitors: tuple[MonitorInfo, ...],
    config: RuntimeConfig,
) -> tuple[str, ...]:
    if config.primary_monitor_only and len(monitors) > 1:
        return ("multiple monitors detected; v1 is using the primary monitor only",)
    return ()


def _combined_monitor(monitors: tuple[MonitorInfo, ...]) -> MonitorInfo:
    left = min(monitor.left for monitor in monitors)
    top = min(monitor.top for monitor in monitors)
    right = max(monitor.left + monitor.width for monitor in monitors)
    bottom = max(monitor.top + monitor.height for monitor in monitors)
    return MonitorInfo(left=left, top=top, width=right - left, height=bottom - top)


def _screenshot_name() -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    return f"screen-{timestamp}.png"
