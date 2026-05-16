# Windows Proof Evidence Checklist

Use this checklist when collecting manual evidence for DeskPilot proof commands
on an owned, unlocked Windows desktop or VM. The checklist is intentionally
artifact-first: a reviewer should be able to inspect the video, trace,
screenshots, manifest, action log, and report without rerunning desktop input.

## Global Setup

- [ ] Confirm the Windows session is unlocked and controlled by the operator.
- [ ] Close unrelated sensitive windows before starting the countdown.
- [ ] Start screen recording before running the command.
- [ ] Run the command from the repository root with an explicit `--trace-root`.
- [ ] Run `desktop-agent proof preflight --trace-root <trace-root>` and resolve
      failed Windows platform, trace-root, or video-capture checks before the
      proof countdown.
- [ ] Prefer built-in recording with `--record-video --video-fps 15` when
      `ffmpeg` is installed on the Windows VM.
- [ ] Use `--video-policy disabled` when the run may not record screen video.
- [ ] Do not touch the mouse or keyboard after the countdown starts.
- [ ] Stop screen recording only after the command prints status and trace path.
- [ ] Copy the recording into the generated trace directory.
- [ ] Run `desktop-agent proof replay <trace-dir>` and save the terminal output.
- [ ] Run `desktop-agent proof replay <trace-dir> --open-artifacts` for manual
      artifact review.
- [ ] Run `desktop-agent proof validate <trace-dir>` and save the terminal
      output; use `--allow-missing-video` only when video capture was
      intentionally disabled and separately justified.
- [ ] After browser, native, mixed, and recovery bundles are collected under
      the same trace root, run `desktop-agent proof validate-suite <trace-root>`
      and save the terminal output before Phase 1 acceptance review.
- [ ] Run `desktop-agent proof validate-suite <trace-root> --write-report` and
      review `proof-suite-report.md` before promoting the four-workflow proof
      pack.
- [ ] Run `desktop-agent proof validate-suite <trace-root>
      --write-status-json` and archive `proof-suite-status.json` with monitoring
      or CI evidence.
- [ ] Run `desktop-agent proof validate-suite <trace-root> --write-runbook`
      and follow `proof-suite-next-actions.md` until no missing or invalid proof
      bundle remains.
- [ ] Run `desktop-agent proof validate-suite <trace-root> --write-archive`
      and store `proof-suite-artifacts.zip` with the review record.

## Required Proof Bundle

- [ ] `proof-manifest.json` lists command, DeskPilot version, Python version,
      platform, Windows version when available, monitor geometry, DPI scale,
      started-at time, completed-at time, and artifact paths.
- [ ] `desktop-agent proof validate <trace-dir>` rejects missing command,
      runtime, Windows version, monitor geometry, DPI scale, or timestamp
      metadata before promotion.
- [ ] The manifest `artifacts.trace_dir` points at the reviewed trace directory.
- [ ] The manifest `artifacts.report_path` exists.
- [ ] The manifest `artifacts.action_log_path` exists.
- [ ] The manifest `artifacts.proof_manifest_path` exists.
- [ ] The manifest lists any `screenshots/*.png` captured during the run.
- [ ] `proof-video.mp4` is stored in the trace directory when `--record-video`
      is used.
- [ ] `video-capture.log` is stored in the trace directory when `--record-video`
      is used.
- [ ] `proof-manifest.json` and the command report link `video_path`,
      `video_log_path`, capture command, and capture status when recording is
      enabled.
- [ ] Any external screen recording is stored in the trace directory or clearly
      linked in the review notes.
- [ ] `action-log.jsonl` contains one monitoring event per visible proof step.
- [ ] The command report contains final status, per-step status, active-window
      metadata, cursor readback, and post-action evidence where available.
- [ ] `desktop-agent proof validate <trace-dir>` reports `validation: passed`
      before a proof bundle is promoted.
