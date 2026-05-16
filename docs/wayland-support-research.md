# Wayland Support Research Track

Wayland support remains a research track, not a beta release target. DeskPilot
must not add a Wayland actuator until screenshot, focus, and input constraints
are resolved in a way that preserves visible local automation, approval gates,
and operator control.

## Research Boundary

- Treat Wayland as explicitly blocked for production automation until the
  required evidence paths are proven on owned desktops.
- Do not bypass compositor security, sandbox boundaries, or portal prompts.
- Do not use stealth injection, credential capture, bot-detection evasion, or
  hidden automation techniques to work around Wayland restrictions.
- Keep the Windows proof pack and later X11 adapter as the supported desktop I/O
  paths until Wayland has its own proof pack.

## Constraints To Resolve

- Screenshot access: confirm whether portal-mediated screenshots or compositor
  APIs can provide reliable before/after evidence without hidden capture.
- Input authority: confirm whether approved virtual keyboard, pointer, or remote
  desktop protocols can emit visible input in a way the operator can stop.
- Focus state: confirm whether the active surface, title, process, and bounds
  can be read with enough confidence for allowed-window enforcement.
- Cursor readback: confirm whether pointer position and movement results can be
  observed after each action.
- Recovery: confirm whether occluded, moved, minimized, or denied targets can be
  detected and safely handed back to the operator.

## Candidate Research Paths

- XDG Desktop Portal screenshot and remote-desktop flows.
- GNOME, KDE, and wlroots-specific permission and session behavior.
- Accessibility APIs that expose focus and window metadata without weakening
  user consent.
- A small optional helper that only runs after explicit operator approval and
  reports its permission state into traces.
- A Wayland smoke checklist mirroring the Windows and future X11 proof lanes.

## Exit Criteria

- A visible screenshot path produces before/after evidence for browser, native,
  mixed, and recovery workflows.
- A permitted input path emits keyboard, mouse, and scroll actions only inside an
  owned interactive session.
- Focus, cursor, and target readback can be captured after actions.
- Emergency stop and pause behavior are verified under Wayland.
- The proof bundle includes video or equivalent portal-captured evidence,
  traces, action logs, candidate reasoning, and reviewer signoff.

## Non-Goals

- No compositor bypasses.
- No headless Wayland automation without visible proof artifacts.
- No production support before the research constraints above are closed.
- No weakening of public-site approvals, safety stops, or redaction behavior.
