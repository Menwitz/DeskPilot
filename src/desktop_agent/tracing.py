"""Trace and report contracts for execution monitoring."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol

from desktop_agent.config import RuntimeConfig
from desktop_agent.task_dsl import TaskDefinition

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


@dataclass(frozen=True)
class RunReport:
    """Final in-memory report returned by the execution engine."""

    task_name: str
    status: RunStatus
    events: tuple[TraceEvent, ...]
    steps: tuple[StepReport, ...]
    abort_reason: str | None = None


class TraceSink(Protocol):
    """Interface for trace and report writers."""

    def prepare_run(self, task: TaskDefinition, config: RuntimeConfig) -> None: ...

    def record_event(self, event: TraceEvent) -> None: ...

    def record_step(self, report: StepReport) -> None: ...

    def write_final_report(
        self,
        status: RunStatus,
        abort_reason: str | None = None,
    ) -> RunReport: ...


class MemoryTraceSink(TraceSink):
    """Trace sink used by tests before filesystem tracing is implemented."""

    def __init__(self) -> None:
        self._task_name = "unknown"
        self.events: list[TraceEvent] = []
        self.steps: list[StepReport] = []

    def prepare_run(self, task: TaskDefinition, config: RuntimeConfig) -> None:
        _ = config
        self._task_name = task.name
        self.events = []
        self.steps = []

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
