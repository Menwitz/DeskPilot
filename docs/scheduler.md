# Scheduler And Run Queue

DeskPilot's scheduler work starts with a local immutable run queue model. The
queue does not launch routines yet; it gives the scheduler, operator UI, traces,
and reports a shared state contract for routine runs.

## Queue States

- `pending`: queued and eligible for later selection.
- `running`: selected for execution; attempts are counted when entering this
  state.
- `paused`: intentionally stopped and resumable by the operator or scheduler.
- `blocked`: cannot run until a missing approval, context, time window, or
  dependency is resolved.
- `completed`: terminal success.
- `failed`: terminal failure.
- `canceled`: terminal operator or policy cancellation.
- `handed_off`: terminal manual handoff to the operator.

Valid transitions are enforced by `desktop_agent.scheduler.RunQueue`. Terminal
states cannot transition back to active work.

## Monitoring Metadata

Each queue entry exposes JSON-safe metadata:

- run ID, routine ID, sequence, status, priority, attempts, max attempts, and
  latest reason.
- terminal flag.
- state transition history with reason text.

The queue exposes aggregate status counts and entry metadata for future trace
events, operator UI run status, and scheduler reports.

## Trace Events

`desktop_agent.scheduler.scheduler_trace_event()` builds the shared
`TraceEvent` contract for scheduler decisions. Events use phase `scheduler` and
include the queue entry metadata plus `scheduler_event` and `scheduler_reason`.

Supported scheduler event kinds:

- `selected_time`: records the selected run time and requires `selected_time`.
- `wait`: records why the scheduler is waiting and requires `wait_reason`.
- `skip`: records why a queued run was skipped and requires `skip_reason`.
- `pause`: records a pause decision.
- `resume`: records a resume decision.
- `retry_later`: records a deferred retry and requires `retry_later_until`.
- `operator_intervention`: records a user action such as pause, stop, approval,
  or handoff and requires `operator_intervention`.

## Current Boundary

This model is local and deterministic. It does not schedule wall-clock jobs,
send desktop input, or bypass routine approvals. Later scheduler tasks will add
time-window eligibility, pause/resume controls, safety gates, and trace events
on top of this queue contract.
