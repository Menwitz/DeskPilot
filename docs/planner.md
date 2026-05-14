# Planner And Execution Engine

The execution engine runs validated YAML tasks as a bounded state machine. It
keeps the loop platform-neutral and delegates screen capture, perception,
safety, actuation, and trace writing through interfaces.

Before safety checks or runtime observation, the engine compiles the validated
task into a static execution plan. The compiler rejects missing, duplicate,
self-referential, or forward `depends_on` references and checks authored
`expected_state` transitions for contradictions. Successful compilation emits a
`compile_task` trace event with step order, dependency, and state-transition
metadata for monitoring and reports.

## Runtime Controls

- Task timeout is the lower of `task.timeout_seconds` and
  `max_runtime_seconds`.
- Step timeout uses `step.timeout_seconds` when provided, otherwise
  `default_timeout_seconds`.
- Retry count uses `step.retry` when provided, otherwise
  `max_retries_per_step`.
- `max_steps` bounds both executed step transitions and action attempts so
  branch loops and retry loops cannot run forever.

## Special Actions

- `wait_for` polls, re-observes, and verifies until the condition is visible or
  the step timeout expires.
- `scroll_until` alternates candidate search with bounded scroll actions in the
  configured region.
- `branch_if_visible` continues when the condition is visible and jumps to
  `on_failure` when it is not.

## Verification

Configured verification runs after the action with a fresh observation and
perception pass. The default verifier supports visible text, not-visible text,
visible image, focused target metadata, window-title containment, and UIA
element existence.

## Recovery Tracing

Retry, wait, scroll, safety, and abort paths write trace events with enough
metadata to understand what the planner tried next. Recovery events identify
the planned recovery action such as waiting and re-observing, scrolling a search
region, retrying another candidate on the next attempt, or aborting with trace.
The recovery policy layer classifies stale observations, missed targets,
disabled controls, occluded controls, and transient loading states before
emitting retry metadata. Failed action attempts also take a fresh read-only
screen observation before retrying, run candidate detection against that
observation, and attach the chosen recovery path to the trace and final report.
Retry waits use bounded backoff from the recovery reason and are sampled within
the configured retry delay range and retry budget.
Target selection failures are split into recoverable UI states and true
ambiguity. Stale observations, missing targets with no candidates, disabled
controls, occluded controls, and loading states can retry inside the step retry
budget. Duplicated visible labels and low-confidence candidates still stop at
the ambiguity gate before any desktop action.
Failed step reports also carry a `failure_category` so operators can separate
perception failures, selection ambiguity, safety stops, verification failures,
and actuation failures without parsing free-form messages.
