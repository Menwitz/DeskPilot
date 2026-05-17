"""Native operator app shell structure and optional PySide6 launcher."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any

from desktop_agent.config import RuntimeConfig
from desktop_agent.failed_run_analyzer import FailedRunAnalysis


class OperatorAppUnavailableError(RuntimeError):
    """Raised when the optional native UI dependency is not installed."""


@dataclass(frozen=True)
class OperatorAppPage:
    """One top-level page in the local operator app shell."""

    page_id: str
    title: str
    purpose: str
    panel_ids: tuple[str, ...] = ()

    def metadata(self) -> dict[str, object]:
        return {
            "page_id": self.page_id,
            "title": self.title,
            "purpose": self.purpose,
            "panel_ids": list(self.panel_ids),
        }


@dataclass(frozen=True)
class OperatorAppShell:
    """Static shell contract shared by the app UI and tests."""

    title: str
    pages: tuple[OperatorAppPage, ...]
    default_page_id: str

    def metadata(self) -> dict[str, object]:
        return {
            "title": self.title,
            "default_page_id": self.default_page_id,
            "pages": [page.metadata() for page in self.pages],
        }


@dataclass(frozen=True)
class LiveRunPanelState:
    """Live run panel fields shown by the operator app."""

    run_id: str | None = None
    current_routine_id: str | None = None
    current_step_id: str | None = None
    screenshot_path: Path | None = None
    selected_target: str | None = None
    next_action: str | None = None
    elapsed_seconds: float = 0.0
    status: str = "idle"
    stop_controls: tuple[str, ...] = (
        "pause",
        "resume",
        "cancel",
        "emergency_stop",
    )

    def metadata(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "current_routine_id": self.current_routine_id,
            "current_step_id": self.current_step_id,
            "screenshot_path": (
                str(self.screenshot_path) if self.screenshot_path else None
            ),
            "selected_target": self.selected_target,
            "next_action": self.next_action,
            "elapsed_seconds": self.elapsed_seconds,
            "status": self.status,
            "stop_controls": list(self.stop_controls),
        }


@dataclass(frozen=True)
class TraceHealthPanelState:
    """Dashboard trace health fields for local monitoring."""

    trace_count: int = 0
    attention_count: int = 0
    artifact_count: int = 0
    warning_trace_count: int = 0
    kind_counts: tuple[tuple[str, int], ...] = ()
    status_counts: tuple[tuple[str, int], ...] = ()
    status: str = "empty"
    schema_version: str | None = None
    generated_at: str | None = None
    benchmark_health_status: str | None = None
    benchmark_artifact_count: int | None = None
    proof_expected_count: int | None = None
    proof_artifact_count: int | None = None
    proof_error_count: int | None = None
    proof_warning_count: int | None = None

    def metadata(self) -> dict[str, object]:
        return {
            "trace_count": self.trace_count,
            "attention_count": self.attention_count,
            "artifact_count": self.artifact_count,
            "warning_trace_count": self.warning_trace_count,
            "kind_counts": dict(self.kind_counts),
            "status_counts": dict(self.status_counts),
            "status": self.status,
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "benchmark_health_status": self.benchmark_health_status,
            "benchmark_artifact_count": self.benchmark_artifact_count,
            "proof_expected_count": self.proof_expected_count,
            "proof_artifact_count": self.proof_artifact_count,
            "proof_error_count": self.proof_error_count,
            "proof_warning_count": self.proof_warning_count,
        }


@dataclass(frozen=True)
class ApprovalDialogState:
    """Approval dialog fields shown before high-risk local actions continue."""

    routine_id: str
    step_id: str
    risk_class: str
    checkpoint_evidence: str
    content_fingerprint: str
    status: str = "pending"
    approver: str | None = None
    reason: str | None = None
    decided_at: str | None = None
    actions: tuple[str, ...] = ("approve", "deny")

    def metadata(self) -> dict[str, object]:
        return {
            "routine_id": self.routine_id,
            "step_id": self.step_id,
            "risk_class": self.risk_class,
            "checkpoint_evidence": self.checkpoint_evidence,
            "content_fingerprint": self.content_fingerprint,
            "status": self.status,
            "approver": self.approver,
            "reason": self.reason,
            "decided_at": self.decided_at,
            "actions": list(self.actions),
        }


@dataclass(frozen=True)
class RecorderReviewPanelState:
    """Recorder review fields shown before saving generated YAML."""

    generated_yaml: str
    selected_targets: tuple[str, ...] = ()
    screenshot_paths: tuple[Path, ...] = ()
    verification_suggestions: tuple[str, ...] = ()
    status: str = "draft"

    def metadata(self) -> dict[str, object]:
        return {
            "generated_yaml": self.generated_yaml,
            "selected_targets": list(self.selected_targets),
            "screenshot_paths": [str(path) for path in self.screenshot_paths],
            "verification_suggestions": list(self.verification_suggestions),
            "status": self.status,
        }


@dataclass(frozen=True)
class TraceViewerTimelineState:
    """Trace viewer timeline fields for reviewing local evidence."""

    trace_kind: str = "run"
    video_path: Path | None = None
    screenshot_paths: tuple[Path, ...] = ()
    action_log_path: Path | None = None
    candidate_reasoning: tuple[str, ...] = ()
    state_delta: tuple[str, ...] = ()
    verification_results: tuple[str, ...] = ()
    proof_gates: tuple[str, ...] = ()
    final_report_path: Path | None = None
    status: str = "empty"

    def metadata(self) -> dict[str, object]:
        return {
            "trace_kind": self.trace_kind,
            "video_path": str(self.video_path) if self.video_path else None,
            "screenshot_paths": [str(path) for path in self.screenshot_paths],
            "action_log_path": (
                str(self.action_log_path) if self.action_log_path else None
            ),
            "candidate_reasoning": list(self.candidate_reasoning),
            "state_delta": list(self.state_delta),
            "verification_results": list(self.verification_results),
            "proof_gates": list(self.proof_gates),
            "final_report_path": (
                str(self.final_report_path) if self.final_report_path else None
            ),
            "status": self.status,
        }


@dataclass(frozen=True)
class RoutinePackManagerState:
    """Routine-pack install and removal fields shown in the operator app."""

    installed_pack_ids: tuple[str, ...] = ()
    selected_pack_id: str | None = None
    install_source_path: Path | None = None
    pending_action: str | None = None
    trust_warnings: tuple[str, ...] = ()
    status: str = "idle"
    actions: tuple[str, ...] = ("install", "replace", "remove", "export")

    def metadata(self) -> dict[str, object]:
        return {
            "installed_pack_ids": list(self.installed_pack_ids),
            "selected_pack_id": self.selected_pack_id,
            "install_source_path": (
                str(self.install_source_path) if self.install_source_path else None
            ),
            "pending_action": self.pending_action,
            "trust_warnings": list(self.trust_warnings),
            "status": self.status,
            "actions": list(self.actions),
        }


@dataclass(frozen=True)
class FailureAnalysisProposalState:
    """One review-only failed-run proposal shown in the operator app."""

    step_id: str
    proposal_type: str
    rationale: str
    yaml_snippet: str
    review_required: bool = True
    applies_automatically: bool = False

    def metadata(self) -> dict[str, object]:
        return {
            "step_id": self.step_id,
            "proposal_type": self.proposal_type,
            "rationale": self.rationale,
            "yaml_snippet": self.yaml_snippet,
            "review_required": self.review_required,
            "applies_automatically": self.applies_automatically,
        }


@dataclass(frozen=True)
class FailureAnalysisReviewPanelState:
    """Failed-run analysis review fields shown in the trace viewer."""

    trace_dir: Path | None = None
    analysis_json_path: Path | None = None
    analysis_markdown_path: Path | None = None
    proposals: tuple[FailureAnalysisProposalState, ...] = ()
    status: str = "empty"

    def metadata(self) -> dict[str, object]:
        return {
            "trace_dir": str(self.trace_dir) if self.trace_dir else None,
            "analysis_json_path": (
                str(self.analysis_json_path) if self.analysis_json_path else None
            ),
            "analysis_markdown_path": (
                str(self.analysis_markdown_path)
                if self.analysis_markdown_path
                else None
            ),
            "proposal_count": len(self.proposals),
            "proposals": [proposal.metadata() for proposal in self.proposals],
            "status": self.status,
        }


@dataclass(frozen=True)
class SettingsPanelState:
    """Settings panel fields exposed by the operator app."""

    trace_root: Path = Path("traces")
    screenshots_enabled: bool = True
    video_capture_enabled: bool = False
    ollama_enabled: bool = False
    emergency_hotkey: str = "ctrl+alt+esc"
    default_activity_profile: str | None = None
    proof_mode: bool = False

    def metadata(self) -> dict[str, object]:
        return {
            "trace_root": str(self.trace_root),
            "screenshots_enabled": self.screenshots_enabled,
            "video_capture_enabled": self.video_capture_enabled,
            "ollama_enabled": self.ollama_enabled,
            "emergency_hotkey": self.emergency_hotkey,
            "default_activity_profile": self.default_activity_profile,
            "proof_mode": self.proof_mode,
        }


def operator_app_shell_spec() -> OperatorAppShell:
    """Return the Phase 8 native app shell page contract."""
    pages = (
        OperatorAppPage(
            page_id="dashboard",
            title="Dashboard",
            purpose="Daily status, recent runs, and next safe action.",
            panel_ids=("live_run", "trace_health"),
        ),
        OperatorAppPage(
            page_id="routine_library",
            title="Routine Library",
            purpose="List, search, inspect, dry-run, and run routines.",
        ),
        OperatorAppPage(
            page_id="routine_packs",
            title="Routine Packs",
            purpose="Install, replace, export, and remove local routine packs.",
            panel_ids=("routine_pack_manager",),
        ),
        OperatorAppPage(
            page_id="record",
            title="Record",
            purpose="Capture a demonstrated routine and review generated YAML.",
            panel_ids=("recorder_review",),
        ),
        OperatorAppPage(
            page_id="run_queue",
            title="Run Queue",
            purpose="Monitor scheduled, running, paused, and blocked routines.",
        ),
        OperatorAppPage(
            page_id="approvals",
            title="Approvals",
            purpose="Review high-risk steps before local execution continues.",
            panel_ids=("approval_dialog",),
        ),
        OperatorAppPage(
            page_id="trace_viewer",
            title="Trace Viewer",
            purpose="Inspect screenshots, action logs, evidence, and reports.",
            panel_ids=("trace_timeline", "failure_analysis_review"),
        ),
        OperatorAppPage(
            page_id="settings",
            title="Settings",
            purpose="Configure local trace, safety, model, and proof options.",
            panel_ids=("settings",),
        ),
        OperatorAppPage(
            page_id="help",
            title="Help",
            purpose="Show local guidance, safety boundaries, and diagnostics.",
        ),
    )
    return OperatorAppShell(
        title="DeskPilot Operator",
        pages=pages,
        default_page_id="dashboard",
    )


def default_live_run_panel_state() -> LiveRunPanelState:
    """Return an idle live-run panel state for app startup."""
    return LiveRunPanelState()


def render_live_run_panel_text(state: LiveRunPanelState | None = None) -> str:
    """Render live-run status for CLI diagnostics and tests."""
    active_state = state or default_live_run_panel_state()
    screenshot = (
        str(active_state.screenshot_path)
        if active_state.screenshot_path is not None
        else "none"
    )
    return "\n".join(
        [
            "Live Run",
            f"- Run ID: {active_state.run_id or 'none'}",
            f"- Status: {active_state.status}",
            f"- Current routine: {active_state.current_routine_id or 'none'}",
            f"- Current step: {active_state.current_step_id or 'none'}",
            f"- Screenshot preview: {screenshot}",
            f"- Selected target: {active_state.selected_target or 'none'}",
            f"- Next action: {active_state.next_action or 'none'}",
            f"- Elapsed seconds: {active_state.elapsed_seconds:g}",
            f"- Stop controls: {', '.join(active_state.stop_controls)}",
        ],
    ) + "\n"


def trace_health_panel_from_metadata(
    payload: Mapping[str, object],
) -> TraceHealthPanelState:
    """Create dashboard trace-health state from trace service metadata."""

    trace_count = payload.get("trace_count")
    artifact_trace_count = payload.get("artifact_trace_count")
    warning_trace_count = payload.get("warning_trace_count")
    health_status = payload.get("health_status")
    attention_traces = payload.get("attention_traces")
    schema_version = payload.get("schema_version")
    generated_at = payload.get("generated_at")
    benchmark_status, benchmark_artifacts = _benchmark_trace_health(payload)
    (
        proof_expected,
        proof_artifacts,
        proof_errors,
        proof_warnings,
    ) = _proof_trace_summary(payload)
    return TraceHealthPanelState(
        trace_count=_summary_int_or_none(trace_count) or 0,
        artifact_count=_summary_int_or_none(artifact_trace_count) or 0,
        warning_trace_count=_summary_int_or_none(warning_trace_count) or 0,
        attention_count=len(attention_traces)
        if isinstance(attention_traces, list)
        else 0,
        kind_counts=_count_pairs(payload.get("by_kind")),
        status_counts=_count_pairs(payload.get("by_status")),
        status=health_status if isinstance(health_status, str) else "loaded",
        schema_version=schema_version if isinstance(schema_version, str) else None,
        generated_at=generated_at if isinstance(generated_at, str) else None,
        benchmark_health_status=benchmark_status,
        benchmark_artifact_count=benchmark_artifacts,
        proof_expected_count=proof_expected,
        proof_artifact_count=proof_artifacts,
        proof_error_count=proof_errors,
        proof_warning_count=proof_warnings,
    )


def render_trace_health_panel_text(state: TraceHealthPanelState) -> str:
    """Render trace health counts for diagnostics and app tests."""

    benchmark_artifacts = (
        state.benchmark_artifact_count
        if state.benchmark_artifact_count is not None
        else "unknown"
    )
    proof_expected = (
        state.proof_expected_count
        if state.proof_expected_count is not None
        else "unknown"
    )
    proof_artifacts = (
        state.proof_artifact_count
        if state.proof_artifact_count is not None
        else "unknown"
    )
    proof_errors = (
        state.proof_error_count if state.proof_error_count is not None else "unknown"
    )
    proof_warnings = (
        state.proof_warning_count
        if state.proof_warning_count is not None
        else "unknown"
    )
    return "\n".join(
        [
            "Trace Health",
            f"- Status: {state.status}",
            f"- Schema version: {state.schema_version or 'unknown'}",
            f"- Generated at: {state.generated_at or 'unknown'}",
            f"- Trace count: {state.trace_count}",
            f"- Attention traces: {state.attention_count}",
            f"- Artifact traces: {state.artifact_count}",
            f"- Warning traces: {state.warning_trace_count}",
            f"- Benchmark health: {state.benchmark_health_status or 'unknown'}",
            f"- Benchmark health artifacts: {benchmark_artifacts}",
            f"- Proof expected: {proof_expected}",
            f"- Proof artifacts: {proof_artifacts}",
            f"- Proof errors: {proof_errors}",
            f"- Proof warnings: {proof_warnings}",
            f"- By kind: {_render_count_pairs(state.kind_counts)}",
            f"- By status: {_render_count_pairs(state.status_counts)}",
        ],
    ) + "\n"


def _benchmark_trace_health(
    payload: Mapping[str, object],
) -> tuple[str | None, int | None]:
    """Extract the compact benchmark health signal from trace-health metadata."""

    # Check artifact traces first because they contain the richest benchmark
    # metadata, then fall back to latest traces for minimal benchmark reports.
    traces: list[object] = []
    for key in ("artifact_traces", "latest"):
        value = payload.get(key)
        if isinstance(value, list):
            traces.extend(value)
    for trace in traces:
        if not isinstance(trace, Mapping) or trace.get("kind") != "benchmark":
            continue
        summary = trace.get("trace_health_summary")
        if not isinstance(summary, Mapping):
            continue
        status = summary.get("health_status")
        artifact_count = summary.get("artifact_trace_count")
        return (
            status if isinstance(status, str) else None,
            artifact_count if _is_summary_int(artifact_count) else None,
        )
    return None, None


def _proof_trace_summary(
    payload: Mapping[str, object],
) -> tuple[int | None, int | None, int | None, int | None]:
    """Extract compact proof finalization counts from trace-health metadata."""

    traces: list[object] = []
    for key in ("latest", "artifact_traces"):
        value = payload.get(key)
        if isinstance(value, list):
            traces.extend(value)
    for trace in traces:
        if not isinstance(trace, Mapping) or trace.get("kind") != "proof_suite":
            continue
        summary = trace.get("proof_summary")
        expected: object = None
        artifacts: object = None
        errors: object = None
        if isinstance(summary, Mapping):
            expected = summary.get("expected_count")
            artifacts = summary.get("artifact_count")
            errors = summary.get("error_count")
        warnings = trace.get("proof_warnings")
        warning_count = (
            len([warning for warning in warnings if isinstance(warning, str)])
            if isinstance(warnings, list)
            else None
        )
        return (
            _summary_int_or_none(expected),
            _summary_int_or_none(artifacts),
            _summary_int_or_none(errors),
            warning_count,
        )
    return None, None, None, None


def _summary_int_or_none(value: object) -> int | None:
    """Return an integer summary count while rejecting JSON booleans."""

    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def render_approval_dialog_text(state: ApprovalDialogState) -> str:
    """Render approval dialog details for diagnostics and tests."""
    return "\n".join(
        [
            "Approval",
            f"- Routine ID: {state.routine_id}",
            f"- Step ID: {state.step_id}",
            f"- Risk class: {state.risk_class}",
            f"- Checkpoint evidence: {state.checkpoint_evidence}",
            f"- Content fingerprint: {state.content_fingerprint}",
            f"- Status: {state.status}",
            f"- Approver: {state.approver or 'none'}",
            f"- Reason: {state.reason or 'none'}",
            f"- Decided at: {state.decided_at or 'none'}",
            f"- Actions: {', '.join(state.actions)}",
        ],
    ) + "\n"


def render_recorder_review_text(state: RecorderReviewPanelState) -> str:
    """Render recorder review details for diagnostics and tests."""
    screenshots = (
        ", ".join(str(path) for path in state.screenshot_paths)
        if state.screenshot_paths
        else "none"
    )
    return "\n".join(
        [
            "Recorder Review",
            f"- Status: {state.status}",
            f"- Generated YAML: {state.generated_yaml}",
            f"- Selected targets: {', '.join(state.selected_targets) or 'none'}",
            f"- Screenshots: {screenshots}",
            "- Verification suggestions: "
            f"{', '.join(state.verification_suggestions) or 'none'}",
        ],
    ) + "\n"


def render_trace_viewer_timeline_text(state: TraceViewerTimelineState) -> str:
    """Render trace timeline evidence for diagnostics and tests."""
    video = str(state.video_path) if state.video_path else "none"
    action_log = str(state.action_log_path) if state.action_log_path else "none"
    final_report = str(state.final_report_path) if state.final_report_path else "none"
    screenshots = (
        ", ".join(str(path) for path in state.screenshot_paths)
        if state.screenshot_paths
        else "none"
    )
    return "\n".join(
        [
            "Trace Timeline",
            f"- Status: {state.status}",
            f"- Trace kind: {state.trace_kind}",
            f"- Video: {video}",
            f"- Screenshots: {screenshots}",
            f"- Action log: {action_log}",
            "- Candidate reasoning: "
            f"{', '.join(state.candidate_reasoning) or 'none'}",
            f"- State delta: {', '.join(state.state_delta) or 'none'}",
            "- Verification results: "
            f"{', '.join(state.verification_results) or 'none'}",
            f"- Proof gates: {', '.join(state.proof_gates) or 'none'}",
            f"- Final report: {final_report}",
        ],
    ) + "\n"


def trace_viewer_timeline_from_report(
    report: Mapping[str, object],
    *,
    report_path: Path | None = None,
) -> TraceViewerTimelineState:
    """Create trace-viewer state from a local report JSON payload."""

    gates = report.get("gates")
    trace_kind = _trace_kind_from_report(report, report_path)
    return TraceViewerTimelineState(
        trace_kind=trace_kind,
        candidate_reasoning=_candidate_ranking_lines(
            report.get("candidate_routines"),
        ),
        proof_gates=_proof_gate_lines(gates),
        verification_results=(
            _proof_verification_lines(report)
            if trace_kind == "proof_suite"
            else _benchmark_verification_lines(report)
        ),
        final_report_path=report_path,
        status=_timeline_status_from_report(report),
    )


def _trace_kind_from_report(
    report: Mapping[str, object],
    report_path: Path | None,
) -> str:
    if report_path is not None:
        if report_path.name == "proof-finalization-status.json":
            return "proof_suite"
        if report_path.name == "goal-plan-report.json":
            return "goal_plan"
        if report_path.name == "benchmark-report.json":
            return "benchmark"
    if "gates" in report and "checked_artifacts" in report:
        return "proof_suite"
    if "selected_routine_id" in report:
        return "goal_plan"
    if "observability_contract" in report and "monitoring_coverage" in report:
        return "benchmark"
    return "run"


def _timeline_status_from_report(report: Mapping[str, object]) -> str:
    status = report.get("status")
    if isinstance(status, str):
        return status
    acceptance = report.get("acceptance")
    if isinstance(acceptance, Mapping):
        acceptance_status = acceptance.get("status")
        if isinstance(acceptance_status, str):
            return acceptance_status
    return "loaded"


def _proof_gate_lines(gates: object) -> tuple[str, ...]:
    if not isinstance(gates, Mapping):
        return ()
    lines: list[str] = []
    for name, status in gates.items():
        if isinstance(name, str) and isinstance(status, str):
            lines.append(f"{name}: {status}")
    return tuple(lines)


def _proof_summary_lines(report: Mapping[str, object]) -> tuple[str, ...]:
    """Render compact proof finalization counts for trace viewer diagnostics."""

    summary = report.get("summary")
    if not isinstance(summary, Mapping):
        return ()
    return tuple(
        f"{name}: {value}"
        for name, value in summary.items()
        if isinstance(name, str) and _is_summary_int(value)
    )


def _proof_warning_lines(report: Mapping[str, object]) -> tuple[str, ...]:
    """Render proof finalization warnings for trace viewer diagnostics."""

    warnings = report.get("warnings")
    if not isinstance(warnings, list):
        return ()
    return tuple(
        f"warning: {warning}" for warning in warnings if isinstance(warning, str)
    )


def _proof_verification_lines(report: Mapping[str, object]) -> tuple[str, ...]:
    """Render proof summary and warnings for trace viewer diagnostics."""

    return (*_proof_summary_lines(report), *_proof_warning_lines(report))


def _is_summary_int(value: object) -> bool:
    """Return true for integer counts while excluding JSON booleans."""

    return isinstance(value, int) and not isinstance(value, bool)


def _candidate_ranking_lines(candidates: object) -> tuple[str, ...]:
    if not isinstance(candidates, list):
        return ()
    lines: list[str] = []
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue
        routine_id = candidate.get("routine_id")
        score = candidate.get("score")
        matched_fields = candidate.get("matched_fields")
        if not isinstance(routine_id, str):
            continue
        matched = _joined_string_values(matched_fields)
        lines.append(f"{routine_id}: score {score} matched {matched}")
    return tuple(lines)


def _benchmark_verification_lines(report: Mapping[str, object]) -> tuple[str, ...]:
    if _trace_kind_from_report(report, None) != "benchmark":
        return ()
    lines: list[str] = []
    schema_version = report.get("schema_version")
    if isinstance(schema_version, str):
        lines.append(f"schema: {schema_version}")
    generated_at = report.get("generated_at")
    if isinstance(generated_at, str):
        lines.append(f"generated_at: {generated_at}")
    acceptance = report.get("acceptance")
    if isinstance(acceptance, Mapping):
        status = acceptance.get("status")
        if isinstance(status, str):
            lines.append(f"acceptance: {status}")
    baseline = report.get("baseline_comparison")
    if isinstance(baseline, Mapping):
        status = baseline.get("status")
        if isinstance(status, str):
            lines.append(f"baseline: {status}")
    coverage = report.get("monitoring_coverage")
    if isinstance(coverage, Mapping):
        passed = coverage.get("passed")
        if isinstance(passed, bool):
            lines.append(f"monitoring coverage: {'passed' if passed else 'failed'}")
    trace_health = report.get("trace_health_summary")
    if isinstance(trace_health, Mapping):
        status = trace_health.get("health_status")
        if isinstance(status, str):
            lines.append(f"trace health: {status}")
        artifact_count = trace_health.get("artifact_trace_count")
        if _is_summary_int(artifact_count):
            lines.append(f"trace health artifacts: {artifact_count}")
        warning_count = trace_health.get("warning_trace_count")
        if _is_summary_int(warning_count):
            lines.append(f"trace health warnings: {warning_count}")
    artifacts = report.get("report_artifacts")
    if isinstance(artifacts, Mapping):
        for name, path in artifacts.items():
            if isinstance(name, str) and isinstance(path, str):
                lines.append(f"artifact {name}: {path}")
    return tuple(lines)


def _joined_string_values(value: object) -> str:
    if not isinstance(value, list):
        return "none"
    items = [item for item in value if isinstance(item, str)]
    return ", ".join(items) or "none"


def _count_pairs(value: object) -> tuple[tuple[str, int], ...]:
    if not isinstance(value, Mapping):
        return ()
    pairs = [
        (key, item)
        for key, item in value.items()
        if isinstance(key, str) and isinstance(item, int)
    ]
    return tuple(sorted(pairs))


def _render_count_pairs(pairs: tuple[tuple[str, int], ...]) -> str:
    return ", ".join(f"{name}={count}" for name, count in pairs) or "none"


def render_routine_pack_manager_text(state: RoutinePackManagerState) -> str:
    """Render routine-pack install and removal details for diagnostics."""
    return "\n".join(
        [
            "Routine Packs",
            f"- Status: {state.status}",
            f"- Installed packs: {', '.join(state.installed_pack_ids) or 'none'}",
            f"- Selected pack: {state.selected_pack_id or 'none'}",
            f"- Install source: {state.install_source_path or 'none'}",
            f"- Pending action: {state.pending_action or 'none'}",
            f"- Trust warnings: {', '.join(state.trust_warnings) or 'none'}",
            f"- Actions: {', '.join(state.actions)}",
        ],
    ) + "\n"


def failure_analysis_review_from_analysis(
    analysis: FailedRunAnalysis,
    *,
    trace_dir: Path | None = None,
) -> FailureAnalysisReviewPanelState:
    """Build UI review state from a failed-run analysis artifact."""
    proposals = tuple(
        FailureAnalysisProposalState(
            step_id=proposal.step_id,
            proposal_type=proposal.proposal_type,
            rationale=proposal.rationale,
            yaml_snippet=proposal.yaml_snippet,
            review_required=proposal.review_required,
            applies_automatically=proposal.applies_automatically,
        )
        for proposal in analysis.proposals
    )
    return FailureAnalysisReviewPanelState(
        trace_dir=trace_dir,
        analysis_json_path=trace_dir / "failed-run-analysis.json"
        if trace_dir is not None
        else None,
        analysis_markdown_path=trace_dir / "failed-run-analysis.md"
        if trace_dir is not None
        else None,
        proposals=proposals,
        status="ready" if proposals else "empty",
    )


def render_failure_analysis_review_text(
    state: FailureAnalysisReviewPanelState,
) -> str:
    """Render failed-run analysis review details for diagnostics and tests."""
    lines = [
        "Failure Analysis Review",
        f"- Status: {state.status}",
        f"- Trace: {state.trace_dir or 'none'}",
        f"- Analysis JSON: {state.analysis_json_path or 'none'}",
        f"- Analysis Markdown: {state.analysis_markdown_path or 'none'}",
        f"- Proposal count: {len(state.proposals)}",
    ]
    for proposal in state.proposals:
        lines.extend(
            [
                f"- Step {proposal.step_id}: {proposal.proposal_type}",
                f"  - Review required: {proposal.review_required}",
                f"  - Applies automatically: {proposal.applies_automatically}",
                f"  - Rationale: {proposal.rationale}",
                f"  - YAML: {proposal.yaml_snippet}",
            ],
        )
    return "\n".join(lines) + "\n"


def settings_panel_from_runtime_config(
    config: RuntimeConfig,
    *,
    video_capture_enabled: bool = False,
    proof_mode: bool = False,
) -> SettingsPanelState:
    """Build app settings state from the shared runtime configuration."""
    return SettingsPanelState(
        trace_root=config.trace_root,
        screenshots_enabled=config.save_screenshots,
        video_capture_enabled=video_capture_enabled,
        ollama_enabled=config.local_model.enabled,
        emergency_hotkey=config.emergency_stop_hotkey,
        default_activity_profile=config.execution_profile.activity_profile,
        proof_mode=proof_mode,
    )


def render_settings_panel_text(state: SettingsPanelState) -> str:
    """Render app settings fields for diagnostics and tests."""
    return "\n".join(
        [
            "Settings",
            f"- Trace root: {state.trace_root}",
            f"- Screenshots: {state.screenshots_enabled}",
            f"- Video capture: {state.video_capture_enabled}",
            f"- Ollama: {state.ollama_enabled}",
            f"- Emergency hotkey: {state.emergency_hotkey}",
            f"- Default activity profile: {state.default_activity_profile or 'none'}",
            f"- Proof mode: {state.proof_mode}",
        ],
    ) + "\n"


def render_operator_app_shell_text(shell: OperatorAppShell | None = None) -> str:
    """Render the shell contract for CLI diagnostics and tests."""
    active_shell = shell or operator_app_shell_spec()
    lines = [active_shell.title, ""]
    for page in active_shell.pages:
        default_marker = (
            " (default)" if page.page_id == active_shell.default_page_id else ""
        )
        lines.append(f"- {page.title}{default_marker}: {page.purpose}")
        for panel_id in page.panel_ids:
            lines.append(f"  panel: {panel_id}")
    return "\n".join(lines) + "\n"


def launch_operator_app(
    argv: Sequence[str] | None = None,
    *,
    shell: OperatorAppShell | None = None,
) -> int:
    """Launch the native PySide6 shell when the optional dependency exists."""
    active_shell = shell or operator_app_shell_spec()
    qt_widgets = _qt_widgets_module()
    app = qt_widgets.QApplication(list(argv or []))
    window = _build_main_window(qt_widgets, active_shell)
    window.show()
    return int(app.exec())


def _qt_widgets_module() -> Any:
    try:
        return import_module("PySide6.QtWidgets")
    except ModuleNotFoundError as exc:
        raise OperatorAppUnavailableError(
            'PySide6 is not installed. Install DeskPilot with "deskpilot[app]".',
        ) from exc


def _build_main_window(qt_widgets: Any, shell: OperatorAppShell) -> Any:
    window = qt_widgets.QMainWindow()
    window.setWindowTitle(shell.title)
    window.resize(1180, 760)

    central = qt_widgets.QWidget()
    layout = qt_widgets.QHBoxLayout(central)
    nav = qt_widgets.QListWidget()
    stack = qt_widgets.QStackedWidget()
    for page in shell.pages:
        nav.addItem(page.title)
        stack.addWidget(_page_widget(qt_widgets, page))
    nav.setCurrentRow(0)
    nav.currentRowChanged.connect(stack.setCurrentIndex)
    layout.addWidget(nav, 1)
    layout.addWidget(stack, 4)
    window.setCentralWidget(central)
    return window


def _page_widget(qt_widgets: Any, page: OperatorAppPage) -> Any:
    widget = qt_widgets.QWidget()
    layout = qt_widgets.QVBoxLayout(widget)
    heading = qt_widgets.QLabel(page.title)
    heading.setObjectName(f"{page.page_id}_heading")
    body = qt_widgets.QLabel(page.purpose)
    body.setWordWrap(True)
    layout.addWidget(heading)
    layout.addWidget(body)
    if "live_run" in page.panel_ids:
        for line in render_live_run_panel_text().splitlines():
            layout.addWidget(qt_widgets.QLabel(line))
    if "approval_dialog" in page.panel_ids:
        layout.addWidget(qt_widgets.QLabel("Approval"))
        layout.addWidget(qt_widgets.QLabel("Routine ID: pending"))
        layout.addWidget(qt_widgets.QLabel("Step ID: pending"))
        layout.addWidget(qt_widgets.QLabel("Risk class: pending"))
        layout.addWidget(qt_widgets.QLabel("Checkpoint evidence: pending"))
        layout.addWidget(qt_widgets.QLabel("Content fingerprint: pending"))
        layout.addWidget(qt_widgets.QLabel("Actions: approve, deny"))
    if "recorder_review" in page.panel_ids:
        layout.addWidget(qt_widgets.QLabel("Recorder Review"))
        layout.addWidget(qt_widgets.QLabel("Generated YAML: pending"))
        layout.addWidget(qt_widgets.QLabel("Selected targets: pending"))
        layout.addWidget(qt_widgets.QLabel("Screenshots: pending"))
        layout.addWidget(qt_widgets.QLabel("Verification suggestions: pending"))
    if "trace_timeline" in page.panel_ids:
        layout.addWidget(qt_widgets.QLabel("Trace Timeline"))
        layout.addWidget(qt_widgets.QLabel("Video: pending"))
        layout.addWidget(qt_widgets.QLabel("Screenshots: pending"))
        layout.addWidget(qt_widgets.QLabel("Action log: pending"))
        layout.addWidget(qt_widgets.QLabel("Candidate reasoning: pending"))
        layout.addWidget(qt_widgets.QLabel("State delta: pending"))
        layout.addWidget(qt_widgets.QLabel("Final report: pending"))
    if "routine_pack_manager" in page.panel_ids:
        layout.addWidget(qt_widgets.QLabel("Routine Packs"))
        layout.addWidget(qt_widgets.QLabel("Installed packs: pending"))
        layout.addWidget(qt_widgets.QLabel("Selected pack: pending"))
        layout.addWidget(qt_widgets.QLabel("Install source: pending"))
        layout.addWidget(qt_widgets.QLabel("Trust warnings: pending"))
        layout.addWidget(qt_widgets.QLabel("Actions: install, replace, remove, export"))
    if "failure_analysis_review" in page.panel_ids:
        layout.addWidget(qt_widgets.QLabel("Failure Analysis Review"))
        layout.addWidget(qt_widgets.QLabel("Proposal count: pending"))
        layout.addWidget(qt_widgets.QLabel("Review required: true"))
        layout.addWidget(qt_widgets.QLabel("Applies automatically: false"))
        layout.addWidget(qt_widgets.QLabel("YAML proposals: pending"))
    if "settings" in page.panel_ids:
        layout.addWidget(qt_widgets.QLabel("Settings"))
        layout.addWidget(qt_widgets.QLabel("Trace root: traces"))
        layout.addWidget(qt_widgets.QLabel("Screenshots: true"))
        layout.addWidget(qt_widgets.QLabel("Video capture: false"))
        layout.addWidget(qt_widgets.QLabel("Ollama: false"))
        layout.addWidget(qt_widgets.QLabel("Emergency hotkey: ctrl+alt+esc"))
        layout.addWidget(qt_widgets.QLabel("Default activity profile: none"))
        layout.addWidget(qt_widgets.QLabel("Proof mode: false"))
    layout.addStretch(1)
    return widget
