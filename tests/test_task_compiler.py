from pathlib import Path

import pytest

from desktop_agent.config import RuntimeConfig
from desktop_agent.task_compiler import TaskCompilationError, TaskCompiler
from desktop_agent.task_dsl import (
    BasicTaskValidator,
    ExpectedStateTransition,
    TaskDefinition,
    TaskStep,
    YamlTaskLoader,
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
    assert compiled.metadata()["compiled_execution_model"] == "desktop_io_v1"
    assert compiled.metadata()["desktop_io_steps"] == [
        {
            "step_id": "open-editor",
            "source_action": "click_text",
            "operations": ["observe", "move", "click", "verify"],
        },
        {
            "step_id": "type-title",
            "source_action": "type_text",
            "operations": ["observe", "type", "verify"],
        },
    ]


def test_task_compiler_preserves_yaml_actions_with_desktop_io_model(
    tmp_path: Path,
) -> None:
    task_path = tmp_path / "routine.yaml"
    task_path.write_text(
        """name: existing yaml routine
allowed_windows:
  - DeskPilot Fixture
timeout_seconds: 30
steps:
  - id: open-menu
    action: click_text
    target: Menu
  - id: search
    action: type_text
    text: report
""",
        encoding="utf-8",
    )
    task = YamlTaskLoader().load(task_path)
    BasicTaskValidator().validate(task, RuntimeConfig())

    compiled = TaskCompiler().compile(task)

    assert [step.action for step in task.steps] == ["click_text", "type_text"]
    assert [step.source_action for step in compiled.desktop_io_steps] == [
        "click_text",
        "type_text",
    ]
    assert compiled.desktop_io_steps[0].operations == (
        "observe",
        "move",
        "click",
        "verify",
    )


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
