"""Local service boundary used by the native operator app."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

from desktop_agent.routines import (
    RoutineCatalog,
    RoutineDefinition,
    RoutineExecutionGate,
    load_routine_catalog,
    routine_execution_gate,
    routine_quarantine_status,
)
from desktop_agent.scheduler import RunQueue


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

    def metadata(self) -> dict[str, object]:
        return {
            "trace_dir": str(self.trace_dir),
            "report_path": str(self.report_path) if self.report_path else None,
            "status": self.status,
            "kind": self.kind,
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


class RunnerService(Protocol):
    """Run and dry-run API boundary for future UI wiring."""

    def execution_gate(self, routine_id: str) -> RoutineExecutionGate:
        """Return whether a routine can enter the execution pipeline."""
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


class TraceService(Protocol):
    """Local trace API boundary for future UI wiring."""

    def list_traces(self, *, limit: int = 50) -> tuple[TraceSummary, ...]:
        """Return local trace summaries."""
        ...

    def read_report(self, trace_dir: Path) -> dict[str, object]:
        """Read a trace report JSON file."""
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

    def capabilities(self) -> tuple[str, ...]:
        return (
            "start",
            "pause",
            "resume",
            "stop",
            "save",
            "discard",
            "generate_yaml",
        )


class LocalRunnerService:
    """Runner boundary that applies the catalog execution gate."""

    def __init__(self, catalog_service: LocalCatalogService) -> None:
        self._catalog_service = catalog_service

    def execution_gate(self, routine_id: str) -> RoutineExecutionGate:
        return routine_execution_gate(
            self._catalog_service._load_catalog(),
            routine_id,
        )


class LocalSchedulerService:
    """Scheduler boundary backed by the immutable local run queue model."""

    def __init__(self, queue: RunQueue | None = None) -> None:
        self._queue = queue or RunQueue()

    def queue_metadata(self) -> dict[str, object]:
        return self._queue.metadata()


class LocalApprovalService:
    """Approval boundary derived from routine approval policies."""

    def __init__(self, catalog_service: LocalCatalogService) -> None:
        self._catalog_service = catalog_service

    def routines_requiring_approval(self) -> tuple[RoutineListItem, ...]:
        catalog = self._catalog_service._load_catalog()
        routines = [
            routine
            for routine in catalog.routines
            if routine.approval_policy != "none"
            and routine_quarantine_status(routine) == "active"
        ]
        return tuple(_routine_list_item(routine) for routine in routines)


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
        for report_name in ("final-report.json", "goal-plan-report.json"):
            report_path = trace_dir / report_name
            if report_path.exists():
                loaded = json.loads(report_path.read_text(encoding="utf-8"))
                if not isinstance(loaded, dict):
                    raise OperatorServiceError("trace report must contain a mapping")
                return cast(dict[str, object], loaded)
        raise OperatorServiceError(f"trace report not found: {trace_dir}")


def default_local_operator_services(
    *,
    routine_pack_root: Path = Path("routine_packs"),
    trace_root: Path = Path("traces"),
) -> LocalOperatorServices:
    """Build the default local service bundle for the native app."""
    catalog = LocalCatalogService(routine_pack_root)
    return LocalOperatorServices(
        catalog=catalog,
        recorder=LocalRecorderService(),
        runner=LocalRunnerService(catalog),
        scheduler=LocalSchedulerService(),
        approvals=LocalApprovalService(catalog),
        traces=LocalTraceService(trace_root),
    )


def _routine_list_item(routine: RoutineDefinition) -> RoutineListItem:
    return RoutineListItem(
        routine_id=routine.id,
        name=routine.name,
        safety_class=routine.safety_class,
        approval_policy=routine.approval_policy,
        quarantine_status=routine_quarantine_status(routine),
    )


def _trace_summary(trace_dir: Path) -> TraceSummary:
    for report_name, kind in (
        ("final-report.json", "run"),
        ("goal-plan-report.json", "goal_plan"),
    ):
        report_path = trace_dir / report_name
        if report_path.exists():
            return TraceSummary(
                trace_dir=trace_dir,
                report_path=report_path,
                status=_report_status(report_path),
                kind=kind,
            )
    return TraceSummary(
        trace_dir=trace_dir,
        report_path=None,
        status=None,
        kind="unknown",
    )


def _report_status(report_path: Path) -> str | None:
    loaded = json.loads(report_path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        return None
    status = loaded.get("status")
    return status if isinstance(status, str) else None
