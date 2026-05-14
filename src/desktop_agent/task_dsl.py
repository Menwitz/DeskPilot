"""Task DSL contracts shared by loaders, validators, and the planner."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

import yaml

from desktop_agent.config import RuntimeConfig


class TaskValidationError(ValueError):
    """Raised when a task definition fails platform-neutral validation."""


@dataclass(frozen=True)
class VerificationDefinition:
    """Planned verification attached to a task step."""

    type: str
    text: str | None = None


@dataclass(frozen=True)
class TaskStep:
    """Single deterministic action in a DeskPilot task."""

    id: str
    action: str
    target: str | None = None
    text: str | None = None
    verify: VerificationDefinition | None = None
    timeout_seconds: float | None = None
    retry: int | None = None


@dataclass(frozen=True)
class TaskDefinition:
    """Validated task loaded from YAML or an in-memory fixture."""

    name: str
    allowed_windows: tuple[str, ...]
    timeout_seconds: float
    steps: tuple[TaskStep, ...]


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

        return TaskDefinition(
            name=str(data.get("name", "")),
            allowed_windows=_string_tuple(data.get("allowed_windows", ())),
            timeout_seconds=_float_value(data.get("timeout_seconds", 0)),
            steps=tuple(_step_from_mapping(item) for item in steps_value),
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
        if len(task.steps) > config.max_steps:
            errors.append("task exceeds max_steps")

        step_ids: set[str] = set()
        for step in task.steps:
            if not step.id:
                errors.append("step id is required")
            elif step.id in step_ids:
                errors.append(f"duplicate step id: {step.id}")
            step_ids.add(step.id)

            if not step.action:
                errors.append(f"step {step.id} action is required")
            if step.retry is not None and step.retry < 0:
                errors.append(f"step {step.id} retry must not be negative")

        if errors:
            raise TaskValidationError("; ".join(errors))


def _step_from_mapping(value: object) -> TaskStep:
    data = _mapping(value, "each step must be a mapping")
    verify_value = data.get("verify")
    verify = None
    if verify_value is not None:
        verify_data = _mapping(verify_value, "verify must be a mapping")
        verify = VerificationDefinition(
            type=str(verify_data.get("type", "")),
            text=_optional_str(verify_data.get("text")),
        )

    return TaskStep(
        id=str(data.get("id", "")),
        action=str(data.get("action", "")),
        target=_optional_str(data.get("target")),
        text=_optional_str(data.get("text")),
        verify=verify,
        timeout_seconds=_optional_float(data.get("timeout_seconds")),
        retry=_optional_int(data.get("retry")),
    )


def _mapping(value: object, message: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TaskValidationError(message)
    return cast(Mapping[str, object], value)


def _string_tuple(value: object) -> tuple[str, ...]:
    if value in (None, ()):
        return ()
    if not isinstance(value, list):
        raise TaskValidationError("allowed_windows must be a list of strings")
    if not all(isinstance(item, str) for item in value):
        raise TaskValidationError("allowed_windows must be a list of strings")
    return tuple(value)


def _float_value(value: object) -> float:
    if not isinstance(value, int | float):
        raise TaskValidationError("timeout_seconds must be a number")
    return float(value)


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if not isinstance(value, int | float):
        raise TaskValidationError("timeout_seconds must be a number")
    return float(value)


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int):
        raise TaskValidationError("retry must be an integer")
    return value


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TaskValidationError("string field must be a string")
    return value
