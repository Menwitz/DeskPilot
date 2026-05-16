from desktop_agent.desktop_io import (
    DESKTOP_IO_MODEL_VERSION,
    SUPPORTED_DESKTOP_IO_KINDS,
    compile_desktop_io_plan,
    desktop_io_kind_spec,
)
from desktop_agent.task_dsl import TaskStep


def test_desktop_io_plan_uses_first_class_action_schema() -> None:
    plan = compile_desktop_io_plan(
        TaskStep(id="type-query", action="type_text", text="report")
    )

    assert plan.step_id == "type-query"
    assert plan.source_action == "type_text"
    assert plan.operations == ("observe", "type", "verify")
    action_metadata = plan.actions[1].to_metadata()
    assert action_metadata == {
        "id": "type-query:2:type",
        "step_id": "type-query",
        "kind": "type",
        "order": 2,
        "source_action": "type_text",
        "kind_contract": {
            "kind": "type",
            "input_channel": "keyboard",
            "emits_desktop_input": True,
            "requires_target": False,
            "bounded": True,
            "supported": True,
        },
        "metadata": {
            "safety": {
                "action_safety_class": "local_mutation",
                "mutation_risk": "local",
                "mutates_state": True,
                "approval_required": False,
                "approval_reason": None,
                "reversibility": "usually_reversible",
                "reversible": True,
                "idempotent": False,
                "app_scope": "task_scope",
                "window_scope": [],
                "allowed_region": None,
            }
        },
    }
    assert plan.to_metadata()["schema_version"] == DESKTOP_IO_MODEL_VERSION
    assert "handoff" in SUPPORTED_DESKTOP_IO_KINDS


def test_desktop_io_schema_supports_required_operation_kinds() -> None:
    required = {
        "observe",
        "move",
        "click",
        "double_click",
        "drag",
        "wheel",
        "type",
        "hotkey",
        "wait",
        "verify",
        "handoff",
    }

    assert set(SUPPORTED_DESKTOP_IO_KINDS) == required
    for kind in required:
        spec = desktop_io_kind_spec(kind)
        assert spec is not None
        assert spec.kind == kind
        assert spec.to_metadata()["supported"] is True
    assert desktop_io_kind_spec("unsupported") is None


def test_desktop_io_actions_carry_safety_metadata() -> None:
    plan = compile_desktop_io_plan(
        TaskStep(
            id="publish",
            action="click_text",
            target="Publish",
            category="submission",
            requires_confirmation=True,
            metadata={"site_sensitive_category": "publish"},
        ),
        allowed_windows=("DeskPilot Fixture",),
    )

    for action in plan.actions:
        safety = action.metadata["safety"]
        assert isinstance(safety, dict)
        assert safety["action_safety_class"] == "message_or_publish"
        assert safety["approval_required"] is True
        assert safety["window_scope"] == ["DeskPilot Fixture"]
