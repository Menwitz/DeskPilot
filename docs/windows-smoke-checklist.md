# Windows Smoke Checklist Command

`desktop-agent windows-smoke-checklist` runs a bounded real-input smoke check on
an owned, unlocked Windows desktop.

It verifies the first layer of the desktop I/O stack:

- the real cursor position can be read;
- Notepad can be launched;
- text can be typed through low-level keyboard input;
- Microsoft Edge can be launched;
- post-action screenshots, active-window metadata, cursor readbacks, reports,
  and monitoring logs are written to the trace.

## Run

```powershell
uv run desktop-agent windows-smoke-checklist --countdown-seconds 5
```

Useful options:

```powershell
uv run desktop-agent windows-smoke-checklist `
  --trace-root traces `
  --random-seed 20260515 `
  --movement-smoothness 0.85 `
  --countdown-seconds 5 `
  --keyboard-text "DeskPilot Windows smoke check" `
  --edge-url "about:blank"
```

## Expected Artifacts

The command writes a trace directory like:

```text
traces/<timestamp>-windows-smoke-checklist/
```

Expected files:

- `windows-smoke-checklist-report.json`
- `windows-smoke-checklist.md`
- `action-log.jsonl`
- `screenshots/*.png`

## Acceptance

- [ ] The command exits with `status: passed`.
- [ ] Notepad opens and shows the configured smoke text.
- [ ] Edge opens in a fresh window.
- [ ] The report contains `post_action_evidence` for every smoke check.
- [ ] `action-log.jsonl` contains one line per smoke check.
- [ ] `screenshots/` contains post-action screenshots.
