"""Trace and report contracts for execution monitoring."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol

from desktop_agent.config import ExecutionProfile, RuntimeConfig
from desktop_agent.task_dsl import (
    TaskDefinition,
    TaskRegion,
    TaskStep,
    VerificationDefinition,
    step_category,
)

RunStatus = Literal["passed", "failed", "aborted", "emergency_stopped"]
StepStatus = Literal["passed", "failed", "skipped"]


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
        self.events: list[TraceEvent] = []
        self.steps: list[StepReport] = []

    def prepare_run(self, task: TaskDefinition, config: RuntimeConfig) -> RuntimeConfig:
        self._task_name = task.name
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
        )


class FileTraceSink(TraceSink):
    """Writes local run artifacts under a unique trace directory."""

    def __init__(self) -> None:
        self._task_name = "unknown"
        self._run_dir: Path | None = None
        self.events: list[TraceEvent] = []
        self.steps: list[StepReport] = []

    @property
    def run_dir(self) -> Path | None:
        return self._run_dir

    def prepare_run(self, task: TaskDefinition, config: RuntimeConfig) -> RuntimeConfig:
        self._task_name = task.name
        self.events = []
        self.steps = []
        self._run_dir = _run_directory(config.trace_root, task.name)
        self._run_dir.mkdir(parents=True, exist_ok=False)
        runtime_config = replace(config, trace_root=self._run_dir)
        _write_json(self._run_dir / "config.json", _config_to_dict(runtime_config))
        _write_json(self._run_dir / "task.json", _task_to_dict(task))
        (self._run_dir / "action-log.jsonl").write_text("", encoding="utf-8")
        return runtime_config

    def record_event(self, event: TraceEvent) -> None:
        self.events.append(event)
        if self._run_dir is None:
            return
        payload = {
            "index": len(self.events),
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
        "execution_profile": _execution_profile_to_dict(config.execution_profile),
        "confirmed_steps": list(config.confirmed_steps),
    }


def _execution_profile_to_dict(profile: ExecutionProfile) -> dict[str, object]:
    return {
        "enabled": profile.enabled,
        "action_delay_seconds": list(profile.action_delay_seconds),
        "retry_delay_seconds": list(profile.retry_delay_seconds),
        "hesitation_probability": profile.hesitation_probability,
        "movement_smoothness": profile.movement_smoothness,
        "random_seed": profile.random_seed,
    }


def _task_to_dict(task: TaskDefinition) -> dict[str, object]:
    return {
        "name": task.name,
        "allowed_windows": list(task.allowed_windows),
        "timeout_seconds": task.timeout_seconds,
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
        "image": str(step.image) if step.image else None,
        "region": _region_to_dict(step.region),
        "verify": _verification_to_dict(step.verify),
        "timeout_seconds": step.timeout_seconds,
        "retry": step.retry,
        "on_failure": step.on_failure,
        "requires_confirmation": step.requires_confirmation,
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
        "task_name": report.task_name,
        "status": report.status,
        "abort_reason": report.abort_reason,
        "trace_dir": str(report.trace_dir) if report.trace_dir else None,
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
        "",
        "## Steps",
    ]
    for step in report.steps:
        lines.append(
            f"- `{step.step_id}` `{step.action}`: {step.status} "
            f"after {step.attempts} attempt(s) - {step.message}"
        )
    lines.extend(["", "## Events"])
    for event in report.events:
        lines.append(f"- `{event.phase}`: {event.message}")
    return "\n".join(lines) + "\n"


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
