"""Local routine run queue models for future scheduled execution."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

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
