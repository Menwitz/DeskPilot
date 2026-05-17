import json
from pathlib import Path

from desktop_agent.benchmark_runner import (
    BenchmarkRunHarness,
    BenchmarkRunMetrics,
    BenchmarkSummaryMetrics,
    _summary_from_runs,
    _summary_to_dict,
    _variance_from_runs,
    _write_variance_report,
    compare_benchmark_to_baseline,
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
    summary_markdown = report.summary_report_path.read_text(encoding="utf-8")
    trace_health_payload = json.loads(
        report.trace_health_path.read_text(encoding="utf-8")
    )
    variance_payload = json.loads(
        report.variance_report_path.read_text(encoding="utf-8")
    )
    pointer_timing_payload = json.loads(
        report.pointer_timing_comparison_path.read_text(encoding="utf-8")
    )
    baseline_metrics_lines = report.baseline_metrics_path.read_text(
        encoding="utf-8"
    ).splitlines()
    assert len(report.runs) == 2
    assert len(report.baseline_runs) == 2
    assert report.summary.run_count == 2
    assert report.baseline_comparison.safety_not_reduced
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
    assert report.schema_version == "benchmark_report_v1"
    assert isinstance(report.generated_at, str)
    assert report_payload["schema_version"] == "benchmark_report_v1"
    assert report_payload["generated_at"] == report.generated_at
    assert report_payload["iterations"] == 2
    assert report_payload["baseline_metrics_path"] == str(
        report.baseline_metrics_path
    )
    assert report_payload["variance_report_path"] == str(report.variance_report_path)
    assert report_payload["baseline_comparison_path"] == str(
        report.baseline_comparison_path
    )
    assert report_payload["pointer_timing_comparison_path"] == str(
        report.pointer_timing_comparison_path
    )
    assert report_payload["trace_health_path"] == str(report.trace_health_path)
    assert report.trace_health_path.exists()
    assert trace_health_payload["trace_count"] == 2
    assert trace_health_payload["health_status"] == "ok"
    assert trace_health_payload["by_kind"] == {"run": 2}
    assert report.summary_report_path.exists()
    assert "# Benchmark Summary" in summary_markdown
    assert "- Schema version: `benchmark_report_v1`" in summary_markdown
    assert f"- Generated at: `{report.generated_at}`" in summary_markdown
    assert f"- Trace health: `{report.trace_health_path}`" in summary_markdown
    assert "- Trace health status: `ok`" in summary_markdown
    assert "- Attention traces: `0`" in summary_markdown
    assert "## Monitoring Coverage" in summary_markdown
    assert "- Observed trace phases: `" in summary_markdown
    assert "select_target" in summary_markdown
    assert "- Observed report fields: `" in summary_markdown
    assert "trace_dir" in summary_markdown
    assert "- Missing report fields: ``" in summary_markdown
    assert "- Acceptance: `passed`" in summary_markdown
    assert "- Deep-search sources: `uia, ocr, image, unknown`" in summary_markdown
    assert report_payload["observability_contract"]["configured"] is True
    assert report_payload["observability_contract"]["benchmark_task_id"] == (
        "browser-fixture-demo"
    )
    assert report_payload["observability_contract"]["deep_search_sources"] == [
        "uia",
        "ocr",
        "image",
        "unknown",
    ]
    assert report_payload["monitoring_coverage"]["configured"] is True
    assert "select_target" in report_payload["monitoring_coverage"][
        "observed_trace_phases"
    ]
    assert "trace_dir" in report_payload["monitoring_coverage"][
        "observed_report_fields"
    ]
    assert "select_target" in report_payload["runs"][0]["observed_trace_phases"]
    assert "trace_dir" in report_payload["runs"][0]["observed_report_fields"]
    assert "select_target" in report_payload["observability_contract"][
        "required_trace_phases"
    ]
    assert "trace_dir" in report_payload["observability_contract"][
        "required_report_fields"
    ]
    assert "grounding_accuracy" in report_payload["observability_contract"][
        "required_metrics"
    ]
    assert report_payload["summary"]["success_rate"] == 1.0
    assert report_payload["summary"]["median_task_time_seconds"] >= 0
    assert report_payload["summary"]["step_count"] > 0
    assert report_payload["summary"]["action_count"] > 0
    assert report_payload["summary"]["retry_count"] >= 0
    assert report_payload["summary"]["grounding_accuracy"] == 1.0
    assert report_payload["summary"]["ambiguity_rate"] == 0
    assert report_payload["summary"]["recovery_rate"] >= 0
    assert report_payload["summary"]["operator_intervention_rate"] == 0
    assert report_payload["acceptance"]["configured"] is True
    assert report_payload["acceptance"]["passed"] is True
    assert report_payload["acceptance"]["status"] == "passed"
    assert report_payload["acceptance"]["thresholds"]["min_success_rate"] == 1.0
    assert report_payload["baseline_summary"]["success_rate"] == 1.0
    assert report_payload["baseline_comparison"]["safety_not_reduced"] is True
    assert report_payload["baseline_comparison"]["status"] in {
        "improved",
        "neutral",
        "regressed",
    }
    assert report_payload["runs"][0]["status"] == "passed"
    assert report_payload["baseline_runs"][0]["status"] == "passed"
    assert report_payload["runs"][0]["step_count"] > 0
    assert report_payload["runs"][0]["action_count"] > 0
    assert report_payload["runs"][0]["grounding_attempt_count"] > 0
    assert report_payload["runs"][0]["grounded_selection_count"] > 0
    assert report_payload["runs"][0]["grounding_accuracy"] == 1.0
    assert Path(report_payload["runs"][0]["trace_dir"]).exists()
    assert Path(report_payload["baseline_runs"][0]["trace_dir"]).exists()
    assert variance_payload["task_time_seconds"]["minimum"] >= 0
    assert variance_payload["step_count"]["maximum"] > 0
    assert variance_payload["grounding_accuracy"]["minimum"] == 1.0
    assert variance_payload["recovery_count"]["population_stdev"] >= 0
    assert pointer_timing_payload["comparison_model"] == "fitts_law"
    assert pointer_timing_payload["samples"][0]["scenario"] == "near-large-target"
    assert (
        report_payload["pointer_timing_comparison"]["samples"][1]["scenario"]
        == "far-small-target"
    )
    assert len(baseline_metrics_lines) == 2


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


def test_benchmark_aggregation_and_variance_reporting_regression(
    tmp_path: Path,
) -> None:
    # The mixed run set catches aggregate-vs-average grounding mistakes and
    # ensures nonzero monitoring rates survive JSON variance reporting.
    runs = (
        BenchmarkRunMetrics(
            iteration=1,
            status="passed",
            task_time_seconds=1.0,
            step_count=2,
            action_count=3,
            retry_count=0,
            grounding_attempt_count=2,
            grounded_selection_count=2,
            grounding_accuracy=1.0,
            ambiguity_count=0,
            recovery_count=0,
            operator_intervention_count=0,
            trace_dir=None,
            abort_reason=None,
        ),
        BenchmarkRunMetrics(
            iteration=2,
            status="failed",
            task_time_seconds=3.0,
            step_count=4,
            action_count=5,
            retry_count=2,
            grounding_attempt_count=4,
            grounded_selection_count=2,
            grounding_accuracy=0.5,
            ambiguity_count=1,
            recovery_count=2,
            operator_intervention_count=1,
            trace_dir=None,
            abort_reason="selection_ambiguity",
        ),
        BenchmarkRunMetrics(
            iteration=3,
            status="passed",
            task_time_seconds=5.0,
            step_count=6,
            action_count=7,
            retry_count=1,
            grounding_attempt_count=0,
            grounded_selection_count=0,
            grounding_accuracy=1.0,
            ambiguity_count=0,
            recovery_count=0,
            operator_intervention_count=0,
            trace_dir=None,
            abort_reason=None,
        ),
    )

    summary = _summary_from_runs(runs)
    variance = _variance_from_runs(runs)
    variance_path = tmp_path / "variance-report.json"
    _write_variance_report(variance_path, variance)

    summary_payload = _summary_to_dict(summary)
    variance_payload = json.loads(variance_path.read_text(encoding="utf-8"))
    assert summary_payload == {
        "run_count": 3,
        "success_rate": 2 / 3,
        "median_task_time_seconds": 3.0,
        "step_count": 12,
        "action_count": 15,
        "retry_count": 3,
        "grounding_accuracy": 4 / 6,
        "ambiguity_rate": 1 / 3,
        "recovery_rate": 1 / 3,
        "operator_intervention_rate": 1 / 3,
    }
    assert variance_payload["task_time_seconds"]["minimum"] == 1.0
    assert variance_payload["task_time_seconds"]["maximum"] == 5.0
    assert variance_payload["task_time_seconds"]["mean"] == 3.0
    assert variance_payload["step_count"]["mean"] == 4.0
    assert variance_payload["action_count"]["mean"] == 5.0
    assert variance_payload["retry_count"]["mean"] == 1.0
    assert variance_payload["grounding_accuracy"]["minimum"] == 0.5
    assert variance_payload["grounding_accuracy"]["maximum"] == 1.0
    assert variance_payload["ambiguity_count"]["mean"] == 1 / 3
    assert variance_payload["recovery_count"]["maximum"] == 2.0
    assert variance_payload["operator_intervention_count"]["mean"] == 1 / 3


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


def test_baseline_comparison_requires_improvement_without_safety_loss() -> None:
    baseline = BenchmarkSummaryMetrics(
        run_count=3,
        success_rate=0.8,
        median_task_time_seconds=5.0,
        step_count=12,
        action_count=12,
        retry_count=2,
        grounding_accuracy=0.95,
        ambiguity_rate=0.1,
        recovery_rate=0.2,
        operator_intervention_rate=0.0,
    )
    faster_candidate = BenchmarkSummaryMetrics(
        run_count=3,
        success_rate=0.8,
        median_task_time_seconds=4.0,
        step_count=12,
        action_count=12,
        retry_count=1,
        grounding_accuracy=0.95,
        ambiguity_rate=0.1,
        recovery_rate=0.1,
        operator_intervention_rate=0.0,
    )
    unsafe_candidate = BenchmarkSummaryMetrics(
        run_count=3,
        success_rate=0.9,
        median_task_time_seconds=4.0,
        step_count=12,
        action_count=12,
        retry_count=1,
        grounding_accuracy=0.90,
        ambiguity_rate=0.2,
        recovery_rate=0.1,
        operator_intervention_rate=0.0,
    )

    faster = compare_benchmark_to_baseline(baseline, faster_candidate)
    unsafe = compare_benchmark_to_baseline(baseline, unsafe_candidate)

    assert faster.improved_speed
    assert faster.safety_not_reduced
    assert faster.improvement_proven
    assert faster.status == "improved"
    assert unsafe.improved_reliability
    assert not unsafe.safety_not_reduced
    assert not unsafe.improvement_proven
    assert unsafe.status == "regressed"


def test_benchmark_acceptance_records_threshold_failures() -> None:
    runs = (
        BenchmarkRunMetrics(
            iteration=1,
            status="passed",
            task_time_seconds=2.0,
            step_count=2,
            action_count=3,
            retry_count=1,
            grounding_attempt_count=2,
            grounded_selection_count=1,
            grounding_accuracy=0.5,
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
        grounding_accuracy=0.5,
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
            grounding_attempt_count=1,
            grounded_selection_count=1,
            grounding_accuracy=1.0,
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
        grounding_accuracy=1.0,
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
