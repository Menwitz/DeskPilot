"""Dry-run preview models for timing budgets and recovery paths."""

from __future__ import annotations

from dataclasses import dataclass

from desktop_agent.action_safety import action_safety_metadata
from desktop_agent.config import RuntimeConfig
from desktop_agent.recovery import RECOVERY_POLICIES, constrain_recovery_policy
from desktop_agent.task_dsl import TaskDefinition, TaskStep, step_category
from desktop_agent.timing import StepTimingBudget, estimate_step_timing_budget
from desktop_agent.window_allowlist import effective_allowed_windows


@dataclass(frozen=True)
class RecoveryPathPreview:
    """Operator-readable recovery path available to one dry-run step."""

    reason: str
    actions: tuple[str, ...]
    chosen_action: str
    backoff_strategy: str
    constrained: bool


@dataclass(frozen=True)
class StepDryRunPreview:
    """Timing and recovery preview for one planned task step."""

    step_id: str
    action: str
    category: str
    timing_budget: StepTimingBudget
    action_delay_seconds: tuple[float, float]
    retry_delay_seconds: tuple[float, float]
    recovery_paths: tuple[RecoveryPathPreview, ...]
    safety_metadata: dict[str, object]


@dataclass(frozen=True)
class DryRunPreview:
    """Preview shown before a dry-run executes the safe planner pipeline."""

    task_name: str
    policy_preset: str
    activity_profile: str | None
    execution_persona: str
    steps: tuple[StepDryRunPreview, ...]


def build_dry_run_preview(task: TaskDefinition, config: RuntimeConfig) -> DryRunPreview:
    """Build a deterministic preview from task and runtime configuration."""

    allowed_windows = effective_allowed_windows(
        task.allowed_windows,
        config.allowed_windows,
    )
    return DryRunPreview(
        task_name=task.name,
        policy_preset=config.policy_preset,
        activity_profile=config.execution_profile.activity_profile,
        execution_persona=config.execution_profile.persona,
        steps=tuple(
            _step_preview(step, config, allowed_windows) for step in task.steps
        ),
    )


def render_dry_run_preview(preview: DryRunPreview) -> str:
    """Render the dry-run preview as compact CLI text."""

    lines = [
        "dry-run preview:",
        f"  policy preset: {preview.policy_preset}",
        "  execution profile: "
        f"{preview.activity_profile or 'custom'} "
        f"(persona {preview.execution_persona})",
    ]
    for step in preview.steps:
        budget = step.timing_budget
        fit_label = "yes" if budget.fits_timeout else "no"
        lines.append(f"  step {step.step_id} ({step.action}, {step.category})")
        safety_class = step.safety_metadata["action_safety_class"]
        mutation_risk = step.safety_metadata["mutation_risk"]
        mutates_state = step.safety_metadata["mutates_state"]
        approval_required = step.safety_metadata["approval_required"]
        reversibility = step.safety_metadata["reversibility"]
        window_scope = step.safety_metadata["window_scope"]
        scope_count = len(window_scope) if isinstance(window_scope, list) else 0
        mutates_label = "yes" if mutates_state is True else "no"
        approval_label = "required" if approval_required is True else "not required"
        lines.append(
            "    safety: "
            f"{safety_class}; mutation {mutation_risk}; mutates state "
            f"{mutates_label}; approval {approval_label}; "
            f"reversibility {reversibility}; "
            f"window scope {scope_count}",
        )
        lines.append(
            "    timing: "
            f"action {_seconds_range(step.action_delay_seconds)} "
            f"x{budget.action_timing_slots}; "
            f"retry {_seconds_range(step.retry_delay_seconds)} "
            f"x{budget.retry_timing_slots}; "
            f"worst-case wait {budget.planned_wait_seconds:.3f}s; "
            f"timeout {budget.timeout_seconds:.3f}s; fits {fit_label}",
        )
        for recovery in step.recovery_paths:
            constrained = " constrained" if recovery.constrained else ""
            lines.append(
                "    recovery: "
                f"{recovery.reason} -> {' -> '.join(recovery.actions)} "
                f"({recovery.backoff_strategy}; chosen {recovery.chosen_action}"
                f"{constrained})",
            )
    return "\n".join(lines)


def _step_preview(
    step: TaskStep,
    config: RuntimeConfig,
    allowed_windows: tuple[str, ...],
) -> StepDryRunPreview:
    return StepDryRunPreview(
        step_id=step.id,
        action=step.action,
        category=step_category(step),
        timing_budget=estimate_step_timing_budget(
            step,
            config.execution_profile,
            default_timeout_seconds=config.default_timeout_seconds,
            max_retries_per_step=config.max_retries_per_step,
        ),
        action_delay_seconds=config.execution_profile.action_delay_seconds,
        retry_delay_seconds=config.execution_profile.retry_delay_seconds,
        recovery_paths=_recovery_previews(step),
        safety_metadata=action_safety_metadata(
            step,
            allowed_windows=allowed_windows,
        ),
    )


def _recovery_previews(step: TaskStep) -> tuple[RecoveryPathPreview, ...]:
    previews: list[RecoveryPathPreview] = []
    for policy in sorted(RECOVERY_POLICIES.values(), key=lambda item: item.reason):
        constrained = constrain_recovery_policy(step, policy)
        previews.append(
            RecoveryPathPreview(
                reason=constrained.policy.reason,
                actions=constrained.policy.actions,
                chosen_action=constrained.chosen_action,
                backoff_strategy=constrained.policy.backoff_strategy,
                constrained=constrained.rule is not None,
            ),
        )
    return tuple(previews)


def _seconds_range(bounds: tuple[float, float]) -> str:
    return f"{bounds[0]:.3f}-{bounds[1]:.3f}s"
