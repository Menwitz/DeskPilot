"""Command-line interface for safe local task planning."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

import yaml

from desktop_agent.actuation import (
    DryRunActuator,
    UnavailableActuator,
    actuation_profile_from_runtime_config,
    create_platform_actuator,
)
from desktop_agent.approval_manifest import (
    ApprovalManifestError,
    apply_approval_manifest,
    require_approval_manifest_if_needed,
)
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
from desktop_agent.content_variables import load_content_variables
from desktop_agent.mouse_demo import (
    MouseDemoError,
    run_browser_fixture,
    run_input_demo,
    run_linkedin_demo,
    run_mixed_fixture,
    run_native_fixture,
    run_recovery_fixture,
    run_windows_smoke_checklist,
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
    ui_state_snapshot_metadata,
)
from desktop_agent.planner import ExecutionEngine
from desktop_agent.platforms.windows.uia import (
    WindowsUiaAdapter,
    WindowsUiaPerceptionEngine,
    WindowsUiaUnavailableError,
    write_uia_tree_snapshot,
)
from desktop_agent.preview import build_dry_run_preview, render_dry_run_preview
from desktop_agent.safety import (
    LocalSafetyPolicy,
    NoopEmergencyStopMonitor,
    create_platform_emergency_stop_monitor,
)
from desktop_agent.screen import (
    Bounds,
    MssScreenObserver,
    ScreenObservation,
    ScreenObserver,
    ScreenUnavailableError,
    StaticScreenObserver,
)
from desktop_agent.site_playbooks import (
    SitePlaybook,
    SitePlaybookValidationError,
    SiteTaskCompiler,
    load_site_playbook,
    load_site_playbooks,
    resolve_site_flow,
)
from desktop_agent.task_dsl import (
    BasicTaskValidator,
    StaticTaskLoader,
    TaskDefinition,
    TaskStep,
    TaskValidationError,
    VerificationDefinition,
    YamlTaskLoader,
    step_category,
)
from desktop_agent.tracing import FileTraceSink, RunReport, TraceEvent


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "run":
            return _run_task(args, dry_run=False)
        if args.command == "dry-run":
            return _run_task(args, dry_run=True)
        if args.command == "list-sites":
            return _list_sites(args)
        if args.command == "list-flows":
            return _list_flows(args)
        if args.command == "compile-site":
            return _compile_site(args)
        if args.command == "run-site":
            return _run_site_task(args, dry_run=False)
        if args.command == "dry-run-site":
            return _run_site_task(args, dry_run=True)
        if args.command == "inspect-screen":
            return _inspect_screen(args)
        if args.command == "calibrate-target":
            return _calibrate_target(args)
        if args.command == "benchmark-run":
            return _run_benchmark(args)
        if args.command in {"demo-input", "demo-mouse"}:
            return _demo_input(args)
        if args.command == "demo-linkedin":
            return _demo_linkedin(args)
        if args.command == "windows-smoke-checklist":
            return _windows_smoke_checklist(args)
        if args.command == "replay":
            return _replay(args)
        if args.command == "proof":
            return _proof(args)
        parser.print_help()
        return 2
    except (
        ConfigError,
        ApprovalManifestError,
        SitePlaybookValidationError,
        TaskValidationError,
        MouseDemoError,
        OSError,
        ValueError,
    ) as exc:
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

    list_sites_parser = subparsers.add_parser(
        "list-sites",
        help="list available website playbook sites",
    )
    _add_site_catalog_options(list_sites_parser)

    list_flows_parser = subparsers.add_parser(
        "list-flows",
        help="list flows for one website playbook site",
    )
    list_flows_parser.add_argument("site")
    _add_site_catalog_options(list_flows_parser)

    compile_site_parser = subparsers.add_parser(
        "compile-site",
        help="compile one website playbook flow into a task YAML",
    )
    compile_site_parser.add_argument("site")
    compile_site_parser.add_argument("flow")
    compile_site_parser.add_argument("--output", required=True, type=Path)
    compile_site_parser.add_argument("--variables", type=Path)
    _add_site_catalog_options(compile_site_parser)

    run_site_parser = subparsers.add_parser(
        "run-site",
        help="execute a website playbook flow",
    )
    _add_site_run_options(run_site_parser)

    dry_run_site_parser = subparsers.add_parser(
        "dry-run-site",
        help="validate and plan a website playbook flow without desktop input",
    )
    _add_site_run_options(dry_run_site_parser)

    inspect_parser = subparsers.add_parser(
        "inspect-screen",
        help="capture screen inspection output",
    )
    inspect_parser.add_argument("--output", required=True, type=Path)
    inspect_parser.add_argument("--verbose", action="store_true")

    calibrate_parser = subparsers.add_parser(
        "calibrate-target",
        help="explain why a task target is selected or rejected",
    )
    calibrate_parser.add_argument("task_yaml", type=Path)
    calibrate_parser.add_argument("--step-id")
    calibrate_parser.add_argument("--output", required=True, type=Path)
    calibrate_parser.add_argument("--config", type=Path)
    calibrate_parser.add_argument("--confidence-threshold", type=float)
    calibrate_parser.add_argument("--allowed-window", action="append", default=[])

    replay_parser = subparsers.add_parser("replay", help="summarize a trace directory")
    replay_parser.add_argument("trace_dir", type=Path)
    replay_parser.add_argument("--verbose", action="store_true")

    proof_parser = subparsers.add_parser("proof", help="proof artifact tools")
    proof_subparsers = proof_parser.add_subparsers(dest="proof_command")
    proof_replay_parser = proof_subparsers.add_parser(
        "replay",
        help="summarize a proof manifest without rerunning input",
    )
    proof_replay_parser.add_argument("trace_dir", type=Path)
    proof_replay_parser.add_argument("--verbose", action="store_true")
    proof_replay_parser.add_argument(
        "--open-artifacts",
        action="store_true",
        help="open existing proof artifact paths with the OS file manager",
    )
    proof_browser_parser = proof_subparsers.add_parser(
        "browser-fixture",
        help="run a real-input local browser form/navigation proof",
    )
    _add_browser_fixture_options(proof_browser_parser)
    proof_native_parser = proof_subparsers.add_parser(
        "native-fixture",
        help="run a real-input native Windows app proof",
    )
    _add_native_fixture_options(proof_native_parser)
    proof_mixed_parser = proof_subparsers.add_parser(
        "mixed-fixture",
        help="run a real-input browser-to-native handoff proof",
    )
    _add_mixed_fixture_options(proof_mixed_parser)
    proof_recovery_parser = proof_subparsers.add_parser(
        "recovery-fixture",
        help="run a real-input delayed-control recovery proof",
    )
    _add_recovery_fixture_options(proof_recovery_parser)

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

    demo_input_parser = subparsers.add_parser(
        "demo-input",
        help="demonstrate global real Windows cursor and keyboard input",
    )
    _add_input_demo_options(demo_input_parser)

    demo_mouse_parser = subparsers.add_parser(
        "demo-mouse",
        help="alias for demo-input",
    )
    _add_input_demo_options(demo_mouse_parser)

    demo_linkedin_parser = subparsers.add_parser(
        "demo-linkedin",
        help="open Edge, navigate to LinkedIn, and perform a safe page action",
    )
    _add_linkedin_demo_options(demo_linkedin_parser)

    windows_smoke_parser = subparsers.add_parser(
        "windows-smoke-checklist",
        help="run a real-input Windows smoke checklist and write trace evidence",
    )
    _add_windows_smoke_checklist_options(windows_smoke_parser)
    return parser


def _add_task_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("task_yaml", type=Path)
    _add_runtime_options(parser)


def _add_runtime_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", type=Path)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--no-screenshots", action="store_true")
    parser.add_argument("--max-runtime-seconds", type=float)
    parser.add_argument("--confidence-threshold", type=float)
    parser.add_argument("--allowed-window", action="append", default=[])
    parser.add_argument("--confirm-step", action="append", default=[])
    parser.add_argument("--approval-manifest", type=Path)


def _add_input_demo_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--trace-root", default=Path("traces"), type=Path)
    parser.add_argument("--random-seed", default=20260515, type=int)
    parser.add_argument("--movement-smoothness", default=0.85, type=float)
    parser.add_argument(
        "--keyboard-text",
        default="DeskPilot controlled input",
        help="text typed into the fresh Notepad window",
    )
    parser.add_argument("--countdown-seconds", default=3.0, type=float)
    _add_video_options(parser)


def _add_linkedin_demo_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--trace-root", default=Path("traces"), type=Path)
    parser.add_argument("--random-seed", default=20260515, type=int)
    parser.add_argument("--movement-smoothness", default=0.85, type=float)
    parser.add_argument("--countdown-seconds", default=3.0, type=float)
    parser.add_argument("--url", default="https://www.linkedin.com/")
    parser.add_argument(
        "--find-text",
        default="LinkedIn",
        help="text highlighted through Edge's browser find box after navigation",
    )
    parser.add_argument("--page-load-seconds", default=5.0, type=float)
    _add_video_options(parser)


def _add_browser_fixture_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--trace-root", default=Path("traces"), type=Path)
    parser.add_argument("--random-seed", default=20260515, type=int)
    parser.add_argument("--movement-smoothness", default=0.85, type=float)
    parser.add_argument("--countdown-seconds", default=3.0, type=float)
    parser.add_argument(
        "--fixture-text",
        default="DeskPilot browser fixture",
        help="text typed into the generated browser fixture form",
    )
    parser.add_argument(
        "--result-text",
        default="DeskPilot browser fixture submitted",
        help="result text searched after submitting the generated form",
    )
    parser.add_argument("--page-load-seconds", default=1.5, type=float)
    _add_video_options(parser)


def _add_native_fixture_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--trace-root", default=Path("traces"), type=Path)
    parser.add_argument("--random-seed", default=20260515, type=int)
    parser.add_argument("--movement-smoothness", default=0.85, type=float)
    parser.add_argument("--countdown-seconds", default=3.0, type=float)
    parser.add_argument(
        "--initial-text",
        default="DeskPilot native fixture",
        help="first text typed into the native Notepad fixture",
    )
    parser.add_argument(
        "--replacement-text",
        default="DeskPilot native fixture updated",
        help="replacement text typed after selecting the Notepad buffer",
    )
    _add_video_options(parser)


def _add_mixed_fixture_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--trace-root", default=Path("traces"), type=Path)
    parser.add_argument("--random-seed", default=20260515, type=int)
    parser.add_argument("--movement-smoothness", default=0.85, type=float)
    parser.add_argument("--countdown-seconds", default=3.0, type=float)
    parser.add_argument(
        "--native-text",
        default="DeskPilot mixed native handoff",
        help="text typed into Notepad during the mixed proof",
    )
    parser.add_argument(
        "--browser-find-text",
        default="DeskPilot Browser Fixture",
        help="browser fixture text searched after Alt+Tab switches back to Edge",
    )
    parser.add_argument("--page-load-seconds", default=1.5, type=float)
    _add_video_options(parser)


def _add_recovery_fixture_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--trace-root", default=Path("traces"), type=Path)
    parser.add_argument("--random-seed", default=20260515, type=int)
    parser.add_argument("--movement-smoothness", default=0.85, type=float)
    parser.add_argument("--countdown-seconds", default=3.0, type=float)
    parser.add_argument("--page-load-seconds", default=0.5, type=float)
    parser.add_argument("--ready-delay-seconds", default=1.5, type=float)
    parser.add_argument("--recovery-wait-seconds", default=2.0, type=float)
    parser.add_argument(
        "--result-text",
        default="Recovery fixture clicked",
        help="result text searched after the delayed control retry succeeds",
    )
    _add_video_options(parser)


def _add_windows_smoke_checklist_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--trace-root", default=Path("traces"), type=Path)
    parser.add_argument("--random-seed", default=20260515, type=int)
    parser.add_argument("--movement-smoothness", default=0.85, type=float)
    parser.add_argument("--countdown-seconds", default=3.0, type=float)
    parser.add_argument(
        "--keyboard-text",
        default="DeskPilot Windows smoke check",
        help="text typed into the disposable Notepad window",
    )
    parser.add_argument("--edge-url", default="about:blank")
    _add_video_options(parser)


def _add_video_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--record-video",
        action="store_true",
        help="record the visible Windows desktop into the trace directory",
    )
    parser.add_argument("--video-fps", default=15, type=int)
    parser.add_argument("--ffmpeg-path", default="ffmpeg")


def _add_site_catalog_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--playbook-dir",
        default=Path("navigation_playbooks"),
        type=Path,
    )


def _add_site_run_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("site")
    parser.add_argument("flow")
    parser.add_argument("--variables", type=Path)
    _add_site_catalog_options(parser)
    _add_runtime_options(parser)


def _run_task(args: argparse.Namespace, *, dry_run: bool) -> int:
    task = YamlTaskLoader().load(args.task_yaml)
    return _run_loaded_task(args, task, args.task_yaml, dry_run=dry_run)


def _run_loaded_task(
    args: argparse.Namespace,
    task: TaskDefinition,
    task_path: Path,
    *,
    dry_run: bool,
    site_run: bool = False,
) -> int:
    file_config = YamlConfigLoader().load(args.config)
    config = resolve_runtime_config(
        file_config,
        task_overrides=task.config_overrides,
        cli_overrides=_cli_overrides_from_args(args),
    )
    manifest_path = getattr(args, "approval_manifest", None)
    if site_run and not dry_run:
        require_approval_manifest_if_needed(task, manifest_path)
    if manifest_path is not None:
        task, config = apply_approval_manifest(task, config, manifest_path)
    trace_sink = FileTraceSink()
    emergency_stop_monitor = (
        NoopEmergencyStopMonitor()
        if dry_run
        else create_platform_emergency_stop_monitor()
    )
    if dry_run:
        print(render_dry_run_preview(build_dry_run_preview(task, config)))
    actuator = (
        DryRunActuator()
        if dry_run
        else create_platform_actuator(
            actuation_profile_from_runtime_config(config),
            emergency_stop_monitor,
        )
    )
    if not dry_run and isinstance(actuator, UnavailableActuator):
        report = _write_platform_unavailable_report(task, config, trace_sink)
        _print_report(report, verbose=args.verbose)
        return 1
    if not dry_run:
        config = config if site_run else _config_with_operator_approvals(task, config)
    engine = ExecutionEngine(
        config_loader=StaticConfigLoader(config),
        task_loader=StaticTaskLoader(task),
        task_validator=BasicTaskValidator(),
        trace_sink=trace_sink,
        safety_policy=LocalSafetyPolicy(),
        screen_observer=_screen_observer_for_mode(dry_run, actuator),
        perception_engine=_perception_engine_for_mode(dry_run),
        target_selector=ConfidenceTargetSelector(),
        actuator=actuator,
        emergency_stop_monitor=emergency_stop_monitor,
    )
    report = engine.run(task_path, args.config)
    _print_report(report, verbose=args.verbose)
    return 0 if report.status == "passed" else 1


def _write_platform_unavailable_report(
    task: TaskDefinition,
    config: RuntimeConfig,
    trace_sink: FileTraceSink,
) -> RunReport:
    # Non-Windows real runs cannot safely execute desktop input, so stop before
    # perception/deep-search can produce misleading target-selection failures.
    reason = "desktop actuation is unavailable on this platform; use dry-run"
    trace_sink.prepare_run(task, config)
    trace_sink.record_event(
        TraceEvent(
            phase="platform_preflight",
            message=reason,
            metadata={
                "platform": sys.platform,
                "actuation_available": False,
                "deep_search_skipped": True,
            },
        )
    )
    return trace_sink.write_final_report("aborted", reason)


def _list_sites(args: argparse.Namespace) -> int:
    for playbook in load_site_playbooks(args.playbook_dir):
        print(playbook.site_id)
    return 0


def _list_flows(args: argparse.Namespace) -> int:
    playbook = _load_named_site(args.playbook_dir, args.site)
    for flow in playbook.flows:
        if flow.description:
            print(f"{flow.id}\t{flow.description}")
        else:
            print(flow.id)
    return 0


def _compile_site(args: argparse.Namespace) -> int:
    task = _compile_site_flow(
        args.playbook_dir,
        args.site,
        args.flow,
        variables_path=args.variables,
    )
    task = replace(
        task,
        metadata={
            **task.metadata,
            "site_compiled_task_path": str(args.output),
        },
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        yaml.safe_dump(_task_to_yaml_dict(task), sort_keys=False),
        encoding="utf-8",
    )
    print(f"compiled: {args.site} {args.flow}")
    print(f"task: {args.output}")
    return 0


def _run_site_task(args: argparse.Namespace, *, dry_run: bool) -> int:
    task = _compile_site_flow(
        args.playbook_dir,
        args.site,
        args.flow,
        variables_path=args.variables,
    )
    return _run_loaded_task(
        args,
        task,
        Path(f"site-{args.site}-{args.flow}.yaml"),
        dry_run=dry_run,
        site_run=True,
    )


def _compile_site_flow(
    playbook_dir: Path,
    site_id: str,
    flow_id: str,
    *,
    variables_path: Path | None = None,
) -> TaskDefinition:
    playbook = _load_named_site(playbook_dir, site_id)
    resolve_site_flow(playbook, flow_id)
    variables = load_content_variables(variables_path)
    return SiteTaskCompiler(variables).compile(playbook, flow_id)


def _load_named_site(playbook_dir: Path, site_id: str) -> SitePlaybook:
    site_path = playbook_dir / f"{site_id}.yaml"
    if site_path.exists():
        return load_site_playbook(site_path)
    available = {
        playbook.site_id: playbook for playbook in load_site_playbooks(playbook_dir)
    }
    if site_id not in available:
        raise SitePlaybookValidationError(f"unknown site: {site_id}")
    return available[site_id]


def _config_with_operator_approvals(
    task: TaskDefinition,
    config: RuntimeConfig,
) -> RuntimeConfig:
    confirmed_steps = list(config.confirmed_steps)
    for step in task.steps:
        if not _step_requires_operator_approval(step):
            continue
        if step.id in confirmed_steps:
            continue
        if _prompt_operator_approval(step):
            confirmed_steps.append(step.id)
        else:
            print(f"step {step.id} not approved; planner will stop before input")
    return replace(
        config,
        require_operator_approval=True,
        confirmed_steps=tuple(dict.fromkeys(confirmed_steps)),
    )


def _step_requires_operator_approval(step: TaskStep) -> bool:
    return step.requires_confirmation or step_category(step) == "submission"


def _prompt_operator_approval(step: TaskStep) -> bool:
    category = step_category(step)
    prompt = (
        f"approve step {step.id} ({step.action}, {category})? "
        f"Type {step.id} to approve: "
    )
    try:
        return input(prompt).strip() == step.id
    except EOFError:
        return False


def _perception_engine_for_mode(dry_run: bool) -> CompositePerceptionEngine:
    if dry_run:
        return CompositePerceptionEngine((DryRunPerceptionEngine(),))
    return CompositePerceptionEngine(
        (
            WindowsUiaPerceptionEngine(),
            OcrPerceptionEngine(),
            OpenCvTemplatePerceptionEngine(),
        ),
    )


def _screen_observer_for_mode(dry_run: bool, actuator: object) -> ScreenObserver:
    if dry_run or sys.platform != "win32" or isinstance(actuator, DryRunActuator):
        return StaticScreenObserver()
    # Real Windows runs need live screenshots so OCR/CV can find browser content.
    return MssScreenObserver()


def _cli_overrides_from_args(args: argparse.Namespace) -> ConfigOverrides:
    return ConfigOverrides(
        save_screenshots=False if args.no_screenshots else None,
        max_runtime_seconds=args.max_runtime_seconds,
        confidence_threshold=args.confidence_threshold,
        allowed_windows=tuple(args.allowed_window) if args.allowed_window else None,
        confirmed_steps=tuple(args.confirm_step) if args.confirm_step else None,
    )


def _task_to_yaml_dict(task: TaskDefinition) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": task.name,
        "allowed_windows": list(task.allowed_windows),
        "timeout_seconds": task.timeout_seconds,
        "steps": [_task_step_to_yaml_dict(step) for step in task.steps],
    }
    if task.config_overrides.confidence_threshold is not None:
        payload["config"] = {
            "confidence_threshold": task.config_overrides.confidence_threshold,
        }
    if task.metadata:
        payload["metadata"] = task.metadata
    return payload


def _task_step_to_yaml_dict(step: TaskStep) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": step.id,
        "action": step.action,
    }
    _put_optional(payload, "target", step.target)
    _put_optional(payload, "text", step.text)
    _put_optional(payload, "image", str(step.image) if step.image else None)
    if step.region is not None:
        payload["region"] = {
            "x": step.region.x,
            "y": step.region.y,
            "width": step.region.width,
            "height": step.region.height,
        }
    if step.verify is not None:
        payload["verify"] = _verification_to_yaml_dict(step.verify)
    if step.checkpoint is not None:
        payload["checkpoint"] = _verification_to_yaml_dict(step.checkpoint)
    _put_optional(payload, "timeout_seconds", step.timeout_seconds)
    _put_optional(payload, "retry", step.retry)
    if step.requires_confirmation:
        payload["requires_confirmation"] = True
    _put_optional(payload, "category", step.category)
    if step.metadata:
        payload["metadata"] = step.metadata
    return payload


def _verification_to_yaml_dict(
    verification: VerificationDefinition,
) -> dict[str, object]:
    payload: dict[str, object] = {"type": verification.type}
    _put_optional(payload, "text", verification.text)
    _put_optional(
        payload,
        "image",
        str(verification.image) if verification.image else None,
    )
    return payload


def _put_optional(
    payload: dict[str, object],
    key: str,
    value: object | None,
) -> None:
    if value is not None:
        payload[key] = value


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


def _calibrate_target(args: argparse.Namespace) -> int:
    task = YamlTaskLoader().load(args.task_yaml)
    step = _calibration_step(task.steps, args.step_id)
    file_config = YamlConfigLoader().load(args.config)
    config = resolve_runtime_config(
        file_config,
        task_overrides=task.config_overrides,
        cli_overrides=ConfigOverrides(
            confidence_threshold=args.confidence_threshold,
            allowed_windows=tuple(args.allowed_window) if args.allowed_window else None,
        ),
    )
    args.output.mkdir(parents=True, exist_ok=True)
    config = replace(config, trace_root=args.output)
    output_path = args.output / "target-calibration.json"
    try:
        observation = MssScreenObserver().observe(config)
    except ScreenUnavailableError as exc:
        payload: dict[str, object] = {
            "status": "failed",
            "reason": str(exc),
            "step_id": step.id,
        }
        output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"error: {payload['reason']}")
        print(f"calibration report: {output_path}")
        return 1

    candidates = _calibration_candidates(args.output, step, observation, config)
    selected = ConfidenceTargetSelector().select(step, candidates, config)
    selection_blocked = (
        "confidence_or_ambiguity_gate" if selected is None and candidates else None
    )
    snapshot = ui_state_snapshot_metadata(
        step,
        candidates,
        selected,
        config,
        selection_blocked=selection_blocked,
    )
    payload = {
        "status": "selected" if selected is not None else "rejected",
        "step_id": step.id,
        "action": step.action,
        "target": step.target,
        "selected_candidate_id": selected.id if selected is not None else None,
        "rejection_reason": None
        if selected is not None
        else _calibration_rejection_reason(snapshot, selection_blocked),
        "candidate_rankings": candidate_ranking_metadata(
            step,
            candidates,
            config,
        )["candidate_rankings"],
        "ui_state_snapshot": snapshot,
    }
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"status: {payload['status']}")
    if payload["rejection_reason"]:
        print(f"reason: {payload['rejection_reason']}")
    if payload["selected_candidate_id"]:
        print(f"selected: {payload['selected_candidate_id']}")
    print(f"calibration report: {output_path}")
    return 0 if selected is not None else 1


def _calibration_step(
    steps: tuple[TaskStep, ...],
    step_id: str | None,
) -> TaskStep:
    if not steps:
        raise ValueError("task must contain at least one step")
    if step_id is None:
        return steps[0]
    for step in steps:
        if step.id == step_id:
            return step
    raise ValueError(f"step not found: {step_id}")


def _calibration_candidates(
    output_dir: Path,
    step: TaskStep,
    observation: ScreenObservation,
    config: RuntimeConfig,
) -> tuple[ElementCandidate, ...]:
    ocr_blocks, _ = _collect_ocr_blocks(observation)
    ocr_candidates = ocr_blocks_to_candidates(step, ocr_blocks, config)
    _, uia_candidates, _ = _collect_uia(output_dir)
    image_candidates = OpenCvTemplatePerceptionEngine().detect(
        step,
        observation,
        config,
    )
    return CandidateFusion().fuse(
        step,
        uia_candidates + ocr_candidates + image_candidates,
        config,
    )


def _calibration_rejection_reason(
    snapshot: dict[str, object],
    selection_blocked: str | None,
) -> str:
    if selection_blocked is not None:
        return selection_blocked
    blocked = snapshot.get("blocked_candidates")
    if isinstance(blocked, list) and blocked:
        first = blocked[0]
        if isinstance(first, dict):
            reason = first.get("blocked_reason")
            if isinstance(reason, str):
                return reason
    return "no_candidates"


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
            allowed_windows=tuple(args.allowed_window) if args.allowed_window else None,
        ),
    )
    print(f"benchmark: {args.task_yaml}")
    print(f"iterations: {len(report.runs)}")
    print(f"metrics: {report.metrics_path}")
    print(f"baseline metrics: {report.baseline_metrics_path}")
    print(f"variance: {report.variance_report_path}")
    print(f"baseline comparison: {report.baseline_comparison_path}")
    print(f"baseline status: {report.baseline_comparison.status}")
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


def _demo_input(args: argparse.Namespace) -> int:
    report = run_input_demo(
        trace_root=args.trace_root,
        random_seed=args.random_seed,
        movement_smoothness=args.movement_smoothness,
        keyboard_text=args.keyboard_text,
        countdown_seconds=args.countdown_seconds,
        record_video=args.record_video,
        video_fps=args.video_fps,
        ffmpeg_path=args.ffmpeg_path,
    )
    print(f"status: {report.status}")
    if report.reason:
        print(f"reason: {report.reason}")
    print(f"trace: {report.trace_dir}")
    print(f"report: {report.report_path}")
    for step in report.steps:
        movement_points = step.metadata.get("movement_points")
        duration = step.metadata.get("movement_duration_seconds")
        if isinstance(movement_points, int) and isinstance(duration, int | float):
            print(
                f"step {step.step_id}: {step.action} "
                f"({movement_points} points, {duration:.3f}s)"
            )
        else:
            print(f"step {step.step_id}: {step.action}")
    return 0 if report.status == "passed" else 1


def _demo_linkedin(args: argparse.Namespace) -> int:
    report = run_linkedin_demo(
        trace_root=args.trace_root,
        random_seed=args.random_seed,
        movement_smoothness=args.movement_smoothness,
        countdown_seconds=args.countdown_seconds,
        url=args.url,
        find_text=args.find_text,
        page_load_seconds=args.page_load_seconds,
        record_video=args.record_video,
        video_fps=args.video_fps,
        ffmpeg_path=args.ffmpeg_path,
    )
    print(f"status: {report.status}")
    if report.reason:
        print(f"reason: {report.reason}")
    print(f"trace: {report.trace_dir}")
    print(f"report: {report.report_path}")
    for step in report.steps:
        movement_points = step.metadata.get("movement_points")
        duration = step.metadata.get("movement_duration_seconds")
        if isinstance(movement_points, int) and isinstance(duration, int | float):
            print(
                f"step {step.step_id}: {step.action} "
                f"({movement_points} points, {duration:.3f}s)"
            )
        else:
            print(f"step {step.step_id}: {step.action}")
    return 0 if report.status == "passed" else 1


def _windows_smoke_checklist(args: argparse.Namespace) -> int:
    report = run_windows_smoke_checklist(
        trace_root=args.trace_root,
        random_seed=args.random_seed,
        movement_smoothness=args.movement_smoothness,
        countdown_seconds=args.countdown_seconds,
        keyboard_text=args.keyboard_text,
        edge_url=args.edge_url,
        record_video=args.record_video,
        video_fps=args.video_fps,
        ffmpeg_path=args.ffmpeg_path,
    )
    print(f"status: {report.status}")
    if report.reason:
        print(f"reason: {report.reason}")
    print(f"trace: {report.trace_dir}")
    print(f"report: {report.report_path}")
    print(f"checklist: {report.trace_dir / 'windows-smoke-checklist.md'}")
    for step in report.steps:
        smoke_check = step.metadata.get("smoke_check")
        if isinstance(smoke_check, dict):
            print(f"check {smoke_check.get('check_id', step.step_id)}: {step.action}")
        else:
            print(f"step {step.step_id}: {step.action}")
    return 0 if report.status == "passed" else 1


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
        if (args.trace_dir / "proof-manifest.json").exists():
            print(f"hint: use desktop-agent proof replay {args.trace_dir}")
        return 1

    report = json.loads(report_path.read_text(encoding="utf-8"))
    if not isinstance(report, dict):
        print("error: final report must contain a JSON object")
        return 1

    print(f"trace: {args.trace_dir}")
    metadata = report.get("metadata")
    if isinstance(metadata, dict):
        site_id = metadata.get("site_id")
        flow_id = metadata.get("site_flow_id")
        if isinstance(site_id, str) and isinstance(flow_id, str):
            print(f"site: {site_id}")
            print(f"flow: {flow_id}")
    if report.get("task_name"):
        print(f"task: {report['task_name']}")
    print(f"status: {report.get('status', 'unknown')}")
    if report.get("abort_reason"):
        print(f"reason: {report['abort_reason']}")
    for line in _replay_timeline_lines(report):
        print(line)
    if args.verbose:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def _replay_timeline_lines(report: dict[str, object]) -> list[str]:
    steps = report.get("steps")
    events = report.get("events")
    if not isinstance(steps, list) or not isinstance(events, list) or not steps:
        return []

    event_rows = [event for event in events if isinstance(event, dict)]
    lines = ["timeline:"]
    for step in steps:
        if not isinstance(step, dict):
            continue
        step_id = step.get("step_id")
        if not isinstance(step_id, str):
            continue
        action = step.get("action") if isinstance(step.get("action"), str) else "?"
        status = step.get("status") if isinstance(step.get("status"), str) else "?"
        attempts = (
            step.get("attempts") if isinstance(step.get("attempts"), int) else "?"
        )
        lines.append(
            f"- step {step_id} ({action}) {status} after {attempts} attempt(s)"
        )
        step_events = [
            event for event in event_rows if _event_step_id(event) == step_id
        ]
        if not step_events:
            lines.append("  1. no step events recorded")
            continue
        for index, event in enumerate(step_events, start=1):
            phase = event.get("phase") if isinstance(event.get("phase"), str) else "?"
            message = (
                event.get("message") if isinstance(event.get("message"), str) else ""
            )
            lines.append(
                f"  {index}. {phase}: {message}{_replay_event_suffix(event)}"
            )
    return lines


def _event_step_id(event: dict[str, object]) -> str | None:
    metadata = event.get("metadata")
    if not isinstance(metadata, dict):
        return None
    for key in ("step_id", "recovery_for_step_id", "checkpoint_for_step_id"):
        value = metadata.get(key)
        if isinstance(value, str):
            return value
    return None


def _replay_event_suffix(event: dict[str, object]) -> str:
    metadata = event.get("metadata")
    if not isinstance(metadata, dict):
        return ""
    details: list[str] = []
    for key, label in (
        ("verification_outcome", "outcome"),
        ("candidate_id", "candidate"),
        ("recovery_reason", "recovery"),
        ("observation_role", "observation"),
        ("failure_category", "failure"),
    ):
        value = metadata.get(key)
        if isinstance(value, str):
            details.append(f"{label} {value}")
    if metadata.get("manual_handoff_required") is True:
        details.append("manual handoff")
    if metadata.get("target_appeared") is True:
        details.append("target appeared")
    if metadata.get("target_disappeared") is True:
        details.append("target disappeared")
    if metadata.get("scroll_moved") is True:
        details.append("scroll moved")
    if not details:
        return ""
    return " [" + "; ".join(details) + "]"


def _proof(args: argparse.Namespace) -> int:
    if args.proof_command == "replay":
        return _proof_replay(args)
    if args.proof_command == "browser-fixture":
        return _proof_browser_fixture(args)
    if args.proof_command == "native-fixture":
        return _proof_native_fixture(args)
    if args.proof_command == "mixed-fixture":
        return _proof_mixed_fixture(args)
    if args.proof_command == "recovery-fixture":
        return _proof_recovery_fixture(args)
    print("error: proof subcommand required")
    return 2


def _proof_browser_fixture(args: argparse.Namespace) -> int:
    report = run_browser_fixture(
        trace_root=args.trace_root,
        random_seed=args.random_seed,
        movement_smoothness=args.movement_smoothness,
        countdown_seconds=args.countdown_seconds,
        fixture_text=args.fixture_text,
        result_text=args.result_text,
        page_load_seconds=args.page_load_seconds,
        record_video=args.record_video,
        video_fps=args.video_fps,
        ffmpeg_path=args.ffmpeg_path,
    )
    print(f"status: {report.status}")
    if report.reason:
        print(f"reason: {report.reason}")
    print(f"trace: {report.trace_dir}")
    print(f"report: {report.report_path}")
    if report.proof_manifest_path:
        print(f"manifest: {report.proof_manifest_path}")
    for step in report.steps:
        movement_points = step.metadata.get("movement_points")
        duration = step.metadata.get("movement_duration_seconds")
        if isinstance(movement_points, int) and isinstance(duration, int | float):
            print(
                f"step {step.step_id}: {step.action} "
                f"({movement_points} points, {duration:.3f}s)"
            )
        else:
            print(f"step {step.step_id}: {step.action}")
    return 0 if report.status == "passed" else 1


def _proof_native_fixture(args: argparse.Namespace) -> int:
    report = run_native_fixture(
        trace_root=args.trace_root,
        random_seed=args.random_seed,
        movement_smoothness=args.movement_smoothness,
        countdown_seconds=args.countdown_seconds,
        initial_text=args.initial_text,
        replacement_text=args.replacement_text,
        record_video=args.record_video,
        video_fps=args.video_fps,
        ffmpeg_path=args.ffmpeg_path,
    )
    print(f"status: {report.status}")
    if report.reason:
        print(f"reason: {report.reason}")
    print(f"trace: {report.trace_dir}")
    print(f"report: {report.report_path}")
    if report.proof_manifest_path:
        print(f"manifest: {report.proof_manifest_path}")
    for step in report.steps:
        print(f"step {step.step_id}: {step.action}")
    return 0 if report.status == "passed" else 1


def _proof_mixed_fixture(args: argparse.Namespace) -> int:
    report = run_mixed_fixture(
        trace_root=args.trace_root,
        random_seed=args.random_seed,
        movement_smoothness=args.movement_smoothness,
        countdown_seconds=args.countdown_seconds,
        native_text=args.native_text,
        browser_find_text=args.browser_find_text,
        page_load_seconds=args.page_load_seconds,
        record_video=args.record_video,
        video_fps=args.video_fps,
        ffmpeg_path=args.ffmpeg_path,
    )
    print(f"status: {report.status}")
    if report.reason:
        print(f"reason: {report.reason}")
    print(f"trace: {report.trace_dir}")
    print(f"report: {report.report_path}")
    if report.proof_manifest_path:
        print(f"manifest: {report.proof_manifest_path}")
    for step in report.steps:
        print(f"step {step.step_id}: {step.action}")
    return 0 if report.status == "passed" else 1


def _proof_recovery_fixture(args: argparse.Namespace) -> int:
    report = run_recovery_fixture(
        trace_root=args.trace_root,
        random_seed=args.random_seed,
        movement_smoothness=args.movement_smoothness,
        countdown_seconds=args.countdown_seconds,
        page_load_seconds=args.page_load_seconds,
        ready_delay_seconds=args.ready_delay_seconds,
        recovery_wait_seconds=args.recovery_wait_seconds,
        result_text=args.result_text,
        record_video=args.record_video,
        video_fps=args.video_fps,
        ffmpeg_path=args.ffmpeg_path,
    )
    print(f"status: {report.status}")
    if report.reason:
        print(f"reason: {report.reason}")
    print(f"trace: {report.trace_dir}")
    print(f"report: {report.report_path}")
    if report.proof_manifest_path:
        print(f"manifest: {report.proof_manifest_path}")
    for step in report.steps:
        recovery = step.metadata.get("recovery")
        if isinstance(recovery, dict):
            print(
                f"recovery {step.step_id}: {recovery.get('reason')} "
                f"({recovery.get('action')})"
            )
        else:
            print(f"step {step.step_id}: {step.action}")
    return 0 if report.status == "passed" else 1


def _proof_replay(args: argparse.Namespace) -> int:
    manifest_path = args.trace_dir / "proof-manifest.json"
    if not manifest_path.exists():
        print(f"error: proof manifest not found: {manifest_path}")
        return 1

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        print("error: proof manifest must contain a JSON object")
        return 1

    print(f"trace: {args.trace_dir}")
    _print_manifest_value("proof", manifest, "proof_name")
    command_line = _manifest_command_line(manifest.get("command"))
    if command_line:
        print(f"command: {command_line}")
    print(f"status: {manifest.get('status', 'unknown')}")
    _print_manifest_value("reason", manifest, "reason")
    _print_manifest_value("started_at", manifest, "started_at")
    _print_manifest_value("completed_at", manifest, "completed_at")
    _print_manifest_value("desktop-agent", manifest, "executable_version")
    _print_manifest_value("python", manifest, "python_version")
    _print_manifest_value("platform", manifest, "platform")

    artifacts = _proof_artifact_paths(manifest)
    for label, path in artifacts:
        suffix = "" if path.exists() else " (missing)"
        print(f"artifact {label}: {path}{suffix}")

    if args.open_artifacts:
        opened = _open_existing_artifacts(artifacts)
        if opened:
            for path in opened:
                print(f"opened artifact: {path}")
        else:
            print("opened artifact: none")

    if args.verbose:
        print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


def _print_manifest_value(
    label: str,
    manifest: dict[object, object],
    key: str,
) -> None:
    value = manifest.get(key)
    if isinstance(value, str) and value:
        print(f"{label}: {value}")


def _manifest_command_line(command: object) -> str | None:
    if not isinstance(command, list):
        return None
    parts = [part for part in command if isinstance(part, str)]
    if len(parts) != len(command):
        return None
    return shlex.join(parts)


def _proof_artifact_paths(
    manifest: dict[object, object],
) -> tuple[tuple[str, Path], ...]:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        return ()

    paths: list[tuple[str, Path]] = []
    for label in (
        "trace_dir",
        "report_path",
        "action_log_path",
        "proof_manifest_path",
        "video_path",
        "video_log_path",
    ):
        value = artifacts.get(label)
        if isinstance(value, str) and value:
            paths.append((label, Path(value)))

    screenshots = artifacts.get("screenshots")
    if isinstance(screenshots, list):
        for index, screenshot in enumerate(screenshots, start=1):
            if isinstance(screenshot, str) and screenshot:
                paths.append((f"screenshot_{index}", Path(screenshot)))
    return tuple(paths)


def _open_existing_artifacts(artifacts: Sequence[tuple[str, Path]]) -> tuple[Path, ...]:
    opened: list[Path] = []
    for _, path in artifacts:
        if not path.exists():
            continue
        _open_path(path)
        opened.append(path)
    return tuple(opened)


def _open_path(path: Path) -> None:
    # Proof replay opens already-recorded artifacts only; it never reruns desktop
    # input or launches a task command.
    if sys.platform == "win32":
        startfile = getattr(os, "startfile", None)
        if startfile is None:
            raise OSError("os.startfile is unavailable")
        startfile(str(path))
        return
    command = (
        ("open", str(path))
        if sys.platform == "darwin"
        else ("xdg-open", str(path))
    )
    subprocess.run(
        command,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


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
