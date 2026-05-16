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
- [ ] Do not touch the mouse or keyboard after the countdown starts.
- [ ] Stop screen recording only after the command prints status and trace path.
- [ ] Copy the recording into the generated trace directory.
- [ ] Run `desktop-agent proof replay <trace-dir>` and save the terminal output.
- [ ] Run `desktop-agent proof replay <trace-dir> --open-artifacts` for manual
      artifact review.

## Required Proof Bundle

- [ ] `proof-manifest.json` lists command, DeskPilot version, Python version,
      platform, Windows version when available, monitor geometry, DPI scale,
      started-at time, completed-at time, and artifact paths.
- [ ] The manifest `artifacts.trace_dir` points at the reviewed trace directory.
- [ ] The manifest `artifacts.report_path` exists.
- [ ] The manifest `artifacts.action_log_path` exists.
- [ ] The manifest `artifacts.proof_manifest_path` exists.
- [ ] The manifest lists any `screenshots/*.png` captured during the run.
- [ ] The screen recording is stored in the trace directory or clearly linked in
      the review notes until `video_path` is automated.
- [ ] `action-log.jsonl` contains one monitoring event per visible proof step.
- [ ] The command report contains final status, per-step status, active-window
      metadata, cursor readback, and post-action evidence where available.
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

- [ ] `desktop-agent proof browser-fixture` evidence shows a real browser form
      or navigation flow, not a browser automation API.
- [ ] `desktop-agent proof native-fixture` evidence shows real interaction with
      a native Windows app.
- [ ] `desktop-agent proof mixed-fixture` evidence shows a browser-to-native
      handoff and real window switching.
- [ ] `desktop-agent proof recovery-fixture` evidence shows delayed, stale,
      duplicated, disabled, occluded, or moving-target recovery behavior.

## Review Outcome

- [ ] Reviewer can verify from artifacts that real OS input occurred.
- [ ] Reviewer can map every visible action in the video to a trace/report
      event.
- [ ] Reviewer can identify any skipped, missing, or failed evidence item.
- [ ] Reviewer records the command, trace directory, recording path, reviewer
      name, review date, and final pass/fail decision.
