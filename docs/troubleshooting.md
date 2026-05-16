# Troubleshooting

Start every investigation from the trace directory printed by the CLI. Use
`desktop-agent replay <trace-dir>` for a quick summary, then inspect
`final-report.md`, `action-log.jsonl`, `task.json`, `config.json`, and any
benchmark reports if the failure came from `benchmark-run`.
For real-input proof bundles, use `desktop-agent proof replay <trace-dir>` to
review `proof-manifest.json`, linked artifacts, and optional artifact opening
without rerunning desktop input.

## Desktop Session Is Locked

DeskPilot v1 requires an unlocked, logged-in desktop. Unlock the Windows
session, make the fixture window visible, and rerun the task.

## Active Window Is Rejected

Check the task `allowed_windows` list and the visible window title. The title
may match an allowed entry exactly, contain a plain entry case-insensitively, or
match a `regex:` entry. For real runs, `config.json` records the effective
allowlist after task and runtime window rules are merged.

## OCR Or Image Matching Finds No Target

Increase fixture visibility, avoid overlapping windows, confirm DPI scaling,
and inspect the trace screenshots, OCR JSON, overlays, and candidate rankings.
Use `desktop-agent calibrate-target <task.yaml> --output <dir>` to capture a
target calibration report. The report shows candidate rankings, UI state
snapshot data, the selected candidate ID, or the rejection reason such as an
ambiguity gate, low confidence, target mismatch, or no candidates.

## Ambiguity Gate Stops

Symptoms:

- `final-report.md` shows a failed step with `[selection_ambiguity]`.
- `action-log.jsonl` has a `select_target` event with
  `selection_blocked: confidence_or_ambiguity_gate`.
- `ui_state_snapshot` lists multiple candidates with blocked reasons such as
  `confidence_or_ambiguity_gate`, `target_mismatch`, or `outside_region`.
- `recover` may show `recovery_reason: layout_change` with
  `selector_family_attempts` when UIA, OCR, or image candidates disagree after a
  minor layout shift.
- `benchmark-report.json` shows an increased `ambiguity_rate`.

Checks:

- Run `desktop-agent calibrate-target <task.yaml> --step-id <step> --output <dir>`
  and inspect the candidate ranking output.
- Confirm the task target text is unique enough for the current UI.
- Confirm a task `region` is present when duplicate labels are expected.
- Check OCR JSON and overlays when UIA is unavailable or the target is rendered
  as an image.

Actions:

- Prefer narrowing `target` text or adding `region` over lowering
  `confidence_threshold`.
- Add a prior `wait_for` step when the target is still loading or changing.
- Use `click_uia` or `safe_action_variants` only when the UIA label maps to the
  same control as the visible text.
- Rerun `benchmark-run` and require `ambiguity_rate` to return to the expected
  threshold before treating the change as an improvement.

## Recovery Stops

Recovery is bounded by step retries, task timeouts, and the task-authored
`recovery` rules. A recovery stop means DeskPilot attempted the allowed recovery
path and still could not verify the step safely.

Symptoms:

- `final-report.md` shows recovery rows before a failed step.
- `action-log.jsonl` contains `recover`, `recover_candidates`, or
  `reobserve_after_failure` events.
- `recover` metadata includes `recovery_reason`, `recovery_policy`,
  `recovery_chosen_action`, `recovery_path_summary`, `retry_index`, and
  `retry_limit_respected`.
- `benchmark-report.json` or `variance-report.json` shows elevated
  `recovery_rate`, `retry_count`, or `recovery_count`.

Checks:

- Compare `recovery_reason` against the UI state: `stale_observation`,
  `missed_target`, `disabled_control`, `occluded_control`,
  `transient_loading`, or `verification_failure`.
- Inspect `recover_candidates` to see whether deep search found a better target
  after re-observation.
- For target-selection failures, inspect the failed step's `diagnostic_bundle`
  in `final-report.json`. It contains the screenshot path, active-window title,
  cursor readback, OCR/UIA/image candidates grouped by source, ranking metadata,
  and blocked-candidate reasons.
- Check the dry-run preview to verify the step has the intended recovery path
  and enough timeout budget for worst-case waits.

Actions:

- Increase `retry` only when the recovery reason is transient and the step
  timeout can still fit the worst-case action and retry waits.
- Add or tighten a `recovery` rule so the task permits only the recovery actions
  that are safe for that step.
- Add `wait_for`, a larger `timeout_seconds`, or a smaller search `region` when
  controls are delayed, disabled, or occluded.
