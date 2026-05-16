from desktop_agent.config import ExecutionProfile, RuntimeConfig
from desktop_agent.safety_audit import (
    build_safety_audit,
    render_safety_audit_markdown,
)
from desktop_agent.task_dsl import TaskDefinition, TaskStep, VerificationDefinition


def test_safety_audit_reports_execution_profile_controls() -> None:
    task = TaskDefinition(
        name="audit fixture",
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=30,
        steps=(
            TaskStep(
                id="click-submit",
                action="click_text",
                target="Submit",
                category="submission",
                checkpoint=VerificationDefinition(type="visible_text", text="Submit"),
            ),
        ),
    )
    config = RuntimeConfig(
        policy_preset="strict_qa",
        require_operator_approval=True,
        confirmed_steps=("click-submit",),
        execution_profile=ExecutionProfile(
            enabled=True,
            persona="careful",
            action_delay_seconds=(0.05, 0.25),
            retry_delay_seconds=(0.10, 0.30),
        ),
    )

    audit = build_safety_audit(task, config)
    rendered = render_safety_audit_markdown(audit)

    assert audit["audit_status"] == "passed"
    assert audit["policy_preset"] == "strict_qa"
    assert audit["require_operator_approval"] is True
    assert audit["findings"] == []
    assert "click-submit" in rendered
    assert "Status: `passed`" in rendered


def test_safety_audit_flags_missing_checkpoint_and_approval() -> None:
    task = TaskDefinition(
        name="audit findings",
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=30,
        steps=(
            TaskStep(
                id="click-submit",
                action="click_text",
                target="Submit",
                category="submission",
                requires_confirmation=True,
            ),
        ),
    )
    config = RuntimeConfig(
        execution_profile=ExecutionProfile(enabled=True),
    )

    audit = build_safety_audit(task, config)
    rendered = render_safety_audit_markdown(audit)

    assert audit["audit_status"] == "attention"
    assert "external mutation step has no pre-action checkpoint" in rendered
    assert "confirmation-required step is not pre-confirmed" in rendered
    assert "operator approval prompts are not required by config" in rendered


def test_safety_audit_flags_sensitive_external_missing_checkpoint() -> None:
    task = TaskDefinition(
        name="audit findings",
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=30,
        steps=(
            TaskStep(
                id="publish",
                action="click_text",
                target="Publish",
                requires_confirmation=True,
                metadata={"site_sensitive_category": "publish"},
            ),
        ),
    )

    audit = build_safety_audit(
        task,
        RuntimeConfig(
            confirmed_steps=("publish",),
            execution_profile=ExecutionProfile(enabled=True),
        ),
    )

    assert audit["audit_status"] == "attention"
    findings = audit["findings"]
    assert isinstance(findings, list)
    first_finding = findings[0]
    assert isinstance(first_finding, dict)
    assert first_finding["message"] == (
        "external mutation step has no pre-action checkpoint"
    )
