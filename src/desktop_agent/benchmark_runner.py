"""Repeated-run benchmark harness for local DeskPilot tasks."""

from __future__ import annotations

import json
import statistics
import time
from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from desktop_agent.actuation import (
    ActuationProfile,
    DryRunActuator,
    FittsLawPointerTimingModel,
    MovementPlan,
    PointerTimingContext,
    PointerTimingEstimate,
    SmoothMovementPlanner,
)
from desktop_agent.benchmarks import (
    BenchmarkAcceptanceThresholds,
    BenchmarkTaskSpec,
    benchmark_task_by_path,
)
from desktop_agent.config import (
    ConfigOverrides,
    ExecutionProfile,
    RuntimeConfig,
    StaticConfigLoader,
    YamlConfigLoader,
    resolve_runtime_config,
)
from desktop_agent.operator_services import LocalTraceService
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
BenchmarkComparisonStatus = Literal["improved", "neutral", "regressed"]

DEFAULT_POINTER_TIMING_PROFILE = ActuationProfile(
    movement_duration_seconds=(0.05, 0.5),
    timing_variation_seconds=(0.0, 0.0),
    movement_steps=8,
    movement_smoothness=0.0,
    random_seed=1,
)
DEFAULT_BASELINE_POINTER_DURATION_SECONDS = 0.2
BENCHMARK_REPORT_SCHEMA_VERSION = "benchmark_report_v1"
TARGET_GROUNDING_ACTIONS: frozenset[str] = frozenset(
    {
        "click_text",
        "click_image",
        "click_uia",
        "scroll_until",
        "wait_for",
        "assert_visible",
        "drag",
    }
)


@dataclass(frozen=True)
class BenchmarkRunMetrics:
    """Per-run metrics persisted by the repeated-run harness."""

    iteration: int
    status: RunStatus
    task_time_seconds: float
    step_count: int
    action_count: int
    retry_count: int
    grounding_attempt_count: int
    grounded_selection_count: int
    grounding_accuracy: float
    ambiguity_count: int
    recovery_count: int
    operator_intervention_count: int
    trace_dir: Path | None
    abort_reason: str | None
    observed_trace_phases: tuple[str, ...] = ()
    observed_report_fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class BenchmarkSummaryMetrics:
    """Aggregate metrics computed across all repeated runs."""

    run_count: int
    success_rate: float
    median_task_time_seconds: float
    step_count: int
    action_count: int
    retry_count: int
    grounding_accuracy: float
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
    grounding_accuracy: MetricVariance
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
class BenchmarkBaselineComparison:
    """Candidate run comparison against a deterministic timing baseline."""

    baseline_summary: BenchmarkSummaryMetrics
    candidate_summary: BenchmarkSummaryMetrics
    success_rate_delta: float
    median_task_time_improvement_seconds: float
    grounding_accuracy_delta: float
    ambiguity_rate_delta: float
    recovery_rate_delta: float
    operator_intervention_rate_delta: float
    improved_reliability: bool
    improved_speed: bool
    safety_not_reduced: bool
    improvement_proven: bool
    status: BenchmarkComparisonStatus


@dataclass(frozen=True)
class PointerTimingScenario:
    """Representative pointer movement used by benchmark model comparison."""

    name: str
    start: tuple[int, int]
    end: tuple[int, int]
    target_size_pixels: tuple[float, float]


@dataclass(frozen=True)
class PointerTimingComparisonSample:
    """One deterministic baseline-vs-model pointer timing comparison."""

    scenario: str
    baseline_duration_seconds: float
    model_duration_seconds: float
    duration_delta_seconds: float
    pointer_distance_pixels: float
    effective_target_width_pixels: float
    model_index_of_difficulty: float


@dataclass(frozen=True)
class PointerTimingComparisonReport:
    """Benchmark report comparing current pointer timing to a fixed baseline."""

    baseline_model: str
    comparison_model: str
    samples: tuple[PointerTimingComparisonSample, ...]


