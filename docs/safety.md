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
- Emergency stop hotkey.
- Maximum runtime, maximum steps, and per-step retry limits.
- Confidence thresholds for OCR, image, and UIA candidate selection.
- Failure reports that explain why a task stopped.
