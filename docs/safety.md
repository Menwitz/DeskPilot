# Safety

DeskPilot v1 is designed for owned and controlled automation. It assumes the
operator has permission to automate the target desktop session and target
applications.

## Required Operating Conditions

- The Windows desktop must be unlocked.
- The user must be logged in.
- Tasks must declare allowed windows.
- Runtime configuration must include timeouts, retry limits, and maximum step
  limits.
- Reports, screenshots, OCR text, and traces are local by default.

## Explicitly Unsupported Uses

DeskPilot does not support stealth automation, CAPTCHA bypass, bot-detection
evasion, credential abuse, or abusive third-party automation.

## Safety Controls Planned For v1

- Active-window allowlist checks before every action.
- Dry-run mode that validates and plans without moving the mouse.
- Emergency stop hotkey polling on Windows.
- Maximum runtime, maximum steps, and per-step retry limits.
- Confidence thresholds for OCR, image, and UIA candidate selection.
- Failure reports that explain why a task stopped.
- Step-level explicit confirmation for task actions marked as sensitive.

## Locked Screen Boundary

v1 does not support locked-screen or background desktop automation. The desktop
must be unlocked and visible because screenshot capture, UI Automation,
computer vision, OCR, and input actuation all depend on the active interactive
session.

## Local Trace Policy

Screenshots, OCR text, candidate data, action logs, and reports are written to
the configured local trace directory. v1 does not upload traces or call cloud AI
services.

## Emergency Stop

`emergency_stop_hotkey` defaults to `ctrl+alt+esc`. On Windows the planner polls
the configured key chord between bounded actions and writes an
`emergency_stopped` report when it is pressed. Unsupported platforms use a safe
no-op monitor until their input adapters exist.

## Human-Like Execution Profile Boundary

The optional execution profile is limited to bounded timing decisions and trace
metadata. It must not change the user's intended task outcome, choose a
different action, leave the allowed window scope, bypass confidence gates, or
hide that automation is running.

Invalid execution profile bounds fail configuration validation before any
desktop action can run. Timing decisions are recorded in traces so failed runs
can be diagnosed without guessing why the planner waited or retried.
Target-aware timing can use selected target geometry and action type to choose
where a delay falls inside the configured bounds, but it does not pick new
targets, bypass confidence checks, or expand allowed timing limits.

Sensitive task steps can declare `requires_confirmation: true`. The planner
stops before the action unless the operator confirms the step ID through runtime
configuration or `--confirm-step`.