- [ ] `desktop-agent proof validate-suite <trace-root>` reports `suite: passed`
      before the four-workflow proof pack is promoted.
- [ ] `proof-suite-report.md` summarizes every required proof, missing bundle,
      duplicate bundle, warning, and blocking validation error.
- [ ] `proof-suite-status.json` records the suite status, expected proofs,
      missing proofs, duplicate proofs, warnings, errors, and per-proof artifact
      paths for monitoring.
- [ ] `proof-suite-next-actions.md` lists missing proof commands, invalid bundle
      revalidation commands, duplicate review items, and final promotion
      commands.
- [ ] `proof-suite-artifacts.zip` contains the generated suite report, status
      JSON, next-actions runbook, proof manifests, action logs, command reports,
      screenshots, and video artifacts when present.
- [ ] If the command uses target selection or deep search, the trace includes
      candidate rankings, rejected candidates, and diagnostic bundle metadata.

## `desktop-agent demo-input`

- [ ] Command recorded:
      `desktop-agent demo-input --trace-root traces --countdown-seconds 5`.
- [ ] Video shows `Win+D` revealing the desktop.
- [ ] Video shows the real Windows cursor moving across global desktop
      waypoints.
- [ ] Video shows the harmless desktop drag-selection.
- [ ] Video shows a fresh Notepad window opening.
- [ ] Video shows the configured text typed into Notepad.
- [ ] `input-demo-report.json` exists and has `status: passed`.
- [ ] `action-log.jsonl` contains cursor movement, drag, app launch, and typing
      monitoring records.
- [ ] Post-action screenshots show the desktop movement evidence and Notepad
      text evidence.
- [ ] Reviewer confirms this low-level proof does not claim OCR, UIA, candidate
      fusion, or website target-selection coverage.

## `desktop-agent demo-linkedin`

- [ ] Command recorded:
      `desktop-agent demo-linkedin --trace-root traces --countdown-seconds 5`.
- [ ] Video shows Microsoft Edge opening in a real desktop window.
- [ ] Video shows the address bar receiving typed navigation input.
- [ ] Video shows the configured URL loading.
- [ ] Video shows real cursor wheel scrolling on the page.
- [ ] Video shows Edge Find opening and the configured text being typed.
- [ ] `linkedin-demo-report.json` exists and has `status: passed`.
- [ ] `action-log.jsonl` contains Edge launch, navigation, scroll, and find-box
      monitoring records.
- [ ] Post-action screenshots show browser state after navigation, scrolling,
      and Find.
- [ ] Reviewer confirms the proof uses no Playwright, DevTools, browser API, or
      account credentials.

## `desktop-agent proof browser-fixture`

- [ ] Command recorded:
      `desktop-agent proof browser-fixture --trace-root traces
      --countdown-seconds 5`.
- [ ] Video shows Microsoft Edge opening the generated local HTML fixture.
- [ ] Video shows the real Windows cursor clicking the form input.
- [ ] Video shows the configured fixture text typed into the form.
- [ ] Video shows Enter submitting the form and navigating to the result page.
- [ ] Video shows Edge Find searching for the configured result text.
- [ ] `browser-fixture.html` exists in the trace directory.
- [ ] `browser-fixture-result.html` exists in the trace directory.
- [ ] `browser-fixture-report.json` exists and has `status: passed`.
- [ ] `action-log.jsonl` contains fixture creation, Edge launch, input focus,
      typing, submit, find, and cursor-readback monitoring records.
- [ ] Post-action screenshots show form focus, typed text, and submitted result
      evidence where visible.
- [ ] Reviewer confirms the proof uses no Playwright, DevTools, browser API, DOM
      automation, or fixture-only fake cursor.

## `desktop-agent proof native-fixture`

- [ ] Command recorded:
      `desktop-agent proof native-fixture --trace-root traces
      --countdown-seconds 5`.
