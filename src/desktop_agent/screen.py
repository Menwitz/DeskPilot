"""Screen observation contracts and shared geometry types."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

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
class ScreenObservation:
    """Snapshot metadata returned by a screen adapter."""

    screenshot_path: Path | None = None
    size: tuple[int, int] = (0, 0)
    active_window_title: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


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
