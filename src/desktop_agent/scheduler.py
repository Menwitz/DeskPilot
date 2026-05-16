"""Local routine run queue models for future scheduled execution."""

from __future__ import annotations

import random
from dataclasses import dataclass, replace
from datetime import datetime, time, timedelta
from typing import Literal

from desktop_agent.routines import RoutineDefinition, RoutineTimeWindow
from desktop_agent.screen import ScreenObservation
from desktop_agent.tracing import TraceEvent
from desktop_agent.window_allowlist import window_title_matches

RunQueueStatus = Literal[
    "pending",
    "running",
    "paused",
    "blocked",
    "completed",
    "failed",
    "canceled",
    "handed_off",
]
SchedulerTraceKind = Literal[
    "selected_time",
    "wait",
    "skip",
    "pause",
    "resume",
    "retry_later",
    "operator_intervention",
]

RUN_QUEUE_STATUSES: frozenset[str] = frozenset(
    {
        "pending",
        "running",
        "paused",
        "blocked",
        "completed",
        "failed",
        "canceled",
        "handed_off",
    },
)
TERMINAL_RUN_QUEUE_STATUSES: frozenset[str] = frozenset(
    {"completed", "failed", "canceled", "handed_off"},
)
RUN_QUEUE_TRANSITIONS: dict[RunQueueStatus, frozenset[RunQueueStatus]] = {
    "pending": frozenset({"running", "paused", "blocked", "canceled", "handed_off"}),
    "running": frozenset(
        {"paused", "blocked", "completed", "failed", "canceled", "handed_off"},
    ),
    "paused": frozenset({"pending", "running", "canceled", "handed_off"}),
    "blocked": frozenset({"pending", "running", "failed", "canceled", "handed_off"}),
    "completed": frozenset(),
    "failed": frozenset(),
    "canceled": frozenset(),
    "handed_off": frozenset(),
}
SCHEDULER_TRACE_KINDS: frozenset[str] = frozenset(
    {
        "selected_time",
        "wait",
        "skip",
        "pause",
        "resume",
        "retry_later",
        "operator_intervention",
    },
)
SCHEDULE_WEEKDAY_INDEX: dict[str, int] = {
    "mon": 0,
    "tue": 1,
    "wed": 2,
    "thu": 3,
    "fri": 4,
    "sat": 5,
    "sun": 6,
}


class RunQueueError(ValueError):
    """Raised when queue entries or state transitions are invalid."""


