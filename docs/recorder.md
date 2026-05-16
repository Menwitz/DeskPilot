# Recorder

DeskPilot includes an early local recorder control surface behind
`desktop-agent record`. The first implementation manages recording session
state and reviewed event conversion; later Phase 4 work will add live event
capture, review metadata, and richer YAML export controls.

## Controls

Start a session:

```bash
desktop-agent record start --state traces/recorder-session.json --name "Morning inbox"
```

Start can also seed operator review metadata:

```bash
desktop-agent record start \
  --state traces/recorder-session.json \
  --name "Morning inbox" \
  --description "Review unread support messages" \
  --input "support inbox" \
  --output "triaged messages" \
  --tag email \
  --risk-class medium \
  --expected-duration-seconds 420
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

Review metadata can be updated before save:

```bash
desktop-agent record review \
  --state traces/recorder-session.json \
  --routine-name "Daily inbox triage" \
  --description "Review unread support messages" \
  --input "support inbox" \
  --output "draft replies" \
  --tag email \
  --risk-class medium \
  --expected-duration-seconds 420
```

The saved JSON uses `deskpilot_recorder_session_v1` and contains the session
ID, name, status, timestamps, review metadata, event count, and recorder
events. Review metadata captures routine name, description, inputs, outputs,
tags, risk class, and expected duration. Recorder events are timestamped records
with an event type (`observation`, `input_event`, or `selected_point`),
active-window title, screenshot path, selected point, low-level input payload,
candidate context, and metadata. Candidate context can carry source, label, UIA
control type, bounds, confidence, and source-specific metadata.

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
When an observation event carries planner-style `state_delta` metadata, the
generator adds a visible-text verification suggestion to the previous action
from newly appeared text such as `visible_text_added`.
Generated task metadata includes the reviewed routine name, description, inputs,
outputs, tags, risk class, and expected duration so trace artifacts and final
reports can surface the operator-reviewed routine contract.

## Test Coverage

Recorder tests include fake browser and native event streams that generate valid
tasks without real desktop input. The browser stream also runs through the
dry-run execution pipeline and checks `task.json` plus `final-report.json` for
the reviewed routine metadata and inferred verification.
