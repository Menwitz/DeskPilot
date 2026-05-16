"""Safety audit report generation for execution-profile runs."""

from __future__ import annotations

from desktop_agent.action_safety import action_safety_profile
from desktop_agent.config import RuntimeConfig
from desktop_agent.task_dsl import TaskDefinition, TaskStep, step_category

EXTERNAL_MUTATION_RISKS: frozenset[str] = frozenset(
    {"external", "sensitive_external"}
)


def build_safety_audit(
    task: TaskDefinition,
    config: RuntimeConfig,
) -> dict[str, object]:
    """Build a machine-readable safety audit for a configured task run."""

    findings = _audit_findings(task, config)
    return {
        "audit_status": "attention" if findings else "passed",
        "task_name": task.name,
        "policy_preset": config.policy_preset,
        "require_operator_approval": config.require_operator_approval,
        "allowed_windows": list(config.allowed_windows or task.allowed_windows),
        "emergency_stop_hotkey": config.emergency_stop_hotkey,
        "primary_monitor_only": config.primary_monitor_only,
        "execution_profile": {
            "enabled": config.execution_profile.enabled,
            "persona": config.execution_profile.persona,
            "action_delay_seconds": list(config.execution_profile.action_delay_seconds),
            "retry_delay_seconds": list(config.execution_profile.retry_delay_seconds),
            "movement_smoothness": config.execution_profile.movement_smoothness,
            "keyboard_interval_seconds": list(
                config.execution_profile.keyboard_interval_seconds,
            ),
            "scroll_interval_seconds": list(
                config.execution_profile.scroll_interval_seconds,
            ),
        },
        "sensitive_steps": [
            _sensitive_step_audit(step, config)
            for step in task.steps
            if _sensitive_step(step)
        ],
        "findings": findings,
    }


def render_safety_audit_markdown(audit: dict[str, object]) -> str:
    """Render the safety audit as a compact Markdown artifact."""

    findings = _object_list(audit.get("findings"))
    sensitive_steps = _object_list(audit.get("sensitive_steps"))
    lines = [
        f"# DeskPilot Safety Audit: {audit.get('task_name', 'unknown')}",
        "",
        f"- Status: `{audit.get('audit_status', 'unknown')}`",
        f"- Policy preset: `{audit.get('policy_preset', 'unknown')}`",
        f"- Operator approval required: `{audit.get('require_operator_approval')}`",
        f"- Emergency stop hotkey: `{audit.get('emergency_stop_hotkey', 'unknown')}`",
        "",
        "## Sensitive Steps",
    ]
    if not sensitive_steps:
        lines.append("- None")
    for step in sensitive_steps:
        lines.append(
            "- "
            f"`{step.get('step_id')}` `{step.get('action')}` "
            f"category `{step.get('category')}`; "
            f"confirmed `{step.get('confirmed')}`; "
            f"checkpoint `{step.get('has_checkpoint')}`",
        )
    lines.extend(["", "## Findings"])
    if not findings:
        lines.append("- None")
    for finding in findings:
        lines.append(
            "- "
            f"[{finding.get('severity')}] {finding.get('message')} "
            f"(`{finding.get('step_id', 'run')}`)",
        )
    return "\n".join(lines) + "\n"


def _sensitive_step_audit(
    step: TaskStep,
    config: RuntimeConfig,
) -> dict[str, object]:
    return {
        "step_id": step.id,
        "action": step.action,
        "category": step_category(step),
        "requires_confirmation": step.requires_confirmation,
        "confirmed": step.id in config.confirmed_steps,
        "has_checkpoint": step.checkpoint is not None,
        "safe_action_variants": list(step.safe_action_variants),
    }


def _audit_findings(
    task: TaskDefinition,
    config: RuntimeConfig,
) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    if not (config.allowed_windows or task.allowed_windows):
        findings.append(
            {
                "severity": "high",
                "step_id": "run",
                "message": "run has no allowed window boundary",
            }
        )
    for step in task.steps:
        if _external_mutation_missing_checkpoint(step):
            findings.append(
                {
                    "severity": "medium",
                    "step_id": step.id,
                    "message": (
                        "external mutation step has no pre-action checkpoint"
                    ),
                }
            )
        if step.requires_confirmation and step.id not in config.confirmed_steps:
            findings.append(
                {
                    "severity": "medium",
                    "step_id": step.id,
                    "message": "confirmation-required step is not pre-confirmed",
                }
            )
    if config.execution_profile.enabled and not config.require_operator_approval:
        findings.append(
            {
                "severity": "low",
                "step_id": "run",
                "message": "operator approval prompts are not required by config",
            }
        )
    return findings


def _sensitive_step(step: TaskStep) -> bool:
    return step.requires_confirmation or step_category(step) == "submission"


def _external_mutation_missing_checkpoint(step: TaskStep) -> bool:
    profile = action_safety_profile(step)
    return profile.mutation_risk in EXTERNAL_MUTATION_RISKS and step.checkpoint is None


def _object_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]
