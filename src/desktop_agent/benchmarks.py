"""Benchmark suite definitions for human-like execution evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from desktop_agent.config import RuntimeConfig
from desktop_agent.task_dsl import BasicTaskValidator, YamlTaskLoader

BenchmarkDomain = Literal["browser", "native_windows", "mixed"]
BenchmarkPipelineMode = Literal["dry_run", "run"]
DeepSearchSource = Literal["uia", "ocr", "image", "unknown"]

BENCHMARK_METRICS: tuple[str, ...] = (
    "success_rate",
    "median_task_time_seconds",
    "step_count",
    "action_count",
    "retry_count",
    "ambiguity_rate",
    "recovery_rate",
    "operator_intervention_rate",
)

TRACE_MONITORING_PHASES: tuple[str, ...] = (
    "load_config",
    "load_task",
    "validate_task",
    "prepare_trace",
    "safety",
    "observe_screen",
    "detect_candidates",
    "select_target",
    "execute_action",
    "verify_result",
)

REPORT_FIELDS: tuple[str, ...] = (
    "task_name",
    "status",
    "abort_reason",
    "steps",
    "events",
    "trace_dir",
)


@dataclass(frozen=True)
class BenchmarkTaskSpec:
    """One benchmark task and the observability contract it must produce."""

    id: str
    name: str
    task_path: Path
    fixture_paths: tuple[Path, ...]
    allowed_windows: tuple[str, ...]
    pipeline_modes: tuple[BenchmarkPipelineMode, ...]
    deep_search_sources: tuple[DeepSearchSource, ...]
    required_trace_phases: tuple[str, ...]
    required_report_fields: tuple[str, ...]
    required_metrics: tuple[str, ...]
    description: str


@dataclass(frozen=True)
class BenchmarkSuite:
    """A benchmark suite grouped by workflow domain."""

    id: str
    domain: BenchmarkDomain
    name: str
    description: str
    tasks: tuple[BenchmarkTaskSpec, ...]


DEFAULT_BENCHMARK_SUITES: tuple[BenchmarkSuite, ...] = (
    BenchmarkSuite(
        id="browser-fixture-suite",
        domain="browser",
        name="Browser Fixture Suite",
        description="Exercises browser form entry, scrolling, and verification.",
        tasks=(
            BenchmarkTaskSpec(
                id="browser-fixture-demo",
                name="Browser fixture completion",
                task_path=Path("examples/browser-task.yaml"),
                fixture_paths=(Path("examples/browser_fixture.html"),),
                allowed_windows=("DeskPilot Browser Fixture",),
                pipeline_modes=("dry_run", "run"),
                deep_search_sources=("uia", "ocr", "image", "unknown"),
                required_trace_phases=TRACE_MONITORING_PHASES,
                required_report_fields=REPORT_FIELDS,
                required_metrics=BENCHMARK_METRICS,
                description=(
                    "Completes the browser fixture and records candidate search,"
                    " scroll recovery, verification, and final report data."
                ),
            ),
            BenchmarkTaskSpec(
                id="adversarial-fixture-demo",
                name="Adversarial browser fixture completion",
                task_path=Path("examples/adversarial-task.yaml"),
                fixture_paths=(Path("examples/adversarial_fixture.html"),),
                allowed_windows=("DeskPilot Adversarial Fixture",),
                pipeline_modes=("dry_run", "run"),
                deep_search_sources=("uia", "ocr", "image", "unknown"),
                required_trace_phases=TRACE_MONITORING_PHASES,
                required_report_fields=REPORT_FIELDS,
                required_metrics=BENCHMARK_METRICS,
                description=(
                    "Exercises duplicated labels, a disabled delayed control,"
                    " and a moving target with traceable candidate selection."
                ),
            ),
        ),
    ),
    BenchmarkSuite(
        id="native-windows-fixture-suite",
        domain="native_windows",
        name="Native Windows Fixture Suite",
        description="Exercises native input, buttons, and simple UI state.",
        tasks=(
            BenchmarkTaskSpec(
                id="native-fixture-demo",
                name="Native fixture completion",
                task_path=Path("examples/native-task.yaml"),
                fixture_paths=(Path("examples/native_fixture.py"),),
                allowed_windows=("DeskPilot Native Fixture",),
                pipeline_modes=("dry_run", "run"),
                deep_search_sources=("uia", "ocr", "image", "unknown"),
                required_trace_phases=TRACE_MONITORING_PHASES,
                required_report_fields=REPORT_FIELDS,
                required_metrics=BENCHMARK_METRICS,
                description=(
                    "Completes the native fixture and records candidate search,"
                    " text entry, UI state verification, and final report data."
                ),
            ),
        ),
    ),
    BenchmarkSuite(
        id="mixed-fixture-suite",
        domain="mixed",
        name="Mixed Fixture Suite",
        description="Exercises browser-to-native workflow handoff.",
        tasks=(
            BenchmarkTaskSpec(
                id="mixed-fixture-demo",
                name="Mixed browser and native completion",
                task_path=Path("examples/mixed-task.yaml"),
                fixture_paths=(
                    Path("examples/browser_fixture.html"),
                    Path("examples/native_fixture.py"),
                ),
                allowed_windows=(
                    "DeskPilot Browser Fixture",
                    "DeskPilot Native Fixture",
                ),
                pipeline_modes=("dry_run", "run"),
                deep_search_sources=("uia", "ocr", "image", "unknown"),
                required_trace_phases=TRACE_MONITORING_PHASES,
                required_report_fields=REPORT_FIELDS,
                required_metrics=BENCHMARK_METRICS,
                description=(
                    "Completes a browser step sequence, switches windows, and"
                    " completes native UI work with traceable handoff evidence."
                ),
            ),
        ),
    ),
)


def default_benchmark_suites() -> tuple[BenchmarkSuite, ...]:
    """Return the built-in benchmark suites in stable execution order."""

    return DEFAULT_BENCHMARK_SUITES


def all_benchmark_tasks() -> tuple[BenchmarkTaskSpec, ...]:
    """Flatten built-in benchmark suites for future repeated-run harnesses."""

    return tuple(task for suite in DEFAULT_BENCHMARK_SUITES for task in suite.tasks)


def benchmark_suite_by_id(suite_id: str) -> BenchmarkSuite:
    """Look up a benchmark suite by stable ID."""

    for suite in DEFAULT_BENCHMARK_SUITES:
        if suite.id == suite_id:
            return suite
    raise KeyError(f"unknown benchmark suite: {suite_id}")


def validate_benchmark_suites(root: Path = Path(".")) -> tuple[str, ...]:
    """Validate that built-in suites reference loadable task and fixture files."""

    errors: list[str] = []
    loader = YamlTaskLoader()
    validator = BasicTaskValidator()
    config = RuntimeConfig(max_steps=200)

    for task_spec in all_benchmark_tasks():
        task_path = root / task_spec.task_path
        if not task_path.exists():
            errors.append(f"benchmark task file not found: {task_spec.task_path}")
            continue
        for fixture_path in task_spec.fixture_paths:
            if not (root / fixture_path).exists():
                errors.append(f"benchmark fixture not found: {fixture_path}")

        try:
            task = loader.load(task_path)
            validator.validate(task, config)
        except Exception as exc:
            errors.append(f"benchmark task invalid: {task_spec.task_path}: {exc}")
            continue

        missing_windows = set(task_spec.allowed_windows) - set(task.allowed_windows)
        if missing_windows:
            windows = ", ".join(sorted(missing_windows))
            errors.append(f"benchmark allowed windows missing from task: {windows}")

    return tuple(errors)