- Add a stronger `verify` condition when recovery succeeds physically but the
  report cannot prove the final state.
- Reduce execution-profile retry bounds if recovery waits consume too much of
  the task timeout.

## Safety Stops

Safety stops are intentional. They mean the planner or final actuation guard
blocked input before it could leave the approved operating boundary.

Symptoms:

- `final-report.md` shows `[safety_stop]`.
- Failure messages mention active-window rejection, missing confirmation,
  operator approval, policy preset rejection, final actuator guard rejection, or
  emergency stop.
- `execute_action` metadata may include `input_blocked: true` and
  `actuation_guard` values such as `active_window`, `allowed_region`, or
  `emergency_stop`.
- `safety-audit.md` lists unconfirmed sensitive steps, missing checkpoints, or
  policy findings for execution-profile runs.

Checks:

- Compare the visible window title with the task `allowed_windows` and runtime
  `allowed_windows`.
- Inspect `config.json` for `policy_preset`, `require_operator_approval`,
  `confirmed_steps`, and `emergency_stop_hotkey`.
- Inspect `task.json` for `requires_confirmation`, `category: submission`,
  `checkpoint`, and step `region` values.
- Check whether the CLI prompt was declined or could not read input during a
  real `run`.

Actions:

- Fix `allowed_windows` or refocus the approved window; do not bypass the
  window check.
- Add `--confirm-step <step-id>` or `confirmed_steps` only after reviewing the
  step, its checkpoint, and the target window.
- Use `strict_qa` for submission-heavy QA runs and `exploratory_testing` for
  runs that must stop before final submission.
- Adjust `region` only to match the intended control's visible bounds.
- If `emergency_stop` fired, inspect the keyboard state and rerun only after
  the stop chord is no longer active.

## Public Site Playbook Stops

Website playbook runs include `site_id`, `site_flow_id`, playbook version,
domain, sensitive-step, and blocked-state metadata in `task.json`,
`action-log.jsonl`, and `final-report.json`. `desktop-agent replay <trace-dir>`
prints the site and flow when those fields are present.

Symptoms:

- Logged-out session: a blocked-state step reports `logged-out` or sign-in
  text; authenticate manually in the browser, then rerun the same flow.
- Consent dialog: a blocked-state step reports consent, cookie, or privacy
  text; resolve the dialog manually according to the operator's preference, then
  rerun the flow.
- Site redesign: an unsupported-layout blocked state, missing landmark, or
  repeated target mismatch appears in the action log; inspect the page and
  update the playbook landmarks or flow.
- CAPTCHA or suspicious-activity challenge: the report says the challenge is
  not automated; do not solve or bypass it with DeskPilot, and either resolve it
  manually or abandon the run.
- Permission restriction: account, policy, restricted, or unavailable-action
  text appears in the blocked-state reason; use an authorized account or choose
  a permitted flow instead of working around the restriction.
- Ambiguous selector: candidate rankings or `candidate_count` checks show
  multiple matching controls; narrow the landmark, search region, or
  flow-specific target before rerunning.

Actions:

- Resolve logged-out, consent, permission, and account states manually, then
  rerun the same flow.
- Do not attempt CAPTCHA solving, bot-detection bypass, or stealth workarounds.
- Update the playbook landmark or flow when a site redesign changes labels.
- Add a narrower landmark, search region, or flow-specific target when selector
  ambiguity is expected.

## Approval Manifest Stops

Sensitive `run-site` flows require `--approval-manifest <path>`. The manifest
must match the compiled task's `site_id`, `site_flow_id`, sensitive step IDs,
and `content_variables_fingerprint`.

Symptoms:

- The CLI exits with `approval manifest is required for sensitive site flow`.
- The CLI exits with a `site_id mismatch`, `flow_id mismatch`, unknown step, or
  `content_fingerprint mismatch`.
- `final-report.json` is absent because validation failed before the planner
  created a run trace.

Actions:

- Compile or dry-run the same site flow with the same `--variables` file and
  inspect `final-report.json` or `task.json` for the content fingerprint.
- Update the manifest only after reviewing the exact local content variables
  and approved sensitive step IDs.
- Keep the manifest beside the reviewed content payload or in an ops-controlled
  local evidence folder; do not reuse a manifest after changing content.

## Packaged Executable Fails

Run `deskpilot.exe --help` first. If that works, run a `dry-run` with
`packaging/default-config.yaml`. For real desktop execution, confirm the
Windows optional dependencies are installed and the session is unlocked.
