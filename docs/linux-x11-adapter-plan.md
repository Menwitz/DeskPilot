# Linux X11 Adapter Plan

This is a post-Windows-beta plan. DeskPilot remains Windows-first until the
browser, native, mixed, and recovery proof lanes are complete with video plus
traces on owned Windows desktops.

## Entry Criteria

- Windows proof pack is complete and reviewed.
- TraceSchemaV2 is stable enough to represent non-Windows evidence without
  changing the core report contract.
- Operator app and routine-pack workflows can run without platform-specific UI
  assumptions.
- X11 work has a dedicated owned Linux desktop for smoke testing.

## Candidate Adapter Shape

- `X11ScreenObserver`: capture screenshots and monitor geometry from the active
  X11 session.
- `X11WindowInspector`: read active window title, process, bounds, and focus
  state from X11/EWMH.
- `X11Actuator`: emit mouse, keyboard, and scroll input to the interactive X11
  session.
- `X11FocusRecoveryController`: refocus approved windows when the active window
  drifts.
- `X11SmokeChecklist`: opt-in proof command gated behind an environment flag,
  mirroring `DESKPILOT_WINDOWS_SMOKE=1`.

## Safety Requirements

- Never run from a headless session that cannot produce visible screenshots.
- Preserve allowed-window checks before input.
- Preserve emergency-stop behavior or document a Linux-specific equivalent.
- Keep screenshots, OCR, candidate rankings, traces, and reports local.
- Keep public-site and high-risk mutation approval rules unchanged.

## Proof Expectations

- Low-level cursor/keyboard proof with trace artifacts.
- Browser fixture proof.
- Native app proof using a simple local app such as a text editor or calculator.
- Mixed browser-to-native handoff proof.
- Recovery proof for occluded, delayed, or moved targets.

## Open Questions

- Whether to use Xlib, python-xlib, xdotool-compatible subprocess calls, or a
  small native helper for input.
- How to read active-window and process metadata consistently across common X11
  window managers.
- Whether screenshot capture should use MSS, XGetImage, or a compositor-aware
  tool.
- How to package optional Linux dependencies without affecting the Windows
  package.
