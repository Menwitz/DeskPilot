# Browser Fixture Proof

`desktop-agent proof browser-fixture` is a Windows-only proof command for a real
browser form/navigation workflow. It writes local HTML fixture and result pages
into the trace directory, opens the fixture in Microsoft Edge, clicks the form
input with the real cursor, types text with the real keyboard, submits the form
to navigate to the local result page, then uses browser Find to search for the
resulting confirmation text.

The command does not use Playwright, DevTools, browser extension APIs, DOM
automation, or a synthetic cursor.

## Run

From the repository root on an owned, unlocked Windows desktop:

```powershell
uv run desktop-agent proof browser-fixture --countdown-seconds 5
```

Useful options:

```powershell
uv run desktop-agent proof browser-fixture `
  --trace-root traces `
  --random-seed 20260515 `
  --movement-smoothness 0.85 `
  --countdown-seconds 5 `
  --fixture-text "DeskPilot browser fixture" `
  --result-text "DeskPilot browser fixture submitted" `
  --page-load-seconds 1.5
```

## Expected Behavior

- The command writes `browser-fixture.html` and
  `browser-fixture-result.html` into the trace directory.
- Edge opens the generated local file in a real browser window.
- The real cursor clicks the fixture input field.
- DeskPilot types the configured fixture text.
- DeskPilot presses Enter to submit the form and navigate to the result page.
- Edge Find searches for the configured result text after submission.
- A report and proof manifest are written under
  `traces/<timestamp>-browser-fixture/`.

## Expected Artifacts

- `browser-fixture.html`
- `browser-fixture-result.html`
- `browser-fixture-report.json`
- `proof-manifest.json`
- `action-log.jsonl`
- `screenshots/*.png`

Review the bundle with:

```powershell
uv run desktop-agent proof replay traces/<timestamp>-browser-fixture
```

Use [Windows Proof Evidence Checklist](windows-proof-evidence-checklist.md) to
record the video, trace, manifest, screenshots, replay output, and reviewer
decision.

## Acceptance

- [ ] The command exits with `status: passed`.
- [ ] Video shows Edge opening the local fixture file.
- [ ] Video shows the real cursor focusing the form input.
- [ ] Video shows typed fixture text in the form.
- [ ] Video shows the form submission and result text search.
- [ ] `browser-fixture-report.json` contains post-action evidence for each step.
- [ ] `proof-manifest.json` links command, environment metadata, report, action
      log, screenshots, and trace directory.
- [ ] Reviewer confirms no browser automation API or fixture-only fake cursor was
      used.
