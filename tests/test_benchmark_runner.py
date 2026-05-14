import json
from pathlib import Path

from desktop_agent.benchmark_runner import BenchmarkRunHarness


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
    assert len(report.runs) == 2
    assert report.summary.run_count == 2
    assert report.summary.success_rate == 1.0
    assert report.summary.step_count > 0
    assert report.summary.action_count > 0
    assert report.variance.step_count.minimum > 0
    assert report.variance.action_count.maximum > 0
    assert len(metrics_lines) == 2
    assert report_payload["iterations"] == 2
    assert report_payload["variance_report_path"] == str(report.variance_report_path)
    assert report_payload["summary"]["success_rate"] == 1.0
    assert report_payload["summary"]["median_task_time_seconds"] >= 0
    assert report_payload["summary"]["step_count"] > 0
    assert report_payload["summary"]["action_count"] > 0
    assert report_payload["summary"]["retry_count"] >= 0
    assert report_payload["summary"]["ambiguity_rate"] == 0
    assert report_payload["summary"]["recovery_rate"] >= 0
    assert report_payload["summary"]["operator_intervention_rate"] == 0
    assert report_payload["runs"][0]["status"] == "passed"
    assert report_payload["runs"][0]["step_count"] > 0
    assert report_payload["runs"][0]["action_count"] > 0
    assert Path(report_payload["runs"][0]["trace_dir"]).exists()
    assert variance_payload["task_time_seconds"]["minimum"] >= 0
    assert variance_payload["step_count"]["maximum"] > 0
    assert variance_payload["recovery_count"]["population_stdev"] >= 0


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
