import json
from pathlib import Path

from desktop_agent.benchmark_runner import (
    BenchmarkRunHarness,
    BenchmarkRunMetrics,
    BenchmarkSummaryMetrics,
    compare_pointer_timing_models,
    evaluate_benchmark_acceptance,
)
from desktop_agent.benchmarks import BenchmarkAcceptanceThresholds, all_benchmark_tasks


def test_benchmark_run_harness_stores_per_run_metrics(tmp_path: Path) -> None:
    output_dir = tmp_path / "benchmark"

    report = BenchmarkRunHarness().run_task(
        Path("examples/browser-task.yaml"),
        iterations=2,
        output_dir=output_dir,
    )

    metrics_lines = report.metrics_path.read_text(encoding="utf-8").splitlines()
    report_payload = json.loads(report.report_path.read_text(encoding="utf-8"))
    variance_payload = json.loads(
        report.variance_report_path.read_text(encoding="utf-8")
    )
    pointer_timing_payload = json.loads(
        report.pointer_timing_comparison_path.read_text(encoding="utf-8")
    )
    assert len(report.runs) == 2
    assert report.summary.run_count == 2
    assert report.summary.success_rate == 1.0
    assert report.summary.step_count > 0
    assert report.summary.action_count > 0
    assert report.variance.step_count.minimum > 0
    assert report.variance.action_count.maximum > 0
    assert report.acceptance.configured
    assert report.acceptance.passed
    assert report.acceptance.status == "passed"
    assert len(report.pointer_timing_comparison.samples) == 3
    assert len(metrics_lines) == 2
    assert report_payload["iterations"] == 2
    assert report_payload["variance_report_path"] == str(report.variance_report_path)
    assert report_payload["pointer_timing_comparison_path"] == str(
        report.pointer_timing_comparison_path
    )
    assert report_payload["summary"]["success_rate"] == 1.0
    assert report_payload["summary"]["median_task_time_seconds"] >= 0
    assert report_payload["summary"]["step_count"] > 0
    assert report_payload["summary"]["action_count"] > 0
    assert report_payload["summary"]["retry_count"] >= 0
    assert report_payload["summary"]["ambiguity_rate"] == 0
    assert report_payload["summary"]["recovery_rate"] >= 0
    assert report_payload["summary"]["operator_intervention_rate"] == 0
    assert report_payload["acceptance"]["configured"] is True
    assert report_payload["acceptance"]["passed"] is True
    assert report_payload["acceptance"]["status"] == "passed"
    assert report_payload["acceptance"]["thresholds"]["min_success_rate"] == 1.0
    assert report_payload["runs"][0]["status"] == "passed"
    assert report_payload["runs"][0]["step_count"] > 0
    assert report_payload["runs"][0]["action_count"] > 0
    assert Path(report_payload["runs"][0]["trace_dir"]).exists()
    assert variance_payload["task_time_seconds"]["minimum"] >= 0
    assert variance_payload["step_count"]["maximum"] > 0
    assert variance_payload["recovery_count"]["population_stdev"] >= 0
    assert pointer_timing_payload["comparison_model"] == "fitts_law"
    assert pointer_timing_payload["samples"][0]["scenario"] == "near-large-target"
    assert (
        report_payload["pointer_timing_comparison"]["samples"][1]["scenario"]
        == "far-small-target"
    )


def test_benchmark_run_harness_rejects_empty_iterations(tmp_path: Path) -> None:
    try:
        BenchmarkRunHarness().run_task(
            Path("examples/browser-task.yaml"),
            iterations=0,
            output_dir=tmp_path / "benchmark",
        )
    except ValueError as exc:
        assert str(exc) == "iterations must be greater than zero"
    else:
        raise AssertionError("expected iterations validation failure")


def test_pointer_timing_comparison_contrasts_model_with_baseline() -> None:
    comparison = compare_pointer_timing_models()
    samples = {sample.scenario: sample for sample in comparison.samples}

    near = samples["near-large-target"]
    far = samples["far-small-target"]

    assert comparison.baseline_model == "deterministic_fixed_duration"
    assert comparison.comparison_model == "fitts_law"
    assert near.baseline_duration_seconds == 0.2
    assert far.baseline_duration_seconds == 0.2
    assert far.model_duration_seconds > near.model_duration_seconds
    assert far.model_index_of_difficulty > near.model_index_of_difficulty


def test_benchmark_acceptance_records_threshold_failures() -> None:
    runs = (
        BenchmarkRunMetrics(
            iteration=1,
            status="passed",
            task_time_seconds=2.0,
            step_count=2,
            action_count=3,
            retry_count=1,
            ambiguity_count=1,
            recovery_count=0,
            operator_intervention_count=0,
            trace_dir=None,
            abort_reason=None,
        ),
    )
    summary = BenchmarkSummaryMetrics(
        run_count=1,
        success_rate=1.0,
        median_task_time_seconds=2.0,
        step_count=2,
        action_count=3,
        retry_count=1,
        ambiguity_rate=1.0,
        recovery_rate=0.0,
        operator_intervention_rate=0.0,
    )
    thresholds = BenchmarkAcceptanceThresholds(
        min_success_rate=1.0,
        max_median_task_time_seconds=1.0,
        max_task_time_seconds_per_run=1.0,
        max_step_count_per_run=1,
        max_action_count_per_run=1,
        max_retry_count_per_run=0,
        max_ambiguity_rate=0.0,
        max_recovery_rate=0.0,
        max_operator_intervention_rate=0.0,
    )

    acceptance = evaluate_benchmark_acceptance(runs, summary, thresholds)

    assert not acceptance.passed
    assert acceptance.status == "failed"
    assert any("max_action_count_per_run" in failure for failure in acceptance.failures)


def test_benchmark_acceptance_is_not_configured_for_ad_hoc_tasks() -> None:
    runs = (
        BenchmarkRunMetrics(
            iteration=1,
            status="passed",
            task_time_seconds=0.1,
            step_count=1,
            action_count=1,
            retry_count=0,
            ambiguity_count=0,
            recovery_count=0,
            operator_intervention_count=0,
            trace_dir=None,
            abort_reason=None,
        ),
    )
    summary = BenchmarkSummaryMetrics(
        run_count=1,
        success_rate=1.0,
        median_task_time_seconds=0.1,
        step_count=1,
        action_count=1,
        retry_count=0,
        ambiguity_rate=0.0,
        recovery_rate=0.0,
        operator_intervention_rate=0.0,
    )

    acceptance = evaluate_benchmark_acceptance(runs, summary, None)

    assert acceptance.configured is False
    assert acceptance.passed is True
    assert acceptance.status == "not_configured"


def test_builtin_benchmark_thresholds_pass_current_dry_run_baseline(
    tmp_path: Path,
) -> None:
    for task in all_benchmark_tasks():
        report = BenchmarkRunHarness().run_task(
            task.task_path,
            iterations=1,
            output_dir=tmp_path / task.id,
        )

        assert report.acceptance.configured
        assert report.acceptance.passed, report.acceptance.failures
