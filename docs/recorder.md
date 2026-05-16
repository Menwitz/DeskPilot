# Recorder

DeskPilot includes an early local recorder control surface behind
`desktop-agent record`. The first implementation manages recording session
state only; later Phase 4 work will add event capture, selector extraction, and
YAML generation.

## Controls

Start a session:

```bash
desktop-agent record start --state traces/recorder-session.json --name "Morning inbox"
```

Pause, stop, save, or discard the same session:

```bash
desktop-agent record pause --state traces/recorder-session.json
desktop-agent record stop --state traces/recorder-session.json
desktop-agent record save --state traces/recorder-session.json --output traces/morning-inbox-recording.json --confirm-save
desktop-agent record discard --state traces/recorder-session.json
```

`record save` requires operator confirmation. Use `--confirm-save` for an
explicit non-interactive confirmation, or type `SAVE` at the prompt.

The saved JSON uses `deskpilot_recorder_session_v1` and contains the session
ID, name, status, timestamps, event count, and recorder events. Recorder events
are timestamped records with an event type (`observation`, `input_event`, or
`selected_point`), active-window title, screenshot path, selected point,
low-level input payload, candidate context, and metadata. Candidate context can
carry source, label, UIA control type, bounds, confidence, and source-specific
metadata.

For clicked points, the recorder has a UIA capture helper that hit-tests the
point with the Windows UIA adapter and stores element name, control type,
bounds, enabled/visible state, and confidence as `uia` candidate context. This
is the first stable-selector capture source. The recorder also has an OCR
context helper that filters nearby OCR text blocks around a clicked point,
preserving text, bounds, confidence, whether the point was inside the block, and
distance from the click. Image fallback capture only runs when no stable UIA or
OCR context exists; it writes a bounded snippet around the clicked point and
stores the snippet path, source screenshot, crop bounds, and fallback reason as
`image` candidate context.

Live Windows event capture and editable YAML/playbook generation are tracked in
the remaining recorder roadmap tasks.

The recorder generator can already convert reviewed session events into a
`TaskDefinition` with `click_uia`, `click_text`, `click_image`, `type_text`,
`press_key`, `scroll`, `wait_for`, and `assert_visible` steps. It prefers UIA
context, then OCR context, then image snippets for clicked points. Generated
tasks infer `allowed_windows` from the active-window titles recorded on events.
