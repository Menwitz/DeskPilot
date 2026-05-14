"""Runtime configuration contracts and defaults."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class RuntimeConfig:
    """Validated runtime settings used by the execution pipeline."""

    default_timeout_seconds: float = 30.0
    confidence_threshold: float = 0.8
    max_steps: int = 100
    max_retries_per_step: int = 1
    max_runtime_seconds: float = 600.0
    trace_root: Path = Path("traces")
    save_screenshots: bool = True
    save_ocr_text: bool = True
    allowed_windows: tuple[str, ...] = field(default_factory=tuple)
    emergency_stop_hotkey: str = "ctrl+alt+esc"
    primary_monitor_only: bool = True


class ConfigLoader(Protocol):
    """Interface for config file loaders."""

    def load(self, config_path: Path | None) -> RuntimeConfig: ...


class StaticConfigLoader(ConfigLoader):
    """Config loader used by tests and simple embedded runs."""

    def __init__(self, config: RuntimeConfig | None = None) -> None:
        self._config = config or RuntimeConfig()

    def load(self, config_path: Path | None) -> RuntimeConfig:
        _ = config_path
        return self._config
