"""Task DSL contracts shared by loaders, validators, and the planner."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, cast

import yaml

from desktop_agent.config import (
    ConfigOverrides,
    RuntimeConfig,
    config_overrides_from_mapping,
)


class TaskValidationError(ValueError):
    """Raised when a task definition fails platform-neutral validation."""


SUPPORTED_ACTIONS: frozenset[str] = frozenset(
    {
        "click_text",
        "click_image",
        "click_uia",
        "type_text",
        "press_key",
        "scroll",
        "scroll_until",
        "wait_for",
        "assert_visible",
        "branch_if_visible",
        "drag",
    },
)

SUPPORTED_VERIFICATION_TYPES: frozenset[str] = frozenset(
    {
        "visible_text",
        "not_visible_text",
        "visible_image",
        "focused",
        "window_title_contains",
        "uia_element_exists",
    },
)

TASK_STEP_CATEGORIES: frozenset[str] = frozenset(
    {
        "navigation",
        "recognition",
        "data_entry",
        "verification",
        "submission",
    },
)

DEFAULT_CATEGORY_BY_ACTION: dict[str, str] = {
    "type_text": "data_entry",
    "wait_for": "recognition",
    "assert_visible": "recognition",
    "branch_if_visible": "recognition",
    "press_key": "navigation",
    "scroll": "navigation",
    "scroll_until": "navigation",
    "drag": "navigation",
    "click_text": "navigation",
    "click_image": "navigation",
    "click_uia": "navigation",
}

SAFE_ACTION_VARIANTS_BY_ACTION: dict[str, frozenset[str]] = {
    "click_text": frozenset({"click_text", "click_uia"}),
    "click_uia": frozenset({"click_text", "click_uia"}),
}


@dataclass(frozen=True)
class VerificationDefinition:
    """Verification attached to a task step."""

    type: str
    text: str | None = None
    image: Path | None = None


@dataclass(frozen=True)
class TaskRegion:
    """Optional task-region restriction in screenshot coordinate space."""

    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class TaskStep:
    """Single deterministic action in a DeskPilot task."""

    id: str
    action: str
    target: str | None = None
    text: str | None = None
    image: Path | None = None
    region: TaskRegion | None = None
    verify: VerificationDefinition | None = None
    timeout_seconds: float | None = None
    retry: int | None = None
    on_failure: str | None = None
    requires_confirmation: bool = False
    category: str | None = None
    entropy_budget: float | None = None
    safe_action_variants: tuple[str, ...] = ()


@dataclass(frozen=True)
class TaskDefinition:
    """Validated task loaded from YAML or an in-memory fixture."""

    name: str
    allowed_windows: tuple[str, ...]
    timeout_seconds: float
    steps: tuple[TaskStep, ...]
    config_overrides: ConfigOverrides = field(default_factory=ConfigOverrides)
    entropy_budget: float | None = None


class TaskLoader(Protocol):
    """Interface for task source adapters."""

    def load(self, task_path: Path) -> TaskDefinition: ...


class StaticTaskLoader(TaskLoader):
    """Task loader used by tests and embedded dry runs."""

    def __init__(self, task: TaskDefinition) -> None:
        self._task = task

    def load(self, task_path: Path) -> TaskDefinition:
        _ = task_path
        return self._task


class YamlTaskLoader(TaskLoader):
    """Loads the YAML task shape accepted by the CLI."""

    def load(self, task_path: Path) -> TaskDefinition:
        if not task_path.exists():
            raise TaskValidationError(f"task file not found: {task_path}")

        loaded = yaml.safe_load(task_path.read_text(encoding="utf-8"))
        data = _mapping(loaded, "task file must contain a mapping")
        steps_value = data.get("steps", ())
        if not isinstance(steps_value, list):
            raise TaskValidationError("steps must be a list")
        config_value = data.get("config")
        config_overrides = ConfigOverrides()
        if config_value is not None:
            config_data = _mapping(config_value, "config must be a mapping")
            config_overrides = config_overrides_from_mapping(dict(config_data))

        return TaskDefinition(
            name=str(data.get("name", "")),
            allowed_windows=_string_tuple(data.get("allowed_windows", ())),
            timeout_seconds=_float_value(data.get("timeout_seconds", 0)),
            steps=tuple(
                _step_from_mapping(item, task_path.parent) for item in steps_value
            ),
            config_overrides=config_overrides,
            entropy_budget=_optional_float(
                data.get("entropy_budget"),
                "entropy_budget",
            ),
        )


class TaskValidator(Protocol):
    """Interface for task validators."""

    def validate(self, task: TaskDefinition, config: RuntimeConfig) -> None: ...


class BasicTaskValidator(TaskValidator):
    """Performs the structural checks required by the architecture pipeline."""

    def validate(self, task: TaskDefinition, config: RuntimeConfig) -> None:
        errors: list[str] = []
        if not task.name:
            errors.append("task name is required")
        if not task.allowed_windows:
            errors.append("allowed_windows is required")
        if task.timeout_seconds <= 0:
            errors.append("timeout_seconds must be greater than zero")
        if task.entropy_budget is not None and task.entropy_budget < 0:
            errors.append("entropy_budget must not be negative")
        if not task.steps:
            errors.append("steps is required")
        if len(task.steps) > config.max_steps:
            errors.append("task exceeds max_steps")

        all_step_ids = {step.id for step in task.steps if step.id}
        explicit_step_entropy = 0.0
        step_ids: set[str] = set()
        for step in task.steps:
            if not step.id:
                errors.append("step id is required")
            elif step.id in step_ids:
                errors.append(f"duplicate step id: {step.id}")
            step_ids.add(step.id)

            if not step.action:
                errors.append(f"step {step.id} action is required")
            elif step.action not in SUPPORTED_ACTIONS:
                errors.append(f"unknown action: {step.action}")
            if step.category is not None and step.category not in TASK_STEP_CATEGORIES:
                errors.append(f"unknown step category: {step.category}")
            if step.entropy_budget is not None:
                if step.entropy_budget < 0:
                    errors.append(
                        f"step {step.id} entropy_budget must not be negative"
                    )
                explicit_step_entropy += step.entropy_budget
            errors.extend(_validate_safe_action_variants(step))
            if step.retry is not None and step.retry < 0:
                errors.append(f"step {step.id} retry must not be negative")
            if step.timeout_seconds is not None and step.timeout_seconds <= 0:
                errors.append(
                    f"step {step.id} timeout_seconds must be greater than zero"
                )
            if step.on_failure is not None and step.on_failure not in all_step_ids:
                errors.append(f"step {step.id} on_failure target does not exist")
            errors.extend(_validate_action_shape(step))
            errors.extend(_validate_verification_shape(step))

        if (
            task.entropy_budget is not None
            and explicit_step_entropy > task.entropy_budget
        ):
            errors.append("step entropy_budget total exceeds task entropy_budget")

        if errors:
            raise TaskValidationError("; ".join(errors))


def _step_from_mapping(value: object, task_dir: Path) -> TaskStep:
    data = _mapping(value, "each step must be a mapping")
    verify_value = data.get("verify")
    verify = None
    if verify_value is not None:
        verify = _verification_from_mapping(verify_value, task_dir)

    return TaskStep(
        id=str(data.get("id", "")),
        action=str(data.get("action", "")),
        target=_optional_str(data.get("target")),
        text=_optional_str(data.get("text")),
        image=_optional_image(data.get("image"), task_dir),
        region=_optional_region(data.get("region")),
        verify=verify,
        timeout_seconds=_optional_float(data.get("timeout_seconds")),
        retry=_optional_int(data.get("retry")),
        on_failure=_optional_str(data.get("on_failure")),
        requires_confirmation=_optional_bool(data.get("requires_confirmation")),
        category=_optional_str(data.get("category")),
        entropy_budget=_optional_float(data.get("entropy_budget"), "entropy_budget"),
        safe_action_variants=_optional_string_tuple(
            data.get("safe_action_variants"),
            "safe_action_variants",
        )
        or (),
    )


def _verification_from_mapping(
    value: object,
    task_dir: Path,
) -> VerificationDefinition:
    data = _mapping(value, "verify must be a mapping")
    return VerificationDefinition(
        type=str(data.get("type", "")),
        text=_optional_str(data.get("text")),
        image=_optional_image(data.get("image"), task_dir),
    )


def _validate_action_shape(step: TaskStep) -> list[str]:
    errors: list[str] = []
    if step.action in {"click_text", "click_uia"} and not step.target:
        errors.append(f"step {step.id} target is required for {step.action}")
    if step.action == "click_image" and step.image is None:
        errors.append(f"step {step.id} image is required for click_image")
    if step.action in {"type_text", "press_key"} and step.text is None:
        errors.append(f"step {step.id} text is required for {step.action}")
    if step.action == "wait_for" and step.verify is None and not step.target:
        errors.append(f"step {step.id} target or verify is required for wait_for")
    if step.action == "assert_visible" and step.verify is None and not step.target:
        errors.append(f"step {step.id} target or verify is required for assert_visible")
    if step.action == "scroll_until" and step.region is None:
        errors.append(f"step {step.id} region is required for scroll_until")
    if step.action == "branch_if_visible":
        if step.verify is None and not step.target:
            errors.append(
                f"step {step.id} target or verify is required for branch_if_visible"
            )
        if step.on_failure is None:
            errors.append(
                f"step {step.id} on_failure is required for branch_if_visible"
            )
    return errors


def _validate_verification_shape(step: TaskStep) -> list[str]:
    if step.verify is None:
        return []

    errors: list[str] = []
    if step.verify.type not in SUPPORTED_VERIFICATION_TYPES:
        errors.append(f"unknown verification type: {step.verify.type}")
    if (
        step.verify.type in {"visible_text", "not_visible_text"}
        and not step.verify.text
    ):
        errors.append(f"step {step.id} verify.text is required")
    if step.verify.type == "visible_image" and step.verify.image is None:
        errors.append(f"step {step.id} verify.image is required")
    if step.verify.type == "window_title_contains" and not step.verify.text:
        errors.append(f"step {step.id} verify.text is required")
    return errors


def _validate_safe_action_variants(step: TaskStep) -> list[str]:
    if not step.safe_action_variants:
        return []
    allowed = SAFE_ACTION_VARIANTS_BY_ACTION.get(step.action)
    if allowed is None:
        return [f"step {step.id} does not support safe_action_variants"]
    errors: list[str] = []
    for variant in step.safe_action_variants:
        if variant not in SUPPORTED_ACTIONS:
            errors.append(f"unknown safe action variant: {variant}")
        elif variant not in allowed:
            errors.append(
                f"step {step.id} safe_action_variants must be equivalent to "
                f"{step.action}",
            )
    return errors


def step_category(step: TaskStep) -> str:
    """Return an explicit step category or a stable action-based default."""

    if step.category is not None:
        return step.category
    return DEFAULT_CATEGORY_BY_ACTION.get(step.action, "navigation")


def _mapping(value: object, message: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TaskValidationError(message)
    return cast(Mapping[str, object], value)


def _string_tuple(value: object) -> tuple[str, ...]:
    return _optional_string_tuple(value, "allowed_windows") or ()


def _optional_string_tuple(
    value: object,
    field_name: str,
) -> tuple[str, ...] | None:
    if value in (None, ()):
        return None
    if not isinstance(value, list):
        raise TaskValidationError(f"{field_name} must be a list of strings")
    if not all(isinstance(item, str) for item in value):
        raise TaskValidationError(f"{field_name} must be a list of strings")
    return tuple(value)


def _float_value(value: object) -> float:
    if not isinstance(value, int | float):
        raise TaskValidationError("timeout_seconds must be a number")
    return float(value)


def _optional_float(value: object, field_name: str = "timeout_seconds") -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TaskValidationError(f"{field_name} must be a number")
    return float(value)


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TaskValidationError("retry must be an integer")
    return value


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TaskValidationError("string field must be a string")
    return value


def _optional_bool(value: object) -> bool:
    if value is None:
        return False
    if not isinstance(value, bool):
        raise TaskValidationError("requires_confirmation must be true or false")
    return value


def _optional_image(value: object, task_dir: Path) -> Path | None:
    image = _optional_str(value)
    if image is None:
        return None

    raw_path = Path(image)
    candidates = [raw_path] if raw_path.is_absolute() else [task_dir / raw_path]
    if not raw_path.is_absolute():
        candidates.append(Path("examples") / "assets" / raw_path)

    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise TaskValidationError(f"image template not found: {image}")


def _optional_region(value: object) -> TaskRegion | None:
    if value is None:
        return None
    data = _mapping(value, "region must be a mapping")
    region = TaskRegion(
        x=_required_int(data, "x"),
        y=_required_int(data, "y"),
        width=_required_int(data, "width"),
        height=_required_int(data, "height"),
    )
    if region.width <= 0 or region.height <= 0:
        raise TaskValidationError("region width and height must be greater than zero")
    return region


def _required_int(data: Mapping[str, object], key: str) -> int:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise TaskValidationError(f"region.{key} must be an integer")
    return value
