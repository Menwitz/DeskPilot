"""Action execution contracts for desktop input adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from desktop_agent.config import RuntimeConfig
from desktop_agent.perception import ElementCandidate
from desktop_agent.task_dsl import TaskStep


@dataclass(frozen=True)
class ActionResult:
    """Outcome returned by an input adapter after a step action is attempted."""

    success: bool
    message: str


class Actuator(Protocol):
    """Interface for platform-specific input adapters."""

    def execute(
        self,
        step: TaskStep,
        target: ElementCandidate | None,
        config: RuntimeConfig,
    ) -> ActionResult: ...


class DryRunActuator(Actuator):
    """Adapter used by tests and dry-run flows where no input is sent."""

    def execute(
        self,
        step: TaskStep,
        target: ElementCandidate | None,
        config: RuntimeConfig,
    ) -> ActionResult:
        _ = target, config
        return ActionResult(success=True, message=f"planned {step.action}")
