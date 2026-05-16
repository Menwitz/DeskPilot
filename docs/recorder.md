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

The saved JSON uses `deskpilot_recorder_session_v1` and currently contains the
session ID, name, status, timestamps, and an empty event list. Event capture and
editable YAML/playbook generation are tracked in the recorder roadmap tasks.
