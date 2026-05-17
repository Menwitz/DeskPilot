# Tracing And Reports

DeskPilot writes local trace artifacts for every CLI run. The trace sink creates
a unique run directory under `trace_root` and then hands that directory back to
the execution pipeline as the active `config.trace_root`.

## Files

- `config.json` stores the normalized runtime configuration used by the run.
- `task.json` stores the normalized task definition.
- `action-log.jsonl` stores every trace event as newline-delimited JSON.
- `trace-schema.json` stores the TraceSchemaV2 contract used by the run.
- `safety-audit.json` stores an execution-profile safety audit when
  `execution_profile.enabled` is true.
- `safety-audit.md` stores the human-readable safety audit for the same runs.
- `final-report.json` stores the machine-readable final report.
- `final-report.md` stores a human-readable report.
- `screenshots/` receives screen captures when `save_screenshots` is enabled.
- `ocr/` receives OCR output when `save_ocr_text` is enabled.
- `overlays/` receives computer-vision candidate overlays when screenshot
  saving is enabled.

Approval manifests and content variable files are not copied into the trace
directory. Trace metadata records their local path, approved step IDs, variable
names, and content fingerprint so operators can audit the run without exposing
raw content payloads in reports.

When `redaction_policy.evidence_mode` is `metadata_only`, the resolved runtime
config disables screenshot and OCR text artifact files while preserving
structured trace metadata, action logs, and reports.
Failed metadata-only runs must still keep enough local report metadata to debug
the failure path: final reports retain the abort reason, failed step status,
candidate ID, failure category, candidate rankings, before/after observation
metadata, cursor/focus details when available, and the action-log event stream.
Leaving `redaction_policy` unset, or explicitly setting `evidence_mode: full`,
keeps screenshot and OCR artifact capture enabled when the matching
`save_screenshots` and `save_ocr_text` settings are also enabled.

## Report Contents

The final report includes the task name, final status, abort reason when
present, step reports, selected candidate IDs, event metadata, candidate
rankings, confidence values, screenshot paths, timing decisions, and the trace
directory. Step reports and step-related trace events include `step_category`
metadata so benchmark and timing analysis can group navigation, recognition,
data-entry, verification, and submission work. Enabled `execution_timing` events
also include `execution_persona`, `persona_timing_bias`, `klm_operators`,
`klm_operator_counts`, `klm_total_seconds`, and input-mode metadata for the
bounded cognitive timing model. Timing events include `random_seed` and
`sample_records` entries for every sampled value used in the decision. Each
sample record includes its label, value, and lower and upper bounds so seeded
randomness can be replayed and checked against the configured range.
The active `policy_preset` is stored in `config.json` and the `load_config`
event so report review can tell whether the run used strict QA, personal
automation, or exploratory-testing safety behavior.
`config.json` also records `require_operator_approval`, which is enabled by CLI
real runs after operator prompts are processed.
Scheduler decisions use phase `scheduler` and include `scheduler_event`,
`scheduler_reason`, run queue entry metadata, and the event-specific fields for
selected time, wait reason, skip reason, retry-later time, or operator
intervention. These events make queued routine decisions reviewable before the
future scheduler starts desktop input.
Scheduler safety checks use phase `scheduler_safety_gate` and include
`scheduler_safety_allowed`, `scheduler_safety_reason`, active-window title,
required app/site, and allowed context patterns so a blocked scheduled run can
be traced back to desktop readiness or app-context mismatch.
Scheduled approval checks use phase `scheduler_approval_gate` and include
`scheduler_approval_allowed`, `scheduler_approval_required`, approval policy,
operator confirmation state, approval-manifest presence, mutation limit, and
the block/pass reason.
For sensitive site workflows, final report metadata records validated approval
manifest fields and content-variable fingerprints, while step metadata records
variable names, masked variable names, or counts according to
`redaction_policy.content_variables`, always with
`content_variables_redacted: true`.
For execution-profile runs, `safety-audit.json` and `safety-audit.md` summarize
the active policy preset, operator-approval state, allowed windows, emergency
stop hotkey, sensitive steps, checkpoint coverage, and audit findings.
Text-entry `execute_action` events include `keyboard_cadence_applied`,
`keyboard_interval_count`, and `keyboard_interval_seconds` when a cadence
profile inserts bounded waits between typed characters. The Markdown report
prints the interval count on the action row.
When `redaction_policy.typed_text` is `mask` or `suppress`, action metadata also
records the typed-text redaction mode and a masked or suppressed value; the
actuator still sends the original text to the local desktop.
Scroll `execute_action` events include `scroll_cadence_applied`,
`scroll_step_count`, `scroll_step_clicks`, and `scroll_interval_seconds` when a
cadence profile splits a multi-click wheel action. The Markdown report prints
the emitted step count on the action row.

