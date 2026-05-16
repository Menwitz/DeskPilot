# Mixed Fixture Proof

`desktop-agent proof mixed-fixture` is a Windows-only proof command for a real
browser-to-native handoff. It opens a generated local browser fixture in
Microsoft Edge, opens a fresh Notepad window, types native text, switches back
to Edge with `Alt+Tab`, and uses browser Find to confirm the browser fixture is
again focused.

The command does not use Playwright, DevTools, app APIs, accessibility write
APIs, or synthetic window switching.

## Run

From the repository root on an owned, unlocked Windows desktop:

```powershell
uv run desktop-agent proof mixed-fixture --countdown-seconds 5
```

Useful options:

```powershell
uv run desktop-agent proof mixed-fixture `
  --trace-root traces `
  --random-seed 20260515 `
  --movement-smoothness 0.85 `
  --countdown-seconds 5 `
  --native-text "DeskPilot mixed native handoff" `
  --browser-find-text "DeskPilot Browser Fixture" `
  --page-load-seconds 1.5
```

## Expected Behavior

- Edge opens the generated local browser fixture.
- Notepad opens as a real native Windows application.
- DeskPilot types the configured native handoff text into Notepad.
- DeskPilot sends `Alt+Tab` to switch back to Edge.
- Edge Find searches for the configured browser fixture text.
- A report and proof manifest are written under
  `traces/<timestamp>-mixed-fixture/`.

## Expected Artifacts

- `browser-fixture.html`
- `browser-fixture-result.html`
- `mixed-fixture-report.json`
- `proof-manifest.json`
- `action-log.jsonl`
- `screenshots/*.png`

Review the bundle with:

```powershell
uv run desktop-agent proof replay traces/<timestamp>-mixed-fixture
```

Use [Windows Proof Evidence Checklist](windows-proof-evidence-checklist.md) to
record the video, trace, manifest, screenshots, replay output, and reviewer
decision.

## Acceptance

- [ ] The command exits with `status: passed`.
- [ ] Video shows Edge opening the local browser fixture.
- [ ] Video shows Notepad opening after the browser step.
- [ ] Video shows native handoff text typed into Notepad.
- [ ] Video shows `Alt+Tab` returning focus to Edge.
- [ ] Video shows Edge Find searching the browser fixture text.
- [ ] `mixed-fixture-report.json` contains post-action evidence for each step.
- [ ] `proof-manifest.json` links command, environment metadata, report, action
      log, screenshots, and trace directory.
- [ ] Reviewer confirms no browser API, app API, accessibility write API, or
      synthetic window switch was used.
