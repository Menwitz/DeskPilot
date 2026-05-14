"""Dry-run preview models for timing budgets and recovery paths."""

from __future__ import annotations

from dataclasses import dataclass

from desktop_agent.config import RuntimeConfig
from desktop_agent.recovery import RECOVERY_POLICIES, constrain_recovery_policy
from desktop_agent.task_dsl import TaskDefinition, TaskStep, step_category
from desktop_agent.timing import StepTimingBudget, estimate_step_timing_budget


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


@dataclass(frozen=True)
class DryRunPreview:
    """Preview shown before a dry-run executes the safe planner pipeline."""

    task_name: str
    policy_preset: str
    steps: tuple[StepDryRunPreview, ...]


def build_dry_run_preview(task: TaskDefinition, config: RuntimeConfig) -> DryRunPreview:
    """Build a deterministic preview from task and runtime configuration."""

    return DryRunPreview(
        task_name=task.name,
        policy_preset=config.policy_preset,
        steps=tuple(_step_preview(step, config) for step in task.steps),
    )


def render_dry_run_preview(preview: DryRunPreview) -> str:
    """Render the dry-run preview as compact CLI text."""

    lines = [
        "dry-run preview:",
        f"  policy preset: {preview.policy_preset}",
    ]
    for step in preview.steps:
        budget = step.timing_budget
        fit_label = "yes" if budget.fits_timeout else "no"
        lines.append(f"  step {step.step_id} ({step.action}, {step.category})")
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


def _step_preview(step: TaskStep, config: RuntimeConfig) -> StepDryRunPreview:
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
