"""Pre-execution compilation for validated DeskPilot tasks."""

from __future__ import annotations

from dataclasses import dataclass

from desktop_agent.task_dsl import (
    ExpectedStateTransition,
    TaskDefinition,
    TaskStep,
    TaskValidationError,
)


class TaskCompilationError(TaskValidationError):
    """Raised when a structurally valid task cannot form an execution plan."""


@dataclass(frozen=True)
class CompiledStepDependency:
    """Dependency contract for one compiled step."""

    step_id: str
    depends_on: tuple[str, ...]


@dataclass(frozen=True)
class CompiledStateTransition:
    """Expected UI state boundary for one compiled step."""

    step_id: str
    before: str | None
    after: str | None


@dataclass(frozen=True)
class CompiledTask:
    """Static execution plan metadata produced before runtime observation."""

    step_order: tuple[str, ...]
    dependencies: tuple[CompiledStepDependency, ...]
    state_transitions: tuple[CompiledStateTransition, ...]

    def metadata(self) -> dict[str, object]:
        """Return compact trace metadata for monitoring compiled task shape."""

        return {
            "step_order": list(self.step_order),
            "dependency_count": sum(
                len(dependency.depends_on) for dependency in self.dependencies
            ),
            "dependencies": [
                {
                    "step_id": dependency.step_id,
                    "depends_on": list(dependency.depends_on),
                }
                for dependency in self.dependencies
            ],
            "state_transition_count": len(self.state_transitions),
            "state_transitions": [
                {
                    "step_id": transition.step_id,
                    "before": transition.before,
                    "after": transition.after,
                }
                for transition in self.state_transitions
            ],
        }


class TaskCompiler:
    """Build and validate the static step graph before execution starts."""

    def compile(self, task: TaskDefinition) -> CompiledTask:
        errors: list[str] = []
        step_order = tuple(step.id for step in task.steps)
        positions = _step_positions(task.steps, errors)
        dependencies = _compile_dependencies(task.steps, positions, errors)
        state_transitions = _compile_state_transitions(task.steps, errors)

        if errors:
            raise TaskCompilationError("; ".join(errors))
        return CompiledTask(
            step_order=step_order,
            dependencies=dependencies,
            state_transitions=state_transitions,
        )


def _step_positions(
    steps: tuple[TaskStep, ...],
    errors: list[str],
) -> dict[str, int]:
    positions: dict[str, int] = {}
    for index, step in enumerate(steps):
        if not step.id:
            errors.append("step id is required for compilation")
            continue
        if step.id in positions:
            errors.append(f"duplicate compiled step id: {step.id}")
            continue
        positions[step.id] = index
    return positions


def _compile_dependencies(
    steps: tuple[TaskStep, ...],
    positions: dict[str, int],
    errors: list[str],
) -> tuple[CompiledStepDependency, ...]:
    compiled: list[CompiledStepDependency] = []
    for step in steps:
        seen: set[str] = set()
        for dependency in step.depends_on:
            if not dependency.strip():
                errors.append(f"step {step.id} dependency id must not be empty")
                continue
            if dependency in seen:
                errors.append(f"step {step.id} has duplicate dependency: {dependency}")
                continue
            seen.add(dependency)
            if dependency not in positions:
                errors.append(f"step {step.id} dependency target does not exist")
                continue
            if dependency == step.id:
                errors.append(f"step {step.id} cannot depend on itself")
                continue
            if positions[dependency] >= positions.get(step.id, -1):
                errors.append(
                    f"step {step.id} dependency must reference an earlier step"
                )
        if step.depends_on:
            compiled.append(
                CompiledStepDependency(step_id=step.id, depends_on=step.depends_on)
            )
    return tuple(compiled)


def _compile_state_transitions(
    steps: tuple[TaskStep, ...],
    errors: list[str],
) -> tuple[CompiledStateTransition, ...]:
    compiled: list[CompiledStateTransition] = []
    known_state: str | None = None
    for step in steps:
        expected = step.expected_state
        if expected is None:
            continue
        before = _state_label(expected, "before", step.id, errors)
        after = _state_label(expected, "after", step.id, errors)
        if before is None and after is None:
            errors.append(
                f"step {step.id} expected_state must define before or after"
            )
        if known_state is not None and before is not None and before != known_state:
            errors.append(
                f"step {step.id} expected_state.before must match prior state "
                f"{known_state}"
            )

        # When a step omits an explicit before state, carry the prior compiled
        # state forward so reports still show the checked transition boundary.
        compiled_before = before if before is not None else known_state
        compiled.append(
            CompiledStateTransition(
                step_id=step.id,
                before=compiled_before,
                after=after,
            )
        )
        if after is not None:
            known_state = after
        elif before is not None and known_state is None:
            known_state = before
    return tuple(compiled)


def _state_label(
    expected: ExpectedStateTransition,
    field_name: str,
    step_id: str,
    errors: list[str],
) -> str | None:
    value = expected.before if field_name == "before" else expected.after
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        errors.append(f"step {step_id} expected_state.{field_name} must not be empty")
        return None
    return stripped
