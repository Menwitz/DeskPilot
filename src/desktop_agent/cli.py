"""Command-line interface for safe local task planning."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from collections.abc import Mapping, Sequence
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
    execution_profile_for_activity,
    resolve_runtime_config,
)
from desktop_agent.content_variables import load_content_variables
from desktop_agent.failed_run_analyzer import (
    analyze_failed_run_trace,
    write_failed_run_analysis,
)
from desktop_agent.focus_recovery import (
    NoopFocusRecoveryController,
    create_platform_focus_recovery_controller,
)
from desktop_agent.goal_planning import (
    GoalPlan,
    GoalRoutingRequest,
    goal_plan_from_mapping,
    missing_input_prompts,
    rank_goal_plan_with_optional_model,
    route_goal_to_routine,
)
from desktop_agent.goal_reporting import write_goal_plan_trace
from desktop_agent.local_models import (
    LocalModelStatus,
    OllamaLocalModelProvider,
    write_local_model_status_report,
)
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
from desktop_agent.operator_services import LocalTraceService
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
from desktop_agent.proof_manifest import (
    PROOF_FINALIZATION_STATUS_NAME,
    run_proof_preflight,
    validate_proof_bundle,
    validate_proof_review,
    validate_proof_suite,
    verify_proof_suite_archive,
    verify_proof_suite_promotion,
    write_proof_archive_verification,
    write_proof_finalization_status,
    write_proof_preflight_report,
    write_proof_promotion_verification,
    write_proof_review_status,
    write_proof_suite_archive,
    write_proof_suite_promotion,
    write_proof_suite_report,
    write_proof_suite_review_template,
    write_proof_suite_runbook,
    write_proof_suite_status,
)
from desktop_agent.recorder import (
    RECORDER_DEFAULT_RISK_CLASS,
    RecorderController,
    RecorderError,
    RecorderReviewMetadata,
    generate_task_from_recorder_session,
)
from desktop_agent.redaction import RedactionPolicy
from desktop_agent.routine_pack_manifest import (
    RoutinePackManifest,
    RoutinePackManifestError,
    RoutinePackTrustWarning,
    load_routine_pack_manifests,
    routine_pack_trust_warnings,
)
from desktop_agent.routine_pack_ops import (
    RoutinePackConflict,
    RoutinePackOperationError,
    export_routine_pack,
    import_routine_pack,
)
from desktop_agent.routine_pack_runner import (
    run_routine_pack_tests,
    write_routine_pack_proof_bundle,
)
from desktop_agent.routines import (
    RoutineDefinition,
    RoutineDefinitionError,
    load_routine_catalog,
    render_routine_catalog_index,
    render_routine_documentation_template,
    require_validated_routine_for_execution,
    routine_failure_counters_from_trace_root,
    routine_promotion_gates,
    routine_quarantine_status,
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
    ScreenObserver,
    ScreenUnavailableError,
    StaticScreenObserver,
)
from desktop_agent.screen_captioning import (
    screen_caption_review_from_inspection,
    write_screen_caption_review_report,
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
    ExpectedStateTransition,
    RecoveryRule,
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
        if args.command == "list-routines":
            return _list_routines(args)
        if args.command == "show-routine":
            return _show_routine(args)
        if args.command == "compile-routine":
            return _compile_routine(args)
        if args.command == "export-routine":
            return _export_routine(args)
        if args.command == "generate-routine-docs":
            return _generate_routine_docs(args)
        if args.command == "run-routine":
            return _run_routine(args, dry_run=False)
        if args.command == "dry-run-routine":
            return _run_routine(args, dry_run=True)
        if args.command == "list-routine-packs":
            return _list_routine_packs(args)
        if args.command == "show-routine-pack":
            return _show_routine_pack(args)
        if args.command == "import-routine-pack":
            return _import_routine_pack(args)
        if args.command == "export-routine-pack":
            return _export_routine_pack(args)
        if args.command == "test-routine-pack":
            return _test_routine_pack(args)
        if args.command == "write-routine-pack-proof":
            return _write_routine_pack_proof(args)
        if args.command == "plan-goal":
            return _plan_goal(args)
        if args.command == "local-model":
            return _local_model(args)
        if args.command == "inspect-screen":
            return _inspect_screen(args)
        if args.command == "calibrate-target":
            return _calibrate_target(args)
        if args.command == "benchmark-run":
            return _run_benchmark(args)
        if args.command == "record":
            return _record(args)
        if args.command in {"demo-input", "demo-mouse"}:
            return _demo_input(args)
        if args.command == "demo-linkedin":
            return _demo_linkedin(args)
        if args.command == "windows-smoke-checklist":
            return _windows_smoke_checklist(args)
        if args.command == "replay":
            return _replay(args)
        if args.command == "trace-health":
            return _trace_health(args)
        if args.command == "analyze-failed-run":
            return _analyze_failed_run(args)
        if args.command == "proof":
            return _proof(args)
        parser.print_help()
        return 2
    except (
        ConfigError,
        ApprovalManifestError,
        SitePlaybookValidationError,
        RecorderError,
        RoutineDefinitionError,
        RoutinePackManifestError,
        RoutinePackOperationError,
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

    list_routines_parser = subparsers.add_parser(
        "list-routines",
        help="list routine catalog entries",
    )
    _add_routine_catalog_options(list_routines_parser)
    list_routines_parser.add_argument("--query")

    show_routine_parser = subparsers.add_parser(
        "show-routine",
        help="show one routine catalog entry",
    )
    show_routine_parser.add_argument("routine_id")
    _add_routine_catalog_options(show_routine_parser)

    compile_routine_parser = subparsers.add_parser(
        "compile-routine",
        help="compile a routine into task YAML",
    )
    compile_routine_parser.add_argument("routine_id")
    compile_routine_parser.add_argument("--output", required=True, type=Path)
    _add_routine_catalog_options(compile_routine_parser)
    _add_site_catalog_options(compile_routine_parser)

    export_routine_parser = subparsers.add_parser(
        "export-routine",
        help="export one routine definition as YAML",
    )
    export_routine_parser.add_argument("routine_id")
    export_routine_parser.add_argument("--output", required=True, type=Path)
    _add_routine_catalog_options(export_routine_parser)

    generate_routine_docs_parser = subparsers.add_parser(
        "generate-routine-docs",
        help="write routine catalog index and routine documentation template",
    )
    generate_routine_docs_parser.add_argument(
        "--index-output",
        default=Path("docs/routine-catalog-index.md"),
        type=Path,
    )
    generate_routine_docs_parser.add_argument(
        "--template-output",
        default=Path("docs/routine-documentation-template.md"),
        type=Path,
    )
    generate_routine_docs_parser.add_argument(
        "--failure-history-root",
        type=Path,
        help="optional trace root containing final-report.json files",
    )
    _add_routine_catalog_options(generate_routine_docs_parser)

    run_routine_parser = subparsers.add_parser(
        "run-routine",
        help="execute a routine catalog entry",
    )
    run_routine_parser.add_argument("routine_id")
    _add_routine_catalog_options(run_routine_parser)
    _add_site_catalog_options(run_routine_parser)
    _add_routine_failure_history_options(run_routine_parser)
    _add_runtime_options(run_routine_parser)

    dry_run_routine_parser = subparsers.add_parser(
        "dry-run-routine",
        help="validate and plan a routine without desktop input",
    )
    dry_run_routine_parser.add_argument("routine_id")
    _add_routine_catalog_options(dry_run_routine_parser)
    _add_site_catalog_options(dry_run_routine_parser)
    _add_routine_failure_history_options(dry_run_routine_parser)
    _add_runtime_options(dry_run_routine_parser)

    list_routine_packs_parser = subparsers.add_parser(
        "list-routine-packs",
        help="list installed routine pack manifests",
    )
    _add_routine_catalog_options(list_routine_packs_parser)

    show_routine_pack_parser = subparsers.add_parser(
        "show-routine-pack",
        help="show one installed routine pack manifest",
    )
    show_routine_pack_parser.add_argument("pack_id")
    _add_routine_catalog_options(show_routine_pack_parser)

    import_routine_pack_parser = subparsers.add_parser(
        "import-routine-pack",
        help="validate and install a local routine pack directory or zip",
    )
    import_routine_pack_parser.add_argument("source", type=Path)
    import_routine_pack_parser.add_argument("--replace", action="store_true")
    _add_routine_catalog_options(import_routine_pack_parser)

    export_routine_pack_parser = subparsers.add_parser(
        "export-routine-pack",
        help="export an installed routine pack as a directory or zip",
    )
    export_routine_pack_parser.add_argument("pack_id")
    export_routine_pack_parser.add_argument("--output", required=True, type=Path)
    export_routine_pack_parser.add_argument("--replace", action="store_true")
    _add_routine_catalog_options(export_routine_pack_parser)

    test_routine_pack_parser = subparsers.add_parser(
        "test-routine-pack",
        help="validate one routine pack without desktop input",
    )
    test_routine_pack_parser.add_argument("pack_id")
    test_routine_pack_parser.add_argument("--output", type=Path)
    _add_routine_catalog_options(test_routine_pack_parser)

    proof_routine_pack_parser = subparsers.add_parser(
        "write-routine-pack-proof",
        help="write a local proof bundle for one routine pack",
    )
    proof_routine_pack_parser.add_argument("pack_id")
    proof_routine_pack_parser.add_argument("--output", required=True, type=Path)
    _add_routine_catalog_options(proof_routine_pack_parser)

    plan_goal_parser = subparsers.add_parser(
        "plan-goal",
        help="dry-run goal-to-routine planning without desktop input",
    )
    plan_goal_parser.add_argument("user_goal")
    plan_goal_parser.add_argument("--intent")
    plan_goal_parser.add_argument("--required-app")
    plan_goal_parser.add_argument("--required-site")
    plan_goal_parser.add_argument("--tag", action="append", default=[])
    plan_goal_parser.add_argument("--input", action="append", default=[])
    plan_goal_parser.add_argument(
        "--max-safety-class",
        default="sensitive",
        choices=("low", "medium", "high", "sensitive"),
    )
    plan_goal_parser.add_argument("--session-state", action="append", default=[])
    plan_goal_parser.add_argument("--config", type=Path)
    plan_goal_parser.add_argument("--trace-root", type=Path)
    _add_routine_catalog_options(plan_goal_parser)

    local_model_parser = subparsers.add_parser(
        "local-model",
        help="inspect optional local Ollama health and model inventory",
    )
    local_model_subparsers = local_model_parser.add_subparsers(
        dest="local_model_command",
    )
    local_model_status_parser = local_model_subparsers.add_parser(
        "status",
        help="check configured local model status",
    )
    _add_local_model_options(local_model_status_parser)
    local_model_status_parser.add_argument(
        "--probe-disabled",
        action="store_true",
        help="probe Ollama even when local_model.enabled is false",
    )
    local_model_list_parser = local_model_subparsers.add_parser(
        "list",
        help="list models advertised by the configured local Ollama endpoint",
    )
    _add_local_model_options(local_model_list_parser)

    inspect_parser = subparsers.add_parser(
        "inspect-screen",
        help="capture screen inspection output",
    )
    inspect_parser.add_argument("--output", required=True, type=Path)
    inspect_parser.add_argument("--verbose", action="store_true")
    inspect_parser.add_argument(
        "--caption-output",
        type=Path,
        help="write a review-only local model screenshot caption prompt report",
    )

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
    replay_parser.add_argument(
        "--write-summary",
        action="store_true",
        help="write replay-summary.md with timeline, screenshots, and state deltas",
    )

    trace_health_parser = subparsers.add_parser(
        "trace-health",
        help="summarize local trace counts by report kind and status",
    )
    trace_health_parser.add_argument(
        "--trace-root",
        default=Path("traces"),
        type=Path,
    )
    trace_health_parser.add_argument("--limit", default=50, type=int)
    trace_health_parser.add_argument("--json", action="store_true")
    trace_health_parser.add_argument("--output", type=Path)
    trace_health_parser.add_argument("--markdown-output", type=Path)
    trace_health_parser.add_argument(
        "--fail-on-attention",
        action="store_true",
        help="return a nonzero exit code when trace health needs review",
    )

    analyze_failed_run_parser = subparsers.add_parser(
        "analyze-failed-run",
        help="write review-only YAML improvement proposals for a failed trace",
    )
    analyze_failed_run_parser.add_argument("trace_dir", type=Path)

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
    proof_validate_review_parser = proof_subparsers.add_parser(
        "validate-review",
        help="validate a completed proof-suite human review template",
    )
    proof_validate_review_parser.add_argument("review_path", type=Path)
    proof_validate_review_parser.add_argument(
        "--write-status-json",
        action="store_true",
        help="write proof-suite-review-status.json after validation",
    )
    proof_validate_review_parser.add_argument(
        "--status-json-path",
        type=Path,
        help="write review status JSON to an explicit path",
    )
    proof_preflight_parser = proof_subparsers.add_parser(
        "preflight",
        help="check Windows proof prerequisites without sending desktop input",
    )
    proof_preflight_parser.add_argument(
        "--trace-root",
        default=Path("traces"),
        type=Path,
    )
    proof_preflight_parser.add_argument("--ffmpeg-path", default="ffmpeg")
    proof_preflight_parser.add_argument(
        "--allow-non-windows",
        action="store_true",
        help="do not fail preflight when running outside Windows",
    )
    proof_preflight_parser.add_argument(
        "--video-policy",
        choices=("full", "disabled"),
        default="full",
        help="disable proof video preflight when using external recording",
    )
    proof_preflight_parser.add_argument(
        "--write-report",
        action="store_true",
        help="write proof-preflight.json after preflight",
    )
    proof_preflight_parser.add_argument(
        "--report-path",
        type=Path,
        help="write the preflight report to an explicit JSON path",
    )
    proof_validate_parser = proof_subparsers.add_parser(
        "validate",
        help="validate a proof bundle without rerunning input",
    )
    proof_validate_parser.add_argument("trace_dir", type=Path)
    proof_validate_parser.add_argument(
        "--allow-missing-video",
        action="store_true",
        help="validate non-video proof artifacts when video capture was disabled",
    )
    proof_validate_suite_parser = proof_subparsers.add_parser(
        "validate-suite",
        help="validate browser, native, mixed, and recovery proof bundles",
    )
    proof_validate_suite_parser.add_argument("trace_root", type=Path)
    proof_validate_suite_parser.add_argument(
        "--allow-missing-video",
        action="store_true",
        help="validate non-video proof artifacts when video capture was disabled",
    )
    proof_validate_suite_parser.add_argument(
        "--require-preflight",
        action="store_true",
        help="fail suite validation unless proof-preflight.json passed",
    )
    proof_validate_suite_parser.add_argument(
        "--require-review",
        action="store_true",
        help="fail suite validation unless proof-suite-review-status.json passed",
    )
    proof_validate_suite_parser.add_argument(
        "--write-report",
        action="store_true",
        help="write proof-suite-report.md after validation",
    )
    proof_validate_suite_parser.add_argument(
        "--report-path",
        type=Path,
        help="write the suite report to an explicit Markdown path",
    )
    proof_validate_suite_parser.add_argument(
        "--write-status-json",
        action="store_true",
        help="write proof-suite-status.json after validation",
    )
    proof_validate_suite_parser.add_argument(
        "--status-json-path",
        type=Path,
        help="write the suite status JSON to an explicit path",
    )
    proof_validate_suite_parser.add_argument(
        "--write-runbook",
        action="store_true",
        help="write proof-suite-next-actions.md after validation",
    )
    proof_validate_suite_parser.add_argument(
        "--runbook-path",
        type=Path,
        help="write the next-actions runbook to an explicit Markdown path",
    )
    proof_validate_suite_parser.add_argument(
        "--write-archive",
        action="store_true",
        help="write proof-suite-artifacts.zip after validation",
    )
    proof_validate_suite_parser.add_argument(
        "--archive-path",
        type=Path,
        help="write the proof suite artifact archive to an explicit zip path",
    )
    proof_validate_suite_parser.add_argument(
        "--write-review-template",
        action="store_true",
        help="write proof-suite-review.md after validation",
    )
    proof_validate_suite_parser.add_argument(
        "--review-template-path",
        type=Path,
        help="write the human review template to an explicit Markdown path",
    )
    proof_promote_suite_parser = proof_subparsers.add_parser(
        "promote-suite",
        help="write final proof-suite promotion JSON after all gates pass",
    )
    proof_promote_suite_parser.add_argument("trace_root", type=Path)
    proof_promote_suite_parser.add_argument(
        "--allow-missing-video",
        action="store_true",
        help="promote artifacts with an externally reviewed recording",
    )
    proof_promote_suite_parser.add_argument(
        "--promotion-path",
        type=Path,
        help="write the promotion JSON to an explicit path",
    )
    proof_promote_suite_parser.add_argument(
        "--write-report",
        action="store_true",
        help="write proof-suite-report.md alongside the promotion result",
    )
    proof_promote_suite_parser.add_argument(
        "--write-status-json",
        action="store_true",
        help="write proof-suite-status.json alongside the promotion result",
    )
    proof_promote_suite_parser.add_argument(
        "--write-runbook",
        action="store_true",
        help="write proof-suite-next-actions.md alongside the promotion result",
    )
    proof_promote_suite_parser.add_argument(
        "--write-archive",
        action="store_true",
        help="write proof-suite-artifacts.zip after promotion JSON is written",
    )
    proof_finalize_suite_parser = proof_subparsers.add_parser(
        "finalize-suite",
        help="write and verify the complete post-review proof-suite evidence pack",
    )
    proof_finalize_suite_parser.add_argument("trace_root", type=Path)
    proof_finalize_suite_parser.add_argument(
        "--allow-missing-video",
        action="store_true",
        help="finalize artifacts with an externally reviewed recording",
    )
    proof_verify_promotion_parser = proof_subparsers.add_parser(
        "verify-promotion",
        help="verify proof-suite promotion JSON digests against local artifacts",
    )
    proof_verify_promotion_parser.add_argument("promotion_path", type=Path)
    proof_verify_promotion_parser.add_argument(
        "--write-status-json",
        action="store_true",
        help="write proof-promotion-verification.json after verification",
    )
    proof_verify_promotion_parser.add_argument(
        "--status-json-path",
        type=Path,
        help="write promotion verification status JSON to an explicit path",
    )
    proof_verify_archive_parser = proof_subparsers.add_parser(
        "verify-archive",
        help="verify a zipped proof-suite archive against its promotion record",
    )
    proof_verify_archive_parser.add_argument("archive_path", type=Path)
    proof_verify_archive_parser.add_argument(
        "--write-status-json",
        action="store_true",
        help="write proof-archive-verification.json after verification",
    )
    proof_verify_archive_parser.add_argument(
        "--status-json-path",
        type=Path,
        help="write archive verification status JSON to an explicit path",
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
    benchmark_parser.add_argument(
        "--fail-on-monitoring-gap",
        action="store_true",
        help="return nonzero when a configured benchmark misses trace coverage",
    )

    record_parser = subparsers.add_parser(
        "record",
        help="control a local routine recording session",
    )
    _add_record_options(record_parser)

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


def _add_record_options(parser: argparse.ArgumentParser) -> None:
    record_subparsers = parser.add_subparsers(dest="record_command")
    start_parser = record_subparsers.add_parser("start", help="start recording")
    _add_record_state_option(start_parser)
    start_parser.add_argument("--name", default="untitled routine")
    start_parser.add_argument("--overwrite", action="store_true")
    _add_record_review_options(start_parser, include_routine_name=False)

    pause_parser = record_subparsers.add_parser("pause", help="pause recording")
    _add_record_state_option(pause_parser)

    stop_parser = record_subparsers.add_parser("stop", help="stop recording")
    _add_record_state_option(stop_parser)

    save_parser = record_subparsers.add_parser("save", help="save recording")
    _add_record_state_option(save_parser)
    save_parser.add_argument("--output", required=True, type=Path)
    save_parser.add_argument(
        "--confirm-save",
        action="store_true",
        help="confirm that the operator reviewed and wants to save this recording",
    )

    review_parser = record_subparsers.add_parser(
        "review",
        help="update routine review metadata",
    )
    _add_record_state_option(review_parser)
    _add_record_review_options(review_parser, include_routine_name=True)

    export_parser = record_subparsers.add_parser(
        "export-task",
        help="export the current recording as editable task YAML",
    )
    _add_record_state_option(export_parser)
    export_parser.add_argument("--output", required=True, type=Path)
    export_parser.add_argument(
        "--proof-checklist",
        type=Path,
        help="write a markdown checklist for dry-run and Windows proof review",
    )

    discard_parser = record_subparsers.add_parser(
        "discard",
        help="discard recording",
    )
    _add_record_state_option(discard_parser)


def _add_record_state_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--state",
        default=Path("traces/recorder-session.json"),
        type=Path,
        help="local recorder control-state file",
    )


def _add_record_review_options(
    parser: argparse.ArgumentParser,
    *,
    include_routine_name: bool,
) -> None:
    if include_routine_name:
        parser.add_argument("--routine-name")
    parser.add_argument("--description")
    parser.add_argument("--input", action="append", dest="routine_inputs")
    parser.add_argument("--output", action="append", dest="routine_outputs")
    parser.add_argument("--tag", action="append", dest="routine_tags")
    parser.add_argument("--risk-class")
    parser.add_argument("--expected-duration-seconds", type=float)


def _add_task_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("task_yaml", type=Path)
    _add_runtime_options(parser)


def _add_runtime_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", type=Path)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--no-screenshots", action="store_true")
    parser.add_argument(
        "--activity-profile",
        choices=("focused", "careful", "background_assist", "batch_work"),
        help="apply a named bounded timing preset for this run",
    )
    parser.add_argument("--max-runtime-seconds", type=float)
    parser.add_argument("--confidence-threshold", type=float)
    parser.add_argument("--allowed-window", action="append", default=[])
    parser.add_argument("--confirm-step", action="append", default=[])
    parser.add_argument("--approval-manifest", type=Path)


def _add_local_model_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        help="optional JSON report path for local model monitoring",
    )


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
    parser.add_argument(
        "--video-policy",
        choices=("full", "disabled"),
        default="full",
        help="disable video capture even when --record-video is present",
    )


def _video_recording_enabled(args: argparse.Namespace) -> bool:
    return bool(args.record_video and args.video_policy != "disabled")


def _add_site_catalog_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--playbook-dir",
        default=Path("navigation_playbooks"),
        type=Path,
    )


def _add_routine_catalog_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--routine-pack-root",
        default=Path("routine_packs"),
        type=Path,
    )


def _add_routine_failure_history_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--failure-history-root",
        type=Path,
        help="optional trace root used to apply routine quarantine counters",
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
        focus_recovery_controller=NoopFocusRecoveryController()
        if dry_run
        else create_platform_focus_recovery_controller(),
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


def _list_routines(args: argparse.Namespace) -> int:
    catalog = load_routine_catalog(args.routine_pack_root)
    routines = (
        [result.routine for result in catalog.search(args.query)]
        if args.query
        else list(catalog.routines)
    )
    for routine in routines:
        print(f"{routine.id}\t{routine.name}")
    return 0


def _show_routine(args: argparse.Namespace) -> int:
    routine = _load_routine(args)
    print(f"id: {routine.id}")
    print(f"name: {routine.name}")
    print(f"description: {routine.description}")
    print(f"goal: {routine.goal}")
    if routine.required_app:
        print(f"required_app: {routine.required_app}")
    if routine.required_site:
        print(f"required_site: {routine.required_site}")
    print(f"tags: {', '.join(routine.tags)}")
    print(f"safety_class: {routine.safety_class}")
    print(f"schedule_policy: {routine.schedule_policy}")
    print(f"approval_policy: {routine.approval_policy}")
    print(f"routine_schema_version: {routine.schema_version}")
    print(f"expected_duration_seconds: {routine.expected_duration_seconds:g}")
    print("schedule:")
    for line in _routine_schedule_summary(routine).splitlines():
        print(f"  {line}")
    print(f"failed_evidence_count: {routine.failed_evidence_count}")
    print(f"quarantine_failure_threshold: {routine.quarantine_failure_threshold}")
    print(f"quarantine_status: {routine_quarantine_status(routine)}")
    if routine.quarantine_reason:
        print(f"quarantine_reason: {routine.quarantine_reason}")
    print(f"redaction_policy: {routine.redaction_policy.metadata()}")
    print(f"reference: {_routine_reference_summary(routine)}")
    print("promotion_gates:")
    for gate in routine_promotion_gates(routine):
        requirement = "required" if gate.required else "not_required"
        print(f"  - {gate.id}: {requirement}")
    return 0


def _compile_routine(args: argparse.Namespace) -> int:
    routine = _load_routine(args)
    task = _compile_routine_task(routine, playbook_dir=args.playbook_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        yaml.safe_dump(_task_to_yaml_dict(task), sort_keys=False),
        encoding="utf-8",
    )
    print(f"compiled routine: {routine.id}")
    print(f"task: {args.output}")
    return 0


def _export_routine(args: argparse.Namespace) -> int:
    routine = _load_routine(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        yaml.safe_dump(_routine_to_yaml_dict(routine), sort_keys=False),
        encoding="utf-8",
    )
    print(f"exported routine: {routine.id}")
    print(f"routine: {args.output}")
    return 0


def _generate_routine_docs(args: argparse.Namespace) -> int:
    catalog = load_routine_catalog(args.routine_pack_root)
    failure_counters = (
        routine_failure_counters_from_trace_root(args.failure_history_root)
        if args.failure_history_root is not None
        else None
    )
    args.index_output.parent.mkdir(parents=True, exist_ok=True)
    args.template_output.parent.mkdir(parents=True, exist_ok=True)
    args.index_output.write_text(
        render_routine_catalog_index(catalog, failure_counters),
        encoding="utf-8",
    )
    args.template_output.write_text(
        render_routine_documentation_template(),
        encoding="utf-8",
    )
    print(f"routine catalog index: {args.index_output}")
    print(f"routine documentation template: {args.template_output}")
    return 0


def _list_routine_packs(args: argparse.Namespace) -> int:
    manifests = load_routine_pack_manifests(args.routine_pack_root)
    for manifest in manifests:
        warning_count = len(routine_pack_trust_warnings(manifest))
        print(
            f"{manifest.id}\t{manifest.version}\t"
            f"{manifest.trust_level}\t{manifest.name}\twarnings={warning_count}",
        )
    return 0


def _show_routine_pack(args: argparse.Namespace) -> int:
    manifests = load_routine_pack_manifests(args.routine_pack_root)
    manifest = next(
        (item for item in manifests if item.id == args.pack_id),
        None,
    )
    if manifest is None:
        raise RoutinePackOperationError(f"unknown routine pack: {args.pack_id}")
    print(f"id: {manifest.id}")
    print(f"name: {manifest.name}")
    print(f"description: {manifest.description}")
    print(f"version: {manifest.version}")
    print(f"publisher: {manifest.publisher}")
    print(f"trust_level: {manifest.trust_level}")
    print(f"routine_globs: {', '.join(manifest.routine_globs)}")
    print(f"docs: {', '.join(manifest.docs) or 'none'}")
    print(f"fixtures: {', '.join(manifest.fixtures) or 'none'}")
    print(f"tests: {', '.join(manifest.tests) or 'none'}")
    print(f"safety.max_safety_class: {manifest.safety.max_safety_class}")
    print(f"safety.requires_review: {manifest.safety.requires_review}")
    print(
        "safety.external_mutation_allowed: "
        f"{manifest.safety.external_mutation_allowed}",
    )
    print(f"safety.approval_required: {manifest.safety.approval_required}")
    print(f"proof.windows_proof_required: {manifest.proof.windows_proof_required}")
    print(
        "proof.expected_artifacts: "
        f"{', '.join(manifest.proof.expected_artifacts)}",
    )
    _print_routine_pack_warnings(manifest)
    return 0


def _import_routine_pack(args: argparse.Namespace) -> int:
    result = import_routine_pack(
        args.source,
        args.routine_pack_root,
        replace=args.replace,
    )
    action = "replaced" if result.replaced_existing else "imported"
    print(f"{action} routine pack: {result.manifest.id}")
    print(f"source: {result.source_path}")
    print(f"installed: {result.installed_path}")
    _print_routine_pack_conflicts(result.conflicts)
    _print_trust_warning_messages(result.trust_warnings)
    return 0


def _export_routine_pack(args: argparse.Namespace) -> int:
    result = export_routine_pack(
        args.routine_pack_root,
        args.pack_id,
        args.output,
        replace=args.replace,
    )
    kind = "archive" if result.archive else "directory"
    print(f"exported routine pack: {result.manifest.id}")
    print(f"output_{kind}: {result.output_path}")
    _print_trust_warning_messages(result.trust_warnings)
    return 0


def _test_routine_pack(args: argparse.Namespace) -> int:
    result = run_routine_pack_tests(args.routine_pack_root, args.pack_id)
    print(f"routine pack: {result.pack_id}")
    print(f"status: {result.status}")
    print(f"routines: {result.routine_count}")
    print(f"validated_routines: {result.validated_routine_count}")
    if result.errors:
        print("errors:")
        for error in result.errors:
            print(f"  - {error}")
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result.metadata(), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        print(f"report: {args.output}")
    return 1 if result.status == "failed" else 0


def _write_routine_pack_proof(args: argparse.Namespace) -> int:
    result = write_routine_pack_proof_bundle(
        args.routine_pack_root,
        args.pack_id,
        args.output,
    )
    print(f"routine pack proof: {result.pack_id}")
    print(f"status: {result.test_result.status}")
    print(f"bundle: {result.bundle_dir}")
    print(f"report: {result.report_path}")
    print(f"checklist: {result.checklist_path}")
    return 1 if result.test_result.status == "failed" else 0


def _print_routine_pack_warnings(manifest: RoutinePackManifest) -> None:
    warnings = routine_pack_trust_warnings(manifest)
    _print_trust_warning_messages(warnings)


def _print_trust_warning_messages(
    warnings: tuple[RoutinePackTrustWarning, ...],
) -> None:
    if not warnings:
        print("trust_warnings: none")
        return
    print("trust_warnings:")
    for warning in warnings:
        print(f"  - {warning.message}")


def _print_routine_pack_conflicts(
    conflicts: tuple[RoutinePackConflict, ...],
) -> None:
    if not conflicts:
        print("conflicts: none")
        return
    print("conflicts:")
    for conflict in conflicts:
        print(f"  - {conflict.severity}/{conflict.kind}: {conflict.message}")


def _run_routine(args: argparse.Namespace, *, dry_run: bool) -> int:
    routine = _load_executable_routine(args)
    task = _compile_routine_task(routine, playbook_dir=args.playbook_dir)
    task_path = (
        routine.reference.task_path
        if routine.reference.kind == "task" and routine.reference.task_path
        else Path(f"routine-{routine.id}.yaml")
    )
    return _run_loaded_task(args, task, task_path, dry_run=dry_run)


def _load_executable_routine(args: argparse.Namespace) -> RoutineDefinition:
    catalog = load_routine_catalog(args.routine_pack_root)
    failure_history_root = getattr(args, "failure_history_root", None)
    failure_counters = (
        routine_failure_counters_from_trace_root(failure_history_root)
        if failure_history_root is not None
        else None
    )
    return require_validated_routine_for_execution(
        catalog,
        args.routine_id,
        failure_counters,
    )


def _plan_goal(args: argparse.Namespace) -> int:
    catalog = load_routine_catalog(args.routine_pack_root)
    config = resolve_runtime_config(YamlConfigLoader().load(args.config))
    request = GoalRoutingRequest(
        user_goal=args.user_goal,
        normalized_intent=args.intent or args.user_goal.casefold(),
        required_app=args.required_app,
        required_site=args.required_site,
        tags=tuple(args.tag),
        provided_inputs=tuple(args.input),
        max_safety_class=args.max_safety_class,
    )
    plan = route_goal_to_routine(catalog, request)
    plan = rank_goal_plan_with_optional_model(
        catalog,
        request,
        plan,
        config.local_model,
    )
    print("goal plan:")
    print(f"  goal: {plan.user_goal}")
    print(f"  intent: {plan.normalized_intent}")
    print(f"  status: {plan.execution_status}")
    print(f"  selected: {plan.selected_routine_id or 'none'}")
    print(f"  explanation: {plan.explanation}")
    if plan.expected_evidence:
        print(f"  expected_evidence: {', '.join(plan.expected_evidence)}")
    if plan.abort_conditions:
        print(f"  abort_conditions: {', '.join(plan.abort_conditions)}")
    print("  candidates:")
    for candidate in plan.candidate_routines:
        print(
            "    - "
            f"{candidate.routine_id} score={candidate.score:g} "
            f"safety={candidate.safety_class} approval={candidate.approval_policy}",
        )
    if plan.model_ranking is not None:
        ranking = plan.model_ranking
        print(
            "  model: "
            f"{ranking.status} provider={ranking.provider} "
            f"model={ranking.model} affected_selection={ranking.affected_selection}",
        )
        if ranking.error:
            print(f"  model_error: {ranking.error}")
    prompts = missing_input_prompts(
        plan,
        required_session_state=tuple(args.session_state),
    )
    if prompts:
        print("  prompts:")
        for prompt in prompts:
            print(f"    - {prompt.kind}:{prompt.key}: {prompt.prompt}")
    trace_dir = write_goal_plan_trace(plan, args.trace_root or config.trace_root)
    print(f"trace: {trace_dir}")
    return 0


def _local_model(args: argparse.Namespace) -> int:
    if args.local_model_command is None:
        print("error: local-model requires a subcommand")
        return 2

    config = resolve_runtime_config(YamlConfigLoader().load(args.config))
    provider = OllamaLocalModelProvider(config.local_model)
    probe_when_disabled = args.local_model_command == "list" or bool(
        getattr(args, "probe_disabled", False),
    )
    status = provider.status(probe_when_disabled=probe_when_disabled)

    if args.local_model_command == "status":
        _print_local_model_status(status)
        if args.output is not None:
            report_path = write_local_model_status_report(status, args.output)
            print(f"report: {report_path}")
        return 0 if status.status in {"available", "disabled"} else 1

    if args.local_model_command == "list":
        if not status.available:
            _print_local_model_status(status)
            if args.output is not None:
                report_path = write_local_model_status_report(status, args.output)
                print(f"report: {report_path}")
            return 1
        if status.models:
            for model in status.models:
                print(model.name)
        else:
            print("no local models")
        if args.output is not None:
            report_path = write_local_model_status_report(status, args.output)
            print(f"report: {report_path}")
        return 0

    print(f"error: unsupported local-model command: {args.local_model_command}")
    return 2


def _print_local_model_status(status: LocalModelStatus) -> None:
    print("local model:")
    print(f"  provider: {status.provider}")
    print(f"  endpoint: {status.endpoint}")
    print(f"  enabled: {status.enabled}")
    print(f"  status: {status.status}")
    print(f"  available: {status.available}")
    print(f"  models: {len(status.models)}")
    if status.error:
        print(f"  error: {status.error}")


def _load_routine(args: argparse.Namespace) -> RoutineDefinition:
    catalog = load_routine_catalog(args.routine_pack_root)
    routine = catalog.by_id(args.routine_id)
    if routine is None:
        raise RoutineDefinitionError(f"unknown routine: {args.routine_id}")
    return routine


def _compile_routine_task(
    routine: RoutineDefinition,
    *,
    playbook_dir: Path,
) -> TaskDefinition:
    if routine.reference.kind == "task":
        if routine.reference.task_path is None:
            raise RoutineDefinitionError("routine task reference path is required")
        task = YamlTaskLoader().load(routine.reference.task_path)
    else:
        if not routine.reference.playbook_site or not routine.reference.playbook_flow:
            raise RoutineDefinitionError("routine playbook reference is incomplete")
        task = _compile_site_flow(
            playbook_dir,
            routine.reference.playbook_site,
            routine.reference.playbook_flow,
            redaction_policy=routine.redaction_policy,
        )
    return replace(
        task,
        name=routine.name,
        metadata={
            **task.metadata,
            **routine.report_metadata(),
            "routine_source_path": str(routine.source_path)
            if routine.source_path
            else None,
        },
    )


def _routine_reference_summary(routine: RoutineDefinition) -> str:
    reference = routine.reference
    if reference.kind == "task":
        return f"task:{reference.task_path}"
    return f"playbook:{reference.playbook_site}/{reference.playbook_flow}"


def _routine_to_yaml_dict(routine: RoutineDefinition) -> dict[str, object]:
    payload: dict[str, object] = {
        "routine_schema_version": routine.schema_version,
        "id": routine.id,
        "name": routine.name,
        "description": routine.description,
        "goal": routine.goal,
        "tags": list(routine.tags),
        "inputs": list(routine.inputs),
        "outputs": list(routine.outputs),
        "safety_class": routine.safety_class,
        "schedule_policy": routine.schedule_policy,
        "approval_policy": routine.approval_policy,
        "expected_duration_seconds": routine.expected_duration_seconds,
        "reference": _routine_reference_to_yaml_dict(routine),
        "failed_evidence_count": routine.failed_evidence_count,
        "quarantine_failure_threshold": routine.quarantine_failure_threshold,
        "quarantine_status": routine.quarantine_status,
    }
    _put_optional(payload, "required_app", routine.required_app)
    _put_optional(payload, "required_site", routine.required_site)
    if routine.schedule != type(routine.schedule)():
        payload["schedule"] = _routine_schedule_to_yaml_dict(routine)
    if routine.redaction_policy != type(routine.redaction_policy)():
        payload["redaction_policy"] = routine.redaction_policy.metadata()
    _put_optional(payload, "quarantine_reason", routine.quarantine_reason)
    return payload


def _routine_schedule_summary(routine: RoutineDefinition) -> str:
    schedule = routine.schedule
    if schedule == type(schedule)():
        return "none"
    lines: list[str] = []
    if schedule.allowed_time_windows:
        lines.append("allowed_time_windows:")
        for window in schedule.allowed_time_windows:
            days = ",".join(window.days) if window.days else "everyday"
            lines.append(
                f"  - {days} {window.start}-{window.end} {window.timezone}",
            )
    if schedule.cooldown_seconds:
        lines.append(f"cooldown_seconds: {schedule.cooldown_seconds:g}")
    if schedule.max_runs_per_day is not None:
        lines.append(f"max_runs_per_day: {schedule.max_runs_per_day}")
    if schedule.max_runs_per_week is not None:
        lines.append(f"max_runs_per_week: {schedule.max_runs_per_week}")
    if schedule.max_actions_per_hour is not None:
        lines.append(f"max_actions_per_hour: {schedule.max_actions_per_hour}")
    if schedule.max_external_mutations is not None:
        lines.append(f"max_external_mutations: {schedule.max_external_mutations}")
    if schedule.stop_conditions:
        lines.append(f"stop_conditions: {', '.join(schedule.stop_conditions)}")
    return "\n".join(lines)


def _routine_schedule_to_yaml_dict(routine: RoutineDefinition) -> dict[str, object]:
    schedule = routine.schedule
    payload: dict[str, object] = {}
    if schedule.allowed_time_windows:
        payload["allowed_time_windows"] = [
            {
                "days": list(window.days),
                "start": window.start,
                "end": window.end,
                "timezone": window.timezone,
            }
            for window in schedule.allowed_time_windows
        ]
    if schedule.cooldown_seconds:
        payload["cooldown_seconds"] = schedule.cooldown_seconds
    if schedule.max_runs_per_day is not None:
        payload["max_runs_per_day"] = schedule.max_runs_per_day
    if schedule.max_runs_per_week is not None:
        payload["max_runs_per_week"] = schedule.max_runs_per_week
    if schedule.max_actions_per_hour is not None:
        payload["max_actions_per_hour"] = schedule.max_actions_per_hour
    if schedule.max_external_mutations is not None:
        payload["max_external_mutations"] = schedule.max_external_mutations
    if schedule.stop_conditions:
        payload["stop_conditions"] = list(schedule.stop_conditions)
    return payload


def _routine_reference_to_yaml_dict(
    routine: RoutineDefinition,
) -> dict[str, object]:
    reference = routine.reference
    if reference.kind == "task":
        return {
            "type": "task",
            "path": str(reference.task_path) if reference.task_path else "",
        }
    return {
        "type": "playbook",
        "site": reference.playbook_site or "",
        "flow": reference.playbook_flow or "",
    }


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
    config = resolve_runtime_config(
        YamlConfigLoader().load(args.config),
        cli_overrides=_cli_overrides_from_args(args),
    )
    task = _compile_site_flow(
        args.playbook_dir,
        args.site,
        args.flow,
        variables_path=args.variables,
        redaction_policy=config.redaction_policy,
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
    redaction_policy: RedactionPolicy | None = None,
) -> TaskDefinition:
    playbook = _load_named_site(playbook_dir, site_id)
    resolve_site_flow(playbook, flow_id)
    variables = load_content_variables(variables_path)
    return SiteTaskCompiler(variables, redaction_policy).compile(playbook, flow_id)


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
    activity_profile = getattr(args, "activity_profile", None)
    return ConfigOverrides(
        save_screenshots=False if args.no_screenshots else None,
        max_runtime_seconds=args.max_runtime_seconds,
        confidence_threshold=args.confidence_threshold,
        allowed_windows=tuple(args.allowed_window) if args.allowed_window else None,
        confirmed_steps=tuple(args.confirm_step) if args.confirm_step else None,
        execution_profile=execution_profile_for_activity(activity_profile)
        if activity_profile
        else None,
    )


def _task_to_yaml_dict(task: TaskDefinition) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": task.name,
        "allowed_windows": list(task.allowed_windows),
        "timeout_seconds": task.timeout_seconds,
        "steps": [_task_step_to_yaml_dict(step) for step in task.steps],
    }
    _put_optional(payload, "entropy_budget", task.entropy_budget)
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
    _put_optional(payload, "handoff_prompt", step.handoff_prompt)
    _put_optional(payload, "expected_operator_work", step.expected_operator_work)
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
    _put_optional(payload, "on_failure", step.on_failure)
    if step.requires_confirmation:
        payload["requires_confirmation"] = True
    _put_optional(payload, "category", step.category)
    _put_optional(payload, "entropy_budget", step.entropy_budget)
    if step.safe_action_variants:
        payload["safe_action_variants"] = list(step.safe_action_variants)
    if step.recovery:
        payload["recovery"] = [
            _recovery_rule_to_yaml_dict(rule) for rule in step.recovery
        ]
    if step.depends_on:
        payload["depends_on"] = list(step.depends_on)
    if step.expected_state is not None:
        payload["expected_state"] = _expected_state_to_yaml_dict(
            step.expected_state,
        )
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


def _recovery_rule_to_yaml_dict(rule: RecoveryRule) -> dict[str, object]:
    payload: dict[str, object] = {
        "reason": rule.reason,
        "actions": list(rule.actions),
    }
    _put_optional(payload, "next_step", rule.next_step)
    return payload


def _expected_state_to_yaml_dict(
    state: ExpectedStateTransition,
) -> dict[str, object]:
    payload: dict[str, object] = {}
    _put_optional(payload, "before", state.before)
    _put_optional(payload, "after", state.after)
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
    if args.caption_output is not None:
        caption_report = screen_caption_review_from_inspection(
            payload,
            inspection_report_path=output_path,
        )
        caption_path = write_screen_caption_review_report(
            caption_report,
            args.caption_output,
        )
        print(f"caption report: {caption_path}")
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
    print(f"schema: {report.schema_version}")
    print(f"generated_at: {report.generated_at}")
    print(f"iterations: {len(report.runs)}")
    print(f"metrics: {report.metrics_path}")
    print(f"baseline metrics: {report.baseline_metrics_path}")
    print(f"trace health: {report.trace_health_path}")
    print(f"variance: {report.variance_report_path}")
    print(f"baseline comparison: {report.baseline_comparison_path}")
    print(f"baseline status: {report.baseline_comparison.status}")
    print(f"pointer timing: {report.pointer_timing_comparison_path}")
    print(f"acceptance: {report.acceptance.status}")
    monitoring_status = _benchmark_monitoring_status(report.monitoring_coverage)
    print(f"monitoring coverage: {monitoring_status}")
    for failure in _benchmark_monitoring_failures(report.monitoring_coverage):
        print(f"monitoring gap: {failure}")
    for failure in report.acceptance.failures:
        print(f"acceptance failure: {failure}")
    print(f"report: {report.report_path}")
    print(f"summary: {report.summary_report_path}")
    return _benchmark_exit_code(
        tuple(run.status for run in report.runs),
        acceptance_passed=report.acceptance.passed,
        monitoring_coverage=report.monitoring_coverage,
        fail_on_monitoring_gap=args.fail_on_monitoring_gap,
    )


def _benchmark_exit_code(
    run_statuses: Sequence[str],
    *,
    acceptance_passed: bool,
    monitoring_coverage: Mapping[str, object],
    fail_on_monitoring_gap: bool,
) -> int:
    monitoring_failed = (
        fail_on_monitoring_gap
        and monitoring_coverage.get("configured") is True
        and monitoring_coverage.get("passed") is not True
    )
    if all(status == "passed" for status in run_statuses) and acceptance_passed:
        return 1 if monitoring_failed else 0
    return 1


def _benchmark_monitoring_status(coverage: Mapping[str, object]) -> str:
    if coverage.get("configured") is not True:
        return "not_configured"
    return "passed" if coverage.get("passed") is True else "failed"


def _benchmark_monitoring_failures(coverage: Mapping[str, object]) -> tuple[str, ...]:
    if coverage.get("configured") is not True or coverage.get("passed") is True:
        return ()
    failures: list[str] = []
    missing_phases = _string_sequence(coverage.get("missing_trace_phases"))
    missing_fields = _string_sequence(coverage.get("missing_report_fields"))
    if missing_phases:
        failures.append(f"missing trace phases: {', '.join(missing_phases)}")
    if missing_fields:
        failures.append(f"missing report fields: {', '.join(missing_fields)}")
    return tuple(failures)


def _string_sequence(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def _record(args: argparse.Namespace) -> int:
    controller = RecorderController(args.state)
    if args.record_command == "start":
        session = controller.start(
            name=args.name,
            overwrite=args.overwrite,
            review=_record_start_review_metadata(args),
        )
        print(f"recording started: {session.session_id}")
        print(f"state: {args.state}")
        return 0
    if args.record_command == "pause":
        session = controller.pause()
        print(f"recording paused: {session.session_id}")
        return 0
    if args.record_command == "stop":
        session = controller.stop()
        print(f"recording stopped: {session.session_id}")
        return 0
    if args.record_command == "save":
        if not _confirm_record_save(args):
            print("recording save not confirmed")
            return 1
        session = controller.save(args.output)
        print(f"recording saved: {session.session_id}")
        print(f"output: {args.output}")
        return 0
    if args.record_command == "review":
        session = controller.update_review(
            routine_name=args.routine_name,
            description=args.description,
            inputs=_record_review_values(args.routine_inputs),
            outputs=_record_review_values(args.routine_outputs),
            tags=_record_review_values(args.routine_tags),
            risk_class=args.risk_class,
            expected_duration_seconds=args.expected_duration_seconds,
        )
        print(f"recording review updated: {session.session_id}")
        print(f"routine: {session.review.routine_name}")
        return 0
    if args.record_command == "export-task":
        session = controller.load()
        task = generate_task_from_recorder_session(session)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            yaml.safe_dump(_task_to_yaml_dict(task), sort_keys=False),
            encoding="utf-8",
        )
        if args.proof_checklist is not None:
            args.proof_checklist.parent.mkdir(parents=True, exist_ok=True)
            args.proof_checklist.write_text(
                _recorded_task_proof_checklist(args.output, task),
                encoding="utf-8",
            )
        print(f"recording task exported: {session.session_id}")
        print(f"task: {args.output}")
        if args.proof_checklist is not None:
            print(f"proof checklist: {args.proof_checklist}")
        return 0
    if args.record_command == "discard":
        session = controller.discard()
        print(f"recording discarded: {session.session_id}")
        return 0
    print("error: record subcommand required")
    return 2


def _confirm_record_save(args: argparse.Namespace) -> bool:
    if args.confirm_save:
        return True
    try:
        return input("type SAVE to save recording: ").strip() == "SAVE"
    except EOFError:
        return False


def _record_start_review_metadata(args: argparse.Namespace) -> RecorderReviewMetadata:
    return RecorderReviewMetadata(
        routine_name=args.name,
        description=args.description or "",
        inputs=tuple(args.routine_inputs or ()),
        outputs=tuple(args.routine_outputs or ()),
        tags=tuple(args.routine_tags or ()),
        risk_class=args.risk_class or RECORDER_DEFAULT_RISK_CLASS,
        expected_duration_seconds=args.expected_duration_seconds,
    )


def _record_review_values(values: list[str] | None) -> tuple[str, ...] | None:
    if values is None:
        return None
    return tuple(values)


def _recorded_task_proof_checklist(
    task_path: Path,
    task: TaskDefinition,
) -> str:
    lines = [
        "# Recorded Routine Proof Checklist",
        "",
        f"- Task YAML: `{task_path}`",
        f"- Routine: `{task.name}`",
        "",
        "## Edit And Dry-Run",
        "",
        f"- [ ] Review and edit `{task_path}`.",
        f"- [ ] Run `desktop-agent dry-run {task_path}`.",
        "- [ ] Confirm the dry-run trace contains `task.json`, `action-log.jsonl`, "
        "and `final-report.json`.",
        "",
        "## Windows Proof Flow",
        "",
        "- [ ] Run the edited YAML on an owned Windows desktop with "
        f"`desktop-agent run {task_path}`.",
        "- [ ] Capture the run with the same evidence expectations used by "
        "`docs/windows-proof-evidence-checklist.md`.",
        "- [ ] Use `desktop-agent replay <trace-dir> --write-summary` for the "
        "recorded task trace.",
        "- [ ] For fixture-level proof comparison, run "
        "`desktop-agent proof browser-fixture` or "
        "`desktop-agent proof native-fixture` as applicable.",
    ]
    return "\n".join(lines) + "\n"


def _demo_input(args: argparse.Namespace) -> int:
    report = run_input_demo(
        trace_root=args.trace_root,
        random_seed=args.random_seed,
        movement_smoothness=args.movement_smoothness,
        keyboard_text=args.keyboard_text,
        countdown_seconds=args.countdown_seconds,
        record_video=_video_recording_enabled(args),
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
        record_video=_video_recording_enabled(args),
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
        record_video=_video_recording_enabled(args),
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
        goal_report_path = args.trace_dir / "goal-plan-report.json"
        if goal_report_path.exists():
            return _replay_goal_plan(args)
        proof_suite_status_path = args.trace_dir / PROOF_FINALIZATION_STATUS_NAME
        if proof_suite_status_path.exists():
            return _replay_proof_suite(args)
        benchmark_report_path = args.trace_dir / "benchmark-report.json"
        if benchmark_report_path.exists():
            return _replay_benchmark(args)
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
    if args.write_summary:
        summary_path = _write_replay_summary(args.trace_dir, report)
        print(f"summary: {summary_path}")
    if args.verbose:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def _replay_goal_plan(args: argparse.Namespace) -> int:
    goal_plan_path = args.trace_dir / "goal-plan.json"
    report_path = args.trace_dir / "goal-plan-report.json"
    if not goal_plan_path.exists():
        print(f"error: goal plan not found: {goal_plan_path}")
        return 1

    goal_plan_payload = json.loads(goal_plan_path.read_text(encoding="utf-8"))
    if not isinstance(goal_plan_payload, dict):
        print("error: goal plan must contain a JSON object")
        return 1
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if not isinstance(report, dict):
        print("error: goal plan report must contain a JSON object")
        return 1

    plan = goal_plan_from_mapping(goal_plan_payload)
    events = _read_goal_plan_action_log(args.trace_dir / "action-log.jsonl")

    print(f"trace: {args.trace_dir}")
    print(f"goal plan: {plan.user_goal}")
    print(f"intent: {plan.normalized_intent}")
    print(f"status: {plan.execution_status}")
    print(f"selected: {plan.selected_routine_id or 'none'}")
    print(f"candidates: {len(plan.candidate_routines)}")
    for candidate in plan.candidate_routines:
        matched = ", ".join(candidate.matched_fields) or "none"
        print(
            f"candidate: {candidate.routine_id} score={candidate.score:g} "
            f"matched={matched} safety={candidate.safety_class} "
            f"approval={candidate.approval_policy}",
        )
    if plan.expected_evidence:
        print(f"expected_evidence: {', '.join(plan.expected_evidence)}")
    if plan.abort_conditions:
        print(f"abort_conditions: {', '.join(plan.abort_conditions)}")
    if plan.missing_inputs:
        print(f"missing_inputs: {', '.join(plan.missing_inputs)}")
    for line in _goal_plan_replay_timeline_lines(events):
        print(line)
    if args.write_summary:
        summary_path = _write_goal_plan_replay_summary(
            args.trace_dir,
            plan,
            report,
            events,
        )
        print(f"summary: {summary_path}")
    if args.verbose:
        print(
            json.dumps(
                {
                    "goal_plan": plan.metadata(),
                    "report": report,
                    "events": events,
                },
                indent=2,
                sort_keys=True,
            ),
        )
    return 0


def _replay_proof_suite(args: argparse.Namespace) -> int:
    status_path = args.trace_dir / PROOF_FINALIZATION_STATUS_NAME
    payload = json.loads(status_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        print("error: proof finalization status must contain a JSON object")
        return 1

    print(f"trace: {args.trace_dir}")
    print("proof suite: finalization")
    print(f"status: {payload.get('status', 'unknown')}")
    gates = _string_mapping(payload.get("gates"))
    if gates:
        print("gates:")
        for name, status in gates.items():
            print(f"- {name}: {status}")
    artifacts = _string_mapping(payload.get("artifacts"))
    if artifacts:
        print("artifacts:")
        for name, path in artifacts.items():
            print(f"- {name}: {path}")
    errors = _string_list(payload.get("errors"))
    if errors:
        print("errors:")
        for error in errors:
            print(f"- {error}")
    if args.write_summary:
        summary_path = _write_proof_suite_replay_summary(args.trace_dir, payload)
        print(f"summary: {summary_path}")
    if args.verbose:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _replay_benchmark(args: argparse.Namespace) -> int:
    report_path = args.trace_dir / "benchmark-report.json"
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        print("error: benchmark report must contain a JSON object")
        return 1

    print(f"trace: {args.trace_dir}")
    print(f"benchmark: {payload.get('task_path', 'unknown')}")
    print(f"status: {_benchmark_acceptance_status(payload)}")
    for line in _benchmark_replay_lines(payload):
        print(line)
    if args.write_summary:
        summary_path = _write_benchmark_replay_summary(args.trace_dir, payload)
        print(f"summary: {summary_path}")
    if args.verbose:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _trace_health(args: argparse.Namespace) -> int:
    health = LocalTraceService(args.trace_root).trace_health(limit=args.limit)
    exit_code = _trace_health_exit_code(health, args.fail_on_attention)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(health, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    if args.markdown_output is not None:
        args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_output.write_text(
            _render_trace_health_markdown(args.trace_root, health),
            encoding="utf-8",
        )
    if args.json:
        print(json.dumps(health, indent=2, sort_keys=True))
        if args.output is not None:
            print(f"report: {args.output}", file=sys.stderr)
        if args.markdown_output is not None:
            print(f"summary: {args.markdown_output}", file=sys.stderr)
        return exit_code
    print(f"trace_root: {args.trace_root}")
    print(f"schema_version: {health.get('schema_version', 'unknown')}")
    print(f"generated_at: {health.get('generated_at', 'unknown')}")
    print(f"health_status: {health.get('health_status', 'unknown')}")
    print(f"trace_count: {health['trace_count']}")
    print(f"artifact_trace_count: {health.get('artifact_trace_count', 0)}")
    print("by_kind:")
    for name, count in _int_mapping(health.get("by_kind")).items():
        print(f"- {name}: {count}")
    print("by_status:")
    for name, count in _int_mapping(health.get("by_status")).items():
        print(f"- {name}: {count}")
    attention_statuses = health.get("attention_statuses")
    if isinstance(attention_statuses, list) and attention_statuses:
        rendered_attention = ", ".join(str(status) for status in attention_statuses)
        print(f"attention_statuses: {rendered_attention}")
    attention_traces = health.get("attention_traces")
    if isinstance(attention_traces, list) and attention_traces:
        print("attention_traces:")
        for trace in attention_traces:
            if isinstance(trace, dict):
                print(_trace_health_console_trace_line(trace))
    artifact_traces = health.get("artifact_traces")
    if isinstance(artifact_traces, list) and artifact_traces:
        print("artifact_traces:")
        for trace in artifact_traces:
            if isinstance(trace, dict):
                print(_trace_health_console_trace_line(trace))
    latest_traces = health.get("latest")
    if isinstance(latest_traces, list) and latest_traces:
        print("latest_traces:")
        for trace in latest_traces:
            if isinstance(trace, dict):
                print(_trace_health_console_trace_line(trace))
    if args.output is not None:
        print(f"report: {args.output}")
    if args.markdown_output is not None:
        print(f"summary: {args.markdown_output}")
    return exit_code


def _render_trace_health_markdown(
    trace_root: Path,
    health: dict[str, object],
) -> str:
    lines = [
        "# Trace Health",
        "",
        f"- Trace root: `{trace_root}`",
        f"- Schema version: `{health.get('schema_version', 'unknown')}`",
        f"- Generated at: `{health.get('generated_at', 'unknown')}`",
        f"- Health status: `{health.get('health_status', 'unknown')}`",
        f"- Trace count: `{health.get('trace_count', 0)}`",
        f"- Artifact traces: `{health.get('artifact_trace_count', 0)}`",
        "",
        "## Counts By Kind",
        "",
        *_trace_health_count_lines(health.get("by_kind")),
        "",
        "## Counts By Status",
        "",
        *_trace_health_count_lines(health.get("by_status")),
        "",
        "## Attention Traces",
        "",
        *_trace_health_attention_lines(health.get("attention_traces")),
        "",
        "## Artifact Traces",
        "",
        *_trace_health_latest_lines(health.get("artifact_traces")),
        "",
        "## Latest Traces",
        "",
        *_trace_health_latest_lines(health.get("latest")),
    ]
    return "\n".join(lines) + "\n"


def _trace_health_console_trace_line(trace: dict[object, object]) -> str:
    """Render one trace row for plain console monitoring output."""

    trace_dir = trace.get("trace_dir", "unknown")
    kind = trace.get("kind", "unknown")
    status = trace.get("status", "unknown")
    line = f"- {trace_dir} ({kind}/{status})"
    replay_summary_path = trace.get("replay_summary_path")
    if isinstance(replay_summary_path, str):
        line += f" summary {replay_summary_path}"
    artifacts = _string_mapping(trace.get("report_artifacts"))
    if artifacts:
        rendered = "; ".join(f"{name}={path}" for name, path in artifacts.items())
        line += f" artifacts {rendered}"
    trace_health = _trace_health_summary_text(trace.get("trace_health_summary"))
    if trace_health:
        line += f" trace_health {trace_health}"
    return line


def _trace_health_count_lines(value: object) -> list[str]:
    counts = _int_mapping(value)
    if not counts:
        return ["- None"]
    return [f"- `{name}`: `{count}`" for name, count in counts.items()]


def _trace_health_attention_lines(value: object) -> list[str]:
    if not isinstance(value, list) or not value:
        return ["- None"]
    lines: list[str] = []
    for trace in value:
        if not isinstance(trace, dict):
            continue
        lines.append(_trace_health_trace_line(trace))
    return lines or ["- None"]


def _trace_health_latest_lines(value: object) -> list[str]:
    if not isinstance(value, list) or not value:
        return ["- None"]
    lines = [
        _trace_health_trace_line(trace) for trace in value if isinstance(trace, dict)
    ]
    return lines or ["- None"]


def _trace_health_trace_line(trace: dict[object, object]) -> str:
    trace_dir = trace.get("trace_dir", "unknown")
    report_path = trace.get("report_path", "none")
    kind = trace.get("kind", "unknown")
    status = trace.get("status", "unknown")
    line = f"- `{status}` `{kind}` trace `{trace_dir}` report `{report_path}`"
    replay_summary_path = trace.get("replay_summary_path")
    if isinstance(replay_summary_path, str):
        line += f" summary `{replay_summary_path}`"
    artifacts = _string_mapping(trace.get("report_artifacts"))
    if artifacts:
        rendered = "; ".join(f"{name}={path}" for name, path in artifacts.items())
        line += f" artifacts `{rendered}`"
    trace_health = _trace_health_summary_text(trace.get("trace_health_summary"))
    if trace_health:
        line += f" trace_health `{trace_health}`"
    return line


def _trace_health_summary_text(value: object) -> str:
    """Render only the compact fields needed when scanning trace-health rows."""

    if not isinstance(value, dict):
        return ""
    status = value.get("health_status")
    artifact_count = value.get("artifact_trace_count")
    parts: list[str] = []
    if isinstance(status, str):
        parts.append(f"status={status}")
    if isinstance(artifact_count, int):
        parts.append(f"artifacts={artifact_count}")
    return "; ".join(parts)


def _trace_health_exit_code(
    health: dict[str, object],
    fail_on_attention: bool,
) -> int:
    if fail_on_attention and health.get("health_status") == "attention":
        return 1
    return 0


def _analyze_failed_run(args: argparse.Namespace) -> int:
    analysis = analyze_failed_run_trace(args.trace_dir)
    write_failed_run_analysis(args.trace_dir, analysis)
    print(f"status: {analysis.status}")
    print(f"proposals: {len(analysis.proposals)}")
    print(f"diagnostic ready: {str(analysis.diagnostic_ready).lower()}")
    print(f"analysis: {args.trace_dir / 'failed-run-analysis.json'}")
    print(f"review: {args.trace_dir / 'failed-run-analysis.md'}")
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


def _read_goal_plan_action_log(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    events: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        if isinstance(event, dict):
            events.append(event)
    return events


def _goal_plan_replay_timeline_lines(
    events: list[dict[str, object]],
) -> list[str]:
    if not events:
        return []
    lines = ["timeline:"]
    for event in events:
        phase = event.get("phase") if isinstance(event.get("phase"), str) else "?"
        message = (
            event.get("message") if isinstance(event.get("message"), str) else "?"
        )
        lines.append(f"- {phase}: {message}{_goal_plan_replay_event_suffix(event)}")
    return lines


def _goal_plan_replay_event_suffix(event: dict[str, object]) -> str:
    metadata = event.get("metadata")
    if not isinstance(metadata, dict):
        return ""
    bits: list[str] = []
    phase = event.get("phase")
    if phase == "goal_plan":
        selected = metadata.get("selected_routine_id")
        candidate_count = metadata.get("candidate_count")
        if isinstance(selected, str):
            bits.append(f"selected {selected}")
        if isinstance(candidate_count, int):
            bits.append(f"candidates {candidate_count}")
        expected_evidence = metadata.get("expected_evidence")
        abort_conditions = metadata.get("abort_conditions")
        if isinstance(expected_evidence, list) and expected_evidence:
            bits.append(f"expected_evidence {len(expected_evidence)}")
        if isinstance(abort_conditions, list) and abort_conditions:
            bits.append(f"abort_conditions {len(abort_conditions)}")
    if phase == "model_assistance":
        provider = metadata.get("provider")
        model = metadata.get("model")
        status = metadata.get("status")
        affected = metadata.get("affected_selection")
        if isinstance(provider, str) and isinstance(model, str):
            bits.append(f"model {provider}/{model}")
        if isinstance(status, str):
            bits.append(f"status {status}")
        if isinstance(affected, bool):
            bits.append(f"affected_selection {affected}")
    return f" [{' '.join(bits)}]" if bits else ""


def _write_goal_plan_replay_summary(
    trace_dir: Path,
    plan: GoalPlan,
    report: dict[str, object],
    events: list[dict[str, object]],
) -> Path:
    summary_path = trace_dir / "replay-summary.md"
    summary_path.write_text(
        _goal_plan_replay_summary_markdown(trace_dir, plan, report, events),
        encoding="utf-8",
    )
    return summary_path


def _goal_plan_replay_summary_markdown(
    trace_dir: Path,
    plan: GoalPlan,
    report: dict[str, object],
    events: list[dict[str, object]],
) -> str:
    desktop_input_required = report.get("desktop_input_required")
    lines = [
        "# DeskPilot Goal Plan Replay Summary",
        "",
        f"- Trace: `{trace_dir}`",
        f"- Goal: `{plan.user_goal}`",
        f"- Intent: `{plan.normalized_intent}`",
        f"- Status: `{plan.execution_status}`",
        f"- Selected routine: `{plan.selected_routine_id or 'none'}`",
        f"- Candidates: `{len(plan.candidate_routines)}`",
        f"- Desktop input required: `{desktop_input_required}`",
    ]
    if plan.expected_evidence:
        lines.append(f"- Expected evidence: `{', '.join(plan.expected_evidence)}`")
    if plan.abort_conditions:
        lines.append(f"- Abort conditions: `{', '.join(plan.abort_conditions)}`")
    if plan.missing_inputs:
        lines.append(f"- Missing inputs: `{', '.join(plan.missing_inputs)}`")
    if plan.candidate_routines:
        lines.extend(["", "## Candidates", ""])
        for candidate in plan.candidate_routines:
            matched = ", ".join(candidate.matched_fields) or "none"
            lines.append(
                "- "
                f"`{candidate.routine_id}` score `{candidate.score:g}` "
                f"matched `{matched}` "
                f"safety `{candidate.safety_class}` "
                f"approval `{candidate.approval_policy}`",
            )
    if plan.model_ranking is not None:
        ranking = plan.model_ranking
        lines.extend(
            [
                "",
                "## Model Assistance",
                "",
                f"- Provider: `{ranking.provider}`",
                f"- Model: `{ranking.model}`",
                f"- Status: `{ranking.status}`",
                f"- Affected selection: `{ranking.affected_selection}`",
            ],
        )
    timeline = _goal_plan_replay_timeline_lines(events)
    if timeline:
        lines.extend(["", "## Timeline", ""])
        lines.extend(timeline[1:])
    return "\n".join(lines) + "\n"


def _write_proof_suite_replay_summary(
    trace_dir: Path,
    payload: dict[str, object],
) -> Path:
    summary_path = trace_dir / "replay-summary.md"
    summary_path.write_text(
        _proof_suite_replay_summary_markdown(trace_dir, payload),
        encoding="utf-8",
    )
    return summary_path


def _proof_suite_replay_summary_markdown(
    trace_dir: Path,
    payload: dict[str, object],
) -> str:
    lines = [
        "# DeskPilot Proof Suite Replay Summary",
        "",
        f"- Trace: `{trace_dir}`",
        f"- Status: `{payload.get('status', 'unknown')}`",
    ]
    gates = _string_mapping(payload.get("gates"))
    if gates:
        lines.extend(["", "## Gates", ""])
        lines.extend(f"- `{name}`: `{status}`" for name, status in gates.items())
    artifacts = _string_mapping(payload.get("artifacts"))
    if artifacts:
        lines.extend(["", "## Artifacts", ""])
        lines.extend(f"- `{name}`: `{path}`" for name, path in artifacts.items())
    errors = _string_list(payload.get("errors"))
    if errors:
        lines.extend(["", "## Errors", ""])
        lines.extend(f"- {error}" for error in errors)
    return "\n".join(lines) + "\n"


def _benchmark_replay_lines(payload: dict[str, object]) -> list[str]:
    lines = [
        f"schema: {payload.get('schema_version', 'unknown')}",
        f"generated_at: {payload.get('generated_at', 'unknown')}",
        f"iterations: {payload.get('iterations', 'unknown')}",
        f"trace_health: {payload.get('trace_health_path', 'unknown')}",
        f"acceptance: {_benchmark_acceptance_status(payload)}",
        f"baseline: {_benchmark_baseline_status(payload)}",
        f"monitoring coverage: {_benchmark_replay_monitoring_status(payload)}",
    ]
    trace_health_summary = payload.get("trace_health_summary")
    if isinstance(trace_health_summary, dict):
        lines.extend(
            [
                "trace_health_status: "
                f"{trace_health_summary.get('health_status', 'unknown')}",
                "trace_health_artifact_traces: "
                f"{trace_health_summary.get('artifact_trace_count', 0)}",
            ],
        )
    summary = payload.get("summary")
    if isinstance(summary, dict):
        for key in (
            "success_rate",
            "grounding_accuracy",
            "ambiguity_rate",
            "recovery_rate",
            "operator_intervention_rate",
        ):
            if key in summary:
                lines.append(f"{key}: {summary[key]}")
    contract = payload.get("observability_contract")
    if isinstance(contract, dict):
        lines.extend(
            [
                f"pipeline_modes: {_string_list_value(contract.get('pipeline_modes'))}",
                "deep_search_sources: "
                f"{_string_list_value(contract.get('deep_search_sources'))}",
            ],
        )
    coverage = payload.get("monitoring_coverage")
    if isinstance(coverage, dict):
        lines.extend(
            [
                "observed_trace_phases: "
                f"{_string_list_value(coverage.get('observed_trace_phases'))}",
                "missing_trace_phases: "
                f"{_string_list_value(coverage.get('missing_trace_phases'))}",
                "observed_report_fields: "
                f"{_string_list_value(coverage.get('observed_report_fields'))}",
                "missing_report_fields: "
                f"{_string_list_value(coverage.get('missing_report_fields'))}",
            ],
        )
    artifacts = _string_mapping(payload.get("report_artifacts"))
    if artifacts:
        lines.append("artifacts:")
        for name, path in artifacts.items():
            lines.append(f"- {name}: {path}")
    runs = payload.get("runs")
    if isinstance(runs, list) and runs:
        lines.append("runs:")
        for run in runs:
            if isinstance(run, dict):
                lines.append(f"- {_benchmark_run_line(run)}")
    return lines


def _benchmark_acceptance_status(payload: dict[str, object]) -> str:
    acceptance = payload.get("acceptance")
    if isinstance(acceptance, dict):
        status = acceptance.get("status")
        if isinstance(status, str):
            return status
    return "unknown"


def _benchmark_baseline_status(payload: dict[str, object]) -> str:
    baseline = payload.get("baseline_comparison")
    if isinstance(baseline, dict):
        status = baseline.get("status")
        if isinstance(status, str):
            return status
    return "unknown"


def _benchmark_replay_monitoring_status(payload: dict[str, object]) -> str:
    coverage = payload.get("monitoring_coverage")
    if isinstance(coverage, dict):
        return _benchmark_monitoring_status(coverage)
    return "not_configured"


def _benchmark_run_line(run: dict[object, object]) -> str:
    iteration = run.get("iteration", "?")
    status = run.get("status", "unknown")
    trace_dir = run.get("trace_dir", "none")
    task_time = run.get("task_time_seconds", "unknown")
    step_count = run.get("step_count", "unknown")
    action_count = run.get("action_count", "unknown")
    return (
        f"run {iteration}: {status} trace={trace_dir} "
        f"time={task_time}s steps={step_count} actions={action_count}"
    )


def _write_benchmark_replay_summary(
    trace_dir: Path,
    payload: dict[str, object],
) -> Path:
    summary_path = trace_dir / "replay-summary.md"
    summary_path.write_text(
        _benchmark_replay_summary_markdown(trace_dir, payload),
        encoding="utf-8",
    )
    return summary_path


def _benchmark_replay_summary_markdown(
    trace_dir: Path,
    payload: dict[str, object],
) -> str:
    lines = [
        "# DeskPilot Benchmark Replay Summary",
        "",
        f"- Trace: `{trace_dir}`",
        f"- Schema: `{payload.get('schema_version', 'unknown')}`",
        f"- Generated at: `{payload.get('generated_at', 'unknown')}`",
        f"- Task: `{payload.get('task_path', 'unknown')}`",
        f"- Status: `{_benchmark_acceptance_status(payload)}`",
        f"- Baseline: `{_benchmark_baseline_status(payload)}`",
        f"- Monitoring coverage: `{_benchmark_replay_monitoring_status(payload)}`",
        f"- Trace health: `{payload.get('trace_health_path', 'unknown')}`",
        *_benchmark_replay_trace_health_summary_lines(
            payload.get("trace_health_summary"),
        ),
        "",
        "## Observability Contract",
        "",
        *_benchmark_contract_summary_lines(payload.get("observability_contract")),
        "",
        "## Monitoring Coverage",
        "",
        *_benchmark_monitoring_summary_lines(payload.get("monitoring_coverage")),
        "",
        "## Report Artifacts",
        "",
        *_benchmark_replay_artifact_lines(payload.get("report_artifacts")),
        "",
        "## Runs",
        "",
        *_benchmark_run_summary_lines(payload.get("runs")),
    ]
    return "\n".join(lines) + "\n"


def _benchmark_contract_summary_lines(value: object) -> list[str]:
    if not isinstance(value, dict) or value.get("configured") is not True:
        return ["- Configured: `false`"]
    return [
        f"- Benchmark task: `{value.get('benchmark_task_id', 'unknown')}`",
        f"- Pipeline modes: `{_string_list_value(value.get('pipeline_modes'))}`",
        "- Deep-search sources: "
        f"`{_string_list_value(value.get('deep_search_sources'))}`",
        "- Required trace phases: "
        f"`{_string_list_value(value.get('required_trace_phases'))}`",
        "- Required report fields: "
        f"`{_string_list_value(value.get('required_report_fields'))}`",
        f"- Required metrics: `{_string_list_value(value.get('required_metrics'))}`",
    ]


def _benchmark_replay_trace_health_summary_lines(value: object) -> list[str]:
    if not isinstance(value, dict):
        return []
    return [
        f"- Trace health status: `{value.get('health_status', 'unknown')}`",
        f"- Trace health artifacts: `{value.get('artifact_trace_count', 0)}`",
    ]


def _benchmark_monitoring_summary_lines(value: object) -> list[str]:
    if not isinstance(value, dict) or value.get("configured") is not True:
        return ["- Configured: `false`"]
    return [
        f"- Passed: `{value.get('passed', False)}`",
        "- Observed trace phases: "
        f"`{_string_list_value(value.get('observed_trace_phases'))}`",
        "- Missing trace phases: "
        f"`{_string_list_value(value.get('missing_trace_phases'))}`",
        "- Observed report fields: "
        f"`{_string_list_value(value.get('observed_report_fields'))}`",
        "- Missing report fields: "
        f"`{_string_list_value(value.get('missing_report_fields'))}`",
    ]


def _benchmark_replay_artifact_lines(value: object) -> list[str]:
    artifacts = _string_mapping(value)
    if not artifacts:
        return ["- None"]
    return [f"- `{name}`: `{path}`" for name, path in artifacts.items()]


def _benchmark_run_summary_lines(value: object) -> list[str]:
    if not isinstance(value, list) or not value:
        return ["- No benchmark runs recorded."]
    lines = []
    for run in value:
        if isinstance(run, dict):
            lines.append(f"- `{_benchmark_run_line(run)}`")
    return lines or ["- No benchmark runs recorded."]


def _string_mapping(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {
        key: item
        for key, item in value.items()
        if isinstance(key, str) and isinstance(item, str)
    }


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _string_list_value(value: object) -> str:
    items = _string_list(value)
    return ", ".join(items) if items else "none"


def _int_mapping(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {
        key: item
        for key, item in value.items()
        if isinstance(key, str) and isinstance(item, int)
    }


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
    if metadata.get("post_refocus_verification_passed") is True:
        details.append("focus recovered")
    elif metadata.get("focus_recovery_attempted") is True:
        details.append("focus recovery failed")
    if not details:
        return ""
    return " [" + "; ".join(details) + "]"


def _write_replay_summary(trace_dir: Path, report: dict[str, object]) -> Path:
    summary_path = trace_dir / "replay-summary.md"
    summary_path.write_text(
        _replay_summary_markdown(trace_dir, report),
        encoding="utf-8",
    )
    return summary_path


def _replay_summary_markdown(trace_dir: Path, report: dict[str, object]) -> str:
    lines = [
        "# DeskPilot Replay Summary",
        "",
        f"- Trace: `{trace_dir}`",
        f"- Task: `{report.get('task_name', 'unknown')}`",
        f"- Status: `{report.get('status', 'unknown')}`",
    ]
    abort_reason = report.get("abort_reason")
    if abort_reason:
        lines.append(f"- Reason: `{abort_reason}`")
    lines.extend(["", "## Timeline"])
    timeline = _replay_timeline_lines(report)
    if timeline:
        lines.extend(timeline[1:])
    else:
        lines.append("- No step timeline available.")
    lines.extend(["", "## Evidence"])
    evidence_lines = _replay_evidence_lines(report)
    step_evidence_lines = _replay_step_evidence_lines(report)
    if evidence_lines or step_evidence_lines:
        lines.extend(evidence_lines)
        lines.extend(step_evidence_lines)
    else:
        lines.append("- No screenshot or state-delta evidence found.")
    return "\n".join(lines) + "\n"


def _replay_evidence_lines(report: dict[str, object]) -> list[str]:
    events = report.get("events")
    if not isinstance(events, list):
        return []
    lines: list[str] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        metadata = event.get("metadata")
        if not isinstance(metadata, dict):
            continue
        raw_phase = event.get("phase")
        phase = raw_phase if isinstance(raw_phase, str) else "event"
        _append_evidence_bundle(lines, phase, metadata, "pre_action_evidence")
        _append_evidence_bundle(lines, phase, metadata, "post_action_evidence")
        if phase == "state_delta":
            _append_state_delta_lines(lines, metadata)
    return lines


def _append_evidence_bundle(
    lines: list[str],
    phase: str,
    metadata: dict[object, object],
    key: str,
) -> None:
    bundle = metadata.get(key)
    if not isinstance(bundle, dict):
        return
    screenshot_path = bundle.get("screenshot_path")
    active_window_title = bundle.get("active_window_title")
    lines.append(f"- `{phase}` `{key}`")
    if isinstance(screenshot_path, str):
        lines.append(f"  - Screenshot: `{screenshot_path}`")
    if isinstance(active_window_title, str):
        lines.append(f"  - Active window: `{active_window_title}`")


def _append_state_delta_lines(
    lines: list[str],
    metadata: dict[object, object],
) -> None:
    lines.append("- `state_delta` changes")
    for key, label in (
        ("visible_text_added", "Visible text added"),
        ("visible_text_removed", "Visible text removed"),
        ("target_appeared", "Target appeared"),
        ("target_disappeared", "Target disappeared"),
        ("scroll_moved", "Scroll moved"),
    ):
        value = metadata.get(key)
        if value not in (None, [], False):
            lines.append(f"  - {label}: `{value}`")


def _replay_step_evidence_lines(report: dict[str, object]) -> list[str]:
    steps = report.get("steps")
    if not isinstance(steps, list):
        return []
    lines: list[str] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        metadata = step.get("metadata")
        if not isinstance(metadata, dict):
            continue
        raw_step_id = step.get("step_id")
        step_id = raw_step_id if isinstance(raw_step_id, str) else "?"
        for key in ("success_evidence", "failure_evidence"):
            evidence = metadata.get(key)
            if isinstance(evidence, dict):
                _append_step_evidence_lines(lines, step_id, key, evidence)
    return lines


def _append_step_evidence_lines(
    lines: list[str],
    step_id: str,
    key: str,
    evidence: dict[object, object],
) -> None:
    lines.append(f"- step `{step_id}` `{key}`")
    for field, label in (
        ("success_evidence_type", "Success evidence type"),
        ("failure_evidence_type", "Failure evidence type"),
        ("action_message", "Action message"),
        ("verification_outcome", "Verification outcome"),
        ("before_active_window_title", "Before active window"),
        ("before_focused_element", "Before focused element"),
        ("scroll_moved", "Scroll moved"),
    ):
        value = evidence.get(field)
        if value not in (None, [], False):
            lines.append(f"  - {label}: `{value}`")
    post_action = evidence.get("post_action_evidence")
    if isinstance(post_action, dict):
        screenshot_path = post_action.get("screenshot_path")
        active_window_title = post_action.get("active_window_title")
        if isinstance(screenshot_path, str):
            lines.append(f"  - Post screenshot: `{screenshot_path}`")
        if isinstance(active_window_title, str):
            lines.append(f"  - Post active window: `{active_window_title}`")
    state_delta = evidence.get("state_delta")
    if isinstance(state_delta, dict):
        _append_state_delta_lines(lines, state_delta)


def _proof(args: argparse.Namespace) -> int:
    if args.proof_command == "replay":
        return _proof_replay(args)
    if args.proof_command == "preflight":
        return _proof_preflight(args)
    if args.proof_command == "validate-review":
        return _proof_validate_review(args)
    if args.proof_command == "validate":
        return _proof_validate(args)
    if args.proof_command == "validate-suite":
        return _proof_validate_suite(args)
    if args.proof_command == "promote-suite":
        return _proof_promote_suite(args)
    if args.proof_command == "finalize-suite":
        return _proof_finalize_suite(args)
    if args.proof_command == "verify-promotion":
        return _proof_verify_promotion(args)
    if args.proof_command == "verify-archive":
        return _proof_verify_archive(args)
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


def _proof_preflight(args: argparse.Namespace) -> int:
    result = run_proof_preflight(
        args.trace_root,
        require_windows=not args.allow_non_windows,
        require_video=args.video_policy != "disabled",
        ffmpeg_path=args.ffmpeg_path,
    )
    print(f"trace_root: {args.trace_root}")
    print(f"preflight: {'passed' if result.passed else 'failed'}")
    for check in result.checks:
        print(f"check {check.name}: {check.status} - {check.message}")
    if args.write_report or args.report_path:
        report_path = write_proof_preflight_report(result, args.report_path)
        print(f"report: {report_path}")
    return 0 if result.passed else 1


def _proof_validate_review(args: argparse.Namespace) -> int:
    result = validate_proof_review(args.review_path)
    print(f"review: {args.review_path}")
    print(f"review_validation: {'passed' if result.passed else 'failed'}")
    if result.decision:
        print(f"decision: {result.decision}")
    print(f"checked: {result.checked_count}")
    for item in result.unchecked_items:
        print(f"unchecked: {item}")
    for warning in result.warnings:
        print(f"warning: {warning}")
    for error in result.errors:
        print(f"error: {error}")
    if args.write_status_json or args.status_json_path:
        status_path = write_proof_review_status(result, args.status_json_path)
        print(f"status_json: {status_path}")
    return 0 if result.passed else 1


def _proof_validate(args: argparse.Namespace) -> int:
    result = validate_proof_bundle(
        args.trace_dir,
        require_video=not args.allow_missing_video,
    )
    print(f"trace: {args.trace_dir}")
    print(f"validation: {'passed' if result.passed else 'failed'}")
    for label, path in result.artifact_paths:
        print(f"artifact {label}: {path}")
    for warning in result.warnings:
        print(f"warning: {warning}")
    for error in result.errors:
        print(f"error: {error}")
    return 0 if result.passed else 1


def _proof_validate_suite(args: argparse.Namespace) -> int:
    result = validate_proof_suite(
        args.trace_root,
        require_video=not args.allow_missing_video,
        require_preflight=args.require_preflight,
        require_review=args.require_review,
    )
    print(f"trace_root: {args.trace_root}")
    print(f"suite: {'passed' if result.passed else 'failed'}")
    print(f"expected: {', '.join(result.expected_proofs)}")
    for warning in result.warnings:
        print(f"warning: {warning}")
    for duplicate in result.duplicate_proofs:
        print(f"warning: duplicate proof bundle: {duplicate}")
    for bundle in result.bundle_results:
        proof_name = bundle.proof_name or str(bundle.trace_dir)
        print(
            f"proof {proof_name}: {'passed' if bundle.passed else 'failed'} "
            f"({bundle.trace_dir})",
        )
        for warning in bundle.warnings:
            print(f"warning: {proof_name}: {warning}")
    for error in result.errors:
        print(f"error: {error}")
    if args.write_report or args.report_path:
        report_path = write_proof_suite_report(result, args.report_path)
        print(f"report: {report_path}")
    if args.write_status_json or args.status_json_path:
        status_path = write_proof_suite_status(result, args.status_json_path)
        print(f"status_json: {status_path}")
    if args.write_runbook or args.runbook_path:
        runbook_path = write_proof_suite_runbook(
            result,
            args.runbook_path,
            require_video=not args.allow_missing_video,
        )
        print(f"runbook: {runbook_path}")
    if args.write_archive or args.archive_path:
        archive_path = write_proof_suite_archive(
            result,
            args.archive_path,
            require_video=not args.allow_missing_video,
        )
        print(f"archive: {archive_path}")
    if args.write_review_template or args.review_template_path:
        review_path = write_proof_suite_review_template(
            result,
            args.review_template_path,
        )
        print(f"review_template: {review_path}")
    return 0 if result.passed else 1


def _proof_promote_suite(args: argparse.Namespace) -> int:
    require_video = not args.allow_missing_video
    result = validate_proof_suite(
        args.trace_root,
        require_video=require_video,
        require_preflight=True,
        require_review=True,
    )
    print(f"trace_root: {args.trace_root}")
    print(f"promotion: {'passed' if result.passed else 'failed'}")
    for warning in result.warnings:
        print(f"warning: {warning}")
    for duplicate in result.duplicate_proofs:
        print(f"warning: duplicate proof bundle: {duplicate}")
    for bundle in result.bundle_results:
        proof_name = bundle.proof_name or str(bundle.trace_dir)
        print(
            f"proof {proof_name}: {'passed' if bundle.passed else 'failed'} "
            f"({bundle.trace_dir})",
        )
        for warning in bundle.warnings:
            print(f"warning: {proof_name}: {warning}")
    for error in result.errors:
        print(f"error: {error}")

    promotion_path = write_proof_suite_promotion(
        result,
        args.promotion_path,
        require_video=require_video,
    )
    print(f"promotion_json: {promotion_path}")
    if args.write_report:
        report_path = write_proof_suite_report(result)
        print(f"report: {report_path}")
    if args.write_status_json:
        status_path = write_proof_suite_status(result)
        print(f"status_json: {status_path}")
    if args.write_runbook:
        runbook_path = write_proof_suite_runbook(
            result,
            require_video=require_video,
        )
        print(f"runbook: {runbook_path}")
    if args.write_archive:
        archive_path = write_proof_suite_archive(result, require_video=require_video)
        print(f"archive: {archive_path}")
    return 0 if result.passed else 1


def _proof_finalize_suite(args: argparse.Namespace) -> int:
    require_video = not args.allow_missing_video
    result = validate_proof_suite(
        args.trace_root,
        require_video=require_video,
        require_preflight=True,
        require_review=True,
    )
    print(f"trace_root: {args.trace_root}")
    print(f"suite: {'passed' if result.passed else 'failed'}")
    for warning in result.warnings:
        print(f"warning: {warning}")
    for duplicate in result.duplicate_proofs:
        print(f"warning: duplicate proof bundle: {duplicate}")
    for bundle in result.bundle_results:
        proof_name = bundle.proof_name or str(bundle.trace_dir)
        print(
            f"proof {proof_name}: {'passed' if bundle.passed else 'failed'} "
            f"({bundle.trace_dir})",
        )
        for warning in bundle.warnings:
            print(f"warning: {proof_name}: {warning}")
    for error in result.errors:
        print(f"error: {error}")

    report_path = write_proof_suite_report(result)
    status_path = write_proof_suite_status(result)
    runbook_path = write_proof_suite_runbook(result, require_video=require_video)
    promotion_path = write_proof_suite_promotion(result, require_video=require_video)
    promotion_verification = verify_proof_suite_promotion(promotion_path)
    promotion_verification_path = write_proof_promotion_verification(
        promotion_verification,
    )
    archive_path = write_proof_suite_archive(result, require_video=require_video)
    archive_verification = verify_proof_suite_archive(archive_path)
    archive_verification_path = write_proof_archive_verification(
        archive_verification,
    )
    finalization_status_path = write_proof_finalization_status(
        result,
        promotion_verification,
        archive_verification,
        artifact_paths={
            "suite_report": report_path,
            "suite_status": status_path,
            "suite_runbook": runbook_path,
            "promotion": promotion_path,
            "promotion_verification": promotion_verification_path,
            "archive": archive_path,
            "archive_verification": archive_verification_path,
        },
    )

    print(f"report: {report_path}")
    print(f"status_json: {status_path}")
    print(f"runbook: {runbook_path}")
    print(f"promotion_json: {promotion_path}")
    print(
        "promotion_verification: "
        f"{'passed' if promotion_verification.passed else 'failed'}",
    )
    print(f"promotion_verification_json: {promotion_verification_path}")
    print(f"archive: {archive_path}")
    print(
        "archive_verification: "
        f"{'passed' if archive_verification.passed else 'failed'}",
    )
    print(f"archive_verification_json: {archive_verification_path}")
    print(f"finalization_status_json: {finalization_status_path}")
    for error in promotion_verification.errors:
        print(f"error: promotion verification: {error}")
    for error in archive_verification.errors:
        print(f"error: archive verification: {error}")
    passed = result.passed and promotion_verification.passed
    return 0 if passed and archive_verification.passed else 1


def _proof_verify_promotion(args: argparse.Namespace) -> int:
    result = verify_proof_suite_promotion(args.promotion_path)
    print(f"promotion_json: {args.promotion_path}")
    print(f"promotion_verification: {'passed' if result.passed else 'failed'}")
    print(f"checked_artifacts: {len(result.checked_artifacts)}")
    for artifact_name in result.checked_artifacts:
        print(f"artifact: {artifact_name}")
    for warning in result.warnings:
        print(f"warning: {warning}")
    for error in result.errors:
        print(f"error: {error}")
    if args.write_status_json or args.status_json_path:
        status_path = write_proof_promotion_verification(
            result,
            args.status_json_path,
        )
        print(f"status_json: {status_path}")
    return 0 if result.passed else 1


def _proof_verify_archive(args: argparse.Namespace) -> int:
    result = verify_proof_suite_archive(args.archive_path)
    print(f"archive: {args.archive_path}")
    print(f"archive_verification: {'passed' if result.passed else 'failed'}")
    print(f"checked_artifacts: {len(result.checked_artifacts)}")
    for artifact_name in result.checked_artifacts:
        print(f"artifact: {artifact_name}")
    for warning in result.warnings:
        print(f"warning: {warning}")
    for error in result.errors:
        print(f"error: {error}")
    if args.write_status_json or args.status_json_path:
        status_path = write_proof_archive_verification(
            result,
            args.status_json_path,
        )
        print(f"status_json: {status_path}")
    return 0 if result.passed else 1


def _proof_browser_fixture(args: argparse.Namespace) -> int:
    report = run_browser_fixture(
        trace_root=args.trace_root,
        random_seed=args.random_seed,
        movement_smoothness=args.movement_smoothness,
        countdown_seconds=args.countdown_seconds,
        fixture_text=args.fixture_text,
        result_text=args.result_text,
        page_load_seconds=args.page_load_seconds,
        record_video=_video_recording_enabled(args),
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
        record_video=_video_recording_enabled(args),
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
        record_video=_video_recording_enabled(args),
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
        record_video=_video_recording_enabled(args),
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
