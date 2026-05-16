from datetime import UTC, datetime
from typing import cast

import pytest

from desktop_agent.routines import RoutineDefinition, routine_definition_from_mapping
from desktop_agent.scheduler import (
    RUN_QUEUE_STATUSES,
    RunQueue,
    RunQueueError,
    RunQueueStatus,
    SchedulerTraceKind,
    evaluate_scheduled_approval_gate,
    evaluate_scheduled_run_safety,
    scheduler_approval_gate_trace_event,
    scheduler_safety_gate_trace_event,
    scheduler_trace_event,
    select_schedule_time,
)
from desktop_agent.screen import ScreenObservation


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
    ["failed", "canceled", "stopped", "emergency_stopped", "handed_off"],
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


def test_scheduler_acceptance_pause_resume_cancel_and_retry_later() -> None:
    queue = RunQueue().enqueue("browser.read-page")
    queue = queue.transition("run-0001", "running", reason="window ready")
    queue = queue.transition("run-0001", "paused", reason="operator pause")
    queue = queue.transition("run-0001", "pending", reason="operator resume")
    retry_entry = queue.by_id("run-0001")
    assert retry_entry is not None

    retry_event = scheduler_trace_event(
        retry_entry,
        "retry_later",
        reason="cooldown active",
        retry_later_until="2026-05-16T10:00:00-04:00",
    )
    queue = queue.transition("run-0001", "canceled", reason="operator cancel")
    canceled_entry = queue.by_id("run-0001")
    assert canceled_entry is not None

    assert retry_event.metadata["scheduler_event"] == "retry_later"
    assert retry_event.metadata["retry_later_until"] == "2026-05-16T10:00:00-04:00"
    assert canceled_entry.status == "canceled"
    assert [transition.to_status for transition in canceled_entry.history] == [
        "running",
        "paused",
        "pending",
        "canceled",
    ]


def test_scheduler_acceptance_manual_handoff_terminal_state() -> None:
    queue = RunQueue().enqueue("browser.read-page")
    queue = queue.transition("run-0001", "running", reason="window ready")
    running_entry = queue.by_id("run-0001")
    assert running_entry is not None

    handoff_event = scheduler_trace_event(
        running_entry,
        "operator_intervention",
        reason="manual handoff requested",
        operator_intervention="manual_handoff",
    )
    queue = queue.transition("run-0001", "handed_off", reason="manual handoff")
    handed_off_entry = queue.by_id("run-0001")
    assert handed_off_entry is not None

    assert handoff_event.metadata["scheduler_event"] == "operator_intervention"
    assert handoff_event.metadata["operator_intervention"] == "manual_handoff"
    assert handed_off_entry.status == "handed_off"
    assert handed_off_entry.terminal is True


def test_scheduler_safety_gate_allows_ready_desktop_context() -> None:
    entry = RunQueue().enqueue("browser.read-page").next_pending()
    routine = _routine(required_app="Microsoft Edge", required_site="example.com")
    assert entry is not None

    decision = evaluate_scheduled_run_safety(
        entry,
        routine,
        ScreenObservation(
            size=(1920, 1080),
            active_window_title="Example.com - Microsoft Edge",
        ),
        allowed_windows=("Microsoft Edge",),
    )
    event = scheduler_safety_gate_trace_event(entry, decision)

    assert decision.allowed is True
    assert decision.reason == "scheduled_run_context_ready"
    assert event.phase == "scheduler_safety_gate"
    assert event.metadata["scheduler_safety_allowed"] is True
    assert event.metadata["required_app"] == "Microsoft Edge"


def test_scheduler_safety_gate_blocks_unready_desktop() -> None:
    entry = RunQueue().enqueue("browser.read-page").next_pending()
    routine = _routine(required_app="Microsoft Edge", required_site=None)
    assert entry is not None

    decision = evaluate_scheduled_run_safety(
        entry,
        routine,
        ScreenObservation(size=(0, 0), active_window_title=None),
    )

    assert decision.allowed is False
    assert decision.reason == "active_desktop_not_ready"
    assert scheduler_safety_gate_trace_event(entry, decision).metadata[
        "scheduler_safety_reason"
    ] == "active_desktop_not_ready"


