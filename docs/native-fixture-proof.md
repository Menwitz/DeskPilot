# Native Fixture Proof

`desktop-agent proof native-fixture` is a Windows-only proof command for a real
native application workflow. It opens a fresh Notepad window, types configured
text through low-level keyboard input, selects the buffer with `Ctrl+A`, replaces
the text, and records cursor/focus/screenshot evidence after each step.

The command does not use app APIs, accessibility write APIs, clipboard
injection, or a synthetic text surface.

## Run

From the repository root on an owned, unlocked Windows desktop:

```powershell
uv run desktop-agent proof native-fixture --countdown-seconds 5
```

Useful options:

```powershell
uv run desktop-agent proof native-fixture `
  --trace-root traces `
  --random-seed 20260515 `
  --movement-smoothness 0.85 `
  --countdown-seconds 5 `
  --initial-text "DeskPilot native fixture" `
  --replacement-text "DeskPilot native fixture updated"
```

## Expected Behavior

- Notepad opens as a real native Windows application.
- DeskPilot types the configured initial text.
- DeskPilot sends `Ctrl+A` to select the Notepad buffer.
- DeskPilot types the configured replacement text.
- A report and proof manifest are written under
  `traces/<timestamp>-native-fixture/`.

## Expected Artifacts

- `native-fixture-report.json`
- `proof-manifest.json`
- `action-log.jsonl`
- `screenshots/*.png`

Review the bundle with:

```powershell
uv run desktop-agent proof replay traces/<timestamp>-native-fixture
```

Use [Windows Proof Evidence Checklist](windows-proof-evidence-checklist.md) to
record the video, trace, manifest, screenshots, replay output, and reviewer
decision.

## Acceptance

- [ ] The command exits with `status: passed`.
- [ ] Video shows a fresh Notepad window opening.
- [ ] Video shows the initial text typed into Notepad.
- [ ] Video shows `Ctrl+A` selecting the text.
- [ ] Video shows replacement text appearing in Notepad.
- [ ] `native-fixture-report.json` contains post-action evidence for each step.
- [ ] `proof-manifest.json` links command, environment metadata, report, action
      log, screenshots, and trace directory.
- [ ] Reviewer confirms no app API, accessibility write API, clipboard
      injection, or fake text surface was used.
