"""Repeated-run benchmark harness for local DeskPilot tasks."""

from __future__ import annotations

import json
import statistics
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from desktop_agent.actuation import DryRunActuator
from desktop_agent.benchmarks import (
    BenchmarkAcceptanceThresholds,
    benchmark_task_by_path,
)
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

BenchmarkAcceptanceStatus = Literal["passed", "failed", "not_configured"]


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
class MetricVariance:
    """Run-to-run distribution values for one numeric metric."""

    minimum: float
    maximum: float
    mean: float
    population_stdev: float


@dataclass(frozen=True)
class BenchmarkVarianceReport:
    """Variance report for timing, recovery, and execution-count metrics."""

    task_time_seconds: MetricVariance
    step_count: MetricVariance
    action_count: MetricVariance
    retry_count: MetricVariance
    ambiguity_count: MetricVariance
    recovery_count: MetricVariance
    operator_intervention_count: MetricVariance


@dataclass(frozen=True)
class BenchmarkAcceptanceResult:
    """Threshold evaluation result for a repeated benchmark invocation."""

    configured: bool
    passed: bool
    status: BenchmarkAcceptanceStatus
    failures: tuple[str, ...]
    thresholds: BenchmarkAcceptanceThresholds | None


@dataclass(frozen=True)
class BenchmarkRunReport:
    """Machine-readable report for one repeated benchmark invocation."""

    task_path: Path
    output_dir: Path
    metrics_path: Path
    report_path: Path
    variance_report_path: Path
    runs: tuple[BenchmarkRunMetrics, ...]
    summary: BenchmarkSummaryMetrics
    variance: BenchmarkVarianceReport
    acceptance: BenchmarkAcceptanceResult


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
        variance = _variance_from_runs(runs)
        task_spec = benchmark_task_by_path(task_path)
        thresholds = task_spec.acceptance_thresholds if task_spec else None
        acceptance = evaluate_benchmark_acceptance(runs, summary, thresholds)
        metrics_path = output_dir / "runs.jsonl"
        report_path = output_dir / "benchmark-report.json"
        variance_report_path = output_dir / "variance-report.json"
        _write_metrics(metrics_path, runs)
        _write_variance_report(variance_report_path, variance)
        _write_report(
            report_path,
            task_path,
            output_dir,
            metrics_path,
            variance_report_path,
            runs,
            summary,
            acceptance,
        )
        return BenchmarkRunReport(
            task_path=task_path,
            output_dir=output_dir,
            metrics_path=metrics_path,
            report_path=report_path,
            variance_report_path=variance_report_path,
            runs=runs,
            summary=summary,
            variance=variance,
            acceptance=acceptance,
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


def evaluate_benchmark_acceptance(
    runs: tuple[BenchmarkRunMetrics, ...],
    summary: BenchmarkSummaryMetrics,
    thresholds: BenchmarkAcceptanceThresholds | None,
) -> BenchmarkAcceptanceResult:
    """Evaluate repeated-run metrics against the built-in benchmark thresholds."""

    if thresholds is None:
        # Ad hoc tasks can still use the harness, but only built-in benchmarks
        # carry threshold gates that define whether behavior improved.
        return BenchmarkAcceptanceResult(
            configured=False,
            passed=True,
            status="not_configured",
            failures=(),
            thresholds=None,
        )

    failures: list[str] = []
    max_task_time = max(run.task_time_seconds for run in runs)
    max_step_count = max(run.step_count for run in runs)
    max_action_count = max(run.action_count for run in runs)
    max_retry_count = max(run.retry_count for run in runs)

    if summary.success_rate < thresholds.min_success_rate:
        failures.append(
            "min_success_rate missed: "
            f"{summary.success_rate:.3f} < {thresholds.min_success_rate:.3f}"
        )
    if (
        summary.median_task_time_seconds
        > thresholds.max_median_task_time_seconds
    ):
        failures.append(
            "max_median_task_time_seconds exceeded: "
            f"{summary.median_task_time_seconds:.3f} > "
            f"{thresholds.max_median_task_time_seconds:.3f}"
        )
    if max_task_time > thresholds.max_task_time_seconds_per_run:
        failures.append(
            "max_task_time_seconds_per_run exceeded: "
            f"{max_task_time:.3f} > {thresholds.max_task_time_seconds_per_run:.3f}"
        )
    if max_step_count > thresholds.max_step_count_per_run:
        failures.append(
            "max_step_count_per_run exceeded: "
            f"{max_step_count} > {thresholds.max_step_count_per_run}"
        )
    if max_action_count > thresholds.max_action_count_per_run:
        failures.append(
            "max_action_count_per_run exceeded: "
            f"{max_action_count} > {thresholds.max_action_count_per_run}"
        )
    if max_retry_count > thresholds.max_retry_count_per_run:
        failures.append(
            "max_retry_count_per_run exceeded: "
            f"{max_retry_count} > {thresholds.max_retry_count_per_run}"
        )
    if summary.ambiguity_rate > thresholds.max_ambiguity_rate:
        failures.append(
            "max_ambiguity_rate exceeded: "
            f"{summary.ambiguity_rate:.3f} > {thresholds.max_ambiguity_rate:.3f}"
        )
    if summary.recovery_rate > thresholds.max_recovery_rate:
        failures.append(
            "max_recovery_rate exceeded: "
            f"{summary.recovery_rate:.3f} > {thresholds.max_recovery_rate:.3f}"
        )
    if (
        summary.operator_intervention_rate
        > thresholds.max_operator_intervention_rate
    ):
        failures.append(
            "max_operator_intervention_rate exceeded: "
            f"{summary.operator_intervention_rate:.3f} > "
            f"{thresholds.max_operator_intervention_rate:.3f}"
        )

    passed = not failures
    return BenchmarkAcceptanceResult(
        configured=True,
        passed=passed,
        status="passed" if passed else "failed",
        failures=tuple(failures),
        thresholds=thresholds,
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
    variance_report_path: Path,
    runs: tuple[BenchmarkRunMetrics, ...],
    summary: BenchmarkSummaryMetrics,
    acceptance: BenchmarkAcceptanceResult,
) -> None:
    payload = {
        "task_path": str(task_path),
        "output_dir": str(output_dir),
        "metrics_path": str(metrics_path),
        "variance_report_path": str(variance_report_path),
        "iterations": len(runs),
        "summary": _summary_to_dict(summary),
        "acceptance": _acceptance_to_dict(acceptance),
        "runs": [_metrics_to_dict(run) for run in runs],
    }
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_variance_report(
    path: Path,
    variance: BenchmarkVarianceReport,
) -> None:
    path.write_text(
        json.dumps(_variance_report_to_dict(variance), indent=2, sort_keys=True)
        + "\n",
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


def _variance_from_runs(
    runs: tuple[BenchmarkRunMetrics, ...],
) -> BenchmarkVarianceReport:
    return BenchmarkVarianceReport(
        task_time_seconds=_metric_variance(run.task_time_seconds for run in runs),
        step_count=_metric_variance(float(run.step_count) for run in runs),
        action_count=_metric_variance(float(run.action_count) for run in runs),
        retry_count=_metric_variance(float(run.retry_count) for run in runs),
        ambiguity_count=_metric_variance(float(run.ambiguity_count) for run in runs),
        recovery_count=_metric_variance(float(run.recovery_count) for run in runs),
        operator_intervention_count=_metric_variance(
            float(run.operator_intervention_count) for run in runs
        ),
    )


def _metric_variance(values: Iterable[float]) -> MetricVariance:
    samples = tuple(values)
    return MetricVariance(
        minimum=min(samples),
        maximum=max(samples),
        mean=statistics.fmean(samples),
        population_stdev=statistics.pstdev(samples),
    )


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


def _variance_report_to_dict(report: BenchmarkVarianceReport) -> dict[str, object]:
    return {
        "task_time_seconds": _variance_to_dict(report.task_time_seconds),
        "step_count": _variance_to_dict(report.step_count),
        "action_count": _variance_to_dict(report.action_count),
        "retry_count": _variance_to_dict(report.retry_count),
        "ambiguity_count": _variance_to_dict(report.ambiguity_count),
        "recovery_count": _variance_to_dict(report.recovery_count),
        "operator_intervention_count": _variance_to_dict(
            report.operator_intervention_count
        ),
    }


def _variance_to_dict(variance: MetricVariance) -> dict[str, float]:
    return {
        "minimum": variance.minimum,
        "maximum": variance.maximum,
        "mean": variance.mean,
        "population_stdev": variance.population_stdev,
    }


def _acceptance_to_dict(acceptance: BenchmarkAcceptanceResult) -> dict[str, object]:
    return {
        "configured": acceptance.configured,
        "passed": acceptance.passed,
        "status": acceptance.status,
        "failures": list(acceptance.failures),
        "thresholds": _thresholds_to_dict(acceptance.thresholds)
        if acceptance.thresholds
        else None,
    }


def _thresholds_to_dict(
    thresholds: BenchmarkAcceptanceThresholds,
) -> dict[str, object]:
    return {
        "min_success_rate": thresholds.min_success_rate,
        "max_median_task_time_seconds": thresholds.max_median_task_time_seconds,
        "max_task_time_seconds_per_run": thresholds.max_task_time_seconds_per_run,
        "max_step_count_per_run": thresholds.max_step_count_per_run,
        "max_action_count_per_run": thresholds.max_action_count_per_run,
        "max_retry_count_per_run": thresholds.max_retry_count_per_run,
        "max_ambiguity_rate": thresholds.max_ambiguity_rate,
        "max_recovery_rate": thresholds.max_recovery_rate,
        "max_operator_intervention_rate": thresholds.max_operator_intervention_rate,
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
