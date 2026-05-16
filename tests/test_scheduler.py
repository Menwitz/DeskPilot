from typing import cast

import pytest

from desktop_agent.scheduler import (
    RUN_QUEUE_STATUSES,
    RunQueue,
    RunQueueError,
    RunQueueStatus,
    SchedulerTraceKind,
    scheduler_trace_event,
)


def test_run_queue_enqueues_pending_entries_by_priority() -> None:
    queue = (
        RunQueue()
        .enqueue("browser.read-page", priority=50)
        .enqueue("native.notepad-draft", priority=10)
    )

    next_entry = queue.next_pending()

    assert next_entry is not None
    assert next_entry.id == "run-0002"
    assert next_entry.routine_id == "native.notepad-draft"
    assert queue.status_counts()["pending"] == 2


def test_run_queue_transitions_record_history_and_attempts() -> None:
    queue = RunQueue().enqueue("browser.read-page", max_attempts=2)

    queue = queue.transition("run-0001", "running", reason="allowed window ready")
    queue = queue.transition("run-0001", "paused", reason="operator pause")
    queue = queue.transition("run-0001", "running", reason="operator resume")
    queue = queue.transition("run-0001", "completed", reason="routine passed")

    entry = queue.by_id("run-0001")
    assert entry is not None
    assert entry.status == "completed"
    assert entry.attempts == 2
    assert entry.terminal is True
    assert [transition.to_status for transition in entry.history] == [
        "running",
        "paused",
        "running",
        "completed",
    ]
    metadata = entry.metadata()
    history = cast(list[dict[str, object]], metadata["history"])
    assert metadata["status"] == "completed"
    assert history[-1]["reason"] == "routine passed"


@pytest.mark.parametrize(
    "terminal_status",
    ["failed", "canceled", "handed_off"],
)
def test_run_queue_terminal_states_stop_later_transitions(
    terminal_status: str,
) -> None:
    queue = RunQueue().enqueue("browser.read-page")
    queue = queue.transition("run-0001", "running", reason="start")
    queue = queue.transition(
        "run-0001",
        cast(RunQueueStatus, terminal_status),
        reason="terminal",
    )

    with pytest.raises(RunQueueError, match="invalid run queue transition"):
        queue.transition("run-0001", "running", reason="restart")


def test_run_queue_blocks_and_releases_entries() -> None:
    queue = RunQueue().enqueue("social-content.linkedin-approved-publish")

    queue = queue.transition("run-0001", "blocked", reason="approval missing")
    queue = queue.transition("run-0001", "pending", reason="approval supplied")

    entry = queue.by_id("run-0001")
    assert entry is not None
    assert entry.status == "pending"
    assert entry.reason == "approval supplied"


def test_run_queue_rejects_invalid_entries_and_transitions() -> None:
    queue = RunQueue().enqueue("browser.read-page", run_id="morning")

    with pytest.raises(RunQueueError, match="duplicate run queue id"):
        queue.enqueue("browser.search-web", run_id="morning")
    with pytest.raises(RunQueueError, match="invalid run queue transition"):
        queue.transition("morning", "completed", reason="skip running")
    with pytest.raises(RunQueueError, match="exceeded max_attempts"):
        queue.transition("morning", "running", reason="first").transition(
            "morning",
            "paused",
            reason="pause",
        ).transition("morning", "running", reason="second")


def test_run_queue_metadata_summarizes_monitoring_state() -> None:
    queue = RunQueue().enqueue("browser.read-page").enqueue("native.notepad-draft")
    queue = queue.transition("run-0001", "running", reason="selected")
    queue = queue.transition("run-0002", "blocked", reason="context unavailable")

    metadata = queue.metadata()
    counts = cast(dict[str, int], metadata["run_queue_status_counts"])

    assert set(counts) == RUN_QUEUE_STATUSES
    assert metadata["run_queue_size"] == 2
    assert counts["running"] == 1
    assert counts["blocked"] == 1


def test_scheduler_trace_event_records_selected_time_and_queue_metadata() -> None:
    queue = RunQueue().enqueue("browser.read-page")
    entry = queue.next_pending()
    assert entry is not None

    event = scheduler_trace_event(
        entry,
        "selected_time",
        reason="inside allowed window",
        selected_time="2026-05-16T09:30:00-04:00",
    )

    assert event.phase == "scheduler"
    assert "scheduler selected-time" in event.message
    assert event.metadata["scheduler_event"] == "selected_time"
    assert event.metadata["selected_time"] == "2026-05-16T09:30:00-04:00"
    assert event.metadata["run_id"] == "run-0001"
    assert event.metadata["routine_id"] == "browser.read-page"


@pytest.mark.parametrize(
    ("kind", "field", "value"),
    [
        ("wait", "wait_reason", "cooldown_active"),
        ("skip", "skip_reason", "outside_allowed_window"),
        ("retry_later", "retry_later_until", "2026-05-16T10:00:00-04:00"),
        ("operator_intervention", "operator_intervention", "pause_button"),
    ],
)
def test_scheduler_trace_event_records_required_reason_fields(
    kind: str,
    field: str,
    value: str,
) -> None:
    entry = RunQueue().enqueue("browser.read-page").next_pending()
    assert entry is not None
    kwargs: dict[str, str | None] = {
        "wait_reason": None,
        "skip_reason": None,
        "retry_later_until": None,
        "operator_intervention": None,
    }
    kwargs[field] = value

    event = scheduler_trace_event(
        entry,
        cast(SchedulerTraceKind, kind),
        reason="scheduler decision",
        wait_reason=kwargs["wait_reason"],
        skip_reason=kwargs["skip_reason"],
        retry_later_until=kwargs["retry_later_until"],
        operator_intervention=kwargs["operator_intervention"],
    )

    assert event.metadata["scheduler_event"] == kind
    assert event.metadata[field] == value


@pytest.mark.parametrize(
    "kind",
    ["selected_time", "wait", "skip", "retry_later", "operator_intervention"],
)
def test_scheduler_trace_event_requires_kind_specific_fields(kind: str) -> None:
    entry = RunQueue().enqueue("browser.read-page").next_pending()
    assert entry is not None

    with pytest.raises(RunQueueError, match="is required"):
        scheduler_trace_event(
            entry,
            cast(SchedulerTraceKind, kind),
            reason="missing detail",
        )


@pytest.mark.parametrize("kind", ["pause", "resume"])
def test_scheduler_trace_event_records_pause_and_resume(kind: str) -> None:
    entry = RunQueue().enqueue("browser.read-page").next_pending()
    assert entry is not None

    event = scheduler_trace_event(
        entry,
        cast(SchedulerTraceKind, kind),
        reason=f"operator {kind}",
    )

    assert event.metadata["scheduler_event"] == kind
    assert event.metadata["scheduler_reason"] == f"operator {kind}"
