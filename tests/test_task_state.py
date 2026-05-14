from desktop_agent.task_dsl import ExpectedStateTransition, TaskStep
from desktop_agent.task_state import TaskStateTracker


def test_task_state_tracker_records_completed_steps_and_believed_state() -> None:
    tracker = TaskStateTracker()
    open_step = TaskStep(
        id="open-editor",
        action="click_text",
        target="Edit",
        expected_state=ExpectedStateTransition(after="editor-open"),
    )
    type_step = TaskStep(
        id="type-title",
        action="type_text",
        text="Draft",
        depends_on=("open-editor",),
        expected_state=ExpectedStateTransition(
            before="editor-open",
            after="title-entered",
        ),
    )

    assert tracker.check_before_step(open_step).passed
    first_update = tracker.mark_step_completed(open_step)
    second_check = tracker.check_before_step(type_step)
    second_update = tracker.mark_step_completed(type_step)

    assert first_update.believed_state == "editor-open"
    assert second_check.passed
    assert second_update.completed_steps == ("open-editor", "type-title")
    assert second_update.believed_state == "title-entered"


def test_task_state_tracker_rejects_missing_dependencies() -> None:
    tracker = TaskStateTracker()
    step = TaskStep(
        id="submit",
        action="click_text",
        target="Submit",
        depends_on=("prepare",),
    )

    check = tracker.check_before_step(step)

    assert not check.passed
    assert check.missing_dependencies == ("prepare",)
    assert check.message == "step dependencies are not complete"
