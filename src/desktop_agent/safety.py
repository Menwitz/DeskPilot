"""Safety policy contracts for local desktop automation."""

from __future__ import annotations

import ctypes
import sys
from dataclasses import dataclass
from typing import Any, Protocol, cast

from desktop_agent.config import RuntimeConfig
from desktop_agent.screen import ScreenObservation
from desktop_agent.task_dsl import TaskDefinition, TaskStep, step_category

STRICT_QA_CONFIRMATION_CATEGORIES: frozenset[str] = frozenset({"submission"})
EXPLORATORY_BLOCKED_CATEGORIES: frozenset[str] = frozenset({"submission"})
OPERATOR_APPROVAL_CATEGORIES: frozenset[str] = frozenset({"submission"})


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
        observation: ScreenObservation | None = None,
    ) -> SafetyDecision: ...


class EmergencyStopMonitor(Protocol):
    """Interface for checking whether the operator requested an immediate stop."""

    def is_triggered(self, config: RuntimeConfig) -> bool: ...


class NoopEmergencyStopMonitor(EmergencyStopMonitor):
    """Emergency monitor used by tests and platforms without hotkey polling."""

    def is_triggered(self, config: RuntimeConfig) -> bool:
        _ = config
        return False


class StaticEmergencyStopMonitor(EmergencyStopMonitor):
    """Deterministic emergency monitor for planner tests."""

    def __init__(self, *, triggered: bool) -> None:
        self._triggered = triggered

    def is_triggered(self, config: RuntimeConfig) -> bool:
        _ = config
        return self._triggered


class WindowsHotkeyEmergencyStopMonitor(EmergencyStopMonitor):
    """Polls the configured Windows hotkey without installing hooks."""

    def __init__(self) -> None:
        self._user32: Any | None = None
        if sys.platform == "win32":
            self._user32 = cast(Any, ctypes).windll.user32

    def is_triggered(self, config: RuntimeConfig) -> bool:
        if self._user32 is None:
            return False
        virtual_keys = _hotkey_virtual_keys(config.emergency_stop_hotkey)
        # GetAsyncKeyState is process-local polling of the global key state; the
        # planner checks it between bounded actions so the operator can stop a run.
        return bool(virtual_keys) and all(
            self._user32.GetAsyncKeyState(virtual_key) & 0x8000
            for virtual_key in virtual_keys
        )


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
        observation: ScreenObservation | None = None,
    ) -> SafetyDecision:
        _ = step, config
        if not task.allowed_windows:
            return SafetyDecision(False, "task must declare allowed windows")
        if (
            config.require_operator_approval
            and _operator_approval_required(step)
            and step.id not in config.confirmed_steps
        ):
            return SafetyDecision(
                False,
                f"step {step.id} requires operator approval",
            )
        if step.requires_confirmation and step.id not in config.confirmed_steps:
            return SafetyDecision(
                False,
                f"step {step.id} requires explicit confirmation",
            )
        category = step_category(step)
        if (
            config.policy_preset == "strict_qa"
            and category in STRICT_QA_CONFIRMATION_CATEGORIES
            and step.id not in config.confirmed_steps
        ):
            return SafetyDecision(
                False,
                f"step {step.id} requires confirmation under strict_qa policy",
            )
        if (
            config.policy_preset == "exploratory_testing"
            and category in EXPLORATORY_BLOCKED_CATEGORIES
        ):
            return SafetyDecision(
                False,
                f"step {step.id} is blocked by exploratory_testing policy",
            )
        if (
            observation
            and observation.active_window_title
            and observation.active_window_title not in task.allowed_windows
        ):
            return SafetyDecision(
                False,
                "active window is outside the task allowed_windows",
            )
        return SafetyDecision(True, "allowed")


def _operator_approval_required(step: TaskStep) -> bool:
    return (
        step.requires_confirmation
        or step_category(step) in OPERATOR_APPROVAL_CATEGORIES
    )


def create_platform_emergency_stop_monitor() -> EmergencyStopMonitor:
    if sys.platform == "win32":
        return WindowsHotkeyEmergencyStopMonitor()
    return NoopEmergencyStopMonitor()


def _hotkey_virtual_keys(hotkey: str) -> tuple[int, ...]:
    keys: list[int] = []
    for part in hotkey.split("+"):
        normalized = part.strip().lower()
        if not normalized:
            continue
        if normalized not in _HOTKEY_ALIASES:
            raise ValueError(f"unsupported emergency stop key: {part}")
        keys.append(_HOTKEY_ALIASES[normalized])
    return tuple(keys)


_HOTKEY_ALIASES = {
    "ctrl": 0x11,
    "control": 0x11,
    "shift": 0x10,
    "alt": 0x12,
    "esc": 0x1B,
    "escape": 0x1B,
    "space": 0x20,
    "enter": 0x0D,
    "return": 0x0D,
    **{chr(code).lower(): code for code in range(ord("A"), ord("Z") + 1)},
    **{str(number): ord(str(number)) for number in range(10)},
}