Pre-action `observe_screen` events include `pre_action_evidence` before
candidate detection or desktop input runs. The evidence bundle contains the
screenshot path, active-window title, active-window process metadata when
available, focused element metadata when available, cursor readback and cursor
position, monitor geometry, and DPI scale. These fields are also stored as event
metadata in `final-report.json` for report and replay tooling.
Post-action `observe_after_action` events and failed-attempt
`reobserve_after_failure` events include `post_action_evidence` with the same
desktop evidence fields plus observer warnings, so verification and recovery
reports can show what changed after input.
After verification, the planner emits `state_delta` with before/after screenshot
paths, focus changes, visible text additions/removals, target
appearance/disappearance, and scroll movement metadata from the emitted input.
`verify_result` events include `verification_outcome` with `passed`, `failed`,
or `inconclusive`. Inconclusive verification uses bounded retry recovery while
retry budget remains; exhausted inconclusive checks emit `manual_handoff` with
`manual_handoff_required: true`.
Authored `manual_handoff` actions emit a `manual_handoff` event before resume
verification with `handoff_prompt`, `expected_operator_work`, and
`resume_verification` metadata.

The `compile_task` event records static step order, dependency edges, and
expected UI state transitions before the planner observes the screen or attempts
input. Task JSON also stores each step's `depends_on` and `expected_state`
contracts for report review.
It also records `compiled_execution_model: desktop_io_v1` and
`desktop_io_steps`, preserving existing YAML actions while exposing the
lower-level operation sequence each step will use. Each compiled operation is
reported as a schema action with stable ID, order, kind, source step, source
semantic action, kind contract, and metadata fields. Kind contracts identify
the input channel, supported status, target requirement, boundedness, and
whether the operation emits desktop input. Operation metadata includes the same
resolved action-safety fields used by planner events and step reports. Invalid
desktop I/O action schemas fail compilation before runtime observation or input.
For report consumers, each compiled action also surfaces a top-level `safety`
object with approval requirement, approval reason, reversibility, idempotence,
allowed window scope, and allowed region.

The `execution_path` event records whether an action attempt uses the standard,
fast, or careful path. Fast-path timing events include the original sampled
delay, the reduced lower-bound delay, and the reduction amount. Careful-path
timing events include the original sampled delay, the upper-bound delay, and the
extension amount. Both paths include target confidence and
`safety_checks_required: true` so reports can confirm path selection did not
remove safety checks.
The `desktop_io_plan` event records how each semantic YAML action maps to
low-level desktop operations such as `observe`, `move`, `click`, `type`,
`hotkey`, `wheel`, `verify`, and `wait`. The same operation list is copied onto
`execute_action` metadata.
The `action_safety` event records the resolved safety class, mutation risk,
approval requirement and reason, reversibility, idempotence, allowed window
scope, and allowed region before a step can emit input. The same core safety
fields are also included on step-related monitoring events and step reports.

For steps with `checkpoint`, traces include `observe_checkpoint`,
`checkpoint_candidates`, and `verification_checkpoint` before any action timing
or actuation event. Failed checkpoints are categorized as
`verification_checkpoint` failures in the final report.

`task_state` events record completed dependency checks and the planner's local
believed UI state before and after steps. State failures are categorized as
`task_state` failures, which makes skipped setup or invalid branch paths visible
in reports.

`input_wait` events record requested and elapsed action-delay seconds after
timing decisions and before `execute_action`, providing evidence that real
desktop input was delayed by the timing controller. If the emergency stop trips
during an action wait or retry wait, the planner records an `emergency_stop`
event with `timing_phase`, requested and elapsed wait seconds, and the
`emergency_stop_boundary` that stopped the run.

Each executed step also emits `step_timeout_budget` metadata with the planned
action wait, retry wait, total planned wait, remaining timeout, and whether the
budget fits before any desktop action is attempted.

Task artifacts include task-level and step-level `entropy_budget` values, and
step-related trace events include explicit `step_entropy_budget` metadata when a
step has one. The planner also emits an `entropy_budget` event that summarizes
the checked task and step allocations, including runtime capacity derived from
max-step, retry, and timeout-feasible timing limits.

