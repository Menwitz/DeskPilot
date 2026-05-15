# Actuation

DeskPilot v1 sends desktop input through a high-level `DesktopActuator` and a
low-level `InputBackend`. The planner stays platform-neutral, while the backend
owns the operating-system calls.

## Supported Input

- mouse movement
- click and double click
- drag from a selected target to a destination region
- wheel scrolling
- text typing
- single key press and simple key chords such as `ctrl+s`

`wait_for`, `assert_visible`, and `branch_if_visible` are passive actions. They
do not send input through the actuator.

## Coordinates

Perception candidates are expressed in screenshot coordinates. Before sending
mouse input, the actuator converts candidate centers through the active
`MonitorInfo` when the screen observation includes one. This applies monitor
origin and DPI scale so Windows receives physical desktop coordinates.

If an observation has no monitor metadata, the actuator treats candidate bounds
as already physical. Tests use this fallback for deterministic fixtures.

## Movement Profile

Mouse movement uses a bounded minimum-jerk path over a small optional curved
Bezier trajectory. The `ActuationProfile` controls movement duration, timing
variation, path step count, smoothness, and deterministic random seed. The tiny
variation is for local reliability around UI latency, not for stealth or
bot-evasion behavior. All actuation randomness goes through the shared seeded
sampler, so the same profile seed replays the same timing variation, curve
direction, overshoot, and settle decisions in tests and diagnostics. Movement
metadata records the seed and sample records for the sampled actuation values.
For real desktop runs, enabled `RuntimeConfig.execution_profile.movement_smoothness`
is copied into the platform actuation profile before the `DesktopActuator` is
created, so the planner's configured smoothness reaches real pointer paths.
Click, drag, and scroll metadata include `movement_smoothness`, making report
review able to confirm the real actuator consumed the execution profile.

Movement duration is estimated behind a local `PointerTimingModel` interface.
The default `FittsLawPointerTimingModel` uses pointer distance and effective
target width to estimate movement time, then clamps the estimate inside
`ActuationProfile.movement_duration_seconds`. Action metadata includes the
pointer timing model, distance, effective target width, index of difficulty, and
bounded model duration for trace and report inspection.
Movement metadata also records the pointer path model used for the emitted
physical points.

Overshoot, correction, and settle behavior are configurable through
`ActuationProfile.overshoot_probability`, `overshoot_pixels`, and
`settle_duration_seconds`. Overshoot is disabled by default. When enabled, it is
clamped by the effective target width, followed by a correction path back to the
target center, and then an optional settle wait. Metadata records whether
overshoot happened, the overshoot point, and settle duration.

Keyboard text entry can use `ActuationProfile.keyboard_interval_seconds` to add
bounded sleeps between characters. The actuator still emits the exact authored
text in order; metadata records whether cadence was applied and the interval
values used.

Wheel scrolling can use `ActuationProfile.scroll_interval_seconds` to split a
multi-click scroll into same-direction unit scroll events with bounded sleeps
between them. The total scroll click count is preserved, and metadata records
the emitted scroll steps and interval values.

## Safety

The execution engine checks task safety before calling the actuator. The
planner merges task and runtime `allowed_windows` into the effective runtime
config, then the actuator re-checks that same allowlist through the backend
before input. Plain window entries match exact titles or case-insensitive title
substrings; `regex:` entries run case-insensitive regular expressions. If the
active window does not match, no input is sent and the action returns a failed
result. Real actuation also applies a final step-region guard for targeted click
and scroll actions, and `create_platform_actuator` can receive the same
emergency-stop monitor used by the planner so the input adapter blocks before
desktop input when the stop chord is active.

## Testing

`FakeInputBackend` records input events without moving the real mouse or sending
keys. Unit tests cover coordinate conversion, clicks, typing, key chords, drag,
scroll, movement planning, active-window blocking, region blocking, and final
emergency-stop blocking.

For a visible Windows-only low-level input demonstration, run:

```powershell
uv run desktop-agent demo-input
```

The command uses the main Windows cursor globally, reveals the desktop, moves
through smooth waypoints, performs a harmless desktop drag-selection, opens
Notepad, and types with keyboard cadence. `demo-mouse` is retained as an alias
for the same command. See [Real Input Demo](mouse-demo.md) for the runbook and
report details.

For a browser-focused low-level demo, run:

```powershell
uv run desktop-agent demo-linkedin
```

The command opens Edge, types the LinkedIn URL through the address bar, scrolls
the page with the real cursor, and uses browser Find to highlight text. See
[LinkedIn Edge Demo](linkedin-demo.md) for the runbook.

For a compact Windows smoke checklist, run:

```powershell
uv run desktop-agent windows-smoke-checklist
```

The command verifies cursor readback, Notepad typing, Edge launch, trace file
creation, post-action screenshots, and monitoring logs. See
[Windows Smoke Checklist Command](windows-smoke-checklist.md) for the runbook.

## Platform Support

`create_platform_actuator()` returns the Windows input backend on Windows and a
clear unavailable adapter elsewhere. This keeps non-Windows development safe
while preserving the Windows-first adapter boundary.

The Windows backend supports `SendInput` absolute and relative mouse move
events. Normal automation and the global input demo use absolute movement for
precise target placement on the virtual desktop. `SetCursorPos` is retained
only as a fallback if Windows rejects a move event.
