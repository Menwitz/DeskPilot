"""Trace and report contracts for execution monitoring."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol

from desktop_agent.config import ExecutionProfile, LocalModelConfig, RuntimeConfig
from desktop_agent.safety_audit import (
    build_safety_audit,
    render_safety_audit_markdown,
)
from desktop_agent.task_dsl import (
    ExpectedStateTransition,
    RecoveryRule,
    TaskDefinition,
    TaskRegion,
    TaskStep,
    VerificationDefinition,
    step_category,
)

RunStatus = Literal["passed", "failed", "aborted", "emergency_stopped"]
StepStatus = Literal["passed", "failed", "skipped"]


@dataclass(frozen=True)
class TraceSchemaV2:
    """Versioned closed-loop trace contract for observe-decide-act-verify runs."""

    version: str = "2"

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "sections": {
                "observation": {
                    "description": "screen, focus, cursor, OCR, UIA, and CV state",
                    "typical_fields": [
                        "screenshot_path",
                        "active_window_title",
                        "active_window_process",
                        "focused_element",
                        "cursor_position",
                        "monitor",
                        "dpi_scale",
                        "visible_controls",
                    ],
                },
                "target_reasoning": {
                    "description": "selected target, alternatives, and rejections",
                    "typical_fields": [
                        "selected_candidate",
                        "candidate_rankings",
                        "rejected_candidates",
                        "rejection_reasons",
                        "confidence_values",
                        "coordinate_conversion",
                    ],
                },
                "input": {
                    "description": "real or dry-run input planned and emitted",
                    "typical_fields": [
                        "input_action",
                        "movement_points",
                        "keyboard_interval_seconds",
                        "scroll_step_clicks",
                    ],
                },
                "verification": {
                    "description": "post-action checks and observed state changes",
                    "typical_fields": [
                        "verification_type",
                        "verification_outcome",
                        "verification_status",
                        "post_action_evidence",
                        "manual_handoff_required",
                    ],
                },
                "state_delta": {
                    "description": "focused, visual, text, and viewport changes",
                    "typical_fields": [
                        "state_delta",
                        "focus_changed",
                        "visible_text_changed",
                        "viewport_moved",
                    ],
                },
                "model_assistance": {
                    "description": "optional local model decision disclosure",
                    "typical_fields": [
                        "provider",
                        "model",
                        "prompt_class",
                        "input_artifact_references",
                        "output_hash",
                        "affected_selection",
                    ],
                },
            },
        }


TRACE_SCHEMA_V2 = TraceSchemaV2()


@dataclass(frozen=True)
class TraceEvent:
    """Single monitoring event emitted by the execution pipeline."""

    phase: str
    message: str
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class StepReport:
    """Machine-readable summary for one executed task step."""

    step_id: str
    action: str
    status: StepStatus
    attempts: int
    message: str
    candidate_id: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class RunReport:
    """Final in-memory report returned by the execution engine."""

    task_name: str
    status: RunStatus
    events: tuple[TraceEvent, ...]
    steps: tuple[StepReport, ...]
    abort_reason: str | None = None
    trace_dir: Path | None = None
    metadata: dict[str, object] = field(default_factory=dict)


class TraceSink(Protocol):
    """Interface for trace and report writers."""

    def prepare_run(self, task: TaskDefinition, config: RuntimeConfig) -> RuntimeConfig:
        """Prepare trace output and return the config the pipeline should use."""
        ...

    def record_event(self, event: TraceEvent) -> None: ...

    def record_step(self, report: StepReport) -> None: ...

    def write_final_report(
        self,
        status: RunStatus,
        abort_reason: str | None = None,
    ) -> RunReport: ...


class MemoryTraceSink(TraceSink):
    """Trace sink used by tests that do not need filesystem artifacts."""

    def __init__(self) -> None:
        self._task_name = "unknown"
        self._task_metadata: dict[str, object] = {}
        self.events: list[TraceEvent] = []
        self.steps: list[StepReport] = []

    def prepare_run(self, task: TaskDefinition, config: RuntimeConfig) -> RuntimeConfig:
        self._task_name = task.name
        self._task_metadata = dict(task.metadata)
        self.events = []
        self.steps = []
        return config

    def record_event(self, event: TraceEvent) -> None:
        self.events.append(event)

    def record_step(self, report: StepReport) -> None:
        self.steps.append(report)

    def write_final_report(
        self,
        status: RunStatus,
        abort_reason: str | None = None,
    ) -> RunReport:
        return RunReport(
            task_name=self._task_name,
            status=status,
            events=tuple(self.events),
            steps=tuple(self.steps),
            abort_reason=abort_reason,
            metadata=dict(self._task_metadata),
        )


class FileTraceSink(TraceSink):
    """Writes local run artifacts under a unique trace directory."""

    def __init__(self) -> None:
        self._task_name = "unknown"
        self._task_metadata: dict[str, object] = {}
        self._run_dir: Path | None = None
        self.events: list[TraceEvent] = []
        self.steps: list[StepReport] = []

    @property
    def run_dir(self) -> Path | None:
        return self._run_dir

    def prepare_run(self, task: TaskDefinition, config: RuntimeConfig) -> RuntimeConfig:
        self._task_name = task.name
        self._task_metadata = dict(task.metadata)
        self.events = []
        self.steps = []
        self._run_dir = _run_directory(config.trace_root, task.name)
        self._run_dir.mkdir(parents=True, exist_ok=False)
        runtime_config = replace(config, trace_root=self._run_dir)
        _write_json(self._run_dir / "trace-schema.json", TRACE_SCHEMA_V2.to_dict())
        _write_json(self._run_dir / "config.json", _config_to_dict(runtime_config))
        _write_json(self._run_dir / "task.json", _task_to_dict(task))
        if runtime_config.execution_profile.enabled:
            audit = build_safety_audit(task, runtime_config)
            _write_json(self._run_dir / "safety-audit.json", audit)
            (self._run_dir / "safety-audit.md").write_text(
                render_safety_audit_markdown(audit),
                encoding="utf-8",
            )
        (self._run_dir / "action-log.jsonl").write_text("", encoding="utf-8")
        return runtime_config

    def record_event(self, event: TraceEvent) -> None:
        self.events.append(event)
        if self._run_dir is None:
            return
        payload = {
            "index": len(self.events),
            "trace_schema_version": TRACE_SCHEMA_V2.version,
            "phase": event.phase,
            "message": event.message,
            "metadata": _json_safe(event.metadata),
        }
        with (self._run_dir / "action-log.jsonl").open("a", encoding="utf-8") as file:
            file.write(json.dumps(payload, sort_keys=True) + "\n")

    def record_step(self, report: StepReport) -> None:
        self.steps.append(report)

    def write_final_report(
        self,
        status: RunStatus,
        abort_reason: str | None = None,
    ) -> RunReport:
        report = RunReport(
            task_name=self._task_name,
            status=status,
            events=tuple(self.events),
            steps=tuple(self.steps),
            abort_reason=abort_reason,
            trace_dir=self._run_dir,
            metadata=dict(self._task_metadata),
        )
        if self._run_dir is not None:
            _write_json(
                self._run_dir / "final-report.json", _run_report_to_dict(report)
            )
            (self._run_dir / "final-report.md").write_text(
                _run_report_markdown(report),
                encoding="utf-8",
            )
        return report


def _run_directory(trace_root: Path, task_name: str) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    return trace_root / f"{timestamp}-{_slug(task_name)}"


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip()).strip("-")
    return slug or "run"


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _config_to_dict(config: RuntimeConfig) -> dict[str, object]:
    return {
        "default_timeout_seconds": config.default_timeout_seconds,
        "confidence_threshold": config.confidence_threshold,
        "max_steps": config.max_steps,
        "max_retries_per_step": config.max_retries_per_step,
        "max_runtime_seconds": config.max_runtime_seconds,
        "trace_root": str(config.trace_root),
        "save_screenshots": config.save_screenshots,
        "save_ocr_text": config.save_ocr_text,
        "allowed_windows": list(config.allowed_windows),
        "emergency_stop_hotkey": config.emergency_stop_hotkey,
        "primary_monitor_only": config.primary_monitor_only,
        "policy_preset": config.policy_preset,
        "require_operator_approval": config.require_operator_approval,
        "execution_profile": _execution_profile_to_dict(config.execution_profile),
        "confirmed_steps": list(config.confirmed_steps),
        "local_model": _local_model_to_dict(config.local_model),
    }


def _execution_profile_to_dict(profile: ExecutionProfile) -> dict[str, object]:
    return {
        "persona": profile.persona,
        "enabled": profile.enabled,
        "action_delay_seconds": list(profile.action_delay_seconds),
        "retry_delay_seconds": list(profile.retry_delay_seconds),
        "action_delay_distribution": profile.action_delay_distribution,
        "retry_delay_distribution": profile.retry_delay_distribution,
        "action_variant_distribution": profile.action_variant_distribution,
        "hesitation_probability": profile.hesitation_probability,
        "movement_smoothness": profile.movement_smoothness,
        "keyboard_interval_seconds": list(profile.keyboard_interval_seconds),
        "scroll_interval_seconds": list(profile.scroll_interval_seconds),
        "random_seed": profile.random_seed,
    }


def _local_model_to_dict(config: LocalModelConfig) -> dict[str, object]:
    return {
        "enabled": config.enabled,
        "provider": config.provider,
        "model": config.model,
        "endpoint": config.endpoint,
        "request_timeout_seconds": config.request_timeout_seconds,
        "use_for_goal_ranking": config.use_for_goal_ranking,
    }


def _task_to_dict(task: TaskDefinition) -> dict[str, object]:
    return {
        "name": task.name,
        "allowed_windows": list(task.allowed_windows),
        "timeout_seconds": task.timeout_seconds,
        "entropy_budget": task.entropy_budget,
        "metadata": task.metadata,
        "steps": [_step_to_dict(step) for step in task.steps],
    }


def _step_to_dict(step: TaskStep) -> dict[str, object]:
    return {
        "id": step.id,
        "action": step.action,
        "category": step.category,
        "resolved_category": step_category(step),
        "target": step.target,
        "text": step.text,
        "handoff_prompt": step.handoff_prompt,
        "expected_operator_work": step.expected_operator_work,
        "image": str(step.image) if step.image else None,
        "region": _region_to_dict(step.region),
        "verify": _verification_to_dict(step.verify),
        "checkpoint": _verification_to_dict(step.checkpoint),
        "timeout_seconds": step.timeout_seconds,
        "retry": step.retry,
        "on_failure": step.on_failure,
        "requires_confirmation": step.requires_confirmation,
        "entropy_budget": step.entropy_budget,
        "safe_action_variants": list(step.safe_action_variants),
        "recovery": [_recovery_rule_to_dict(rule) for rule in step.recovery],
        "depends_on": list(step.depends_on),
        "expected_state": _expected_state_to_dict(step.expected_state),
        "metadata": step.metadata,
    }


def _expected_state_to_dict(
    expected_state: ExpectedStateTransition | None,
) -> dict[str, object] | None:
    if expected_state is None:
        return None
    return {
        "before": expected_state.before,
        "after": expected_state.after,
    }


def _recovery_rule_to_dict(rule: RecoveryRule) -> dict[str, object]:
    return {
        "reason": rule.reason,
        "actions": list(rule.actions),
        "next_step": rule.next_step,
    }


def _region_to_dict(region: TaskRegion | None) -> dict[str, int] | None:
    if region is None:
        return None
    return {
        "x": region.x,
        "y": region.y,
        "width": region.width,
        "height": region.height,
    }


def _verification_to_dict(
    verify: VerificationDefinition | None,
) -> dict[str, object] | None:
    if verify is None:
        return None
    return {
        "type": verify.type,
        "text": verify.text,
        "image": str(verify.image) if verify.image else None,
    }


def _run_report_to_dict(report: RunReport) -> dict[str, object]:
    return {
        "trace_schema_version": TRACE_SCHEMA_V2.version,
        "trace_schema": TRACE_SCHEMA_V2.to_dict(),
        "task_name": report.task_name,
        "status": report.status,
        "abort_reason": report.abort_reason,
        "trace_dir": str(report.trace_dir) if report.trace_dir else None,
        "metadata": _json_safe(report.metadata),
        "steps": [_step_report_to_dict(step) for step in report.steps],
        "events": [_event_to_dict(event) for event in report.events],
    }


def _event_to_dict(event: TraceEvent) -> dict[str, object]:
    return {
        "phase": event.phase,
        "message": event.message,
        "metadata": _json_safe(event.metadata),
    }


def _step_report_to_dict(step: StepReport) -> dict[str, object]:
    return {
        "step_id": step.step_id,
        "action": step.action,
        "status": step.status,
        "attempts": step.attempts,
        "message": step.message,
        "candidate_id": step.candidate_id,
        "metadata": _json_safe(step.metadata),
    }


def _run_report_markdown(report: RunReport) -> str:
    lines = [
        f"# DeskPilot Run Report: {report.task_name}",
        "",
        f"- Status: `{report.status}`",
        f"- Abort reason: `{report.abort_reason}`"
        if report.abort_reason
        else "- Abort reason: none",
        f"- Trace directory: `{report.trace_dir}`"
        if report.trace_dir
        else "- Trace directory: memory",
    ]
    site_id = report.metadata.get("site_id")
    flow_id = report.metadata.get("site_flow_id")
    if isinstance(site_id, str) and isinstance(flow_id, str):
        lines.append(f"- Site flow: `{site_id}` / `{flow_id}`")
    lines.extend(["", "## Steps"])
    for step in report.steps:
        failure_category = step.metadata.get("failure_category")
        category_suffix = (
            f" [{failure_category}]" if isinstance(failure_category, str) else ""
        )
        lines.append(
            f"- `{step.step_id}` `{step.action}`: {step.status} "
            f"after {step.attempts} attempt(s){category_suffix} - {step.message}"
        )
    lines.extend(["", "## Events"])
    for event in report.events:
        lines.append(
            f"- `{event.phase}`: {event.message}{_event_markdown_suffix(event)}"
        )
    return "\n".join(lines) + "\n"


def _event_markdown_suffix(event: TraceEvent) -> str:
    details: list[str] = []
    recovery_summary = event.metadata.get("recovery_path_summary")
    if isinstance(recovery_summary, str):
        details.append(recovery_summary)
    selection_blocked = event.metadata.get("selection_blocked")
    if isinstance(selection_blocked, str):
        details.append(selection_blocked)
    delay_seconds = event.metadata.get("delay_seconds")
    if isinstance(delay_seconds, int | float):
        details.append(f"delay {delay_seconds:.3f}s")
    cadence_applied = event.metadata.get("keyboard_cadence_applied")
    interval_count = event.metadata.get("keyboard_interval_count")
    if cadence_applied is True and isinstance(interval_count, int):
        details.append(f"keyboard cadence {interval_count} interval(s)")
    scroll_cadence_applied = event.metadata.get("scroll_cadence_applied")
    scroll_step_count = event.metadata.get("scroll_step_count")
    if scroll_cadence_applied is True and isinstance(scroll_step_count, int):
        details.append(f"scroll cadence {scroll_step_count} step(s)")
    actuation_guard = event.metadata.get("actuation_guard")
    if event.metadata.get("input_blocked") is True and isinstance(
        actuation_guard,
        str,
    ):
        details.append(f"input blocked by {actuation_guard}")
    if event.phase == "action_safety":
        safety_class = event.metadata.get("action_safety_class")
        approval_required = event.metadata.get("approval_required")
        window_scope = event.metadata.get("window_scope")
        if isinstance(safety_class, str):
            details.append(f"safety {safety_class}")
        if isinstance(approval_required, bool):
            approval_label = "required" if approval_required else "not required"
            details.append(f"approval {approval_label}")
        if isinstance(window_scope, list):
            details.append(f"scope {len(window_scope)} window(s)")
    blocked_state = event.metadata.get("site_blocked_state_id")
    blocked_reason = event.metadata.get("site_blocked_state_reason")
    if isinstance(blocked_state, str):
        if isinstance(blocked_reason, str):
            details.append(f"blocked state {blocked_state}: {blocked_reason}")
        else:
            details.append(f"blocked state {blocked_state}")
    if not details:
        return ""
    return " - " + "; ".join(details)


def _json_safe(value: object) -> object:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_json_safe(item) for item in value]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)
