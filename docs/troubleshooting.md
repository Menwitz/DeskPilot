# Troubleshooting

Start every investigation from the trace directory printed by the CLI. Use
`desktop-agent replay <trace-dir>` for a quick summary, then inspect
`final-report.md`, `action-log.jsonl`, `task.json`, `config.json`, and any
benchmark reports if the failure came from `benchmark-run`.
Use `desktop-agent analyze-failed-run <trace-dir>` to write
`failed-run-analysis.json` and `failed-run-analysis.md` with review-only YAML
improvement proposals. These proposals are never applied automatically.
For real-input proof bundles, use `desktop-agent proof replay <trace-dir>` to
review `proof-manifest.json`, linked artifacts, and optional artifact opening
without rerunning desktop input.

## Desktop Session Is Locked

DeskPilot v1 requires an unlocked, logged-in desktop. Unlock the Windows
session, make the fixture window visible, and rerun the task. Do not run real
desktop input from a Windows service, scheduled task without an interactive
session, disconnected RDP session, or locked screen; screenshots, UIA focus,
cursor readback, and `SendInput` cannot prove the visible workflow in those
states.

Checks:

- Run `desktop-agent windows-smoke-checklist --trace-root traces` from the same
  user session that will run the proof.
- Confirm the monitor is awake, the desktop is unlocked, and the target app is
  visible in the foreground.
- Inspect `final-report.json` for active-window, screenshot, focus, or cursor
  readback evidence gaps.

## Missing Windows Permissions Or UIA Access

Windows UI Automation and low-level input require the terminal or packaged app
to run inside the same interactive desktop as the target app. If UIA candidates
are empty, focus cannot be read, or input is blocked, treat it as an
environment issue before changing selectors.

Checks:

- Install Windows support with the `windows` extra on machines that need UIA:
  `pip install ".[windows]"`.
- Run DeskPilot at the same integrity level as the target app. If the target
  app is elevated, launch the terminal or packaged app elevated as well.
- Keep the target window visible and inside the allowed window list.
- Check `action-log.jsonl` for missing `uia_candidates`, active-window
  rejection, `actuation_guard`, or `input_blocked` metadata.

Actions:

- Prefer fixing the session, privilege level, or allowed-window rule before
  weakening confidence thresholds.
- Rerun `desktop-agent inspect-screen` or `desktop-agent calibrate-target` and
  verify that UIA, OCR, or image candidates are present before a real run.

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

## OCR Is Unavailable Or Disabled

OCR is optional and local-only. When Tesseract or the OCR Python dependencies
are missing, DeskPilot can still use UIA and image candidates, but text rendered
only as pixels may not be selectable.

Symptoms:

- No `ocr/` directory or OCR JSON appears in the trace even though screenshots
  exist.
- Candidate rankings contain UIA or image candidates but no OCR candidates.
- A task that depends on visible rendered text fails with no candidates or low
  confidence.

Checks:

- Install OCR support with `pip install ".[ocr]"` or `uv sync --extra ocr`.
- Confirm the local Tesseract binary is installed and available on `PATH`.
- Confirm redaction settings did not intentionally set OCR artifact output to
  metadata-only or suppress OCR text evidence.
- Run `desktop-agent inspect-screen --caption-output <path>` or
  `desktop-agent calibrate-target <task.yaml> --output <dir>` and inspect the
  candidate sources.

Actions:

- Prefer UIA selectors for native controls when available.
- Improve contrast, zoom, DPI scaling, or target region before lowering OCR
  confidence thresholds.
- If local policy forbids OCR text artifacts, keep `ocr_text: suppress` and use
  UIA or image matching for the routine.

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

## Video Capture Fails

Proof video capture is optional and Windows-only. It uses ffmpeg `gdigrab` and
writes `proof-video.mp4` plus `video-capture.log` in the trace directory when
`--record-video` is enabled.

Symptoms:

- The CLI reports `video capture requires Windows desktop input`.
- `proof-video.mp4` is missing, empty, or not linked from `proof-manifest.json`.
- `video-capture.log` contains ffmpeg startup, monitor, or permission errors.

Checks:

- Confirm the run is on an unlocked Windows desktop, not a locked screen or
  disconnected session.
- Confirm `ffmpeg` is installed and available on `PATH`.
- Inspect `video-capture.log`, `proof-manifest.json`, and `final-report.json`
  before rerunning.
- Confirm the selected `--video-fps` is greater than zero and low enough for
  the machine to encode reliably.

Actions:

- Rerun the proof with `--record-video --video-fps 15` after fixing ffmpeg or
  the interactive session.
- Use `--video-policy disabled` when local policy forbids screen recording; the
  trace and screenshots remain the proof source.
- Keep the failed trace directory for review instead of overwriting evidence.

## Local Model Is Unavailable

Local model assistance is optional and disabled by default. DeskPilot must keep
deterministic routing, validation, approvals, and safety gates working when
Ollama is not installed, stopped, or missing the configured model.

Symptoms:

- `desktop-agent local-model status --config config.yaml` reports a disabled,
  unreachable, or unhealthy provider.
- Goal planning returns deterministic candidates but no accepted model ranking.
- Trace or goal reports show model output rejected by the structured validator.

Checks:

- Confirm `local_model.enabled` is intentionally set to `true`; leave it
  disabled when no model should be used.
- Confirm the endpoint is loopback only: `127.0.0.1`, `localhost`, or `::1`.
- Run `desktop-agent local-model list --config config.yaml` and verify the
  configured model name exists.
- Inspect model disclosure fields in the trace or goal-plan report:
  provider, model name, prompt class, output hash, and accepted/rejected status.

Actions:

- Start Ollama locally or change the config to an installed local model.
- Disable `use_for_goal_ranking` if deterministic routine search is sufficient.
- Do not use remote model endpoints or model output that invents routine IDs,
  URLs, commands, selectors, or actions.
