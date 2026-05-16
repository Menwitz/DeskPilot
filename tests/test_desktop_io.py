from desktop_agent.desktop_io import (
    DESKTOP_IO_MODEL_VERSION,
    SUPPORTED_DESKTOP_IO_KINDS,
    DesktopIoAction,
    DesktopIoPlan,
    DesktopIoValidationError,
    compile_desktop_io_plan,
    desktop_io_kind_spec,
    validate_desktop_io_action,
    validate_desktop_io_plan,
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


def test_desktop_io_validation_rejects_unsupported_action_kind() -> None:
    action = DesktopIoAction(
        id="step:1:unsupported",
        step_id="step",
        kind="unsupported",
        order=1,
        source_action="custom",
        metadata={"safety": {}},
    )

    try:
        validate_desktop_io_action(action)
    except DesktopIoValidationError as exc:
        assert "unsupported desktop I/O action kind" in str(exc)
    else:
        raise AssertionError("expected DesktopIoValidationError")


def test_desktop_io_validation_rejects_ordering_and_missing_safety() -> None:
    plan = DesktopIoPlan(
        step_id="step",
        source_action="click_text",
        actions=(
            DesktopIoAction(
                id="step:2:click",
                step_id="step",
                kind="click",
                order=2,
                source_action="click_text",
            ),
        ),
    )

    try:
        validate_desktop_io_plan(plan)
    except DesktopIoValidationError as exc:
        message = str(exc)
        assert "order must be contiguous" in message
        assert "missing safety metadata" in message
    else:
        raise AssertionError("expected DesktopIoValidationError")