When a step declares `safe_action_variants`, the planner emits an
`action_variant` event with the available variants, selected action, configured
variant distribution, whether a randomized selection was used, and the seed and
sample records behind that selection.

Recovery events include `recovery_policy`, `recovery_reason`, and
`recovery_actions` so reports can distinguish stale observations, missed
targets, disabled controls, occluded controls, and transient loading states.
When a step has an explicit `recovery` rule, recovery events also include the
allowed actions and whether the default policy was constrained by that rule.
Constrained recovery events include `recovery_rejected_policy_actions`, and the
Markdown report prints rejected actions on the recovery row.
Failed action attempts emit `reobserve_after_failure` before retry metadata is
written. The recovery monitor then runs candidate detection on the fresh
observation and records `recover_candidates`, so deep-search output is visible
in the trace. Recovery events also include `recovery_chosen_action`,
`recovery_path`, `recovery_path_summary`, and `reobserve_before_retry`; the
Markdown report prints the path summary on recovery rows. The same event
includes `recovery_tree_actions`, `recovery_tree_chosen_action`,
`recovery_tree_can_retry`, and `recovery_tree_requires_operator` so the operator
UI can show the concrete recovery tree for refocus, reobserve, alternate
candidate, scroll search, wait, reopen-surface, and handoff branches.
Focus-loss recovery records a `focus_loss` recovery event, invokes only the
allowed-window refocus controller, captures `observe_after_refocus`, and stores
`post_refocus_verification_passed` with the post-refocus active-window title.
Layout-change recovery records a `layout_change` recovery event when normal
selection fails across multiple candidate families. The event includes
`selector_family_attempts`, `alternate_selector_family`, and
`alternate_selector_candidate_id`, and the following `select_target` event shows
whether that alternate family resolved the target.
Retry timing events and recovery events include bounded-backoff metadata:
`retry_backoff_strategy`, `retry_index`, `retry_budget`,
`retry_backoff_fraction`, and `retry_limit_respected`.
Selection recovery uses the same `recover` event contract. Ambiguous duplicated
labels keep `selection_blocked: confidence_or_ambiguity_gate` and do not emit a
retry recovery event.
Failed step reports include `failure_category` in step metadata and failure
events. Current categories distinguish `perception_failure`,
`selection_ambiguity`, `safety_stop`, `verification_failure`, and
`actuation_failure`; timeout and execution-limit failures keep their own
category values. The Markdown report prints the category beside failed steps.
Failed click steps also include `failure_evidence` with visible-before
candidates and the state delta observed after the click attempt.
Failed type steps include `failure_evidence` with the active window, focused
element, active process, and state delta captured around the typing attempt.
Failed scroll steps include `failure_evidence` with `scroll_moved` and emitted
scroll-click metadata so reports can show whether the viewport likely moved.
Passed action steps include `success_evidence` with post-action evidence,
verification outcome, and state delta for the resulting state.
Markdown event rows include compact decision details for recovery paths,
ambiguity gates, and timing delays so timing, ambiguity, recovery, and safety
stops can be reviewed without opening the JSON report. Final actuator guard
failures include `input_blocked` and `actuation_guard` metadata, and the
Markdown report prints which guard blocked input. Target-selection failures
include a `diagnostic_bundle` in the failure event and failed step metadata. The
bundle includes the screenshot path, active-window title, monitor metadata,
cursor readback, candidates grouped by source, ranking metadata, selected
candidate if any, and blocked-candidate reasons.
After target selection, the planner emits `ui_state_snapshot` with visible
controls, the selected candidate, confidence and fusion scores, and blocked
candidate reasons such as disabled, not visible, below confidence threshold,
outside region, target mismatch, or ambiguity gate.
The `select_target` event also includes a `target_reasoning` schema section:
selected candidate details, rejected candidates with rejection reasons,
confidence values by candidate ID, and coordinate conversion from screenshot
bounds to physical desktop coordinates when monitor metadata is available.

## Replay

