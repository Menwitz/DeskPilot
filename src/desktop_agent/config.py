"""Runtime configuration contracts and defaults."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, cast

import yaml


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


class ConfigError(ValueError):
    """Raised when a configuration file cannot be loaded safely."""


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


class YamlConfigLoader(ConfigLoader):
    """Loads the project-level YAML config format used by the CLI."""

    def load(self, config_path: Path | None) -> RuntimeConfig:
        if config_path is None:
            return RuntimeConfig()
        if not config_path.exists():
            raise ConfigError(f"config file not found: {config_path}")

        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        if loaded is None:
            return RuntimeConfig()
        if not isinstance(loaded, dict):
            raise ConfigError("config file must contain a mapping")

        data = cast(dict[str, object], loaded)
        return RuntimeConfig(
            default_timeout_seconds=_float_value(
                data,
                "default_timeout_seconds",
                RuntimeConfig.default_timeout_seconds,
            ),
            confidence_threshold=_float_value(
                data,
                "confidence_threshold",
                RuntimeConfig.confidence_threshold,
            ),
            max_steps=_int_value(data, "max_steps", RuntimeConfig.max_steps),
            max_retries_per_step=_int_value(
                data,
                "max_retries_per_step",
                RuntimeConfig.max_retries_per_step,
            ),
            max_runtime_seconds=_float_value(
                data,
                "max_runtime_seconds",
                RuntimeConfig.max_runtime_seconds,
            ),
            trace_root=Path(str(data.get("trace_root", RuntimeConfig.trace_root))),
            save_screenshots=_bool_value(
                data,
                "save_screenshots",
                RuntimeConfig.save_screenshots,
            ),
            save_ocr_text=_bool_value(
                data,
                "save_ocr_text",
                RuntimeConfig.save_ocr_text,
            ),
            allowed_windows=_string_tuple(data.get("allowed_windows", ())),
            emergency_stop_hotkey=str(
                data.get(
                    "emergency_stop_hotkey",
                    RuntimeConfig.emergency_stop_hotkey,
                ),
            ),
            primary_monitor_only=_bool_value(
                data,
                "primary_monitor_only",
                RuntimeConfig.primary_monitor_only,
            ),
        )


def _float_value(data: dict[str, object], key: str, default: float) -> float:
    value = data.get(key, default)
    if not isinstance(value, int | float):
        raise ConfigError(f"{key} must be a number")
    return float(value)


def _int_value(data: dict[str, object], key: str, default: int) -> int:
    value = data.get(key, default)
    if not isinstance(value, int):
        raise ConfigError(f"{key} must be an integer")
    return value


def _bool_value(data: dict[str, object], key: str, default: bool) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise ConfigError(f"{key} must be true or false")
    return value


def _string_tuple(value: object) -> tuple[str, ...]:
    if value in (None, ()):
        return ()
    if not isinstance(value, list):
        raise ConfigError("allowed_windows must be a list of strings")
    if not all(isinstance(item, str) for item in value):
        raise ConfigError("allowed_windows must be a list of strings")
    return tuple(value)
