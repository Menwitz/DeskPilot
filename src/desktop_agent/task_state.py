"""Local task-state tracking for planner execution."""

from __future__ import annotations

from dataclasses import dataclass

from desktop_agent.task_dsl import TaskStep


@dataclass(frozen=True)
class TaskStateCheck:
    """Result of checking whether a step can run from local task state."""

    passed: bool
    message: str
    believed_state: str | None
    expected_before: str | None
    missing_dependencies: tuple[str, ...] = ()

    def metadata(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "message": self.message,
            "believed_state": self.believed_state,
            "expected_before": self.expected_before,
            "missing_dependencies": list(self.missing_dependencies),
        }


@dataclass(frozen=True)
class TaskStateUpdate:
    """Recorded local state after a step completes."""

    completed_steps: tuple[str, ...]
    believed_state: str | None
    expected_after: str | None

    def metadata(self) -> dict[str, object]:
        return {
            "completed_steps": list(self.completed_steps),
            "believed_state": self.believed_state,
            "expected_after": self.expected_after,
        }


class TaskStateTracker:
    """Tracks completed steps and authored UI state transitions locally."""

    def __init__(self) -> None:
        self._completed_steps: list[str] = []
        self._believed_state: str | None = None

    def check_before_step(self, step: TaskStep) -> TaskStateCheck:
        expected_before = (
            step.expected_state.before if step.expected_state is not None else None
        )
        missing_dependencies = tuple(
            dependency
            for dependency in step.depends_on
            if dependency not in self._completed_steps
        )
        if missing_dependencies:
            return TaskStateCheck(
                passed=False,
                message="step dependencies are not complete",
                believed_state=self._believed_state,
                expected_before=expected_before,
                missing_dependencies=missing_dependencies,
            )
        if (
            expected_before is not None
            and self._believed_state is not None
            and expected_before != self._believed_state
        ):
            return TaskStateCheck(
                passed=False,
                message="believed task state does not match step precondition",
                believed_state=self._believed_state,
                expected_before=expected_before,
            )
        return TaskStateCheck(
            passed=True,
            message="task state allows step",
            believed_state=self._believed_state,
            expected_before=expected_before,
        )

    def mark_step_completed(self, step: TaskStep) -> TaskStateUpdate:
        if step.id not in self._completed_steps:
            self._completed_steps.append(step.id)
        expected_after = (
            step.expected_state.after if step.expected_state is not None else None
        )
        if expected_after is not None:
            self._believed_state = expected_after
        elif (
            self._believed_state is None
            and step.expected_state is not None
            and step.expected_state.before is not None
        ):
            self._believed_state = step.expected_state.before
        return TaskStateUpdate(
            completed_steps=tuple(self._completed_steps),
            believed_state=self._believed_state,
            expected_after=expected_after,
        )
