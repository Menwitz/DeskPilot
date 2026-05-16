from desktop_agent.desktop_io import (
    DESKTOP_IO_MODEL_VERSION,
    SUPPORTED_DESKTOP_IO_KINDS,
    compile_desktop_io_plan,
)
from desktop_agent.task_dsl import TaskStep


def test_desktop_io_plan_uses_first_class_action_schema() -> None:
    plan = compile_desktop_io_plan(
        TaskStep(id="type-query", action="type_text", text="report")
    )

    assert plan.step_id == "type-query"
    assert plan.source_action == "type_text"
    assert plan.operations == ("observe", "type", "verify")
    assert plan.actions[1].to_metadata() == {
        "id": "type-query:2:type",
        "step_id": "type-query",
        "kind": "type",
        "order": 2,
        "source_action": "type_text",
        "metadata": {},
    }
    assert plan.to_metadata()["schema_version"] == DESKTOP_IO_MODEL_VERSION
    assert "handoff" in SUPPORTED_DESKTOP_IO_KINDS
