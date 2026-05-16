"""Runtime configuration contracts and defaults."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Protocol, cast

import yaml

from desktop_agent.window_allowlist import window_allowlist_errors

EXECUTION_PERSONAS: frozenset[str] = frozenset({"careful", "normal", "fast"})
SAMPLING_DISTRIBUTIONS: frozenset[str] = frozenset({"uniform", "center_weighted"})
ACTIVITY_PROFILE_NAMES: frozenset[str] = frozenset(
    {"focused", "careful", "background_assist", "batch_work"},
)
POLICY_PRESETS: frozenset[str] = frozenset(
    {"strict_qa", "personal_automation", "exploratory_testing"},
)


@dataclass(frozen=True)
class ExecutionProfile:
    """Optional bounded timing profile for natural-feeling local automation."""

    activity_profile: str | None = None
    persona: str = "normal"
    enabled: bool = False
    action_delay_seconds: tuple[float, float] = (0.0, 0.0)
    retry_delay_seconds: tuple[float, float] = (0.0, 0.0)
    action_delay_distribution: str = "uniform"
    retry_delay_distribution: str = "uniform"
    action_variant_distribution: str = "uniform"
    hesitation_probability: float = 0.0
    movement_smoothness: float = 0.0
    keyboard_interval_seconds: tuple[float, float] = (0.0, 0.0)
    scroll_interval_seconds: tuple[float, float] = (0.0, 0.0)
    random_seed: int | None = None


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
    policy_preset: str = "personal_automation"
    require_operator_approval: bool = False
    execution_profile: ExecutionProfile = field(default_factory=ExecutionProfile)
    confirmed_steps: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ConfigOverrides:
    """Optional config layer used for task-level and CLI overrides."""

    default_timeout_seconds: float | None = None
    confidence_threshold: float | None = None
    max_steps: int | None = None
    max_retries_per_step: int | None = None
    max_runtime_seconds: float | None = None
    trace_root: Path | None = None
    save_screenshots: bool | None = None
    save_ocr_text: bool | None = None
    allowed_windows: tuple[str, ...] | None = None
    emergency_stop_hotkey: str | None = None
    primary_monitor_only: bool | None = None
    policy_preset: str | None = None
    require_operator_approval: bool | None = None
    execution_profile: ExecutionProfile | None = None
    confirmed_steps: tuple[str, ...] | None = None


class ConfigError(ValueError):
    """Raised when a configuration file cannot be loaded safely."""


ACTIVITY_PROFILE_PRESETS: dict[str, ExecutionProfile] = {
    "focused": ExecutionProfile(
        activity_profile="focused",
        persona="normal",
        enabled=True,
        action_delay_seconds=(0.08, 0.25),
        retry_delay_seconds=(0.25, 0.9),
        action_delay_distribution="center_weighted",
        retry_delay_distribution="center_weighted",
        action_variant_distribution="uniform",
        hesitation_probability=0.05,
        movement_smoothness=0.72,
        keyboard_interval_seconds=(0.01, 0.03),
        scroll_interval_seconds=(0.02, 0.06),
    ),
    "careful": ExecutionProfile(
        activity_profile="careful",
        persona="careful",
        enabled=True,
        action_delay_seconds=(0.18, 0.65),
        retry_delay_seconds=(0.8, 2.4),
        action_delay_distribution="center_weighted",
        retry_delay_distribution="center_weighted",
        action_variant_distribution="center_weighted",
        hesitation_probability=0.2,
        movement_smoothness=0.86,
        keyboard_interval_seconds=(0.025, 0.07),
        scroll_interval_seconds=(0.05, 0.12),
    ),
    "background_assist": ExecutionProfile(
        activity_profile="background_assist",
        persona="careful",
        enabled=True,
        action_delay_seconds=(0.45, 1.4),
        retry_delay_seconds=(2.0, 6.0),
        action_delay_distribution="center_weighted",
        retry_delay_distribution="center_weighted",
        action_variant_distribution="center_weighted",
        hesitation_probability=0.25,
        movement_smoothness=0.9,
        keyboard_interval_seconds=(0.04, 0.12),
        scroll_interval_seconds=(0.08, 0.18),
    ),
    "batch_work": ExecutionProfile(
        activity_profile="batch_work",
        persona="fast",
        enabled=True,
        action_delay_seconds=(0.04, 0.16),
        retry_delay_seconds=(0.2, 0.8),
        action_delay_distribution="uniform",
        retry_delay_distribution="center_weighted",
        action_variant_distribution="uniform",
        hesitation_probability=0.02,
        movement_smoothness=0.62,
        keyboard_interval_seconds=(0.005, 0.02),
        scroll_interval_seconds=(0.01, 0.04),
    ),
}


def execution_profile_for_activity(activity_profile: str) -> ExecutionProfile:
    """Return the built-in bounded timing preset for a named activity profile."""
    if activity_profile not in ACTIVITY_PROFILE_PRESETS:
        raise ConfigError(
            "execution_profile.activity_profile must be focused, careful, "
            "background_assist, or batch_work",
        )
    return ACTIVITY_PROFILE_PRESETS[activity_profile]


class ConfigLoader(Protocol):
    """Interface for config file loaders."""

    def load(self, config_path: Path | None) -> RuntimeConfig: ...


class StaticConfigLoader(ConfigLoader):
    """Config loader used by tests and simple embedded runs."""

    def __init__(self, config: RuntimeConfig | None = None) -> None:
        self._config = config or RuntimeConfig()

    def load(self, config_path: Path | None) -> RuntimeConfig:
        _ = config_path
        validate_config(self._config)
        return self._config


class YamlConfigLoader(ConfigLoader):
    """Loads the project-level YAML config format used by the CLI."""

    def load(self, config_path: Path | None) -> RuntimeConfig:
        if config_path is None:
            config = RuntimeConfig()
            validate_config(config)
            return config
        if not config_path.exists():
            raise ConfigError(f"config file not found: {config_path}")

        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        if loaded is None:
            config = RuntimeConfig()
            validate_config(config)
            return config
        if not isinstance(loaded, dict):
            raise ConfigError("config file must contain a mapping")

        data = cast(dict[str, object], loaded)
        config = apply_config_overrides(
            RuntimeConfig(),
            config_overrides_from_mapping(data),
        )
        validate_config(config)
        return config


def resolve_runtime_config(
    file_config: RuntimeConfig,
    task_overrides: ConfigOverrides | None = None,
    cli_overrides: ConfigOverrides | None = None,
) -> RuntimeConfig:
    """Resolve config precedence: CLI > task YAML > config file > defaults."""

    config = apply_config_overrides(file_config, task_overrides or ConfigOverrides())
    config = apply_config_overrides(config, cli_overrides or ConfigOverrides())
    validate_config(config)
    return config


def apply_config_overrides(
    config: RuntimeConfig,
    overrides: ConfigOverrides,
) -> RuntimeConfig:
    return replace(
        config,
        default_timeout_seconds=_coalesce(
            overrides.default_timeout_seconds,
            config.default_timeout_seconds,
        ),
        confidence_threshold=_coalesce(
            overrides.confidence_threshold,
            config.confidence_threshold,
        ),
        max_steps=_coalesce(overrides.max_steps, config.max_steps),
        max_retries_per_step=_coalesce(
            overrides.max_retries_per_step,
            config.max_retries_per_step,
        ),
        max_runtime_seconds=_coalesce(
            overrides.max_runtime_seconds,
            config.max_runtime_seconds,
        ),
        trace_root=_coalesce(overrides.trace_root, config.trace_root),
        save_screenshots=_coalesce(
            overrides.save_screenshots,
            config.save_screenshots,
        ),
        save_ocr_text=_coalesce(overrides.save_ocr_text, config.save_ocr_text),
        allowed_windows=_coalesce(overrides.allowed_windows, config.allowed_windows),
        emergency_stop_hotkey=_coalesce(
            overrides.emergency_stop_hotkey,
            config.emergency_stop_hotkey,
        ),
        primary_monitor_only=_coalesce(
            overrides.primary_monitor_only,
            config.primary_monitor_only,
        ),
        policy_preset=_coalesce(overrides.policy_preset, config.policy_preset),
        require_operator_approval=_coalesce(
            overrides.require_operator_approval,
            config.require_operator_approval,
        ),
        execution_profile=_coalesce(
            overrides.execution_profile,
            config.execution_profile,
        ),
        confirmed_steps=_coalesce(overrides.confirmed_steps, config.confirmed_steps),
    )


def config_overrides_from_mapping(data: dict[str, object]) -> ConfigOverrides:
    return ConfigOverrides(
        default_timeout_seconds=_optional_float(data, "default_timeout_seconds"),
        confidence_threshold=_optional_float(data, "confidence_threshold"),
        max_steps=_optional_int(data, "max_steps"),
        max_retries_per_step=_optional_int(data, "max_retries_per_step"),
        max_runtime_seconds=_optional_float(data, "max_runtime_seconds"),
        trace_root=_optional_path(data, "trace_root"),
        save_screenshots=_optional_bool(data, "save_screenshots"),
        save_ocr_text=_optional_bool(data, "save_ocr_text"),
        allowed_windows=_optional_string_tuple(data, "allowed_windows"),
        emergency_stop_hotkey=_optional_str(data, "emergency_stop_hotkey"),
        primary_monitor_only=_optional_bool(data, "primary_monitor_only"),
        policy_preset=_optional_str(data, "policy_preset"),
        require_operator_approval=_optional_bool(data, "require_operator_approval"),
        execution_profile=_optional_execution_profile(data, "execution_profile"),
        confirmed_steps=_optional_string_tuple(data, "confirmed_steps"),
    )


def validate_config(config: RuntimeConfig) -> None:
    errors: list[str] = []
    if config.default_timeout_seconds <= 0:
        errors.append("default_timeout_seconds must be greater than zero")
    if config.confidence_threshold <= 0 or config.confidence_threshold > 1:
        errors.append("confidence_threshold must be greater than 0 and at most 1")
    if config.max_steps <= 0:
        errors.append("max_steps must be greater than zero")
    if config.max_retries_per_step < 0:
        errors.append("max_retries_per_step must not be negative")
    if config.max_runtime_seconds <= 0:
        errors.append("max_runtime_seconds must be greater than zero")
    if not str(config.trace_root):
        errors.append("trace_root is required")
    if not config.emergency_stop_hotkey.strip():
        errors.append("emergency_stop_hotkey is required")
    errors.extend(window_allowlist_errors(config.allowed_windows))
    if any(not step_id.strip() for step_id in config.confirmed_steps):
        errors.append("confirmed_steps entries must not be blank")
    if config.policy_preset not in POLICY_PRESETS:
        errors.append(
            "policy_preset must be strict_qa, personal_automation, "
            "or exploratory_testing",
        )
    errors.extend(_validate_execution_profile(config.execution_profile))

    if errors:
        raise ConfigError("; ".join(errors))


def _coalesce[T](value: T | None, fallback: T) -> T:
    return fallback if value is None else value


def _optional_float(data: dict[str, object], key: str) -> float | None:
    if key not in data:
        return None
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ConfigError(f"{key} must be a number")
    return float(value)


def _optional_int(data: dict[str, object], key: str) -> int | None:
    if key not in data:
        return None
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{key} must be an integer")
    return value


def _optional_bool(data: dict[str, object], key: str) -> bool | None:
    if key not in data:
        return None
    value = data[key]
    if not isinstance(value, bool):
        raise ConfigError(f"{key} must be true or false")
    return value


def _optional_str(data: dict[str, object], key: str) -> str | None:
    if key not in data:
        return None
    value = data[key]
    if not isinstance(value, str):
        raise ConfigError(f"{key} must be a string")
    return value


def _optional_path(data: dict[str, object], key: str) -> Path | None:
    value = _optional_str(data, key)
    return None if value is None else Path(value)


def _optional_string_tuple(
    data: dict[str, object],
    key: str,
) -> tuple[str, ...] | None:
    if key not in data:
        return None
    value = data[key]
    if value in (None, ()):
        return None
    if not isinstance(value, list):
        raise ConfigError(f"{key} must be a list of strings")
    if not all(isinstance(item, str) for item in value):
        raise ConfigError(f"{key} must be a list of strings")
    return tuple(value)


def _optional_execution_profile(
    data: dict[str, object],
    key: str,
) -> ExecutionProfile | None:
    if key not in data:
        return None
    value = data[key]
    if not isinstance(value, dict):
        raise ConfigError("execution_profile must be a mapping")

    profile = cast(dict[str, object], value)
    activity_profile = _optional_activity_profile(profile, "activity_profile")
    defaults = (
        execution_profile_for_activity(activity_profile)
        if activity_profile is not None
        else ExecutionProfile()
    )
    return ExecutionProfile(
        activity_profile=activity_profile,
        persona=_optional_str_with_default(profile, "persona", defaults.persona),
        enabled=_optional_bool_with_default(profile, "enabled", defaults.enabled),
        action_delay_seconds=_optional_seconds_pair(
            profile,
            "action_delay_seconds",
            defaults.action_delay_seconds,
        ),
        retry_delay_seconds=_optional_seconds_pair(
            profile,
            "retry_delay_seconds",
            defaults.retry_delay_seconds,
        ),
        action_delay_distribution=_optional_str_with_default(
            profile,
            "action_delay_distribution",
            defaults.action_delay_distribution,
        ),
        retry_delay_distribution=_optional_str_with_default(
            profile,
            "retry_delay_distribution",
            defaults.retry_delay_distribution,
        ),
        action_variant_distribution=_optional_str_with_default(
            profile,
            "action_variant_distribution",
            defaults.action_variant_distribution,
        ),
        hesitation_probability=_optional_float_with_default(
            profile,
            "hesitation_probability",
            defaults.hesitation_probability,
        ),
        movement_smoothness=_optional_float_with_default(
            profile,
            "movement_smoothness",
            defaults.movement_smoothness,
        ),
        keyboard_interval_seconds=_optional_seconds_pair(
            profile,
            "keyboard_interval_seconds",
            defaults.keyboard_interval_seconds,
        ),
        scroll_interval_seconds=_optional_seconds_pair(
            profile,
            "scroll_interval_seconds",
            defaults.scroll_interval_seconds,
        ),
        random_seed=_optional_seed(profile, "random_seed"),
    )


def _optional_bool_with_default(
    data: dict[str, object],
    key: str,
    fallback: bool,
) -> bool:
    value = _optional_bool(data, key)
    return fallback if value is None else value


def _optional_str_with_default(
    data: dict[str, object],
    key: str,
    fallback: str,
) -> str:
    value = _optional_str(data, key)
    return fallback if value is None else value


def _optional_activity_profile(
    data: dict[str, object],
    key: str,
) -> str | None:
    value = _optional_str(data, key)
    if value is None:
        return None
    if value not in ACTIVITY_PROFILE_NAMES:
        raise ConfigError(
            "execution_profile.activity_profile must be focused, careful, "
            "background_assist, or batch_work",
        )
    return value


def _optional_float_with_default(
    data: dict[str, object],
    key: str,
    fallback: float,
) -> float:
    value = _optional_float(data, key)
    return fallback if value is None else value


def _optional_seconds_pair(
    data: dict[str, object],
    key: str,
    fallback: tuple[float, float],
) -> tuple[float, float]:
    if key not in data:
        return fallback
    value = data[key]
    if not isinstance(value, list) or len(value) != 2:
        raise ConfigError(f"{key} must be a two-item list of numbers")
    lower, upper = value
    if (
        isinstance(lower, bool)
        or isinstance(upper, bool)
        or not isinstance(lower, int | float)
        or not isinstance(upper, int | float)
    ):
        raise ConfigError(f"{key} must be a two-item list of numbers")
    return (float(lower), float(upper))


def _optional_seed(data: dict[str, object], key: str) -> int | None:
    if key not in data:
        return None
    value = data[key]
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError("random_seed must be an integer")
    return value


def _validate_execution_profile(profile: ExecutionProfile) -> list[str]:
    errors: list[str] = []
    if (
        profile.activity_profile is not None
        and profile.activity_profile not in ACTIVITY_PROFILE_NAMES
    ):
        errors.append(
            "execution_profile.activity_profile must be focused, careful, "
            "background_assist, or batch_work",
        )
    if profile.persona not in EXECUTION_PERSONAS:
        errors.append("execution_profile.persona must be careful, normal, or fast")
    if profile.action_delay_distribution not in SAMPLING_DISTRIBUTIONS:
        errors.append(
            "execution_profile.action_delay_distribution must be uniform "
            "or center_weighted",
        )
    if profile.retry_delay_distribution not in SAMPLING_DISTRIBUTIONS:
        errors.append(
            "execution_profile.retry_delay_distribution must be uniform "
            "or center_weighted",
        )
    if profile.action_variant_distribution not in SAMPLING_DISTRIBUTIONS:
        errors.append(
            "execution_profile.action_variant_distribution must be uniform "
            "or center_weighted",
        )
    errors.extend(
        _validate_seconds_pair(
            profile.action_delay_seconds,
            "execution_profile.action_delay_seconds",
        )
    )
    errors.extend(
        _validate_seconds_pair(
            profile.retry_delay_seconds,
            "execution_profile.retry_delay_seconds",
        )
    )
    errors.extend(
        _validate_seconds_pair(
            profile.keyboard_interval_seconds,
            "execution_profile.keyboard_interval_seconds",
        )
    )
    errors.extend(
        _validate_seconds_pair(
            profile.scroll_interval_seconds,
            "execution_profile.scroll_interval_seconds",
        )
    )
    if profile.hesitation_probability < 0 or profile.hesitation_probability > 1:
        errors.append(
            "execution_profile.hesitation_probability must be between 0 and 1",
        )
    if profile.movement_smoothness < 0 or profile.movement_smoothness > 1:
        errors.append("execution_profile.movement_smoothness must be between 0 and 1")
    return errors


def _validate_seconds_pair(
    value: tuple[float, float],
    field_name: str,
) -> list[str]:
    lower, upper = value
    if lower < 0 or upper < 0:
        return [f"{field_name} values must not be negative"]
    if lower > upper:
        return [f"{field_name} lower bound must not exceed upper bound"]
    return []
