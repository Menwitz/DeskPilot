from typing import cast

import pytest

from desktop_agent.config import ExecutionProfile, RuntimeConfig
from desktop_agent.entropy import (
    entropy_capacity_metadata,
    validate_entropy_budget_constraints,
)
from desktop_agent.task_dsl import TaskDefinition, TaskStep, TaskValidationError


def test_entropy_capacity_counts_timing_retry_and_variant_slots() -> None:
    task = TaskDefinition(
        name="entropy-capacity",
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=30,
        entropy_budget=4.0,
        steps=(
            TaskStep(
                id="click-submit",
                action="click_text",
                target="Submit",
                retry=1,
                entropy_budget=3.0,
                safe_action_variants=("click_uia",),
            ),
        ),
    )
    config = RuntimeConfig(max_retries_per_step=1)

    validate_entropy_budget_constraints(task, config)
    metadata = entropy_capacity_metadata(task, config)

    assert metadata["entropy_task_capacity"] == 4
    step_capacities = cast(
        list[dict[str, object]],
        metadata["entropy_step_capacities"],
    )
    step_capacity = step_capacities[0]
    assert step_capacity["entropy_action_timing_slots"] == 2
    assert step_capacity["entropy_retry_timing_slots"] == 1
    assert step_capacity["entropy_variant_slots"] == 1


def test_entropy_budget_rejects_capacity_above_retry_constraints() -> None:
    task = TaskDefinition(
        name="entropy-over-budget",
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=30,
        entropy_budget=2.0,
        steps=(
            TaskStep(
                id="click-submit",
                action="click_text",
                target="Submit",
                retry=0,
                entropy_budget=2.0,
            ),
        ),
    )

    with pytest.raises(TaskValidationError, match="retry/max-step capacity"):
        validate_entropy_budget_constraints(task, RuntimeConfig())


def test_entropy_budget_rejects_timeout_constrained_capacity() -> None:
    task = TaskDefinition(
        name="entropy-timeout-budget",
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=30,
        steps=(
            TaskStep(
                id="click-submit",
                action="click_text",
                target="Submit",
                retry=1,
                timeout_seconds=0.4,
                entropy_budget=1.0,
            ),
        ),
    )
    config = RuntimeConfig(
        execution_profile=ExecutionProfile(
            enabled=True,
            action_delay_seconds=(0.2, 0.25),
            retry_delay_seconds=(0.2, 0.25),
        ),
    )

    with pytest.raises(TaskValidationError, match="timeout-constrained capacity"):
        validate_entropy_budget_constraints(task, config)