def test_scheduler_safety_gate_blocks_wrong_allowed_app_context() -> None:
    entry = RunQueue().enqueue("browser.read-page").next_pending()
    routine = _routine(required_app="Microsoft Edge", required_site="example.com")
    assert entry is not None

    decision = evaluate_scheduled_run_safety(
        entry,
        routine,
        ScreenObservation(size=(1920, 1080), active_window_title="Notepad"),
        allowed_windows=("Microsoft Edge",),
    )

    assert decision.allowed is False
    assert decision.reason == "allowed_app_context_not_ready"
    assert decision.allowed_context_patterns == (
        "Microsoft Edge",
        "example.com",
    )


def test_scheduler_safety_gate_blocks_non_pending_runs() -> None:
    queue = RunQueue().enqueue("browser.read-page")
    queue = queue.transition("run-0001", "running", reason="already selected")
    entry = queue.by_id("run-0001")
    routine = _routine(required_app=None, required_site=None)
    assert entry is not None

    decision = evaluate_scheduled_run_safety(
        entry,
        routine,
        ScreenObservation(size=(1920, 1080), active_window_title="DeskPilot"),
    )

    assert decision.allowed is False
    assert decision.reason == "run_not_pending"


def test_scheduler_approval_gate_allows_read_only_scheduled_routine() -> None:
    entry = RunQueue().enqueue("browser.read-page").next_pending()
    routine = _routine(required_app=None, required_site=None)
    assert entry is not None

    decision = evaluate_scheduled_approval_gate(entry, routine)

    assert decision.allowed is True
    assert decision.approval_required is False
    assert decision.reason == "scheduled_external_mutation_not_declared"


def test_scheduler_approval_gate_blocks_unapproved_external_mutation() -> None:
    entry = (
        RunQueue()
        .enqueue("social-content.linkedin-approved-publish")
        .next_pending()
    )
    routine = _routine(
        required_app="Microsoft Edge",
        required_site="linkedin.com",
        approval_policy="confirm",
        max_external_mutations=1,
    )
    assert entry is not None

    decision = evaluate_scheduled_approval_gate(entry, routine)
    event = scheduler_approval_gate_trace_event(entry, decision)

    assert decision.allowed is False
    assert decision.approval_required is True
    assert decision.reason == "manual_approval_required"
    assert event.phase == "scheduler_approval_gate"
    assert event.metadata["scheduler_approval_allowed"] is False


def test_scheduler_approval_gate_requires_manifest_when_policy_requires_it() -> None:
    entry = (
        RunQueue()
        .enqueue("social-content.linkedin-approved-publish")
        .next_pending()
    )
    routine = _routine(
        required_app="Microsoft Edge",
        required_site="linkedin.com",
        approval_policy="manifest_required",
        safety_class="high",
        max_external_mutations=1,
    )
    assert entry is not None

    missing_manifest = evaluate_scheduled_approval_gate(
        entry,
        routine,
        operator_confirmed=True,
    )
    approved = evaluate_scheduled_approval_gate(
        entry,
        routine,
        operator_confirmed=True,
        approval_manifest_present=True,
    )

    assert missing_manifest.allowed is False
    assert missing_manifest.reason == "approval_manifest_required"
    assert approved.allowed is True
    assert approved.reason == "scheduled_external_mutation_approved"


