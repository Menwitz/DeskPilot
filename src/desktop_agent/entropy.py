"""Entropy budget validation for bounded random decisions."""

from __future__ import annotations

from dataclasses import dataclass

from desktop_agent.config import RuntimeConfig
from desktop_agent.task_dsl import TaskDefinition, TaskStep, TaskValidationError
from desktop_agent.timing import estimate_step_timing_budget


@dataclass(frozen=True)
class StepEntropyCapacity:
    """Maximum entropy decision units possible for one step configuration."""

    step_id: str
    action_timing_slots: int
    retry_timing_slots: int
    variant_slots: int
    timeout_fits_planned_waits: bool

    @property
    def total_decision_slots(self) -> int:
        return self.action_timing_slots + self.retry_timing_slots + self.variant_slots

    def metadata(self) -> dict[str, object]:
        return {
            "step_id": self.step_id,
            "entropy_action_timing_slots": self.action_timing_slots,
            "entropy_retry_timing_slots": self.retry_timing_slots,
            "entropy_variant_slots": self.variant_slots,
            "entropy_total_decision_slots": self.total_decision_slots,
            "entropy_timeout_fits_planned_waits": self.timeout_fits_planned_waits,
        }


def validate_entropy_budget_constraints(
    task: TaskDefinition,
    config: RuntimeConfig,
) -> None:
    """Reject entropy budgets that exceed configured runtime decision capacity."""

    capacities = tuple(_step_entropy_capacity(step, config) for step in task.steps)
    errors: list[str] = []
    for step, capacity in zip(task.steps, capacities, strict=True):
        step_budget = step.entropy_budget
        if step_budget is None:
            continue
        if not capacity.timeout_fits_planned_waits and step_budget > 0:
            errors.append(
                f"step {step.id} entropy_budget exceeds timeout-constrained capacity",
            )
        if step_budget > capacity.total_decision_slots:
            errors.append(
                f"step {step.id} entropy_budget exceeds retry/max-step capacity",
            )

    if task.entropy_budget is not None:
        task_capacity = _task_entropy_capacity(capacities, config)
        if task.entropy_budget > task_capacity:
            errors.append("entropy_budget exceeds task runtime capacity")

    if errors:
        raise TaskValidationError("; ".join(errors))


def entropy_capacity_metadata(
    task: TaskDefinition,
    config: RuntimeConfig,
) -> dict[str, object]:
    capacities = tuple(_step_entropy_capacity(step, config) for step in task.steps)
    return {
        "entropy_task_capacity": _task_entropy_capacity(capacities, config),
        "entropy_step_capacities": [
            capacity.metadata() for capacity in capacities
        ],
    }


def _step_entropy_capacity(
    step: TaskStep,
    config: RuntimeConfig,
) -> StepEntropyCapacity:
    timing_budget = estimate_step_timing_budget(
        step,
        config.execution_profile,
        default_timeout_seconds=config.default_timeout_seconds,
        max_retries_per_step=config.max_retries_per_step,
    )
    return StepEntropyCapacity(
        step_id=step.id,
        action_timing_slots=timing_budget.action_timing_slots,
        retry_timing_slots=timing_budget.retry_timing_slots,
        variant_slots=1 if step.safe_action_variants else 0,
        timeout_fits_planned_waits=timing_budget.fits_timeout,
    )


def _task_entropy_capacity(
    capacities: tuple[StepEntropyCapacity, ...],
    config: RuntimeConfig,
) -> int:
    # max_steps bounds how many steps can ever consume entropy in one run.
    bounded_capacities = capacities[: config.max_steps]
    return sum(capacity.total_decision_slots for capacity in bounded_capacities)
