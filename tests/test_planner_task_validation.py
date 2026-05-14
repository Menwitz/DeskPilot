import pytest

from desktop_agent.config import RuntimeConfig
from desktop_agent.task_dsl import (
    BasicTaskValidator,
    TaskDefinition,
    TaskStep,
    TaskValidationError,
)


def test_task_validator_requires_branch_failure_target() -> None:
    task = TaskDefinition(
        name="branch-validation",
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=30,
        steps=(TaskStep(id="branch", action="branch_if_visible", target="Optional"),),
    )

    with pytest.raises(TaskValidationError, match="on_failure is required"):
        BasicTaskValidator().validate(task, RuntimeConfig())


def test_task_validator_rejects_missing_branch_target() -> None:
    task = TaskDefinition(
        name="branch-validation",
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=30,
        steps=(
            TaskStep(
                id="branch",
                action="branch_if_visible",
                target="Optional",
                on_failure="missing",
            ),
        ),
    )

    with pytest.raises(TaskValidationError, match="on_failure target does not exist"):
        BasicTaskValidator().validate(task, RuntimeConfig())


def test_task_validator_requires_scroll_until_region() -> None:
    task = TaskDefinition(
        name="scroll-validation",
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=30,
        steps=(TaskStep(id="scroll", action="scroll_until", target="Submit"),),
    )

    with pytest.raises(TaskValidationError, match="region is required"):
        BasicTaskValidator().validate(task, RuntimeConfig())
