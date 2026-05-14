"""Repeated-run benchmark harness for local DeskPilot tasks."""

from __future__ import annotations

import json
import statistics
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from desktop_agent.actuation import DryRunActuator
from desktop_agent.config import (
    ConfigOverrides,
    RuntimeConfig,
    StaticConfigLoader,
    YamlConfigLoader,
    resolve_runtime_config,
)
from desktop_agent.perception import (
    CompositePerceptionEngine,
    ConfidenceTargetSelector,
    DryRunPerceptionEngine,
)
from desktop_agent.planner import ExecutionEngine
from desktop_agent.safety import LocalSafetyPolicy, NoopEmergencyStopMonitor
from desktop_agent.screen import StaticScreenObserver
from desktop_agent.task_dsl import (
    BasicTaskValidator,
    StaticTaskLoader,
    TaskDefinition,
    YamlTaskLoader,
)
from desktop_agent.tracing import FileTraceSink, RunReport, RunStatus


@dataclass(frozen=True)
class BenchmarkRunMetrics:
    """Per-run metrics persisted by the repeated-run harness."""

    iteration: int
    status: RunStatus
    task_time_seconds: float
    step_count: int
    action_count: int
    retry_count: int
    ambiguity_count: int
    recovery_count: int
    operator_intervention_count: int
    trace_dir: Path | None
    abort_reason: str | None


@dataclass(frozen=True)
class BenchmarkSummaryMetrics:
    """Aggregate metrics computed across all repeated runs."""

    run_count: int
    success_rate: float
    median_task_time_seconds: float
    step_count: int
    action_count: int
    retry_count: int
    ambiguity_rate: float
    recovery_rate: float
    operator_intervention_rate: float


@dataclass(frozen=True)
class BenchmarkRunReport:
    """Machine-readable report for one repeated benchmark invocation."""

    task_path: Path
    output_dir: Path
    metrics_path: Path
    report_path: Path
    runs: tuple[BenchmarkRunMetrics, ...]
    summary: BenchmarkSummaryMetrics


class BenchmarkRunHarness:
    """Executes one task repeatedly through the safe dry-run pipeline."""

    def run_task(
        self,
        task_path: Path,
        *,
        iterations: int,
        output_dir: Path,
        config_path: Path | None = None,
        cli_overrides: ConfigOverrides | None = None,
    ) -> BenchmarkRunReport:
        if iterations <= 0:
            raise ValueError("iterations must be greater than zero")

        task = YamlTaskLoader().load(task_path)
        file_config = YamlConfigLoader().load(config_path)
        config = resolve_runtime_config(
            file_config,
            task_overrides=task.config_overrides,
            cli_overrides=cli_overrides,
        )
        config = resolve_runtime_config(
            config,
            cli_overrides=ConfigOverrides(trace_root=output_dir / "traces"),
        )

        output_dir.mkdir(parents=True, exist_ok=True)
        runs = tuple(
            self._run_once(task_path, task, config, iteration)
            for iteration in range(1, iterations + 1)
        )
        summary = _summary_from_runs(runs)
        metrics_path = output_dir / "runs.jsonl"
        report_path = output_dir / "benchmark-report.json"
        _write_metrics(metrics_path, runs)
        _write_report(report_path, task_path, output_dir, metrics_path, runs, summary)
        return BenchmarkRunReport(
            task_path=task_path,
            output_dir=output_dir,
            metrics_path=metrics_path,
            report_path=report_path,
            runs=runs,
            summary=summary,
        )

    def _run_once(
        self,
        task_path: Path,
        task: TaskDefinition,
        config: RuntimeConfig,
        iteration: int,
    ) -> BenchmarkRunMetrics:
        trace_sink = FileTraceSink()
        engine = ExecutionEngine(
            config_loader=StaticConfigLoader(config),
            task_loader=StaticTaskLoader(task),
            task_validator=BasicTaskValidator(),
            trace_sink=trace_sink,
            safety_policy=LocalSafetyPolicy(),
            screen_observer=StaticScreenObserver(),
            perception_engine=CompositePerceptionEngine((DryRunPerceptionEngine(),)),
            target_selector=ConfidenceTargetSelector(),
            actuator=DryRunActuator(),
            emergency_stop_monitor=NoopEmergencyStopMonitor(),
        )

        started = time.perf_counter()
        report = engine.run(task_path)
        elapsed = time.perf_counter() - started
        return _metrics_from_report(iteration, report, elapsed)


