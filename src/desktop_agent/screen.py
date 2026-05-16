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
            metadata=_desktop_context_metadata(len(monitors)),
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
        # `mss.tools.to_png` expects RGB bytes and uses a keyword-only output path.
        to_png(screenshot.rgb, screenshot.size, output=str(screenshot_path))
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
        user32 = _windows_user32()
        dpi = int(user32.GetDpiForSystem())
    except Exception:
        return (1.0, 1.0)
    scale = dpi / 96
    return (scale, scale)


def detect_active_window_title() -> str | None:
    """Read the current Windows foreground-window title when available."""

    foreground_window = _foreground_window_handle()
    if foreground_window is None:
        return None
    return _window_text(foreground_window)


def detect_active_window_process() -> dict[str, object] | None:
    """Read foreground process metadata without capturing command-line content."""

    if sys.platform != "win32":
        return None
    foreground_window = _foreground_window_handle()
    if foreground_window is None:
        return None
    try:
        process_id = ctypes.c_ulong()
        _windows_user32().GetWindowThreadProcessId(
            foreground_window,
            ctypes.byref(process_id),
        )
    except Exception:
        return None
    if process_id.value == 0:
        return None
    metadata: dict[str, object] = {"process_id": int(process_id.value)}
    process_name = _process_name_from_pid(int(process_id.value))
    if process_name:
        metadata["process_name"] = process_name
    return metadata


def detect_focused_element() -> dict[str, object] | None:
    """Read the focused Win32 control inside the foreground window when possible."""

    if sys.platform != "win32":
        return None
    foreground_window = _foreground_window_handle()
    if foreground_window is None:
        return None
    try:
        thread_id = int(
            _windows_user32().GetWindowThreadProcessId(foreground_window, None)
        )
        gui_info = _GuiThreadInfo()
        gui_info.cbSize = ctypes.sizeof(_GuiThreadInfo)
        if not _windows_user32().GetGUIThreadInfo(
            thread_id,
            ctypes.byref(gui_info),
        ):
            return None
    except Exception:
        return None

    focus_handle = _handle_value(gui_info.hwndFocus)
    if focus_handle is None:
        return None
    metadata: dict[str, object] = {"control_handle": focus_handle}
    control_text = _window_text(focus_handle)
    class_name = _window_class_name(focus_handle)
    if control_text:
        metadata["name"] = control_text
    if class_name:
        metadata["class_name"] = class_name
    return metadata


def ensure_desktop_available() -> None:
    if sys.platform != "win32":
        return
    try:
        foreground_window = int(_windows_user32().GetForegroundWindow())
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


def _desktop_context_metadata(monitor_count: int) -> dict[str, object]:
    metadata: dict[str, object] = {"monitor_count": monitor_count}
    active_window_process = detect_active_window_process()
    if active_window_process is not None:
        metadata["active_window_process"] = active_window_process
    focused_element = detect_focused_element()
    if focused_element is not None:
        metadata["focused_element"] = focused_element
    return metadata


class _Rect(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class _GuiThreadInfo(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_ulong),
        ("flags", ctypes.c_ulong),
        ("hwndActive", ctypes.c_void_p),
        ("hwndFocus", ctypes.c_void_p),
        ("hwndCapture", ctypes.c_void_p),
        ("hwndMenuOwner", ctypes.c_void_p),
        ("hwndMoveSize", ctypes.c_void_p),
        ("hwndCaret", ctypes.c_void_p),
        ("rcCaret", _Rect),
    ]


def _foreground_window_handle() -> int | None:
    if sys.platform != "win32":
        return None
    try:
        foreground_window = int(_windows_user32().GetForegroundWindow())
    except Exception:
        return None
    return foreground_window or None


def _window_text(window_handle: int) -> str | None:
    try:
        user32 = _windows_user32()
        length = int(user32.GetWindowTextLengthW(window_handle))
        if length <= 0:
            return None
        buffer = ctypes.create_unicode_buffer(length + 1)
        copied = int(user32.GetWindowTextW(window_handle, buffer, length + 1))
    except Exception:
        return None
    if copied <= 0:
        return None
    return buffer.value or None


def _window_class_name(window_handle: int) -> str | None:
    try:
        buffer = ctypes.create_unicode_buffer(256)
        copied = int(_windows_user32().GetClassNameW(window_handle, buffer, 256))
    except Exception:
        return None
    if copied <= 0:
        return None
    return buffer.value or None


def _process_name_from_pid(process_id: int) -> str | None:
    if sys.platform != "win32":
        return None
    process_handle = None
    try:
        kernel32 = _windows_kernel32()
        process_handle = kernel32.OpenProcess(0x1000, False, process_id)
        if not process_handle:
            return None
        buffer = ctypes.create_unicode_buffer(260)
        size = ctypes.c_ulong(len(buffer))
        if not kernel32.QueryFullProcessImageNameW(
            process_handle,
            0,
            buffer,
            ctypes.byref(size),
        ):
            return None
    except Exception:
        return None
    finally:
        if process_handle:
            _windows_kernel32().CloseHandle(process_handle)
    return buffer.value.rsplit("\\", 1)[-1] or None


def _handle_value(handle: object) -> int | None:
    if handle is None:
        return None
    if isinstance(handle, int):
        value = handle
    else:
        raw_value = getattr(handle, "value", None)
        if not isinstance(raw_value, int):
            return None
        value = raw_value
    return value or None


def _windows_user32() -> Any:
    return cast(Any, ctypes).windll.user32


def _windows_kernel32() -> Any:
    return cast(Any, ctypes).windll.kernel32


def _screenshot_name() -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    return f"screen-{timestamp}.png"
