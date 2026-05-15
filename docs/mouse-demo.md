# Mouse Demo

`desktop-agent demo-mouse` is a Windows-only local actuator demo. It opens a
small Tkinter fixture and sends real OS mouse input inside that window without
using OCR, UI Automation, image matching, or task target selection.

Use this when validating the lower-level mouse-control behavior before testing
full task perception.

## Run

From the repository root on an unlocked Windows desktop:

```powershell
uv run desktop-agent demo-mouse
```

Expected result:

- A `DeskPilot Mouse Demo` window opens.
- The pointer visibly moves along smooth curved paths.
- The demo clicks a target, drags a token into a drop zone, scrolls over a
  scroll panel, and clicks finish.
- A report is written under `traces/<timestamp>-mouse-demo/`.

Useful options:

```powershell
uv run desktop-agent demo-mouse `
  --movement-smoothness 0.85 `
  --random-seed 20260515 `
  --auto-close-seconds 5
```

Set `--auto-close-seconds 0` to close the window immediately after the sequence.

## What It Proves

This command exercises the same `DesktopActuator`, `WindowsInputBackend`, and
`ActuationProfile` used by real runs. The report records movement point counts,
movement duration, pointer timing metadata, path model, overshoot/correction
state, settle timing, scroll cadence, and the random seed.

It does not prove OCR, UIA, screenshots, candidate fusion, or task YAML target
selection. Those layers are intentionally bypassed so mouse behavior can be
validated independently.

## Safety

The fixture is local and owned. Do not move the mouse while the demo is running.
The window is kept topmost during execution so the generated input lands inside
the fixture.