- [ ] Video shows a fresh Notepad window opening.
- [ ] Video shows the configured initial text typed into Notepad.
- [ ] Video shows `Ctrl+A` selecting the Notepad buffer.
- [ ] Video shows the configured replacement text typed into Notepad.
- [ ] `native-fixture-report.json` exists and has `status: passed`.
- [ ] `action-log.jsonl` contains Notepad launch, initial typing, selection,
      replacement typing, and cursor-readback monitoring records.
- [ ] Post-action screenshots show native app focus, initial text, selection,
      and replacement text evidence where visible.
- [ ] Reviewer confirms the proof uses no app API, accessibility write API,
      clipboard injection, or fake text surface.

## `desktop-agent proof mixed-fixture`

- [ ] Command recorded:
      `desktop-agent proof mixed-fixture --trace-root traces
      --countdown-seconds 5`.
- [ ] Video shows Microsoft Edge opening the generated local browser fixture.
- [ ] Video shows Notepad opening after the browser step.
- [ ] Video shows the configured native handoff text typed into Notepad.
- [ ] Video shows `Alt+Tab` switching focus back to Edge.
- [ ] Video shows Edge Find searching for the configured browser fixture text.
- [ ] `mixed-fixture-report.json` exists and has `status: passed`.
- [ ] `action-log.jsonl` contains browser fixture creation, Edge launch,
      Notepad launch, native typing, Alt+Tab switching, browser Find, and
      cursor-readback monitoring records.
- [ ] Post-action screenshots show browser, native app, window switching, and
      browser-return evidence where visible.
- [ ] Reviewer confirms the proof uses no browser API, app API, accessibility
      write API, or synthetic window switch.

## `desktop-agent proof recovery-fixture`

- [ ] Command recorded:
      `desktop-agent proof recovery-fixture --trace-root traces
      --countdown-seconds 5`.
- [ ] Video shows Microsoft Edge opening the generated recovery fixture.
- [ ] Video shows the recovery target initially disabled.
- [ ] Video shows the first probe click before the target is ready.
- [ ] Video shows the wait interval and target becoming ready.
- [ ] Video shows the retry click succeeding.
- [ ] Video shows Edge Find searching for the configured result text.
- [ ] `recovery-fixture.html` exists in the trace directory.
- [ ] `recovery-fixture-report.json` exists and has `status: passed`.
- [ ] `action-log.jsonl` contains recovery reason, policy, action, retry index,
      probe, wait, retry, browser Find, and cursor-readback monitoring records.
- [ ] Post-action screenshots show disabled, ready, retried, and verified states
      where visible.
- [ ] Reviewer confirms the proof uses no browser API, DOM automation, or
      synthetic cursor.

## `desktop-agent windows-smoke-checklist`

- [ ] Command recorded:
      `desktop-agent windows-smoke-checklist --trace-root traces
      --countdown-seconds 5`.
- [ ] Video shows cursor readback checks completing on the real desktop.
- [ ] Video shows Notepad opening and receiving the configured text.
- [ ] Video shows Microsoft Edge opening.
- [ ] `windows-smoke-checklist-report.json` exists and has `status: passed`.
- [ ] `windows-smoke-checklist.md` exists in the trace directory.
- [ ] `action-log.jsonl` contains one line per smoke check.
- [ ] `screenshots/` contains post-action screenshots for the smoke checks.
- [ ] Reviewer compares `windows-smoke-checklist.md` against the video and
      confirms all checked rows match visible behavior.

## Planned `desktop-agent proof ...` Commands

Use the same global and bundle checks for each fixture command as it lands.

All current Phase 1 proof commands now have command-specific evidence checks.

## Review Outcome

- [ ] Reviewer can verify from artifacts that real OS input occurred.
- [ ] Reviewer can map every visible action in the video to a trace/report
      event.
- [ ] Reviewer can identify any skipped, missing, or failed evidence item.
- [ ] Reviewer records the command, trace directory, recording path, reviewer
      name, review date, and final pass/fail decision.
