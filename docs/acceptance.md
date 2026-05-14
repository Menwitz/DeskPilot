# V1 Acceptance

This document records what can be verified locally in CI and what still needs a
logged-in Windows desktop session.

## Verified Locally

- `desktop-agent dry-run` validates YAML tasks, prints a preview of timing
  bounds and recovery paths, runs the planner with a dry-run actuator, prints
  planned step results, and does not send input.
- `desktop-agent inspect-screen` writes `inspect-screen.json` with screenshot
  metadata, OCR blocks, UIA tree/candidates when available, fused candidates,
  and candidate rankings.
- Failed planner runs include a final status, abort reason, step message,
  events, candidate confidence values, and trace artifacts.
- Execution-profile runs write safety-audit JSON and Markdown artifacts.
- The v1 pipeline uses local screenshot, OCR, computer vision, UIA, actuation,
  tracing, and report modules without requiring a cloud service.
- Safety checks block actions when the active window is outside the task
  whitelist.

## Windows-Only Verification

The following acceptance items require an unlocked, logged-in Windows desktop:

- `desktop-agent run` executing a real YAML task end to end.
- Browser fixture completion.
- Native fixture completion.
- Mixed fixture completion.
- Emergency hotkey stop-time measurement.

Use [Windows E2E Checklist](windows-e2e-checklist.md) for the manual commands,
expected results, and trace evidence to collect.
The checklist also includes opt-in `pytest -m windows_smoke` coverage for
unlocked owned Windows sessions; those tests stay skipped by default outside
that environment.
