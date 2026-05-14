"""Safety policy contracts for local desktop automation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from desktop_agent.config import RuntimeConfig
from desktop_agent.task_dsl import TaskDefinition, TaskStep


@dataclass(frozen=True)
class SafetyDecision:
    """Decision returned before the runner continues or performs an action."""

    allowed: bool
    reason: str


class SafetyPolicy(Protocol):
    """Interface for execution safety checks."""

    def check_preconditions(
        self,
        task: TaskDefinition,
        config: RuntimeConfig,
    ) -> SafetyDecision: ...

    def check_before_action(
        self,
        task: TaskDefinition,
        step: TaskStep,
        config: RuntimeConfig,
    ) -> SafetyDecision: ...


class LocalSafetyPolicy(SafetyPolicy):
    """Applies platform-neutral safety checks before adapters do real work."""

    def check_preconditions(
        self,
        task: TaskDefinition,
        config: RuntimeConfig,
    ) -> SafetyDecision:
        _ = config
        if not task.allowed_windows:
            return SafetyDecision(False, "task must declare allowed windows")
        return SafetyDecision(True, "allowed")

    def check_before_action(
        self,
        task: TaskDefinition,
        step: TaskStep,
        config: RuntimeConfig,
    ) -> SafetyDecision:
        _ = step, config
        if not task.allowed_windows:
            return SafetyDecision(False, "task must declare allowed windows")
        return SafetyDecision(True, "allowed")
