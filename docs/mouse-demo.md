# Real Input Demo

`desktop-agent demo-input` is a Windows-only low-level input demonstration. It
uses the main Windows cursor and keyboard globally. It does not open a fixture,
render a synthetic cursor, constrain movement to a test window, use OCR, use UI
Automation, or run target selection.

`desktop-agent demo-mouse` remains as an alias for the same implementation.

## Run

From the repository root on an unlocked Windows desktop:

```powershell
uv run desktop-agent demo-input
```

Expected result:

- The command counts down so you can stop touching the mouse.
- `Win+D` reveals the desktop.
- The real Windows cursor moves across global desktop waypoints.
- The real cursor performs a harmless desktop drag-selection.
- A fresh Notepad instance opens.
- DeskPilot types the configured text into Notepad with keyboard cadence.
- A report is written under `traces/<timestamp>-input-demo/`.

Useful options:

```powershell
uv run desktop-agent demo-input `
  --trace-root traces `
  --random-seed 20260515 `
  --movement-smoothness 0.85 `
  --keyboard-text "DeskPilot controlled input" `
  --countdown-seconds 3
```

## What It Proves

This command exercises `WindowsInputBackend`, `SmoothMovementPlanner`, and
`ActuationProfile` through a reusable `RealInputController`. The trace records
planned pointer frames, actual `GetCursorPos` readbacks after every movement
frame, drift in pixels, button down/up events, keyboard events, sampled cadence,
and final status.

It proves low-level global cursor and keyboard control. It does not prove OCR,
UIA, screenshots, candidate fusion, YAML planning, or website target selection.

## Safety

Run this only inside an owned, unlocked Windows desktop or VM. The desktop
drag-selection is intentionally used as the mouse-button demonstration because
it is visible and disposable. Do not move the mouse or type while the countdown
and sequence are running.
