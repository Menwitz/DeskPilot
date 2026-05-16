from typing import cast

import pytest

from desktop_agent.scheduler import (
    RUN_QUEUE_STATUSES,
    RunQueue,
    RunQueueError,
    RunQueueStatus,
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
