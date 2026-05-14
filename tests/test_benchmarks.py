from pathlib import Path

from desktop_agent.benchmarks import (
    BENCHMARK_METRICS,
    REPORT_FIELDS,
    TRACE_MONITORING_PHASES,
    all_benchmark_tasks,
    benchmark_suite_by_id,
    default_benchmark_suites,
    validate_benchmark_suites,
)


def test_default_benchmark_suites_cover_required_domains() -> None:
    suites = default_benchmark_suites()

    assert {suite.domain for suite in suites} == {
        "browser",
        "native_windows",
        "mixed",
    }
    assert benchmark_suite_by_id("browser-fixture-suite").domain == "browser"


def test_default_benchmark_tasks_reference_valid_task_and_fixture_files() -> None:
    errors = validate_benchmark_suites(Path("."))

    assert errors == ()
    for task in all_benchmark_tasks():
        assert task.task_path.exists()
        assert all(path.exists() for path in task.fixture_paths)
        assert task.allowed_windows


def test_benchmark_tasks_define_pipeline_search_monitoring_and_reports() -> None:
    for task in all_benchmark_tasks():
        assert task.pipeline_modes == ("dry_run", "run")
        assert {"uia", "ocr", "image", "unknown"} <= set(task.deep_search_sources)
        assert set(TRACE_MONITORING_PHASES) <= set(task.required_trace_phases)
        assert set(REPORT_FIELDS) <= set(task.required_report_fields)
        assert set(BENCHMARK_METRICS) <= set(task.required_metrics)