`desktop-agent replay <trace-dir>` reads `final-report.json` and prints a
summary and per-step timeline without rerunning actions. Timeline rows group
trace events by `step_id` and include compact markers for observations,
selected candidates, verification outcomes, recovery reasons, manual handoff,
state-delta changes, and scroll movement.
For goal-plan traces it reads `goal-plan-report.json` and prints ranked routine
candidates; for finalized proof-suite roots it reads
`proof-finalization-status.json` and prints suite, promotion, and archive gates.
For benchmark output roots it reads `benchmark-report.json` and prints
schema and generation metadata, acceptance status, baseline comparison status,
monitoring coverage, pipeline modes, deep-search sources, required/observed
trace coverage, report-artifact links, and per-run trace links.
Add `--write-summary` to write `replay-summary.md` in the trace directory with
the timeline, screenshot paths from pre/post action evidence, and state-delta
changes. The summary also includes step-level `success_evidence` and
`failure_evidence`, so each executed step can be reviewed without live desktop
access. Benchmark replay summaries include the benchmark schema and generation
timestamp from `benchmark-report.json`.

`desktop-agent trace-health --trace-root traces` prints local trace counts by
report kind and status, including run, goal-plan, benchmark, and proof-suite
reports. It also includes a `health_status` of `empty`, `ok`, or `attention`
when failed, error, invalid, blocked, or unknown trace statuses need review. Add
`--json` when a dashboard, CI step, or monitoring script needs the same payload
used by the operator app trace service. Add `--output traces/trace-health.json`
to persist the monitoring payload as a local report artifact. When `--json` and
`--output` are combined, stdout remains a parseable JSON payload and the report
path notice is written to stderr.
The payload includes `schema_version` and `generated_at` fields so archived
monitoring reports can be compared safely over time.
The JSON payload includes `attention_traces`, a list of trace summaries that
need review, so monitors can link directly to the relevant local reports. Trace
summaries also include `replay_summary_path` when a local `replay-summary.md`
artifact exists, and the CLI plus Markdown trace-health output print that path
for attention traces. Benchmark trace summaries include the `report_artifacts`
manifest from `benchmark-report.json`.
Add `--markdown-output traces/trace-health.md` to write the same health status,
counts, attention trace links, and latest trace links as a human-readable local
report.
Add `--fail-on-attention` when a local monitor or CI smoke step should return
nonzero if failed, error, invalid, blocked, or unknown trace statuses are found.

`desktop-agent analyze-failed-run <trace-dir>` reads `final-report.json` and
writes `failed-run-analysis.json` plus `failed-run-analysis.md`. The analysis
indexes the local final report, action log, task/config snapshots, schema,
safety audit, replay summary, and screenshots when present, and records
`desktop_input_rerun_required: false`. The analyzer can propose YAML selector,
region, checkpoint, recovery, or allowed-window updates, but every proposal is
marked `review_required: true` and `applies_automatically: false`.
Current proposal types are `selector_region_review`,
`verification_checkpoint_review`, `recovery_review`, and `allowed_window_review`.

`desktop-agent proof replay <trace-dir>` reads `proof-manifest.json` and prints
the proof name, original command, status, environment metadata, and artifact
paths without rerunning desktop input. Add `--open-artifacts` to open existing
artifact paths with the local OS file manager for manual review.
When proof video capture is enabled, replay also lists the local `proof-video.mp4`
and `video-capture.log` paths recorded in the manifest.

## TraceSchemaV2

`TraceSchemaV2` is the closed-loop trace contract for observe-decide-act-verify
runs. Every file-backed run writes `trace-schema.json`, every action-log row
includes `trace_schema_version`, and `final-report.json` embeds the schema used
for the run.

`desktop_agent.trace_migrations` contains the compatibility helpers for older
local trace artifacts. The migration layer upgrades legacy final reports and
action-log rows to the current schema, fills missing event defaults, rejects
unknown schema versions, preserves existing report, step, event, and metadata
fields, and records whether the migration was applied. Migration works on a
copied payload so reading an old trace for replay or review does not rewrite the
source artifact in place.

The schema defines six top-level evidence sections:

- `observation`: screenshots, active-window process, focus, cursor, monitor,
  DPI, OCR, UIA, and CV state.
- `target_reasoning`: selected candidate, competing candidates, and rejection
  reasons.
- `input`: planned and emitted mouse, keyboard, scroll, wait, or dry-run input.
- `verification`: post-action checks and post-action evidence.
- `state_delta`: focus changes, visible text changes, viewport movement, and
  other observed differences before and after input.
- `model_assistance`: optional local-model disclosure fields, including
  provider, model name, prompt class, input artifact references, output hash,
  structured output accepted/rejected status, and whether the model affected
  routine selection.