def test_scheduler_approval_gate_blocks_non_pending_external_mutation() -> None:
    queue = RunQueue().enqueue("social-content.linkedin-approved-publish")
    queue = queue.transition("run-0001", "running", reason="already selected")
    entry = queue.by_id("run-0001")
    routine = _routine(
        required_app="Microsoft Edge",
        required_site="linkedin.com",
        approval_policy="confirm",
        max_external_mutations=1,
    )
    assert entry is not None

    decision = evaluate_scheduled_approval_gate(
        entry,
        routine,
        operator_confirmed=True,
    )

    assert decision.allowed is False
    assert decision.reason == "run_not_pending"


def test_seeded_schedule_time_selection_is_deterministic() -> None:
    routine = _routine(
        required_app=None,
        required_site=None,
        allowed_time_windows=[
            {
                "days": ["mon"],
                "start": "09:00",
                "end": "10:00",
                "timezone": "local",
            },
        ],
    )
    now = datetime(2026, 5, 18, 8, 30, tzinfo=UTC)

    first = select_schedule_time(routine, now=now, random_seed=123)
    second = select_schedule_time(routine, now=now, random_seed=123)

    assert first.selected_time == second.selected_time
    assert first.lower_bound == datetime(2026, 5, 18, 9, 0, tzinfo=UTC)
    assert first.upper_bound == datetime(2026, 5, 18, 10, 0, tzinfo=UTC)
    assert first.lower_bound <= first.selected_time <= first.upper_bound
    assert first.metadata()["random_seed"] == 123


def test_unseeded_schedule_time_selection_stays_inside_bounds() -> None:
    routine = _routine(
        required_app=None,
        required_site=None,
        allowed_time_windows=[
            {
                "days": ["mon"],
                "start": "09:00",
                "end": "10:00",
                "timezone": "local",
            },
        ],
    )
    now = datetime(2026, 5, 18, 9, 15, tzinfo=UTC)

    decision = select_schedule_time(routine, now=now)

    assert decision.lower_bound == now
    assert decision.upper_bound == datetime(2026, 5, 18, 10, 0, tzinfo=UTC)
    assert decision.lower_bound <= decision.selected_time <= decision.upper_bound
    assert decision.random_seed is None


def test_schedule_time_selection_uses_next_allowed_day() -> None:
    routine = _routine(
        required_app=None,
        required_site=None,
        allowed_time_windows=[
            {
                "days": ["mon"],
                "start": "09:00",
                "end": "10:00",
                "timezone": "local",
            },
        ],
    )
    now = datetime(2026, 5, 19, 12, 0, tzinfo=UTC)

    decision = select_schedule_time(routine, now=now, random_seed=1)

    assert decision.lower_bound == datetime(2026, 5, 25, 9, 0, tzinfo=UTC)
    assert decision.upper_bound == datetime(2026, 5, 25, 10, 0, tzinfo=UTC)


def _routine(
    *,
    required_app: str | None,
    required_site: str | None,
    approval_policy: str = "none",
    safety_class: str = "low",
    max_external_mutations: int | None = None,
    allowed_time_windows: list[dict[str, object]] | None = None,
) -> RoutineDefinition:
    payload: dict[str, object] = {
        "id": "browser.read-page",
        "name": "Browser read page",
        "description": "Read an owned browser page.",
        "goal": "Review visible page content.",
        "tags": ["browser", "reading"],
        "inputs": ["url"],
        "outputs": ["visible text"],
        "safety_class": safety_class,
        "schedule_policy": "scheduled",
        "approval_policy": approval_policy,
        "expected_duration_seconds": 30,
        "reference": {
            "type": "task",
            "path": "tasks/read-page.yaml",
        },
    }
    if required_app is not None:
        payload["required_app"] = required_app
    if required_site is not None:
        payload["required_site"] = required_site
    schedule: dict[str, object] = {}
    if max_external_mutations is not None:
        schedule["max_external_mutations"] = max_external_mutations
    if allowed_time_windows is not None:
        schedule["allowed_time_windows"] = allowed_time_windows
    if schedule:
        payload["schedule"] = schedule
    return routine_definition_from_mapping(payload)
