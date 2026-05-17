"""Local service boundary used by the native operator app."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, cast

import yaml

from desktop_agent.config import RuntimeConfig
from desktop_agent.content_variables import load_content_variables
from desktop_agent.failed_run_analyzer import (
    analyze_failed_run_trace,
    write_failed_run_analysis,
)
from desktop_agent.preview import build_dry_run_preview, render_dry_run_preview
from desktop_agent.proof_manifest import PROOF_FINALIZATION_STATUS_NAME
from desktop_agent.recorder import (
    RecorderController,
    RecorderEvent,
    RecorderSession,
    generate_task_from_recorder_session,
)
from desktop_agent.routine_pack_manifest import (
    RoutinePackManifest,
    load_routine_pack_manifests,
    routine_pack_trust_warnings,
)
from desktop_agent.routine_pack_ops import (
    RoutinePackImportResult,
    RoutinePackRemoveResult,
    import_routine_pack,
    remove_routine_pack,
)
from desktop_agent.routines import (
    RoutineCatalog,
    RoutineDefinition,
    RoutineExecutionGate,
    load_routine_catalog,
    routine_execution_gate,
    routine_quarantine_status,
)
from desktop_agent.scheduler import RunQueue, RunQueueStatus
from desktop_agent.site_playbooks import (
    SitePlaybook,
    SitePlaybookValidationError,
    SiteTaskCompiler,
    load_site_playbook,
    load_site_playbooks,
    resolve_site_flow,
)
from desktop_agent.task_compiler import TaskCompiler
from desktop_agent.task_dsl import (
    BasicTaskValidator,
    ExpectedStateTransition,
    RecoveryRule,
    TaskDefinition,
    TaskStep,
    VerificationDefinition,
    YamlTaskLoader,
)


class OperatorServiceError(ValueError):
    """Raised when an operator service cannot satisfy a local request."""


@dataclass(frozen=True)
class RoutineListItem:
    """Small routine row for app lists and search results."""

    routine_id: str
    name: str
    safety_class: str
    approval_policy: str
    quarantine_status: str

    def metadata(self) -> dict[str, object]:
        return {
            "routine_id": self.routine_id,
            "name": self.name,
            "safety_class": self.safety_class,
            "approval_policy": self.approval_policy,
            "quarantine_status": self.quarantine_status,
        }


@dataclass(frozen=True)
class TraceSummary:
    """One local trace directory visible in the operator app."""

    trace_dir: Path
    report_path: Path | None
    status: str | None
    kind: str
    replay_summary_path: Path | None = None
    report_artifacts: tuple[tuple[str, str], ...] = ()
    trace_health_summary: tuple[tuple[str, object], ...] = ()
    proof_summary: tuple[tuple[str, int], ...] = ()

    def metadata(self) -> dict[str, object]:
        return {
            "trace_dir": str(self.trace_dir),
            "report_path": str(self.report_path) if self.report_path else None,
            "status": self.status,
            "kind": self.kind,
            "replay_summary_path": (
                str(self.replay_summary_path) if self.replay_summary_path else None
            ),
            "report_artifacts": dict(self.report_artifacts),
            "trace_health_summary": dict(self.trace_health_summary),
            "proof_summary": dict(self.proof_summary),
        }


@dataclass(frozen=True)
class OperatorRunStartResult:
    """Result of starting a routine through the local operator app boundary."""

    run_id: str | None
    routine_id: str
    status: str
    reason: str
    next_action: str | None
    execution_gate: RoutineExecutionGate

    def metadata(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "routine_id": self.routine_id,
            "status": self.status,
            "reason": self.reason,
            "next_action": self.next_action,
            "execution_gate": self.execution_gate.metadata(),
        }


@dataclass(frozen=True)
class OperatorDryRunResult:
    """App-facing dry-run preflight that never sends desktop input."""

    routine_id: str
    status: str
    reason: str
    task_name: str | None
    step_count: int
    desktop_input_required: bool
    preview: str
    compiled_task: dict[str, object]
    execution_gate: RoutineExecutionGate

    def metadata(self) -> dict[str, object]:
        return {
            "routine_id": self.routine_id,
            "status": self.status,
            "reason": self.reason,
            "task_name": self.task_name,
            "step_count": self.step_count,
            "desktop_input_required": self.desktop_input_required,
            "preview": self.preview,
            "compiled_task": self.compiled_task,
            "execution_gate": self.execution_gate.metadata(),
        }


@dataclass(frozen=True)
class OperatorFailedTraceInspection:
    """App-facing summary of why a failed trace stopped."""

    trace_dir: Path
    task_name: str
    status: str
    routine_id: str | None
    failure_reasons: tuple[str, ...]
    proposal_count: int
    diagnostic_ready: bool
    analysis_json_path: Path
    analysis_markdown_path: Path

    def metadata(self) -> dict[str, object]:
        return {
            "trace_dir": str(self.trace_dir),
            "task_name": self.task_name,
            "status": self.status,
            "routine_id": self.routine_id,
            "failure_reasons": list(self.failure_reasons),
            "proposal_count": self.proposal_count,
            "diagnostic_ready": self.diagnostic_ready,
            "analysis_json_path": str(self.analysis_json_path),
            "analysis_markdown_path": str(self.analysis_markdown_path),
        }


@dataclass(frozen=True)
class OperatorRunControlResult:
    """Result of a pause, resume, cancel, or stop request from the app."""

    run_id: str
    routine_id: str
    status: str
    reason: str
    next_action: str | None

    def metadata(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "routine_id": self.routine_id,
            "status": self.status,
            "reason": self.reason,
            "next_action": self.next_action,
        }


@dataclass(frozen=True)
class OperatorApprovalDecision:
    """Evidence-backed approve or deny decision made in the operator app."""

    routine_id: str
    step_id: str
    action: str
    risk_class: str
    checkpoint_evidence: str
    content_fingerprint: str
    approver: str
    reason: str
    decided_at: str

    @property
    def approved(self) -> bool:
        return self.action == "approve"

    def metadata(self) -> dict[str, object]:
        return {
            "routine_id": self.routine_id,
            "step_id": self.step_id,
            "action": self.action,
            "approved": self.approved,
            "risk_class": self.risk_class,
            "checkpoint_evidence": self.checkpoint_evidence,
            "content_fingerprint": self.content_fingerprint,
            "approver": self.approver,
            "reason": self.reason,
            "decided_at": self.decided_at,
        }


@dataclass(frozen=True)
class OperatorRecorderReviewResult:
    """Generated YAML and evidence shown before saving a recorded routine."""

    session_id: str
    generated_yaml: str
    selected_targets: tuple[str, ...]
    screenshot_paths: tuple[Path, ...]
    verification_suggestions: tuple[str, ...]
    status: str

    def metadata(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "generated_yaml": self.generated_yaml,
            "selected_targets": list(self.selected_targets),
            "screenshot_paths": [str(path) for path in self.screenshot_paths],
            "verification_suggestions": list(self.verification_suggestions),
            "status": self.status,
        }


@dataclass(frozen=True)
class OperatorRecordedRoutineResult:
    """Saved recorder output that can be rerun through the routine catalog."""

    routine_id: str
    routine_path: Path
    task_path: Path
    saved_recording_path: Path

    def metadata(self) -> dict[str, object]:
        return {
            "routine_id": self.routine_id,
            "routine_path": str(self.routine_path),
            "task_path": str(self.task_path),
            "saved_recording_path": str(self.saved_recording_path),
        }


@dataclass(frozen=True)
class RoutinePackListItem:
    """Small routine-pack row for app install and removal views."""

    pack_id: str
    name: str
    version: str
    trust_level: str
    max_safety_class: str
    trust_warning_count: int = 0

    def metadata(self) -> dict[str, object]:
        return {
            "pack_id": self.pack_id,
            "name": self.name,
            "version": self.version,
            "trust_level": self.trust_level,
            "max_safety_class": self.max_safety_class,
            "trust_warning_count": self.trust_warning_count,
        }


class CatalogService(Protocol):
    """Routine catalog API consumed by the operator app."""

    def list_routines(self, query: str | None = None) -> tuple[RoutineListItem, ...]:
        """Return routine rows, optionally filtered by catalog search."""
        ...

    def routine(self, routine_id: str) -> RoutineDefinition:
        """Return one routine definition by ID."""
        ...


class RecorderService(Protocol):
    """Recorder API boundary for future UI wiring."""

    def capabilities(self) -> tuple[str, ...]:
        """Return supported recorder operations."""
        ...

    def start_recording(
        self,
        name: str,
        *,
        overwrite: bool = False,
    ) -> RecorderSession:
        """Start a local recorder session for the app."""
        ...

    def record_event(self, event: RecorderEvent) -> RecorderSession:
        """Append one captured recorder event."""
        ...

    def review_recording(self) -> OperatorRecorderReviewResult:
        """Generate editable YAML and evidence for operator review."""
        ...

    def save_recording_as_routine(
        self,
        *,
        routine_id: str | None = None,
        overwrite: bool = False,
    ) -> OperatorRecordedRoutineResult:
        """Save the reviewed recording into the local routine catalog."""
        ...


class RunnerService(Protocol):
    """Run and dry-run API boundary for future UI wiring."""

    def execution_gate(self, routine_id: str) -> RoutineExecutionGate:
        """Return whether a routine can enter the execution pipeline."""
        ...

    def dry_run_routine(self, routine_id: str) -> OperatorDryRunResult:
        """Compile and preview a routine without desktop input."""
        ...

    def start_routine(self, routine_id: str) -> OperatorRunStartResult:
        """Start a local run request without shelling out to the CLI."""
        ...

    def pause_run(self, run_id: str) -> OperatorRunControlResult:
        """Pause a monitored app run."""
        ...

    def resume_run(self, run_id: str) -> OperatorRunControlResult:
        """Resume a paused app run."""
        ...

    def cancel_run(self, run_id: str) -> OperatorRunControlResult:
        """Cancel a monitored app run."""
        ...

    def stop_run(self, run_id: str) -> OperatorRunControlResult:
        """Stop a monitored app run."""
        ...

    def emergency_stop_run(self, run_id: str) -> OperatorRunControlResult:
        """Emergency-stop a monitored app run."""
        ...


class SchedulerService(Protocol):
    """Run queue API boundary for future UI wiring."""

    def queue_metadata(self) -> dict[str, object]:
        """Return JSON-safe run queue state."""
        ...


class ApprovalService(Protocol):
    """Approval API boundary for future UI wiring."""

    def routines_requiring_approval(self) -> tuple[RoutineListItem, ...]:
        """Return routines that need operator approval before mutation."""
        ...

    def resolve_step_approval(
        self,
        *,
        routine_id: str,
        step_id: str,
        action: str,
        risk_class: str,
        checkpoint_evidence: str,
        content_fingerprint: str,
        approver: str,
        reason: str,
        decided_at: str | None = None,
    ) -> OperatorApprovalDecision:
        """Record an evidence-backed operator decision for a sensitive step."""
        ...

    def approval_decisions(self) -> tuple[OperatorApprovalDecision, ...]:
        """Return recorded app approval decisions for monitoring views."""
        ...


class TraceService(Protocol):
    """Local trace API boundary for future UI wiring."""

    def list_traces(self, *, limit: int = 50) -> tuple[TraceSummary, ...]:
        """Return local trace summaries."""
        ...

    def read_report(self, trace_dir: Path) -> dict[str, object]:
        """Read a trace report JSON file."""
        ...

    def trace_summary(self, trace_dir: Path) -> TraceSummary:
        """Return one local trace summary for app state hydration."""
        ...

    def trace_health(self, *, limit: int = 50) -> dict[str, object]:
        """Return aggregate local trace status for dashboard monitoring."""
        ...

    def inspect_failed_trace(self, trace_dir: Path) -> OperatorFailedTraceInspection:
        """Analyze a failed trace and write local review artifacts."""
        ...


class RoutinePackService(Protocol):
    """Routine-pack install and removal API consumed by the operator app."""

    def list_packs(self) -> tuple[RoutinePackListItem, ...]:
        """Return installed routine-pack rows."""
        ...

    def install_pack(
        self,
        source: Path,
        *,
        replace: bool = False,
    ) -> RoutinePackImportResult:
        """Install a validated local routine pack directory or archive."""
        ...

    def remove_pack(self, pack_id: str) -> RoutinePackRemoveResult:
        """Remove one installed local routine pack."""
        ...


class OperatorAppService(Protocol):
    """Composite Python service boundary consumed by PySide6 app widgets."""

    @property
    def catalog(self) -> CatalogService:
        """Return the routine catalog boundary."""
        ...

    @property
    def recorder(self) -> RecorderService:
        """Return the recorder boundary."""
        ...

    @property
    def runner(self) -> RunnerService:
        """Return the runner boundary."""
        ...

    @property
    def scheduler(self) -> SchedulerService:
        """Return the scheduler boundary."""
        ...

    @property
    def approvals(self) -> ApprovalService:
        """Return the approval boundary."""
        ...

    @property
    def traces(self) -> TraceService:
        """Return the local trace boundary."""
        ...

    @property
    def routine_packs(self) -> RoutinePackService:
        """Return the routine-pack boundary."""
        ...


@dataclass(frozen=True)
class LocalOperatorServices:
    """Concrete local service bundle injected into the operator app shell."""

    catalog: CatalogService
    recorder: RecorderService
    runner: RunnerService
    scheduler: SchedulerService
    approvals: ApprovalService
    traces: TraceService
    routine_packs: RoutinePackService


class LocalRunQueueStore:
    """Shared mutable queue store for runner and scheduler app services."""

    def __init__(self, queue: RunQueue | None = None) -> None:
        self.queue = queue or RunQueue()


class LocalCatalogService:
    """Catalog service backed by routine pack YAML files."""

    def __init__(self, root: Path = Path("routine_packs")) -> None:
        self._root = root

    def list_routines(self, query: str | None = None) -> tuple[RoutineListItem, ...]:
        catalog = self._load_catalog()
        if query:
            routines = tuple(result.routine for result in catalog.search(query))
        else:
            routines = tuple(sorted(catalog.routines, key=lambda routine: routine.id))
        return tuple(_routine_list_item(routine) for routine in routines)

    def routine(self, routine_id: str) -> RoutineDefinition:
        routine = self._load_catalog().by_id(routine_id)
        if routine is None:
            raise OperatorServiceError(f"unknown routine: {routine_id}")
        return routine

    def _load_catalog(self) -> RoutineCatalog:
        return load_routine_catalog(self._root)


class LocalRecorderService:
    """Recorder boundary exposing the current local recorder capability list."""

    def __init__(
        self,
        state_path: Path = Path("traces/operator-recorder-session.json"),
        *,
        routine_pack_root: Path = Path("routine_packs"),
    ) -> None:
        self._controller = RecorderController(state_path)
        self._routine_pack_root = routine_pack_root

    def capabilities(self) -> tuple[str, ...]:
        return (
            "start",
            "pause",
            "resume",
            "stop",
            "save",
            "save_as_routine",
            "rerun_saved_routine",
            "discard",
            "generate_yaml",
        )

    def start_recording(
        self,
        name: str,
        *,
        overwrite: bool = False,
    ) -> RecorderSession:
        return self._controller.start(name=name, overwrite=overwrite)

    def record_event(self, event: RecorderEvent) -> RecorderSession:
        return self._controller.record_event(event)

    def review_recording(self) -> OperatorRecorderReviewResult:
        session = self._controller.load()
        task = generate_task_from_recorder_session(session)
        return OperatorRecorderReviewResult(
            session_id=session.session_id,
            generated_yaml=_task_yaml_text(task),
            selected_targets=_recorder_selected_targets(session),
            screenshot_paths=_recorder_screenshot_paths(session),
            verification_suggestions=_verification_suggestions(task),
            status="ready_for_save",
        )

    def save_recording_as_routine(
        self,
        *,
        routine_id: str | None = None,
        overwrite: bool = False,
    ) -> OperatorRecordedRoutineResult:
        session = self._controller.load()
        task = generate_task_from_recorder_session(session)
        saved_routine_id = routine_id or f"recorded.{_slug(task.name)}"
        recorded_root = self._routine_pack_root / "recorded"
        task_path = recorded_root / "tasks" / f"{_slug(task.name)}.task.yaml"
        routine_path = recorded_root / f"{_slug(saved_routine_id)}.routine.yaml"
        saved_recording_path = (
            recorded_root / "recordings" / f"{_slug(task.name)}.recording.json"
        )
        for path in (task_path, routine_path, saved_recording_path):
            if path.exists() and not overwrite:
                raise OperatorServiceError(f"recorded routine output exists: {path}")
        task_path.parent.mkdir(parents=True, exist_ok=True)
        routine_path.parent.mkdir(parents=True, exist_ok=True)
        saved_recording_path.parent.mkdir(parents=True, exist_ok=True)
        task_path.write_text(_task_yaml_text(task), encoding="utf-8")
        routine_path.write_text(
            yaml.safe_dump(
                _recorded_routine_yaml(saved_routine_id, task, task_path),
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        self._controller.save(saved_recording_path)
        return OperatorRecordedRoutineResult(
            routine_id=saved_routine_id,
            routine_path=routine_path,
            task_path=task_path,
            saved_recording_path=saved_recording_path,
        )


class LocalRunnerService:
    """Runner boundary that applies the catalog execution gate."""

    def __init__(
        self,
        catalog_service: LocalCatalogService,
        *,
        playbook_dir: Path = Path("site_playbooks"),
        queue_store: LocalRunQueueStore | None = None,
    ) -> None:
        self._catalog_service = catalog_service
        self._playbook_dir = playbook_dir
        self._queue_store = queue_store or LocalRunQueueStore()

    def execution_gate(self, routine_id: str) -> RoutineExecutionGate:
        return routine_execution_gate(
            self._catalog_service._load_catalog(),
            routine_id,
        )

    def dry_run_routine(self, routine_id: str) -> OperatorDryRunResult:
        gate = self.execution_gate(routine_id)
        if not gate.allowed:
            return OperatorDryRunResult(
                routine_id=routine_id,
                status="blocked",
                reason=gate.reason,
                task_name=None,
                step_count=0,
                desktop_input_required=False,
                preview="",
                compiled_task={},
                execution_gate=gate,
            )
        try:
            routine = self._catalog_service.routine(routine_id)
            task = _compile_routine_task_for_app(routine, self._playbook_dir)
            config = RuntimeConfig()
            BasicTaskValidator().validate(task, config)
            compiled = TaskCompiler().compile(task)
            preview = render_dry_run_preview(build_dry_run_preview(task, config))
        except (OSError, ValueError) as exc:
            return OperatorDryRunResult(
                routine_id=routine_id,
                status="failed",
                reason=str(exc),
                task_name=None,
                step_count=0,
                desktop_input_required=False,
                preview="",
                compiled_task={},
                execution_gate=gate,
            )
        return OperatorDryRunResult(
            routine_id=routine_id,
            status="passed",
            reason="dry_run_validated",
            task_name=task.name,
            step_count=len(task.steps),
            desktop_input_required=False,
            preview=preview,
            compiled_task=compiled.metadata(),
            execution_gate=gate,
        )

    def start_routine(self, routine_id: str) -> OperatorRunStartResult:
        gate = self.execution_gate(routine_id)
        if not gate.allowed:
            return OperatorRunStartResult(
                run_id=None,
                routine_id=routine_id,
                status="blocked",
                reason=gate.reason,
                next_action=None,
                execution_gate=gate,
            )
        queued = self._queue_store.queue.enqueue(
            routine_id,
            # App pauses and resumes share the retry-aware queue transition path.
            max_attempts=100,
            reason="operator_app_start",
        )
        run_id = queued.entries[-1].id
        self._queue_store.queue = queued.transition(
            run_id,
            "running",
            reason="operator_app_start",
        )
        return OperatorRunStartResult(
            run_id=run_id,
            routine_id=routine_id,
            status="running",
            reason="operator_app_start",
            next_action="observe_screen",
            execution_gate=gate,
        )

    def pause_run(self, run_id: str) -> OperatorRunControlResult:
        return self._transition_run(
            run_id,
            "paused",
            reason="operator_app_pause",
            next_action="resume_or_cancel",
        )

    def resume_run(self, run_id: str) -> OperatorRunControlResult:
        return self._transition_run(
            run_id,
            "running",
            reason="operator_app_resume",
            next_action="observe_screen",
        )

    def cancel_run(self, run_id: str) -> OperatorRunControlResult:
        return self._transition_run(
            run_id,
            "canceled",
            reason="operator_app_cancel",
            next_action=None,
        )

    def stop_run(self, run_id: str) -> OperatorRunControlResult:
        return self._transition_run(
            run_id,
            "stopped",
            reason="operator_app_stop",
            next_action=None,
        )

    def emergency_stop_run(self, run_id: str) -> OperatorRunControlResult:
        return self._transition_run(
            run_id,
            "emergency_stopped",
            reason="operator_app_emergency_stop",
            next_action=None,
        )

    def _transition_run(
        self,
        run_id: str,
        status: RunQueueStatus,
        *,
        reason: str,
        next_action: str | None,
    ) -> OperatorRunControlResult:
        entry = self._queue_store.queue.by_id(run_id)
        if entry is None:
            raise OperatorServiceError(f"unknown run id: {run_id}")
        self._queue_store.queue = self._queue_store.queue.transition(
            run_id,
            status,
            reason=reason,
        )
        updated = self._queue_store.queue.by_id(run_id)
        if updated is None:
            raise OperatorServiceError(f"unknown run id after transition: {run_id}")
        return OperatorRunControlResult(
            run_id=run_id,
            routine_id=updated.routine_id,
            status=updated.status,
            reason=reason,
            next_action=next_action,
        )


def _compile_routine_task_for_app(
    routine: RoutineDefinition,
    playbook_dir: Path,
) -> TaskDefinition:
    if routine.reference.kind == "task":
        if routine.reference.task_path is None:
            raise OperatorServiceError("routine task reference path is required")
        task = YamlTaskLoader().load(routine.reference.task_path)
    else:
        if not routine.reference.playbook_site or not routine.reference.playbook_flow:
            raise OperatorServiceError("routine playbook reference is incomplete")
        playbook = _load_named_site_for_app(
            playbook_dir,
            routine.reference.playbook_site,
        )
        resolve_site_flow(playbook, routine.reference.playbook_flow)
        task = SiteTaskCompiler(
            load_content_variables(None),
            routine.redaction_policy,
        ).compile(playbook, routine.reference.playbook_flow)
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


def _load_named_site_for_app(playbook_dir: Path, site_id: str) -> SitePlaybook:
    site_path = playbook_dir / f"{site_id}.yaml"
    if site_path.exists():
        return load_site_playbook(site_path)
    available = {
        playbook.site_id: playbook for playbook in load_site_playbooks(playbook_dir)
    }
    if site_id not in available:
        raise SitePlaybookValidationError(f"unknown site: {site_id}")
    return available[site_id]


class LocalSchedulerService:
    """Scheduler boundary backed by the immutable local run queue model."""

    def __init__(
        self,
        queue_store: LocalRunQueueStore | RunQueue | None = None,
    ) -> None:
        if isinstance(queue_store, RunQueue):
            queue_store = LocalRunQueueStore(queue_store)
        self._queue_store = queue_store or LocalRunQueueStore()

    def queue_metadata(self) -> dict[str, object]:
        return self._queue_store.queue.metadata()


class LocalApprovalService:
    """Approval boundary derived from routine approval policies."""

    def __init__(self, catalog_service: LocalCatalogService) -> None:
        self._catalog_service = catalog_service
        self._decisions: list[OperatorApprovalDecision] = []

    def routines_requiring_approval(self) -> tuple[RoutineListItem, ...]:
        catalog = self._catalog_service._load_catalog()
        routines = [
            routine
            for routine in catalog.routines
            if routine.approval_policy != "none"
            and routine_quarantine_status(routine) == "active"
        ]
        return tuple(_routine_list_item(routine) for routine in routines)

    def resolve_step_approval(
        self,
        *,
        routine_id: str,
        step_id: str,
        action: str,
        risk_class: str,
        checkpoint_evidence: str,
        content_fingerprint: str,
        approver: str,
        reason: str,
        decided_at: str | None = None,
    ) -> OperatorApprovalDecision:
        if action not in {"approve", "deny"}:
            raise OperatorServiceError(f"unsupported approval action: {action}")
        if self._catalog_service._load_catalog().by_id(routine_id) is None:
            raise OperatorServiceError(f"unknown routine: {routine_id}")
        if not checkpoint_evidence.strip():
            raise OperatorServiceError("checkpoint evidence is required")
        if not content_fingerprint.strip():
            raise OperatorServiceError("content fingerprint is required")
        if not approver.strip():
            raise OperatorServiceError("approver is required")
        decision = OperatorApprovalDecision(
            routine_id=routine_id,
            step_id=step_id,
            action=action,
            risk_class=risk_class,
            checkpoint_evidence=checkpoint_evidence,
            content_fingerprint=content_fingerprint,
            approver=approver,
            reason=reason,
            decided_at=decided_at or datetime.now(UTC).isoformat(),
        )
        self._decisions.append(decision)
        return decision

    def approval_decisions(self) -> tuple[OperatorApprovalDecision, ...]:
        return tuple(self._decisions)


class LocalTraceService:
    """Trace boundary backed by local trace directories and report JSON files."""

    def __init__(self, trace_root: Path = Path("traces")) -> None:
        self._trace_root = trace_root

    def list_traces(self, *, limit: int = 50) -> tuple[TraceSummary, ...]:
        if not self._trace_root.exists():
            return ()
        summaries = [
            _trace_summary(path)
            for path in sorted(
                self._trace_root.iterdir(),
                key=lambda item: item.name,
                reverse=True,
            )
            if path.is_dir()
        ]
        return tuple(summaries[:limit])

    def read_report(self, trace_dir: Path) -> dict[str, object]:
        for report_name, _kind in _TRACE_REPORT_NAMES:
            report_path = trace_dir / report_name
            if report_path.exists():
                loaded = json.loads(report_path.read_text(encoding="utf-8"))
                if not isinstance(loaded, dict):
                    raise OperatorServiceError("trace report must contain a mapping")
                return cast(dict[str, object], loaded)
        raise OperatorServiceError(f"trace report not found: {trace_dir}")

    def trace_summary(self, trace_dir: Path) -> TraceSummary:
        if not trace_dir.exists() or not trace_dir.is_dir():
            raise OperatorServiceError(f"trace directory not found: {trace_dir}")
        return _trace_summary(trace_dir)

    def trace_health(self, *, limit: int = 50) -> dict[str, object]:
        summaries = self.list_traces(limit=limit)
        status_counts = _count_trace_values(
            summary.status or "unknown" for summary in summaries
        )
        attention_traces = [
            summary
            for summary in summaries
            if _trace_status_needs_attention(summary.status or "unknown")
        ]
        artifact_traces = [
            summary for summary in summaries if summary.report_artifacts
        ]
        return {
            "schema_version": TRACE_HEALTH_SCHEMA_VERSION,
            "generated_at": datetime.now(UTC).isoformat(),
            "trace_count": len(summaries),
            "artifact_trace_count": len(artifact_traces),
            "by_kind": _count_trace_values(summary.kind for summary in summaries),
            "by_status": status_counts,
            "health_status": _trace_health_status(len(summaries), status_counts),
            "attention_statuses": list(_trace_attention_statuses(status_counts)),
            "attention_traces": [summary.metadata() for summary in attention_traces],
            "artifact_traces": [summary.metadata() for summary in artifact_traces],
            "latest": [summary.metadata() for summary in summaries],
        }

    def inspect_failed_trace(self, trace_dir: Path) -> OperatorFailedTraceInspection:
        report = self.read_report(trace_dir)
        if report.get("status") == "passed":
            raise OperatorServiceError("failed trace inspection requires failed status")
        analysis = analyze_failed_run_trace(trace_dir)
        write_failed_run_analysis(trace_dir, analysis)
        return OperatorFailedTraceInspection(
            trace_dir=trace_dir,
            task_name=analysis.task_name,
            status=analysis.status,
            routine_id=analysis.routine_id,
            failure_reasons=_failed_trace_reasons(report),
            proposal_count=len(analysis.proposals),
            diagnostic_ready=analysis.diagnostic_ready,
            analysis_json_path=trace_dir / "failed-run-analysis.json",
            analysis_markdown_path=trace_dir / "failed-run-analysis.md",
        )


class LocalRoutinePackService:
    """Routine-pack boundary backed by local manifest import and removal ops."""

    def __init__(self, root: Path = Path("routine_packs")) -> None:
        self._root = root

    def list_packs(self) -> tuple[RoutinePackListItem, ...]:
        manifests = load_routine_pack_manifests(self._root)
        return tuple(_routine_pack_list_item(manifest) for manifest in manifests)

    def install_pack(
        self,
        source: Path,
        *,
        replace: bool = False,
    ) -> RoutinePackImportResult:
        return import_routine_pack(source, self._root, replace=replace)

    def remove_pack(self, pack_id: str) -> RoutinePackRemoveResult:
        return remove_routine_pack(self._root, pack_id)


def default_local_operator_services(
    *,
    routine_pack_root: Path = Path("routine_packs"),
    trace_root: Path = Path("traces"),
    playbook_dir: Path = Path("site_playbooks"),
) -> LocalOperatorServices:
    """Build the default local service bundle for the native app."""
    catalog = LocalCatalogService(routine_pack_root)
    queue_store = LocalRunQueueStore()
    return LocalOperatorServices(
        catalog=catalog,
        recorder=LocalRecorderService(
            trace_root / "operator-recorder-session.json",
            routine_pack_root=routine_pack_root,
        ),
        runner=LocalRunnerService(
            catalog,
            playbook_dir=playbook_dir,
            queue_store=queue_store,
        ),
        scheduler=LocalSchedulerService(queue_store),
        approvals=LocalApprovalService(catalog),
        traces=LocalTraceService(trace_root),
        routine_packs=LocalRoutinePackService(routine_pack_root),
    )


def _task_yaml_text(task: TaskDefinition) -> str:
    return yaml.safe_dump(_task_to_yaml_dict(task), sort_keys=False)


def _task_to_yaml_dict(task: TaskDefinition) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": task.name,
        "allowed_windows": list(task.allowed_windows),
        "timeout_seconds": task.timeout_seconds,
        "steps": [_task_step_to_yaml_dict(step) for step in task.steps],
    }
    _put_optional(payload, "entropy_budget", task.entropy_budget)
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


def _recorded_routine_yaml(
    routine_id: str,
    task: TaskDefinition,
    task_path: Path,
) -> dict[str, object]:
    metadata = task.metadata
    routine_name = _metadata_string(metadata, "routine_name") or task.name
    description = (
        _metadata_string(metadata, "routine_description")
        or "Recorded routine generated by DeskPilot."
    )
    safety_class = _recorded_safety_class(
        _metadata_string(metadata, "routine_risk_class"),
    )
    return {
        "id": routine_id,
        "name": routine_name,
        "description": description,
        "goal": f"Replay recorded routine {routine_name}.",
        "required_app": task.allowed_windows[0] if task.allowed_windows else None,
        "tags": _recorded_tags(metadata),
        "inputs": _metadata_string_list(metadata, "routine_inputs"),
        "outputs": _metadata_string_list(metadata, "routine_outputs"),
        "safety_class": safety_class,
        "schedule_policy": "manual",
        "approval_policy": "confirm"
        if safety_class in {"high", "sensitive"}
        else "none",
        "expected_duration_seconds": (
            _metadata_positive_float(metadata, "routine_expected_duration_seconds")
            or 60
        ),
        "reference": {
            "type": "task",
            "path": str(Path("tasks") / task_path.name),
        },
    }


def _recorder_selected_targets(session: RecorderSession) -> tuple[str, ...]:
    targets: list[str] = []
    for event in session.events:
        for candidate in event.candidate_context:
            if candidate.label:
                targets.append(candidate.label)
        if event.input_event is not None:
            text = event.input_event.get("text") or event.input_event.get("target")
            if isinstance(text, str):
                targets.append(text)
    return tuple(dict.fromkeys(targets))


def _failed_trace_reasons(report: dict[str, object]) -> tuple[str, ...]:
    reasons: list[str] = []
    abort_reason = report.get("abort_reason")
    if isinstance(abort_reason, str) and abort_reason:
        reasons.append(abort_reason)
    steps = report.get("steps")
    if isinstance(steps, list):
        for step in steps:
            if isinstance(step, dict):
                reasons.extend(_failed_step_reasons(step))
    return tuple(dict.fromkeys(reasons))


def _failed_step_reasons(step: dict[str, object]) -> tuple[str, ...]:
    if step.get("status") == "passed":
        return ()
    step_id = step.get("step_id") if isinstance(step.get("step_id"), str) else "?"
    metadata = step.get("metadata")
    if not isinstance(metadata, dict):
        return (f"step {step_id}: failed",)
    failure_category = metadata.get("failure_category")
    if isinstance(failure_category, str) and failure_category:
        return (f"step {step_id}: {failure_category}",)
    return (f"step {step_id}: failed",)


def _recorder_screenshot_paths(session: RecorderSession) -> tuple[Path, ...]:
    paths = [
        Path(event.screenshot_path)
        for event in session.events
        if event.screenshot_path is not None
    ]
    return tuple(dict.fromkeys(paths))


def _verification_suggestions(task: TaskDefinition) -> tuple[str, ...]:
    suggestions: list[str] = []
    for step in task.steps:
        if step.verify is not None:
            suggestions.append(
                f"{step.id}: {step.verify.type}"
                + (f" {step.verify.text}" if step.verify.text else ""),
            )
    return tuple(suggestions)


def _recorded_tags(metadata: dict[str, object]) -> list[str]:
    tags = [*_metadata_string_list(metadata, "routine_tags"), "recorded"]
    return list(dict.fromkeys(tags))


def _recorded_safety_class(risk_class: str | None) -> str:
    if risk_class in {"low", "medium", "high", "sensitive"}:
        return risk_class
    if risk_class == "review_required":
        return "medium"
    return "low"


def _metadata_string(metadata: dict[str, object], key: str) -> str | None:
    value = metadata.get(key)
    return value if isinstance(value, str) and value else None


def _metadata_string_list(metadata: dict[str, object], key: str) -> list[str]:
    value = metadata.get(key)
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _metadata_positive_float(metadata: dict[str, object], key: str) -> float | None:
    value = metadata.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value) if value > 0 else None


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9._-]+", "-", value.casefold()).strip("-")
    return slug or "recorded-routine"


def _put_optional(
    payload: dict[str, object],
    key: str,
    value: object | None,
) -> None:
    if value is not None:
        payload[key] = value


def _routine_list_item(routine: RoutineDefinition) -> RoutineListItem:
    return RoutineListItem(
        routine_id=routine.id,
        name=routine.name,
        safety_class=routine.safety_class,
        approval_policy=routine.approval_policy,
        quarantine_status=routine_quarantine_status(routine),
    )


def _count_trace_values(values: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return counts


def _trace_health_status(
    trace_count: int,
    status_counts: Mapping[str, int],
) -> str:
    if trace_count == 0:
        return "empty"
    if _trace_attention_statuses(status_counts):
        return "attention"
    return "ok"


def _trace_attention_statuses(status_counts: Mapping[str, int]) -> tuple[str, ...]:
    return tuple(
        status
        for status in sorted(status_counts)
        if _trace_status_needs_attention(status) and status_counts[status] > 0
    )


def _trace_status_needs_attention(status: str) -> bool:
    return status in _TRACE_ATTENTION_STATUSES


def _trace_summary(trace_dir: Path) -> TraceSummary:
    replay_summary_path = _existing_replay_summary_path(trace_dir)
    for report_name, kind in _TRACE_REPORT_NAMES:
        report_path = trace_dir / report_name
        if report_path.exists():
            payload = _read_report_payload(report_path)
            return TraceSummary(
                trace_dir=trace_dir,
                report_path=report_path,
                status=_report_status_from_payload(payload),
                kind=kind,
                replay_summary_path=replay_summary_path,
                report_artifacts=_report_artifact_pairs(payload),
                trace_health_summary=_report_trace_health_pairs(payload),
                proof_summary=(
                    _report_proof_summary_pairs(payload)
                    if kind == "proof_suite"
                    else ()
                ),
            )
    return TraceSummary(
        trace_dir=trace_dir,
        report_path=None,
        status=None,
        kind="unknown",
        replay_summary_path=replay_summary_path,
    )


def _existing_replay_summary_path(trace_dir: Path) -> Path | None:
    path = trace_dir / "replay-summary.md"
    return path if path.exists() else None


_TRACE_REPORT_NAMES: tuple[tuple[str, str], ...] = (
    ("final-report.json", "run"),
    ("goal-plan-report.json", "goal_plan"),
    ("benchmark-report.json", "benchmark"),
    (PROOF_FINALIZATION_STATUS_NAME, "proof_suite"),
)

TRACE_HEALTH_SCHEMA_VERSION = "trace_health_v1"

_TRACE_ATTENTION_STATUSES = frozenset(
    {
        "blocked",
        "error",
        "failed",
        "invalid",
        "preflight_failed",
        "review_failed",
        "unknown",
    },
)


def _routine_pack_list_item(manifest: RoutinePackManifest) -> RoutinePackListItem:
    return RoutinePackListItem(
        pack_id=manifest.id,
        name=manifest.name,
        version=manifest.version,
        trust_level=manifest.trust_level,
        max_safety_class=manifest.safety.max_safety_class,
        trust_warning_count=len(routine_pack_trust_warnings(manifest)),
    )


def _report_status(report_path: Path) -> str | None:
    return _report_status_from_payload(_read_report_payload(report_path))


def _read_report_payload(report_path: Path) -> dict[str, object]:
    loaded = json.loads(report_path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        return {}
    return cast(dict[str, object], loaded)


def _report_status_from_payload(payload: Mapping[str, object]) -> str | None:
    status = payload.get("status")
    if isinstance(status, str):
        return status
    acceptance = payload.get("acceptance")
    if isinstance(acceptance, dict):
        acceptance_status = acceptance.get("status")
        if isinstance(acceptance_status, str):
            return acceptance_status
    return None


def _report_artifact_pairs(
    payload: Mapping[str, object],
) -> tuple[tuple[str, str], ...]:
    artifacts = payload.get("report_artifacts")
    if not isinstance(artifacts, dict):
        return ()
    return tuple(
        (key, value)
        for key, value in artifacts.items()
        if isinstance(key, str) and isinstance(value, str)
    )


def _report_trace_health_pairs(
    payload: Mapping[str, object],
) -> tuple[tuple[str, object], ...]:
    """Return stable scalar trace-health fields for trace list metadata."""

    summary = payload.get("trace_health_summary")
    if not isinstance(summary, dict):
        return ()
    allowed_keys = (
        "schema_version",
        "generated_at",
        "trace_count",
        "artifact_trace_count",
        "health_status",
    )
    return tuple(
        (key, value)
        for key in allowed_keys
        if isinstance((value := summary.get(key)), str)
        or _is_summary_int(value)
    )


def _report_proof_summary_pairs(
    payload: Mapping[str, object],
) -> tuple[tuple[str, int], ...]:
    """Return final proof summary counts for trace-health metadata."""

    summary = payload.get("summary")
    if not isinstance(summary, dict):
        return ()
    return tuple(
        (key, value)
        for key, value in summary.items()
        if isinstance(key, str) and _is_summary_int(value)
    )


def _is_summary_int(value: object) -> bool:
    """Return true for integer counts while excluding JSON booleans."""

    return isinstance(value, int) and not isinstance(value, bool)
