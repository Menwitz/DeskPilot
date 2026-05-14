from pathlib import Path

from desktop_agent.benchmarks import (
    BENCHMARK_METRICS,
    REPORT_FIELDS,
    TRACE_MONITORING_PHASES,
    all_benchmark_tasks,
    benchmark_suite_by_id,
    benchmark_task_by_path,
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


def test_benchmark_tasks_define_acceptance_thresholds() -> None:
    for task in all_benchmark_tasks():
        thresholds = task.acceptance_thresholds
        assert thresholds.min_success_rate == 1.0
        assert thresholds.max_median_task_time_seconds > 0
        assert thresholds.max_task_time_seconds_per_run >= (
            thresholds.max_median_task_time_seconds
        )
        assert thresholds.max_step_count_per_run > 0
        assert thresholds.max_action_count_per_run > 0
        assert thresholds.max_retry_count_per_run >= 0
        assert 0 <= thresholds.max_ambiguity_rate <= 1
        assert 0 <= thresholds.max_recovery_rate <= 1
        assert 0 <= thresholds.max_operator_intervention_rate <= 1


def test_benchmark_task_lookup_supports_relative_and_absolute_paths() -> None:
    relative_task = benchmark_task_by_path(Path("examples/browser-task.yaml"))
    absolute_task = benchmark_task_by_path(Path.cwd() / "examples/browser-task.yaml")

    assert relative_task is not None
    assert absolute_task is not None
    assert relative_task.id == "browser-fixture-demo"
    assert absolute_task.id == "browser-fixture-demo"