@dataclass(frozen=True)
class BenchmarkRunReport:
    """Machine-readable report for one repeated benchmark invocation."""

    schema_version: str
    generated_at: str
    task_path: Path
    output_dir: Path
    metrics_path: Path
    baseline_metrics_path: Path
    report_path: Path
    summary_report_path: Path
    trace_health_path: Path
    variance_report_path: Path
    baseline_comparison_path: Path
    pointer_timing_comparison_path: Path
    runs: tuple[BenchmarkRunMetrics, ...]
    baseline_runs: tuple[BenchmarkRunMetrics, ...]
    summary: BenchmarkSummaryMetrics
    variance: BenchmarkVarianceReport
    acceptance: BenchmarkAcceptanceResult
    baseline_comparison: BenchmarkBaselineComparison
    pointer_timing_comparison: PointerTimingComparisonReport
    monitoring_coverage: dict[str, object]


DEFAULT_POINTER_TIMING_SCENARIOS: tuple[PointerTimingScenario, ...] = (
    PointerTimingScenario(
        name="near-large-target",
        start=(0, 0),
        end=(100, 0),
        target_size_pixels=(100.0, 100.0),
    ),
    PointerTimingScenario(
        name="far-small-target",
        start=(0, 0),
        end=(500, 0),
        target_size_pixels=(10.0, 10.0),
    ),
    PointerTimingScenario(
        name="diagonal-medium-target",
        start=(50, 50),
        end=(450, 350),
        target_size_pixels=(40.0, 40.0),
    ),
)


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
        baseline_config = _deterministic_baseline_config(config, output_dir)
        baseline_runs = tuple(
            self._run_once(task_path, task, baseline_config, iteration)
            for iteration in range(1, iterations + 1)
        )
        summary = _summary_from_runs(runs)
        baseline_summary = _summary_from_runs(baseline_runs)
        variance = _variance_from_runs(runs)
        task_spec = benchmark_task_by_path(task_path)
        thresholds = task_spec.acceptance_thresholds if task_spec else None
        acceptance = evaluate_benchmark_acceptance(runs, summary, thresholds)
        monitoring_coverage = _monitoring_coverage_to_dict(task_spec, runs)
        metrics_path = output_dir / "runs.jsonl"
        baseline_metrics_path = output_dir / "baseline-runs.jsonl"
        report_path = output_dir / "benchmark-report.json"
        summary_report_path = output_dir / "benchmark-summary.md"
        trace_health_path = output_dir / "trace-health.json"
        variance_report_path = output_dir / "variance-report.json"
        baseline_comparison_path = output_dir / "baseline-comparison.json"
        pointer_timing_comparison_path = output_dir / "pointer-timing-comparison.json"
        generated_at = datetime.now(UTC).isoformat()
        baseline_comparison = compare_benchmark_to_baseline(
            baseline_summary,
            summary,
        )
        pointer_timing_comparison = compare_pointer_timing_models()
        _write_metrics(metrics_path, runs)
        _write_metrics(baseline_metrics_path, baseline_runs)
        _write_variance_report(variance_report_path, variance)
        _write_baseline_comparison(
            baseline_comparison_path,
            baseline_comparison,
        )
        _write_pointer_timing_comparison(
            pointer_timing_comparison_path,
            pointer_timing_comparison,
        )
        trace_health = _write_benchmark_trace_health(
            trace_health_path,
            output_dir / "traces",
        )
        _write_report(
            report_path,
            task_path,
            output_dir,
            metrics_path,
            baseline_metrics_path,
            summary_report_path,
            trace_health_path,
            variance_report_path,
            baseline_comparison_path,
            pointer_timing_comparison_path,
            generated_at,
            task_spec,
            monitoring_coverage,
            runs,
            baseline_runs,
            summary,
            baseline_summary,
            acceptance,
            baseline_comparison,
            pointer_timing_comparison,
        )
        _write_benchmark_summary(
            summary_report_path,
            task_path,
            report_path,
            metrics_path,
            baseline_metrics_path,
            trace_health_path,
            variance_report_path,
            baseline_comparison_path,
            pointer_timing_comparison_path,
            generated_at,
            summary,
            trace_health,
            acceptance,
            baseline_comparison,
            task_spec,
            runs,
            monitoring_coverage,
        )
        return BenchmarkRunReport(
            schema_version=BENCHMARK_REPORT_SCHEMA_VERSION,
            generated_at=generated_at,
            task_path=task_path,
            output_dir=output_dir,
            metrics_path=metrics_path,
            baseline_metrics_path=baseline_metrics_path,
            report_path=report_path,
            summary_report_path=summary_report_path,
            trace_health_path=trace_health_path,
            variance_report_path=variance_report_path,
            baseline_comparison_path=baseline_comparison_path,
            pointer_timing_comparison_path=pointer_timing_comparison_path,
            runs=runs,
            baseline_runs=baseline_runs,
            summary=summary,
            variance=variance,
            acceptance=acceptance,
            baseline_comparison=baseline_comparison,
            pointer_timing_comparison=pointer_timing_comparison,
            monitoring_coverage=monitoring_coverage,
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


def _deterministic_baseline_config(
    config: RuntimeConfig,
    output_dir: Path,
) -> RuntimeConfig:
    """Disable execution-profile timing while preserving safety settings."""

    return replace(
        config,
        trace_root=output_dir / "baseline-traces",
        execution_profile=ExecutionProfile(enabled=False),
    )


def _metrics_from_report(
    iteration: int,
    report: RunReport,
    task_time_seconds: float,
) -> BenchmarkRunMetrics:
    selection_events = tuple(
        event
        for event in report.events
        if event.phase == "select_target"
        and event.metadata.get("step_action") in TARGET_GROUNDING_ACTIONS
    )
    grounded_selection_count = sum(
        1 for event in selection_events if event.metadata.get("candidate_id")
    )
    grounding_attempt_count = len(selection_events)
    return BenchmarkRunMetrics(
        iteration=iteration,
        status=report.status,
        task_time_seconds=task_time_seconds,
        step_count=len(report.steps),
        action_count=sum(
            1 for event in report.events if event.phase == "execute_action"
        ),
        retry_count=sum(max(step.attempts - 1, 0) for step in report.steps),
        grounding_attempt_count=grounding_attempt_count,
        grounded_selection_count=grounded_selection_count,
        grounding_accuracy=_grounding_accuracy(
            grounded_selection_count,
            grounding_attempt_count,
        ),
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
        observed_trace_phases=_observed_trace_phases(report),
        observed_report_fields=_observed_report_fields(),
    )


def _observed_trace_phases(report: RunReport) -> tuple[str, ...]:
    return tuple(dict.fromkeys(event.phase for event in report.events))


def _observed_report_fields() -> tuple[str, ...]:
    return (
        "task_name",
        "status",
        "abort_reason",
        "steps",
        "events",
        "trace_dir",
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


def compare_benchmark_to_baseline(
    baseline: BenchmarkSummaryMetrics,
    candidate: BenchmarkSummaryMetrics,
) -> BenchmarkBaselineComparison:
    """Compare candidate benchmark behavior against deterministic timing."""

    success_rate_delta = candidate.success_rate - baseline.success_rate
    median_task_time_improvement_seconds = (
        baseline.median_task_time_seconds - candidate.median_task_time_seconds
    )
    grounding_accuracy_delta = (
        candidate.grounding_accuracy - baseline.grounding_accuracy
    )
    ambiguity_rate_delta = candidate.ambiguity_rate - baseline.ambiguity_rate
    recovery_rate_delta = candidate.recovery_rate - baseline.recovery_rate
    operator_intervention_rate_delta = (
        candidate.operator_intervention_rate - baseline.operator_intervention_rate
    )
    improved_reliability = success_rate_delta > 0
    improved_speed = median_task_time_improvement_seconds > 0
    safety_not_reduced = (
        grounding_accuracy_delta >= 0
        and ambiguity_rate_delta <= 0
        and recovery_rate_delta <= 0
        and operator_intervention_rate_delta <= 0
    )
    improvement_proven = safety_not_reduced and (
        improved_reliability or improved_speed
    )
    reliability_regressed = success_rate_delta < 0
    status: BenchmarkComparisonStatus
    if improvement_proven:
        status = "improved"
    elif safety_not_reduced and not reliability_regressed:
        status = "neutral"
    else:
        status = "regressed"
    return BenchmarkBaselineComparison(
        baseline_summary=baseline,
        candidate_summary=candidate,
        success_rate_delta=success_rate_delta,
        median_task_time_improvement_seconds=median_task_time_improvement_seconds,
        grounding_accuracy_delta=grounding_accuracy_delta,
        ambiguity_rate_delta=ambiguity_rate_delta,
        recovery_rate_delta=recovery_rate_delta,
        operator_intervention_rate_delta=operator_intervention_rate_delta,
        improved_reliability=improved_reliability,
        improved_speed=improved_speed,
        safety_not_reduced=safety_not_reduced,
        improvement_proven=improvement_proven,
        status=status,
    )


def compare_pointer_timing_models(
    scenarios: tuple[PointerTimingScenario, ...] = DEFAULT_POINTER_TIMING_SCENARIOS,
) -> PointerTimingComparisonReport:
    """Compare current pointer timing against a deterministic fixed baseline."""

    baseline_planner = SmoothMovementPlanner(
        DEFAULT_POINTER_TIMING_PROFILE,
        _DeterministicPointerTimingModel(
            DEFAULT_BASELINE_POINTER_DURATION_SECONDS,
        ),
    )
    comparison_planner = SmoothMovementPlanner(
        DEFAULT_POINTER_TIMING_PROFILE,
        FittsLawPointerTimingModel(),
    )
    samples = tuple(
        _compare_pointer_timing_scenario(
            scenario,
            baseline_planner,
            comparison_planner,
        )
        for scenario in scenarios
    )
    return PointerTimingComparisonReport(
        baseline_model="deterministic_fixed_duration",
        comparison_model="fitts_law",
        samples=samples,
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
    baseline_metrics_path: Path,
    summary_report_path: Path,
    trace_health_path: Path,
    variance_report_path: Path,
    baseline_comparison_path: Path,
    pointer_timing_comparison_path: Path,
    generated_at: str,
    task_spec: BenchmarkTaskSpec | None,
    monitoring_coverage: dict[str, object],
    runs: tuple[BenchmarkRunMetrics, ...],
    baseline_runs: tuple[BenchmarkRunMetrics, ...],
    summary: BenchmarkSummaryMetrics,
    baseline_summary: BenchmarkSummaryMetrics,
    acceptance: BenchmarkAcceptanceResult,
    baseline_comparison: BenchmarkBaselineComparison,
    pointer_timing_comparison: PointerTimingComparisonReport,
) -> None:
    payload = {
        "schema_version": BENCHMARK_REPORT_SCHEMA_VERSION,
        "generated_at": generated_at,
        "task_path": str(task_path),
        "output_dir": str(output_dir),
        "metrics_path": str(metrics_path),
        "baseline_metrics_path": str(baseline_metrics_path),
        "trace_health_path": str(trace_health_path),
        "variance_report_path": str(variance_report_path),
        "baseline_comparison_path": str(baseline_comparison_path),
        "pointer_timing_comparison_path": str(pointer_timing_comparison_path),
        "report_artifacts": _benchmark_report_artifacts_to_dict(
            path,
            metrics_path,
            baseline_metrics_path,
            summary_report_path,
            trace_health_path,
            variance_report_path,
            baseline_comparison_path,
            pointer_timing_comparison_path,
        ),
        "observability_contract": _observability_contract_to_dict(task_spec),
        "monitoring_coverage": monitoring_coverage,
        "iterations": len(runs),
        "summary": _summary_to_dict(summary),
        "baseline_summary": _summary_to_dict(baseline_summary),
        "acceptance": _acceptance_to_dict(acceptance),
        "baseline_comparison": _baseline_comparison_to_dict(baseline_comparison),
        "pointer_timing_comparison": _pointer_timing_comparison_to_dict(
            pointer_timing_comparison,
        ),
        "runs": [_metrics_to_dict(run) for run in runs],
        "baseline_runs": [_metrics_to_dict(run) for run in baseline_runs],
    }
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _benchmark_report_artifacts_to_dict(
    report_path: Path,
    metrics_path: Path,
    baseline_metrics_path: Path,
    summary_report_path: Path,
    trace_health_path: Path,
    variance_report_path: Path,
    baseline_comparison_path: Path,
    pointer_timing_comparison_path: Path,
) -> dict[str, str]:
    return {
        "report": str(report_path),
        "metrics": str(metrics_path),
        "baseline_metrics": str(baseline_metrics_path),
        "summary": str(summary_report_path),
        "trace_health": str(trace_health_path),
        "variance": str(variance_report_path),
        "baseline_comparison": str(baseline_comparison_path),
        "pointer_timing_comparison": str(pointer_timing_comparison_path),
    }


def _write_benchmark_trace_health(
    path: Path,
    trace_root: Path,
) -> dict[str, object]:
    health = LocalTraceService(trace_root).trace_health()
    path.write_text(
        json.dumps(health, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return health


def _observability_contract_to_dict(
    task_spec: BenchmarkTaskSpec | None,
) -> dict[str, object]:
    if task_spec is None:
        return {"configured": False}
    return {
        "configured": True,
        "benchmark_task_id": task_spec.id,
        "pipeline_modes": list(task_spec.pipeline_modes),
        "deep_search_sources": list(task_spec.deep_search_sources),
        "required_trace_phases": list(task_spec.required_trace_phases),
        "required_report_fields": list(task_spec.required_report_fields),
        "required_metrics": list(task_spec.required_metrics),
    }


def _monitoring_coverage_to_dict(
    task_spec: BenchmarkTaskSpec | None,
    runs: tuple[BenchmarkRunMetrics, ...],
) -> dict[str, object]:
    if task_spec is None:
        return {"configured": False}
    observed = sorted(
        phase for run in runs for phase in run.observed_trace_phases
    )
    observed = list(dict.fromkeys(observed))
    required = list(task_spec.required_trace_phases)
    observed_report_fields = sorted(
        field for run in runs for field in run.observed_report_fields
    )
    observed_report_fields = list(dict.fromkeys(observed_report_fields))
    required_report_fields = list(task_spec.required_report_fields)
    missing_trace_phases = [phase for phase in required if phase not in observed]
    missing_report_fields = [
        field for field in required_report_fields if field not in observed_report_fields
    ]
    return {
        "configured": True,
        "passed": not missing_trace_phases and not missing_report_fields,
        "required_trace_phases": required,
        "observed_trace_phases": observed,
        "missing_trace_phases": missing_trace_phases,
        "required_report_fields": required_report_fields,
        "observed_report_fields": observed_report_fields,
        "missing_report_fields": missing_report_fields,
    }


def _write_benchmark_summary(
    path: Path,
    task_path: Path,
    report_path: Path,
    metrics_path: Path,
    baseline_metrics_path: Path,
    trace_health_path: Path,
    variance_report_path: Path,
    baseline_comparison_path: Path,
    pointer_timing_comparison_path: Path,
    generated_at: str,
    summary: BenchmarkSummaryMetrics,
    trace_health: dict[str, object],
    acceptance: BenchmarkAcceptanceResult,
    baseline_comparison: BenchmarkBaselineComparison,
    task_spec: BenchmarkTaskSpec | None,
    runs: tuple[BenchmarkRunMetrics, ...],
    monitoring_coverage: dict[str, object],
) -> None:
    contract = _observability_contract_to_dict(task_spec)
    lines = [
        "# Benchmark Summary",
        "",
        f"- Schema version: `{BENCHMARK_REPORT_SCHEMA_VERSION}`",
        f"- Generated at: `{generated_at}`",
        f"- Task: `{task_path}`",
        f"- Report: `{report_path}`",
        f"- Trace health: `{trace_health_path}`",
        f"- Trace health schema: `{trace_health.get('schema_version', 'unknown')}`",
        "- Trace health generated at: "
        f"`{trace_health.get('generated_at', 'unknown')}`",
        f"- Trace health status: `{trace_health.get('health_status', 'unknown')}`",
        f"- Attention traces: `{len(_trace_health_attention_traces(trace_health))}`",
        f"- Artifact traces: `{trace_health.get('artifact_trace_count', 0)}`",
        f"- Acceptance: `{acceptance.status}`",
        f"- Baseline status: `{baseline_comparison.status}`",
        f"- Success rate: `{summary.success_rate}`",
        f"- Grounding accuracy: `{summary.grounding_accuracy}`",
        f"- Ambiguity rate: `{summary.ambiguity_rate}`",
        f"- Recovery rate: `{summary.recovery_rate}`",
        "",
        "## Observability Contract",
        "",
        *_benchmark_observability_summary_lines(contract),
        "",
        "## Monitoring Coverage",
        "",
        *_benchmark_monitoring_coverage_lines(monitoring_coverage),
        "",
        "## Report Artifacts",
        "",
        *_benchmark_report_artifact_lines(
            _benchmark_report_artifacts_to_dict(
                report_path,
                metrics_path,
                baseline_metrics_path,
                path,
                trace_health_path,
                variance_report_path,
                baseline_comparison_path,
                pointer_timing_comparison_path,
            ),
        ),
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _benchmark_monitoring_coverage_lines(
    coverage: dict[str, object],
) -> list[str]:
    if coverage.get("configured") is not True:
        return ["- Configured: `false`"]
    return [
        f"- Passed: `{coverage.get('passed', False)}`",
        "- Observed trace phases: "
        f"`{_contract_list(coverage, 'observed_trace_phases')}`",
        "- Missing trace phases: "
        f"`{_contract_list(coverage, 'missing_trace_phases')}`",
        "- Observed report fields: "
        f"`{_contract_list(coverage, 'observed_report_fields')}`",
        "- Missing report fields: "
        f"`{_contract_list(coverage, 'missing_report_fields')}`",
    ]


def _benchmark_report_artifact_lines(artifacts: dict[str, str]) -> list[str]:
    return [f"- `{name}`: `{path}`" for name, path in artifacts.items()]


def _trace_health_attention_traces(health: dict[str, object]) -> list[object]:
    value = health.get("attention_traces")
    return value if isinstance(value, list) else []


def _benchmark_observability_summary_lines(
    contract: dict[str, object],
) -> list[str]:
    if contract.get("configured") is not True:
        return ["- Configured: `false`"]
    pipeline_modes = _contract_list(contract, "pipeline_modes")
    deep_search_sources = _contract_list(contract, "deep_search_sources")
    required_trace_phases = _contract_list(contract, "required_trace_phases")
    required_report_fields = _contract_list(contract, "required_report_fields")
    required_metrics = _contract_list(contract, "required_metrics")
    return [
        "- Configured: `true`",
        f"- Benchmark task: `{contract.get('benchmark_task_id', 'unknown')}`",
        f"- Pipeline modes: `{pipeline_modes}`",
        f"- Deep-search sources: `{deep_search_sources}`",
        f"- Required trace phases: `{required_trace_phases}`",
        f"- Required report fields: `{required_report_fields}`",
        f"- Required metrics: `{required_metrics}`",
    ]


def _contract_list(contract: dict[str, object], key: str) -> str:
    value = contract.get(key, [])
    if not isinstance(value, list):
        return ""
    return ", ".join(str(item) for item in value)


def _write_variance_report(
    path: Path,
    variance: BenchmarkVarianceReport,
) -> None:
    path.write_text(
        json.dumps(_variance_report_to_dict(variance), indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )


def _write_baseline_comparison(
    path: Path,
    comparison: BenchmarkBaselineComparison,
) -> None:
    path.write_text(
        json.dumps(
            _baseline_comparison_to_dict(comparison),
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def _write_pointer_timing_comparison(
    path: Path,
    report: PointerTimingComparisonReport,
) -> None:
    path.write_text(
        json.dumps(_pointer_timing_comparison_to_dict(report), indent=2, sort_keys=True)
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
        grounding_accuracy=_grounding_accuracy(
            sum(run.grounded_selection_count for run in runs),
            sum(run.grounding_attempt_count for run in runs),
        ),
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


def _grounding_accuracy(grounded_count: int, attempt_count: int) -> float:
    if attempt_count == 0:
        return 1.0
    return grounded_count / attempt_count


def _variance_from_runs(
    runs: tuple[BenchmarkRunMetrics, ...],
) -> BenchmarkVarianceReport:
    return BenchmarkVarianceReport(
        task_time_seconds=_metric_variance(run.task_time_seconds for run in runs),
        step_count=_metric_variance(float(run.step_count) for run in runs),
        action_count=_metric_variance(float(run.action_count) for run in runs),
        retry_count=_metric_variance(float(run.retry_count) for run in runs),
        grounding_accuracy=_metric_variance(run.grounding_accuracy for run in runs),
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
        "grounding_accuracy": summary.grounding_accuracy,
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
        "grounding_accuracy": _variance_to_dict(report.grounding_accuracy),
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


def _baseline_comparison_to_dict(
    comparison: BenchmarkBaselineComparison,
) -> dict[str, object]:
    return {
        "baseline_summary": _summary_to_dict(comparison.baseline_summary),
        "candidate_summary": _summary_to_dict(comparison.candidate_summary),
        "success_rate_delta": comparison.success_rate_delta,
        "median_task_time_improvement_seconds": (
            comparison.median_task_time_improvement_seconds
        ),
        "grounding_accuracy_delta": comparison.grounding_accuracy_delta,
        "ambiguity_rate_delta": comparison.ambiguity_rate_delta,
        "recovery_rate_delta": comparison.recovery_rate_delta,
        "operator_intervention_rate_delta": (
            comparison.operator_intervention_rate_delta
        ),
        "improved_reliability": comparison.improved_reliability,
        "improved_speed": comparison.improved_speed,
        "safety_not_reduced": comparison.safety_not_reduced,
        "improvement_proven": comparison.improvement_proven,
        "status": comparison.status,
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


def _pointer_timing_comparison_to_dict(
    report: PointerTimingComparisonReport,
) -> dict[str, object]:
    return {
        "baseline_model": report.baseline_model,
        "comparison_model": report.comparison_model,
        "samples": [
            _pointer_timing_sample_to_dict(sample) for sample in report.samples
        ],
    }


def _pointer_timing_sample_to_dict(
    sample: PointerTimingComparisonSample,
) -> dict[str, object]:
    return {
        "scenario": sample.scenario,
        "baseline_duration_seconds": sample.baseline_duration_seconds,
        "model_duration_seconds": sample.model_duration_seconds,
        "duration_delta_seconds": sample.duration_delta_seconds,
        "pointer_distance_pixels": sample.pointer_distance_pixels,
        "effective_target_width_pixels": sample.effective_target_width_pixels,
        "model_index_of_difficulty": sample.model_index_of_difficulty,
    }


def _metrics_to_dict(metrics: BenchmarkRunMetrics) -> dict[str, object]:
    return {
        "iteration": metrics.iteration,
        "status": metrics.status,
        "task_time_seconds": metrics.task_time_seconds,
        "step_count": metrics.step_count,
        "action_count": metrics.action_count,
        "retry_count": metrics.retry_count,
        "grounding_attempt_count": metrics.grounding_attempt_count,
        "grounded_selection_count": metrics.grounded_selection_count,
        "grounding_accuracy": metrics.grounding_accuracy,
        "ambiguity_count": metrics.ambiguity_count,
        "recovery_count": metrics.recovery_count,
        "operator_intervention_count": metrics.operator_intervention_count,
        "trace_dir": str(metrics.trace_dir) if metrics.trace_dir else None,
        "abort_reason": metrics.abort_reason,
        "observed_trace_phases": list(metrics.observed_trace_phases),
        "observed_report_fields": list(metrics.observed_report_fields),
    }


def _compare_pointer_timing_scenario(
    scenario: PointerTimingScenario,
    baseline_planner: SmoothMovementPlanner,
    comparison_planner: SmoothMovementPlanner,
) -> PointerTimingComparisonSample:
    baseline_plan = baseline_planner.plan(
        scenario.start,
        scenario.end,
        scenario.target_size_pixels,
    )
    comparison_plan = comparison_planner.plan(
        scenario.start,
        scenario.end,
        scenario.target_size_pixels,
    )
    comparison_estimate = _require_pointer_timing_estimate(comparison_plan)
    return PointerTimingComparisonSample(
        scenario=scenario.name,
        baseline_duration_seconds=baseline_plan.duration_seconds,
        model_duration_seconds=comparison_plan.duration_seconds,
        duration_delta_seconds=(
            comparison_plan.duration_seconds - baseline_plan.duration_seconds
        ),
        pointer_distance_pixels=comparison_estimate.distance_pixels,
        effective_target_width_pixels=(
            comparison_estimate.effective_target_width_pixels
        ),
        model_index_of_difficulty=comparison_estimate.index_of_difficulty,
    )


def _require_pointer_timing_estimate(plan: MovementPlan) -> PointerTimingEstimate:
    if plan.timing_estimate is None:
        raise ValueError("movement plan did not include a pointer timing estimate")
    return plan.timing_estimate


@dataclass(frozen=True)
class _DeterministicPointerTimingModel:
    """Fixed-duration model used as the benchmark comparison baseline."""

    duration_seconds: float

    def estimate(self, context: PointerTimingContext) -> PointerTimingEstimate:
        return PointerTimingEstimate(
            model="deterministic_fixed_duration",
            duration_seconds=self.duration_seconds,
            distance_pixels=context.distance_pixels,
            effective_target_width_pixels=context.effective_target_width_pixels,
            index_of_difficulty=0.0,
        )
