"""Task DSL contracts shared by loaders, validators, and the planner."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

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
