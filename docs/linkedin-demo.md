# LinkedIn Edge Demo

`desktop-agent demo-linkedin` is a Windows-only low-level browser input demo. It
opens Microsoft Edge, uses real keyboard input to navigate to LinkedIn, scrolls
the page with the real cursor, and uses Edge's Find box to highlight text on the
loaded page.

This demo is intentionally logged-out friendly. It does not enter credentials,
post content, click profile actions, or depend on LinkedIn account state.

## Run

From the repository root on an unlocked Windows desktop:

```powershell
uv run desktop-agent demo-linkedin
```

Expected result:

- The command counts down so you can stop touching the mouse and keyboard.
- Edge opens in a fresh window.
- The address bar is focused with `Ctrl+L`.
- DeskPilot types `https://www.linkedin.com/` and presses Enter.
- After the configured page-load wait, the real cursor scrolls the page.
- Edge Find opens with `Ctrl+F`, DeskPilot types `LinkedIn`, and the browser
  highlights the matching text.
- A report is written under `traces/<timestamp>-linkedin-demo/`.

Useful options:

```powershell
uv run desktop-agent demo-linkedin `
  --trace-root traces `
  --random-seed 20260515 `
  --movement-smoothness 0.85 `
  --countdown-seconds 3 `
  --url "https://www.linkedin.com/" `
  --find-text "LinkedIn" `
  --page-load-seconds 5
```

## What It Proves

This command demonstrates low-level control against a real browser and real web
page without OCR, UIA, browser automation APIs, Playwright, or a fixture window.
The trace records launch metadata, keyboard cadence, pointer frames with
`GetCursorPos` readback, wheel events, and final status.

## Safety

Run this only inside an owned, unlocked Windows desktop or VM. The demo performs
safe browser actions only: navigation, page scroll, and browser Find. Close
sensitive windows before running because the input is global.