def _metrics_from_report(
    iteration: int,
    report: RunReport,
    task_time_seconds: float,
) -> BenchmarkRunMetrics:
    return BenchmarkRunMetrics(
        iteration=iteration,
        status=report.status,
        task_time_seconds=task_time_seconds,
        step_count=len(report.steps),
        action_count=sum(
            1 for event in report.events if event.phase == "execute_action"
        ),
        retry_count=sum(max(step.attempts - 1, 0) for step in report.steps),
        ambiguity_count=sum(
            1
            for event in report.events
            if event.metadata.get("selection_blocked")
            == "confidence_or_ambiguity_gate"
        ),
        recovery_count=sum(1 for event in report.events if event.phase == "recover"),
        operator_intervention_count=sum(
            1
            for step in report.steps
            if "requires explicit confirmation" in step.message
        ),
        trace_dir=report.trace_dir,
        abort_reason=report.abort_reason,
    )


def _write_metrics(path: Path, runs: tuple[BenchmarkRunMetrics, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = (json.dumps(_metrics_to_dict(run), sort_keys=True) + "\n" for run in runs)
    path.write_text("".join(lines), encoding="utf-8")


def _write_report(
    path: Path,
    task_path: Path,
    output_dir: Path,
    metrics_path: Path,
    runs: tuple[BenchmarkRunMetrics, ...],
    summary: BenchmarkSummaryMetrics,
) -> None:
    payload = {
        "task_path": str(task_path),
        "output_dir": str(output_dir),
        "metrics_path": str(metrics_path),
        "iterations": len(runs),
        "summary": _summary_to_dict(summary),
        "runs": [_metrics_to_dict(run) for run in runs],
    }
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _summary_from_runs(
    runs: tuple[BenchmarkRunMetrics, ...],
) -> BenchmarkSummaryMetrics:
    run_count = len(runs)
    successful_runs = sum(1 for run in runs if run.status == "passed")
    return BenchmarkSummaryMetrics(
        run_count=run_count,
        success_rate=successful_runs / run_count,
        median_task_time_seconds=statistics.median(
            run.task_time_seconds for run in runs
        ),
        step_count=sum(run.step_count for run in runs),
        action_count=sum(run.action_count for run in runs),
        retry_count=sum(run.retry_count for run in runs),
        ambiguity_rate=_nonzero_rate(run.ambiguity_count for run in runs),
        recovery_rate=_nonzero_rate(run.recovery_count for run in runs),
        operator_intervention_rate=_nonzero_rate(
            run.operator_intervention_count for run in runs
        ),
    )


def _nonzero_rate(values: Iterable[int]) -> float:
    counts = tuple(values)
    if not counts:
        return 0.0
    return sum(1 for value in counts if value > 0) / len(counts)


def _summary_to_dict(summary: BenchmarkSummaryMetrics) -> dict[str, object]:
    return {
        "run_count": summary.run_count,
        "success_rate": summary.success_rate,
        "median_task_time_seconds": summary.median_task_time_seconds,
        "step_count": summary.step_count,
        "action_count": summary.action_count,
        "retry_count": summary.retry_count,
        "ambiguity_rate": summary.ambiguity_rate,
        "recovery_rate": summary.recovery_rate,
        "operator_intervention_rate": summary.operator_intervention_rate,
    }


def _metrics_to_dict(metrics: BenchmarkRunMetrics) -> dict[str, object]:
    return {
        "iteration": metrics.iteration,
        "status": metrics.status,
        "task_time_seconds": metrics.task_time_seconds,
        "step_count": metrics.step_count,
        "action_count": metrics.action_count,
        "retry_count": metrics.retry_count,
        "ambiguity_count": metrics.ambiguity_count,
        "recovery_count": metrics.recovery_count,
        "operator_intervention_count": metrics.operator_intervention_count,
        "trace_dir": str(metrics.trace_dir) if metrics.trace_dir else None,
        "abort_reason": metrics.abort_reason,
    }