@dataclass(frozen=True)
class RunQueueTransition:
    """Auditable state movement for one queued routine run."""

    from_status: RunQueueStatus
    to_status: RunQueueStatus
    reason: str

    def metadata(self) -> dict[str, object]:
        return {
            "from_status": self.from_status,
            "to_status": self.to_status,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class RunQueueEntry:
    """One scheduled or manually queued routine run."""

    id: str
    routine_id: str
    sequence: int
    status: RunQueueStatus = "pending"
    priority: int = 100
    attempts: int = 0
    max_attempts: int = 1
    reason: str | None = None
    history: tuple[RunQueueTransition, ...] = ()

    @property
    def terminal(self) -> bool:
        return self.status in TERMINAL_RUN_QUEUE_STATUSES

    def transition_to(
        self,
        status: RunQueueStatus,
        *,
        reason: str,
    ) -> RunQueueEntry:
        """Return a copy moved to another valid queue state."""
        _validate_transition(self.status, status)
        attempts = self.attempts + 1 if status == "running" else self.attempts
        if attempts > self.max_attempts:
            raise RunQueueError("run queue entry exceeded max_attempts")
        transition = RunQueueTransition(
            from_status=self.status,
            to_status=status,
            reason=reason,
        )
        return replace(
            self,
            status=status,
            attempts=attempts,
            reason=reason,
            history=(*self.history, transition),
        )

    def metadata(self) -> dict[str, object]:
        return {
            "run_id": self.id,
            "routine_id": self.routine_id,
            "sequence": self.sequence,
            "status": self.status,
            "priority": self.priority,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "reason": self.reason,
            "terminal": self.terminal,
            "history": [transition.metadata() for transition in self.history],
        }


@dataclass(frozen=True)
class SchedulerSafetyGateDecision:
    """Decision that allows or blocks a scheduled routine before execution."""

    allowed: bool
    reason: str
    active_window_title: str | None
    allowed_context_patterns: tuple[str, ...]
    required_app: str | None = None
    required_site: str | None = None

    def metadata(self) -> dict[str, object]:
        return {
            "scheduler_safety_allowed": self.allowed,
            "scheduler_safety_reason": self.reason,
            "active_window_title": self.active_window_title,
            "allowed_context_patterns": list(self.allowed_context_patterns),
            "required_app": self.required_app,
            "required_site": self.required_site,
        }


@dataclass(frozen=True)
class SchedulerApprovalGateDecision:
    """Decision that allows or blocks scheduled external mutation work."""

    allowed: bool
    approval_required: bool
    reason: str
    approval_policy: str
    operator_confirmed: bool
    approval_manifest_present: bool
    max_external_mutations: int | None

    def metadata(self) -> dict[str, object]:
        return {
            "scheduler_approval_allowed": self.allowed,
            "scheduler_approval_required": self.approval_required,
            "scheduler_approval_reason": self.reason,
            "approval_policy": self.approval_policy,
            "operator_confirmed": self.operator_confirmed,
            "approval_manifest_present": self.approval_manifest_present,
            "max_external_mutations": self.max_external_mutations,
        }


@dataclass(frozen=True)
class ScheduleTimeDecision:
    """Selected wall-clock time inside a routine schedule window."""

    selected_time: datetime
    lower_bound: datetime
    upper_bound: datetime
    reason: str
    random_seed: int | None = None
    window: RoutineTimeWindow | None = None

    def metadata(self) -> dict[str, object]:
        return {
            "selected_time": self.selected_time.isoformat(),
            "schedule_lower_bound": self.lower_bound.isoformat(),
            "schedule_upper_bound": self.upper_bound.isoformat(),
            "schedule_time_reason": self.reason,
            "random_seed": self.random_seed,
            "schedule_window": self.window.metadata() if self.window else None,
        }


@dataclass(frozen=True)
class RunQueue:
    """Immutable queue used by scheduler tests and future operator UI state."""

    entries: tuple[RunQueueEntry, ...] = ()

    def enqueue(
        self,
        routine_id: str,
        *,
        run_id: str | None = None,
        priority: int = 100,
        max_attempts: int = 1,
        reason: str | None = None,
    ) -> RunQueue:
        """Return a queue with a new pending routine run appended."""
        if not routine_id.strip():
            raise RunQueueError("routine_id is required")
        sequence = len(self.entries) + 1
        entry_id = run_id or f"run-{sequence:04d}"
        if not entry_id.strip():
            raise RunQueueError("run_id is required")
        if self.by_id(entry_id) is not None:
            raise RunQueueError(f"duplicate run queue id: {entry_id}")
        if max_attempts <= 0:
            raise RunQueueError("max_attempts must be greater than zero")
        entry = RunQueueEntry(
            id=entry_id,
            routine_id=routine_id,
            sequence=sequence,
            priority=priority,
            max_attempts=max_attempts,
            reason=reason,
        )
        return RunQueue(entries=(*self.entries, entry))

    def by_id(self, run_id: str) -> RunQueueEntry | None:
        for entry in self.entries:
            if entry.id == run_id:
                return entry
        return None

    def next_pending(self) -> RunQueueEntry | None:
        pending = [entry for entry in self.entries if entry.status == "pending"]
        if not pending:
            return None
        return min(pending, key=lambda entry: (entry.priority, entry.sequence))

    def transition(
        self,
        run_id: str,
        status: RunQueueStatus,
        *,
        reason: str,
    ) -> RunQueue:
        """Return a queue with one entry moved through a valid transition."""
        updated_entries: list[RunQueueEntry] = []
        found = False
        for entry in self.entries:
            if entry.id != run_id:
                updated_entries.append(entry)
                continue
            found = True
            updated_entries.append(entry.transition_to(status, reason=reason))
        if not found:
            raise RunQueueError(f"unknown run queue id: {run_id}")
        return RunQueue(entries=tuple(updated_entries))

    def status_counts(self) -> dict[str, int]:
        counts = {status: 0 for status in sorted(RUN_QUEUE_STATUSES)}
        for entry in self.entries:
            counts[entry.status] += 1
        return counts

    def metadata(self) -> dict[str, object]:
        return {
            "run_queue_size": len(self.entries),
            "run_queue_status_counts": self.status_counts(),
            "run_queue_entries": [entry.metadata() for entry in self.entries],
        }


def select_schedule_time(
    routine: RoutineDefinition,
    *,
    now: datetime,
    random_seed: int | None = None,
) -> ScheduleTimeDecision:
    """Select a bounded run time from a routine's allowed schedule windows."""
    window_bounds = _next_schedule_window_bounds(routine, now)
    if window_bounds is None:
        return ScheduleTimeDecision(
            selected_time=now,
            lower_bound=now,
            upper_bound=now,
            reason="no_schedule_window_declared",
            random_seed=random_seed,
        )
    window, lower_bound, upper_bound = window_bounds
    sampler = random.Random(random_seed) if random_seed is not None else random.Random()
    fraction = sampler.random()
    duration_seconds = (upper_bound - lower_bound).total_seconds()
    selected_time = lower_bound + timedelta(seconds=duration_seconds * fraction)
    return ScheduleTimeDecision(
        selected_time=selected_time,
        lower_bound=lower_bound,
        upper_bound=upper_bound,
        reason="selected_inside_allowed_time_window",
        random_seed=random_seed,
        window=window,
    )


def evaluate_scheduled_approval_gate(
    entry: RunQueueEntry,
    routine: RoutineDefinition,
    *,
    operator_confirmed: bool = False,
    approval_manifest_present: bool = False,
) -> SchedulerApprovalGateDecision:
    """Require explicit approval before scheduled external mutation work."""
    approval_required = _scheduled_external_mutation_requires_approval(routine)
    if not approval_required:
        return SchedulerApprovalGateDecision(
            allowed=True,
            approval_required=False,
            reason="scheduled_external_mutation_not_declared",
            approval_policy=routine.approval_policy,
            operator_confirmed=operator_confirmed,
            approval_manifest_present=approval_manifest_present,
            max_external_mutations=routine.schedule.max_external_mutations,
        )
    if entry.status != "pending":
        return _scheduled_approval_decision(
            routine,
            allowed=False,
            approval_required=True,
            reason="run_not_pending",
            operator_confirmed=operator_confirmed,
            approval_manifest_present=approval_manifest_present,
        )
    if not operator_confirmed:
        return _scheduled_approval_decision(
            routine,
            allowed=False,
            approval_required=True,
            reason="manual_approval_required",
            operator_confirmed=operator_confirmed,
            approval_manifest_present=approval_manifest_present,
        )
    if (
        routine.approval_policy == "manifest_required"
        and not approval_manifest_present
    ):
        return _scheduled_approval_decision(
            routine,
            allowed=False,
            approval_required=True,
            reason="approval_manifest_required",
            operator_confirmed=operator_confirmed,
            approval_manifest_present=approval_manifest_present,
        )
    return _scheduled_approval_decision(
        routine,
        allowed=True,
        approval_required=True,
        reason="scheduled_external_mutation_approved",
        operator_confirmed=operator_confirmed,
        approval_manifest_present=approval_manifest_present,
    )


def scheduler_approval_gate_trace_event(
    entry: RunQueueEntry,
    decision: SchedulerApprovalGateDecision,
) -> TraceEvent:
    """Build the trace event emitted when scheduled approval gating runs."""
    status = "passed" if decision.allowed else "blocked"
    return TraceEvent(
        phase="scheduler_approval_gate",
        message=f"scheduled approval gate {status}: {decision.reason}",
        metadata={
            **entry.metadata(),
            **decision.metadata(),
        },
    )


def evaluate_scheduled_run_safety(
    entry: RunQueueEntry,
    routine: RoutineDefinition,
    observation: ScreenObservation,
    *,
    allowed_windows: tuple[str, ...] = (),
) -> SchedulerSafetyGateDecision:
    """Check whether the active desktop is ready for a scheduled routine."""
    patterns = _scheduler_allowed_context_patterns(routine, allowed_windows)
    if entry.status != "pending":
        return SchedulerSafetyGateDecision(
            allowed=False,
            reason="run_not_pending",
            active_window_title=observation.active_window_title,
            allowed_context_patterns=patterns,
            required_app=routine.required_app,
            required_site=routine.required_site,
        )
    if not _active_desktop_ready(observation):
        return SchedulerSafetyGateDecision(
            allowed=False,
            reason="active_desktop_not_ready",
            active_window_title=observation.active_window_title,
            allowed_context_patterns=patterns,
            required_app=routine.required_app,
            required_site=routine.required_site,
        )
    if patterns and not window_title_matches(observation.active_window_title, patterns):
        return SchedulerSafetyGateDecision(
            allowed=False,
            reason="allowed_app_context_not_ready",
            active_window_title=observation.active_window_title,
            allowed_context_patterns=patterns,
            required_app=routine.required_app,
            required_site=routine.required_site,
        )
    return SchedulerSafetyGateDecision(
        allowed=True,
        reason="scheduled_run_context_ready",
        active_window_title=observation.active_window_title,
        allowed_context_patterns=patterns,
        required_app=routine.required_app,
        required_site=routine.required_site,
    )


def scheduler_safety_gate_trace_event(
    entry: RunQueueEntry,
    decision: SchedulerSafetyGateDecision,
) -> TraceEvent:
    """Build the trace event emitted when the scheduler safety gate runs."""
    status = "passed" if decision.allowed else "blocked"
    return TraceEvent(
        phase="scheduler_safety_gate",
        message=f"scheduled run safety gate {status}: {decision.reason}",
        metadata={
            **entry.metadata(),
            **decision.metadata(),
        },
    )


def _scheduled_external_mutation_requires_approval(
    routine: RoutineDefinition,
) -> bool:
    mutation_cap = routine.schedule.max_external_mutations
    return (
        routine.schedule_policy == "scheduled"
        and (
            routine.approval_policy != "none"
            or routine.safety_class in {"high", "sensitive"}
            or (mutation_cap is not None and mutation_cap > 0)
        )
    )


def _next_schedule_window_bounds(
    routine: RoutineDefinition,
    now: datetime,
) -> tuple[RoutineTimeWindow, datetime, datetime] | None:
    if not routine.schedule.allowed_time_windows:
        return None
    candidates: list[tuple[RoutineTimeWindow, datetime, datetime]] = []
    for day_offset in range(8):
        candidate_day = now + timedelta(days=day_offset)
        for window in routine.schedule.allowed_time_windows:
            if not _window_allows_day(window, candidate_day.weekday()):
                continue
            start_at = datetime.combine(
                candidate_day.date(),
                _parse_schedule_time(window.start),
                tzinfo=now.tzinfo,
            )
            end_at = datetime.combine(
                candidate_day.date(),
                _parse_schedule_time(window.end),
                tzinfo=now.tzinfo,
            )
            if end_at <= start_at:
                end_at += timedelta(days=1)
            lower_bound = max(now, start_at)
            if lower_bound <= end_at:
                candidates.append((window, lower_bound, end_at))
    if not candidates:
        return None
    return min(candidates, key=lambda item: item[1])


def _window_allows_day(window: RoutineTimeWindow, weekday: int) -> bool:
    if not window.days:
        return True
    return any(SCHEDULE_WEEKDAY_INDEX[day] == weekday for day in window.days)


def _parse_schedule_time(value: str) -> time:
    hour, minute = value.split(":", maxsplit=1)
    return time(hour=int(hour), minute=int(minute))


def _scheduled_approval_decision(
    routine: RoutineDefinition,
    *,
    allowed: bool,
    approval_required: bool,
    reason: str,
    operator_confirmed: bool,
    approval_manifest_present: bool,
) -> SchedulerApprovalGateDecision:
    return SchedulerApprovalGateDecision(
        allowed=allowed,
        approval_required=approval_required,
        reason=reason,
        approval_policy=routine.approval_policy,
        operator_confirmed=operator_confirmed,
        approval_manifest_present=approval_manifest_present,
        max_external_mutations=routine.schedule.max_external_mutations,
    )


def scheduler_trace_event(
    entry: RunQueueEntry,
    kind: SchedulerTraceKind,
    *,
    reason: str,
    selected_time: str | None = None,
    wait_reason: str | None = None,
    skip_reason: str | None = None,
    retry_later_until: str | None = None,
    operator_intervention: str | None = None,
) -> TraceEvent:
    """Build a scheduler TraceEvent with stable queue/report metadata."""
    if not reason.strip():
        raise RunQueueError("scheduler trace reason is required")
    _validate_scheduler_trace_fields(
        kind,
        selected_time=selected_time,
        wait_reason=wait_reason,
        skip_reason=skip_reason,
        retry_later_until=retry_later_until,
        operator_intervention=operator_intervention,
    )
    metadata = {
        **entry.metadata(),
        "scheduler_event": kind,
        "scheduler_reason": reason,
    }
    _put_optional(metadata, "selected_time", selected_time)
    _put_optional(metadata, "wait_reason", wait_reason)
    _put_optional(metadata, "skip_reason", skip_reason)
    _put_optional(metadata, "retry_later_until", retry_later_until)
    _put_optional(metadata, "operator_intervention", operator_intervention)
    return TraceEvent(
        phase="scheduler",
        message=_scheduler_trace_message(entry, kind, reason),
        metadata=metadata,
    )


def _validate_scheduler_trace_fields(
    kind: SchedulerTraceKind,
    *,
    selected_time: str | None,
    wait_reason: str | None,
    skip_reason: str | None,
    retry_later_until: str | None,
    operator_intervention: str | None,
) -> None:
    if kind not in SCHEDULER_TRACE_KINDS:
        raise RunQueueError(f"unsupported scheduler trace event: {kind}")
    required_by_kind = {
        "selected_time": ("selected_time", selected_time),
        "wait": ("wait_reason", wait_reason),
        "skip": ("skip_reason", skip_reason),
        "retry_later": ("retry_later_until", retry_later_until),
        "operator_intervention": ("operator_intervention", operator_intervention),
    }
    required = required_by_kind.get(kind)
    if required is None:
        return
    field_name, value = required
    if value is None or not value.strip():
        raise RunQueueError(f"{field_name} is required for scheduler {kind} events")


def _scheduler_trace_message(
    entry: RunQueueEntry,
    kind: SchedulerTraceKind,
    reason: str,
) -> str:
    label = kind.replace("_", "-")
    return f"scheduler {label} for {entry.id} ({entry.routine_id}): {reason}"


def _put_optional(
    metadata: dict[str, object],
    key: str,
    value: str | None,
) -> None:
    if value is not None:
        metadata[key] = value


def _scheduler_allowed_context_patterns(
    routine: RoutineDefinition,
    allowed_windows: tuple[str, ...],
) -> tuple[str, ...]:
    patterns = [
        *allowed_windows,
        *(entry for entry in (routine.required_app, routine.required_site) if entry),
    ]
    return tuple(dict.fromkeys(patterns))


def _active_desktop_ready(observation: ScreenObservation) -> bool:
    return (
        observation.size[0] > 0
        and observation.size[1] > 0
        and bool(observation.active_window_title)
    )


def _validate_transition(
    from_status: RunQueueStatus,
    to_status: RunQueueStatus,
) -> None:
    if to_status not in RUN_QUEUE_STATUSES:
        raise RunQueueError(f"unsupported run queue status: {to_status}")
    if to_status not in RUN_QUEUE_TRANSITIONS[from_status]:
        raise RunQueueError(
            f"invalid run queue transition: {from_status} -> {to_status}",
        )
