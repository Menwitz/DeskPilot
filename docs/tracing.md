# Tracing And Reports

DeskPilot writes local trace artifacts for every CLI run. The trace sink creates
a unique run directory under `trace_root` and then hands that directory back to
the execution pipeline as the active `config.trace_root`.

## Files

- `config.json` stores the normalized runtime configuration used by the run.
- `task.json` stores the normalized task definition.
- `action-log.jsonl` stores every trace event as newline-delimited JSON.
- `final-report.json` stores the machine-readable final report.
- `final-report.md` stores a human-readable report.
- `screenshots/` receives screen captures when `save_screenshots` is enabled.
- `ocr/` receives OCR output when `save_ocr_text` is enabled.
- `overlays/` receives computer-vision candidate overlays when screenshot
  saving is enabled.

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
`sample_records` entries for every sampled value used in the decision.

The `compile_task` event records static step order, dependency edges, and
expected UI state transitions before the planner observes the screen or attempts
input. Task JSON also stores each step's `depends_on` and `expected_state`
contracts for report review.

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
Failed action attempts emit `reobserve_after_failure` before retry metadata is
written. The recovery monitor then runs candidate detection on the fresh
observation and records `recover_candidates`, so deep-search output is visible
in the trace. Recovery events also include `recovery_chosen_action`,
`recovery_path`, `recovery_path_summary`, and `reobserve_before_retry`; the
Markdown report prints the path summary on recovery rows.
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
Markdown event rows include compact decision details for recovery paths,
ambiguity gates, and timing delays so timing, ambiguity, recovery, and safety
stops can be reviewed without opening the JSON report.
After target selection, the planner emits `ui_state_snapshot` with visible
controls, the selected candidate, confidence and fusion scores, and blocked
candidate reasons such as disabled, not visible, below confidence threshold,
outside region, target mismatch, or ambiguity gate.

## Replay

`desktop-agent replay <trace-dir>` reads `final-report.json` and prints a
summary without rerunning actions.
