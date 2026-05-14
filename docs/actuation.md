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
direction, overshoot, and settle decisions in tests and diagnostics.

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

## Safety

The execution engine checks task safety before calling the actuator. The
actuator also re-checks `RuntimeConfig.allowed_windows` through the backend when
that config field is present. If the active window does not match, no input is
sent and the action returns a failed result.

## Testing

`FakeInputBackend` records input events without moving the real mouse or sending
keys. Unit tests cover coordinate conversion, clicks, typing, key chords, drag,
scroll, movement planning, and active-window blocking.

## Platform Support

`create_platform_actuator()` returns the Windows input backend on Windows and a
clear unavailable adapter elsewhere. This keeps non-Windows development safe
while preserving the Windows-first adapter boundary.
