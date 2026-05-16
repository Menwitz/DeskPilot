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
desktop-agent record save --state traces/recorder-session.json --output traces/morning-inbox-recording.json
desktop-agent record discard --state traces/recorder-session.json
```

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
is the first stable-selector capture source; OCR and image fallback capture are
tracked separately.

Live Windows event capture and editable YAML/playbook generation are tracked in
the remaining recorder roadmap tasks.
