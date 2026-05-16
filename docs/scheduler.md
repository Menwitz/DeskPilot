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
- `stopped`: terminal operator stop from the native app run controls.
- `emergency_stopped`: terminal emergency stop from app controls or runtime
  guardrails.
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

## Safety Gate

`evaluate_scheduled_run_safety()` blocks a queued routine before execution when
the active desktop is not observable, the run is no longer pending, or the
active window does not match the routine's required app/site or supplied
allowed-window patterns. The decision includes `scheduler_safety_allowed`,
`scheduler_safety_reason`, active window title, required app/site, and allowed
context patterns.

`scheduler_safety_gate_trace_event()` turns that decision into a local
`scheduler_safety_gate` trace event so reports can explain why a scheduled
routine ran or stayed blocked.

## Approval Gate

`evaluate_scheduled_approval_gate()` requires operator approval before a
scheduled routine that can perform external mutations is allowed to run. The
gate treats scheduled routines as approval-required when they have a non-`none`
approval policy, a `high` or `sensitive` safety class, or a positive
`max_external_mutations` schedule limit.

The gate blocks when manual approval is missing, when a manifest-required
routine has no manifest, or when the queued run is no longer pending.
`scheduler_approval_gate_trace_event()` emits phase `scheduler_approval_gate`
with approval policy, operator confirmation state, manifest presence, mutation
limit, and allow/block reason.

## Schedule Time Selection

`select_schedule_time()` chooses a run time inside the next allowed routine
schedule window. When a `random_seed` is supplied, the selected time is
reproducible. Without a seed, selection is still bounded by the computed lower
and upper window times, and the returned decision records those bounds for
trace and report review.

## Current Boundary

This model is local and deterministic. It does not schedule wall-clock jobs,
send desktop input, or bypass routine approvals. Later scheduler tasks will add
time-window eligibility, pause/resume controls, safety gates, and trace events
on top of this queue contract.
