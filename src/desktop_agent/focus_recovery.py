"""Allowed-window refocus helpers for bounded recovery paths."""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from dataclasses import dataclass
from typing import Any, Protocol, cast

from desktop_agent.config import RuntimeConfig
from desktop_agent.window_allowlist import WindowAllowlistError, window_title_matches


@dataclass(frozen=True)
class FocusRecoveryResult:
    """Result of trying to restore focus to one configured allowed window."""

    attempted: bool
    success: bool
    message: str
    before_active_window_title: str | None = None
    after_active_window_title: str | None = None
    matched_window_title: str | None = None
    allowed_windows: tuple[str, ...] = ()

    def metadata(self) -> dict[str, object]:
        return {
            "focus_recovery_attempted": self.attempted,
            "focus_recovery_success": self.success,
            "focus_recovery_message": self.message,
            "focus_recovery_before_active_window_title": (
                self.before_active_window_title
            ),
            "focus_recovery_after_active_window_title": self.after_active_window_title,
            "focus_recovery_matched_window_title": self.matched_window_title,
            "focus_recovery_allowed_windows": list(self.allowed_windows),
        }


class FocusRecoveryController(Protocol):
    """Interface for recovering focus without sending task input."""

    def refocus_allowed_window(self, config: RuntimeConfig) -> FocusRecoveryResult: ...


class NoopFocusRecoveryController(FocusRecoveryController):
    """Controller used where foreground-window changes are unavailable."""

    def refocus_allowed_window(self, config: RuntimeConfig) -> FocusRecoveryResult:
        return FocusRecoveryResult(
            attempted=False,
            success=False,
            message="focus recovery is unavailable on this platform",
            allowed_windows=config.allowed_windows,
        )


class WindowsFocusRecoveryController(FocusRecoveryController):
    """Restores focus to the first visible top-level window matching allowlist."""

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise RuntimeError("Windows focus recovery requires Windows")
        self._user32: Any = ctypes.windll.user32

    def refocus_allowed_window(self, config: RuntimeConfig) -> FocusRecoveryResult:
        before_title = self._active_window_title()
        if not config.allowed_windows:
            return FocusRecoveryResult(
                attempted=False,
                success=False,
                message="allowed_windows is required for focus recovery",
                before_active_window_title=before_title,
            )

        try:
            match = self._find_allowed_window(config.allowed_windows)
        except WindowAllowlistError as exc:
            return FocusRecoveryResult(
                attempted=False,
                success=False,
                message=str(exc),
                before_active_window_title=before_title,
                allowed_windows=config.allowed_windows,
            )
        if match is None:
            return FocusRecoveryResult(
                attempted=True,
                success=False,
                message="no visible allowed window was found",
                before_active_window_title=before_title,
                allowed_windows=config.allowed_windows,
            )

        hwnd, matched_title = match
        if self._is_iconic(hwnd):
            self._user32.ShowWindow(hwnd, _SW_RESTORE)
        self._user32.SetForegroundWindow(hwnd)
        after_title = self._active_window_title()
        success = window_title_matches(after_title, config.allowed_windows)
        return FocusRecoveryResult(
            attempted=True,
            success=success,
            message="allowed window refocused"
            if success
            else "allowed window refocus did not become foreground",
            before_active_window_title=before_title,
            after_active_window_title=after_title,
            matched_window_title=matched_title,
            allowed_windows=config.allowed_windows,
        )

    def _find_allowed_window(
        self,
        allowed_windows: tuple[str, ...],
    ) -> tuple[int, str] | None:
        matches: list[tuple[int, str]] = []

        def callback(hwnd: int, _param: int) -> bool:
            if not self._user32.IsWindowVisible(hwnd):
                return True
            title = self._window_title(hwnd)
            if title and window_title_matches(title, allowed_windows):
                matches.append((hwnd, title))
                return False
            return True

        callback_type = cast(Any, ctypes).WINFUNCTYPE(
            wintypes.BOOL,
            wintypes.HWND,
            wintypes.LPARAM,
        )
        self._user32.EnumWindows(callback_type(callback), 0)
        return matches[0] if matches else None

    def _active_window_title(self) -> str | None:
        hwnd = int(self._user32.GetForegroundWindow())
        if hwnd == 0:
            return None
        return self._window_title(hwnd)

    def _window_title(self, hwnd: int) -> str:
        length = int(self._user32.GetWindowTextLengthW(hwnd))
        buffer = ctypes.create_unicode_buffer(length + 1)
        copied = int(self._user32.GetWindowTextW(hwnd, buffer, length + 1))
        if copied <= 0:
            return ""
        return buffer.value

    def _is_iconic(self, hwnd: int) -> bool:
        return bool(self._user32.IsIconic(hwnd))


def create_platform_focus_recovery_controller() -> FocusRecoveryController:
    if sys.platform != "win32":
        return NoopFocusRecoveryController()
    return WindowsFocusRecoveryController()

_SW_RESTORE = 9
