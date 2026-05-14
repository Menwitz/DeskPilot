"""Command-line interface for safe local task planning."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from desktop_agent.actuation import DryRunActuator, create_platform_actuator
from desktop_agent.benchmark_runner import BenchmarkRunHarness
from desktop_agent.computer_vision import OpenCvTemplatePerceptionEngine
from desktop_agent.config import (
    ConfigError,
    ConfigOverrides,
    RuntimeConfig,
    StaticConfigLoader,
    YamlConfigLoader,
    resolve_runtime_config,
)
from desktop_agent.ocr import (
    OcrPerceptionEngine,
    OcrTextBlock,
    OcrUnavailableError,
    TesseractOcrProvider,
    ocr_blocks_to_candidates,
)
from desktop_agent.perception import (
    CandidateFusion,
    CompositePerceptionEngine,
    ConfidenceTargetSelector,
    DryRunPerceptionEngine,
    ElementCandidate,
    candidate_ranking_metadata,
)
from desktop_agent.planner import ExecutionEngine
from desktop_agent.platforms.windows.uia import (
    WindowsUiaAdapter,
    WindowsUiaUnavailableError,
    write_uia_tree_snapshot,
)
from desktop_agent.safety import (
    LocalSafetyPolicy,
    NoopEmergencyStopMonitor,
    create_platform_emergency_stop_monitor,
)
from desktop_agent.screen import (
    Bounds,
    MssScreenObserver,
    ScreenObservation,
    ScreenUnavailableError,
    StaticScreenObserver,
)
from desktop_agent.task_dsl import (
    BasicTaskValidator,
    StaticTaskLoader,
    TaskStep,
    TaskValidationError,
    YamlTaskLoader,
)
from desktop_agent.tracing import FileTraceSink, RunReport


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "run":
            return _run_task(args, dry_run=False)
        if args.command == "dry-run":
            return _run_task(args, dry_run=True)
        if args.command == "inspect-screen":
            return _inspect_screen(args)
        if args.command == "benchmark-run":
            return _run_benchmark(args)
        if args.command == "replay":
            return _replay(args)
        parser.print_help()
        return 2
    except (ConfigError, TaskValidationError, OSError, ValueError) as exc:
        print(f"error: {exc}")
        return 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="desktop-agent")
    subparsers = parser.add_subparsers(dest="command")

    run_parser = subparsers.add_parser("run", help="execute a YAML task")
    _add_task_options(run_parser)

    dry_run_parser = subparsers.add_parser(
        "dry-run",
        help="validate and plan a YAML task without desktop input",
    )
    _add_task_options(dry_run_parser)

    inspect_parser = subparsers.add_parser(
        "inspect-screen",
        help="capture screen inspection output",
    )
    inspect_parser.add_argument("--output", required=True, type=Path)
    inspect_parser.add_argument("--verbose", action="store_true")

    replay_parser = subparsers.add_parser("replay", help="summarize a trace directory")
    replay_parser.add_argument("trace_dir", type=Path)
    replay_parser.add_argument("--verbose", action="store_true")

    benchmark_parser = subparsers.add_parser(
        "benchmark-run",
        help="run one task repeatedly through the dry-run benchmark harness",
    )
    benchmark_parser.add_argument("task_yaml", type=Path)
    benchmark_parser.add_argument("--output", required=True, type=Path)
    benchmark_parser.add_argument("--iterations", required=True, type=int)
    benchmark_parser.add_argument("--config", type=Path)
    benchmark_parser.add_argument("--confidence-threshold", type=float)
    benchmark_parser.add_argument("--allowed-window", action="append", default=[])
    return parser


def _add_task_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("task_yaml", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--no-screenshots", action="store_true")
    parser.add_argument("--max-runtime-seconds", type=float)
    parser.add_argument("--confidence-threshold", type=float)
    parser.add_argument("--allowed-window", action="append", default=[])
    parser.add_argument("--confirm-step", action="append", default=[])


def _run_task(args: argparse.Namespace, *, dry_run: bool) -> int:
    task = YamlTaskLoader().load(args.task_yaml)
    file_config = YamlConfigLoader().load(args.config)
    config = resolve_runtime_config(
        file_config,
        task_overrides=task.config_overrides,
        cli_overrides=_cli_overrides_from_args(args),
    )
    trace_sink = FileTraceSink()
    engine = ExecutionEngine(
        config_loader=StaticConfigLoader(config),
        task_loader=StaticTaskLoader(task),
        task_validator=BasicTaskValidator(),
        trace_sink=trace_sink,
        safety_policy=LocalSafetyPolicy(),
        screen_observer=StaticScreenObserver(),
        perception_engine=_perception_engine_for_mode(dry_run),
        target_selector=ConfidenceTargetSelector(),
        actuator=DryRunActuator() if dry_run else create_platform_actuator(),
        emergency_stop_monitor=create_platform_emergency_stop_monitor()
        if not dry_run
        else NoopEmergencyStopMonitor(),
    )
    report = engine.run(args.task_yaml, args.config)
    _print_report(report, verbose=args.verbose)
    return 0 if report.status == "passed" else 1


def _perception_engine_for_mode(dry_run: bool) -> CompositePerceptionEngine:
    if dry_run:
        return CompositePerceptionEngine((DryRunPerceptionEngine(),))
    return CompositePerceptionEngine(
        (
            OcrPerceptionEngine(),
            OpenCvTemplatePerceptionEngine(),
        ),
    )


def _cli_overrides_from_args(args: argparse.Namespace) -> ConfigOverrides:
    return ConfigOverrides(
        save_screenshots=False if args.no_screenshots else None,
        max_runtime_seconds=args.max_runtime_seconds,
        confidence_threshold=args.confidence_threshold,
        allowed_windows=tuple(args.allowed_window) if args.allowed_window else None,
        confirmed_steps=tuple(args.confirm_step) if args.confirm_step else None,
    )


def _inspect_screen(args: argparse.Namespace) -> int:
    args.output.mkdir(parents=True, exist_ok=True)
    output_path = args.output / "inspect-screen.json"
    config = RuntimeConfig(trace_root=args.output, save_screenshots=True)
    try:
        observation = MssScreenObserver().observe(config)
    except ScreenUnavailableError as exc:
        payload: dict[str, object] = {"status": "failed", "reason": str(exc)}
        output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"error: {payload['reason']}")
        print(f"inspection report: {output_path}")
        return 1

    payload = {
        "status": "passed",
        "screenshot_path": str(observation.screenshot_path)
        if observation.screenshot_path
        else None,
        "size": list(observation.size),
        "warnings": list(observation.warnings),
        "metadata": observation.metadata,
    }
    payload.update(_collect_screen_inspection(args.output, observation, config))
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print("status: passed")
    print(f"inspection report: {output_path}")
    return 0


def _collect_screen_inspection(
    output_dir: Path,
    observation: ScreenObservation,
    config: RuntimeConfig,
) -> dict[str, object]:
    # A targetless inspection step asks OCR/UIA to report all visible candidates
    # above the configured threshold instead of matching one task target.
    inspect_step = TaskStep(id="inspect-screen", action="assert_visible")
    ocr_blocks, ocr_status = _collect_ocr_blocks(observation)
    ocr_candidates = ocr_blocks_to_candidates(inspect_step, ocr_blocks, config)
    uia_tree, uia_candidates, uia_status = _collect_uia(output_dir)
    fused_candidates = CandidateFusion().fuse(
        inspect_step,
        uia_candidates + ocr_candidates,
        config,
    )
    return {
        "ocr": {
            "status": ocr_status,
            "blocks": [_ocr_block_to_dict(block) for block in ocr_blocks],
            "candidates": [
                _candidate_to_dict(candidate) for candidate in ocr_candidates
            ],
        },
        "uia": {
            "status": uia_status,
            "tree": uia_tree,
            "candidates": [
                _candidate_to_dict(candidate) for candidate in uia_candidates
            ],
        },
        "candidates": [_candidate_to_dict(candidate) for candidate in fused_candidates],
        "candidate_rankings": candidate_ranking_metadata(
            inspect_step,
            fused_candidates,
            config,
        )["candidate_rankings"],
    }


def _run_benchmark(args: argparse.Namespace) -> int:
    report = BenchmarkRunHarness().run_task(
        args.task_yaml,
        iterations=args.iterations,
        output_dir=args.output,
        config_path=args.config,
        cli_overrides=ConfigOverrides(
            confidence_threshold=args.confidence_threshold,
            allowed_windows=tuple(args.allowed_window)
            if args.allowed_window
            else None,
        ),
    )
    print(f"benchmark: {args.task_yaml}")
    print(f"iterations: {len(report.runs)}")
    print(f"metrics: {report.metrics_path}")
    print(f"variance: {report.variance_report_path}")
    print(f"pointer timing: {report.pointer_timing_comparison_path}")
    print(f"acceptance: {report.acceptance.status}")
    for failure in report.acceptance.failures:
        print(f"acceptance failure: {failure}")
    print(f"report: {report.report_path}")
    return (
        0
        if all(run.status == "passed" for run in report.runs)
        and report.acceptance.passed
        else 1
    )


def _collect_ocr_blocks(
    observation: ScreenObservation,
) -> tuple[tuple[OcrTextBlock, ...], str]:
    if observation.screenshot_path is None:
        return (), "skipped: no screenshot"
    try:
        blocks = TesseractOcrProvider().extract_text(observation.screenshot_path)
        return blocks, "passed"
    except OcrUnavailableError as exc:
        return (), f"unavailable: {exc}"


def _collect_uia(
    output_dir: Path,
) -> tuple[dict[str, object], tuple[ElementCandidate, ...], str]:
    adapter = WindowsUiaAdapter()
    try:
        tree = adapter.tree_snapshot()
        candidates = adapter.candidates()
    except WindowsUiaUnavailableError as exc:
        return {}, (), f"unavailable: {exc}"
    write_uia_tree_snapshot(output_dir / "uia-tree.json", tree)
    return tree, candidates, "passed"


def _replay(args: argparse.Namespace) -> int:
    report_path = args.trace_dir / "final-report.json"
    if not report_path.exists():
        print(f"error: final report not found: {report_path}")
        return 1

    report = json.loads(report_path.read_text(encoding="utf-8"))
    if not isinstance(report, dict):
        print("error: final report must contain a JSON object")
        return 1

    print(f"trace: {args.trace_dir}")
    if report.get("task_name"):
        print(f"task: {report['task_name']}")
    print(f"status: {report.get('status', 'unknown')}")
    if report.get("abort_reason"):
        print(f"reason: {report['abort_reason']}")
    if args.verbose:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def _print_report(report: RunReport, *, verbose: bool) -> None:
    print(f"task: {report.task_name}")
    print(f"status: {report.status}")
    if report.abort_reason:
        print(f"reason: {report.abort_reason}")
    if report.trace_dir:
        print(f"trace: {report.trace_dir}")
    for step in report.steps:
        print(f"step {step.step_id}: {step.status} ({step.message})")
    if verbose:
        for event in report.events:
            print(f"event {event.phase}: {event.message}")


def _ocr_block_to_dict(block: OcrTextBlock) -> dict[str, object]:
    return {
        "text": block.text,
        "bounds": _bounds_to_dict(block.bounds),
        "confidence": block.confidence,
    }


def _candidate_to_dict(candidate: ElementCandidate) -> dict[str, object]:
    return {
        "id": candidate.id,
        "source": candidate.source,
        "label": candidate.label,
        "bounds": _bounds_to_dict(candidate.bounds),
        "confidence": candidate.confidence,
        "visible": candidate.visible,
        "enabled": candidate.enabled,
        "metadata": candidate.metadata,
    }


def _bounds_to_dict(bounds: Bounds) -> dict[str, int]:
    return {
        "x": bounds.x,
        "y": bounds.y,
        "width": bounds.width,
        "height": bounds.height,
    }
