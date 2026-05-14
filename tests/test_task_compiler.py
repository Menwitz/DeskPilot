import pytest

from desktop_agent.task_compiler import TaskCompilationError, TaskCompiler
from desktop_agent.task_dsl import (
    ExpectedStateTransition,
    TaskDefinition,
    TaskStep,
)


def test_task_compiler_records_dependency_and_state_metadata() -> None:
    task = TaskDefinition(
        name="stateful fixture",
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=30,
        steps=(
            TaskStep(
                id="open-editor",
                action="click_text",
                target="Edit",
                expected_state=ExpectedStateTransition(after="editor-open"),
            ),
            TaskStep(
                id="type-title",
                action="type_text",
                text="Draft",
                depends_on=("open-editor",),
                expected_state=ExpectedStateTransition(
                    before="editor-open",
                    after="title-entered",
                ),
            ),
        ),
    )

    compiled = TaskCompiler().compile(task)

    assert compiled.step_order == ("open-editor", "type-title")
    assert compiled.dependencies[0].step_id == "type-title"
    assert compiled.dependencies[0].depends_on == ("open-editor",)
    assert compiled.state_transitions[1].before == "editor-open"
    assert compiled.state_transitions[1].after == "title-entered"
    assert compiled.metadata()["dependency_count"] == 1
    assert compiled.metadata()["state_transition_count"] == 2


def test_task_compiler_rejects_invalid_dependencies() -> None:
    task = TaskDefinition(
        name="bad dependencies",
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=30,
        steps=(
            TaskStep(
                id="first",
                action="click_text",
                target="Start",
                depends_on=("second",),
            ),
            TaskStep(
                id="second",
                action="click_text",
                target="Finish",
                depends_on=("missing", "missing", "second"),
            ),
        ),
    )

    with pytest.raises(TaskCompilationError) as exc_info:
        TaskCompiler().compile(task)

    message = str(exc_info.value)
    assert "dependency must reference an earlier step" in message
    assert "dependency target does not exist" in message
    assert "duplicate dependency" in message
    assert "cannot depend on itself" in message


def test_task_compiler_rejects_contradictory_expected_state() -> None:
    task = TaskDefinition(
        name="bad state",
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=30,
        steps=(
            TaskStep(
                id="open-editor",
                action="click_text",
                target="Edit",
                expected_state=ExpectedStateTransition(after="editor-open"),
            ),
            TaskStep(
                id="save-title",
                action="press_key",
                text="ctrl+s",
                expected_state=ExpectedStateTransition(
                    before="summary-open",
                    after="saved",
                ),
            ),
        ),
    )

    with pytest.raises(
        TaskCompilationError,
        match=r"expected_state\.before must match prior state editor-open",
    ):
        TaskCompiler().compile(task)
