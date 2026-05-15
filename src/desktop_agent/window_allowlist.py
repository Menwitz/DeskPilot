"""Active-window allowlist matching shared by planner and actuator guards."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

REGEX_PREFIX = "regex:"


class WindowAllowlistError(ValueError):
    """Raised when a window allowlist pattern cannot be evaluated safely."""


def effective_allowed_windows(
    task_allowed_windows: Sequence[str],
    runtime_allowed_windows: Sequence[str],
) -> tuple[str, ...]:
    """Return the de-duplicated allowlist used by planner and actuator checks."""

    return tuple(dict.fromkeys((*task_allowed_windows, *runtime_allowed_windows)))


def window_title_matches(
    active_title: str | None,
    allowed_windows: Sequence[str],
) -> bool:
    """Return whether an active window title is covered by an allowlist entry."""

    if not active_title:
        return False
    return any(
        _window_pattern_matches(active_title, pattern) for pattern in allowed_windows
    )


def window_allowlist_errors(
    patterns: Iterable[str],
    field_name: str = "allowed_windows",
) -> list[str]:
    """Validate window patterns without needing a live active-window title."""

    errors: list[str] = []
    for pattern in patterns:
        if not pattern.strip():
            errors.append(f"{field_name} entries must not be blank")
            continue
        if pattern.startswith(REGEX_PREFIX):
            expression = pattern.removeprefix(REGEX_PREFIX)
            if not expression.strip():
                errors.append(f"{field_name} regex entries must not be empty")
                continue
            try:
                re.compile(expression)
            except re.error as exc:
                errors.append(f"{field_name} invalid regex {pattern!r}: {exc}")
    return errors


def _window_pattern_matches(active_title: str, pattern: str) -> bool:
    if pattern.startswith(REGEX_PREFIX):
        expression = pattern.removeprefix(REGEX_PREFIX)
        try:
            return re.search(expression, active_title, flags=re.IGNORECASE) is not None
        except re.error as exc:
            raise WindowAllowlistError(
                f"invalid allowed window regex {pattern!r}: {exc}",
            ) from exc

    # Plain entries intentionally support both exact equality and title contains.
    return active_title == pattern or pattern.casefold() in active_title.casefold()
