"""Command-line interface for safe local task planning."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from desktop_agent.actuation import DryRunActuator, UnavailableActuator
from desktop_agent.config import ConfigError, RuntimeConfig, YamlConfigLoader
from desktop_agent.perception import ConfidenceTargetSelector, EmptyPerceptionEngine
from desktop_agent.planner import ExecutionEngine
from desktop_agent.safety import LocalSafetyPolicy
from desktop_agent.screen import StaticScreenObserver
from desktop_agent.task_dsl import (
    BasicTaskValidator,
    TaskValidationError,
    YamlTaskLoader,
)
from desktop_agent.tracing import MemoryTraceSink, RunReport


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
    return parser


def _add_task_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("task_yaml", type=Path)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--no-screenshots", action="store_true")
    parser.add_argument("--max-runtime-seconds", type=float)
    parser.add_argument("--confidence-threshold", type=float)
    parser.add_argument("--allowed-window", action="append", default=[])


def _run_task(args: argparse.Namespace, *, dry_run: bool) -> int:
    config = _load_config_with_cli_overrides(args)
    trace_sink = MemoryTraceSink()
    engine = ExecutionEngine(
        config_loader=_LoadedConfig(config),
        task_loader=YamlTaskLoader(),
        task_validator=BasicTaskValidator(),
        trace_sink=trace_sink,
        safety_policy=LocalSafetyPolicy(),
        screen_observer=StaticScreenObserver(),
        perception_engine=EmptyPerceptionEngine(),
        target_selector=ConfidenceTargetSelector(),
        actuator=DryRunActuator() if dry_run else UnavailableActuator(),
    )
    report = engine.run(args.task_yaml, args.config)
    _print_report(report, verbose=args.verbose)
    return 0 if report.status == "passed" else 1


def _load_config_with_cli_overrides(args: argparse.Namespace) -> RuntimeConfig:
    config = YamlConfigLoader().load(args.config)
    allowed_windows = tuple(args.allowed_window) or config.allowed_windows
    return replace(
        config,
        save_screenshots=False if args.no_screenshots else config.save_screenshots,
        max_runtime_seconds=args.max_runtime_seconds or config.max_runtime_seconds,
        confidence_threshold=args.confidence_threshold or config.confidence_threshold,
        allowed_windows=allowed_windows,
    )


def _inspect_screen(args: argparse.Namespace) -> int:
    args.output.mkdir(parents=True, exist_ok=True)
    output_path = args.output / "inspect-screen.json"
    payload = {
        "status": "failed",
        "reason": "real screen inspection is not implemented yet",
    }
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"error: {payload['reason']}")
    print(f"inspection report: {output_path}")
    return 1


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
    for step in report.steps:
        print(f"step {step.step_id}: {step.status} ({step.message})")
    if verbose:
        for event in report.events:
            print(f"event {event.phase}: {event.message}")


class _LoadedConfig:
    def __init__(self, config: RuntimeConfig) -> None:
        self._config = config

    def load(self, config_path: Path | None) -> RuntimeConfig:
        _ = config_path
        return self._config
