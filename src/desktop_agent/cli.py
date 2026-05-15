"""Command-line interface for safe local task planning."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

import yaml

from desktop_agent.actuation import (
    DryRunActuator,
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
from desktop_agent.tracing import FileTraceSink, RunReport


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
        if args.command == "replay":
            return _replay(args)
        parser.print_help()
        return 2
    except (
        ConfigError,
        ApprovalManifestError,
        SitePlaybookValidationError,
        TaskValidationError,
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
    if not dry_run:
        config = (
            config
            if site_run
            else _config_with_operator_approvals(task, config)
        )
    trace_sink = FileTraceSink()
    emergency_stop_monitor = (
        NoopEmergencyStopMonitor()
        if dry_run
        else create_platform_emergency_stop_monitor()
    )
    if dry_run:
        print(render_dry_run_preview(build_dry_run_preview(task, config)))
    engine = ExecutionEngine(
        config_loader=StaticConfigLoader(config),
        task_loader=StaticTaskLoader(task),
        task_validator=BasicTaskValidator(),
        trace_sink=trace_sink,
        safety_policy=LocalSafetyPolicy(),
        screen_observer=StaticScreenObserver(),
        perception_engine=_perception_engine_for_mode(dry_run),
        target_selector=ConfidenceTargetSelector(),
        actuator=DryRunActuator()
        if dry_run
        else create_platform_actuator(
            actuation_profile_from_runtime_config(config),
            emergency_stop_monitor,
        ),
        emergency_stop_monitor=emergency_stop_monitor,
    )
    report = engine.run(task_path, args.config)
    _print_report(report, verbose=args.verbose)
    return 0 if report.status == "passed" else 1


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
            allowed_windows=tuple(args.allowed_window)
            if args.allowed_window
            else None,
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
        "confidence_or_ambiguity_gate"
        if selected is None and candidates
        else None
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
            allowed_windows=tuple(args.allowed_window)
            if args.allowed_window
            else None,
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
