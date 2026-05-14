# Windows E2E Checklist

Use this checklist for the manual validation that cannot run on macOS or Linux.
Run it on an unlocked, logged-in Windows desktop session.

## Prerequisites

- Install Python 3.12 and run `uv sync --extra dev --extra windows --extra ocr --extra cv`.
- Keep the primary monitor active and avoid overlapping the fixture windows.
- Confirm the emergency stop hotkey is available: `ctrl+alt+esc`.
- Build the package with `scripts/build-windows-exe.ps1`.

## Packaged Executable

Run these from the repository root in PowerShell:

```powershell
dist\deskpilot.exe --help
dist\deskpilot.exe dry-run examples\browser-task.yaml --config packaging\default-config.yaml
dist\deskpilot.exe inspect-screen --output traces\manual-inspection
```

Expected result:

- `--help` exits successfully and lists the CLI commands.
- `dry-run` exits successfully, writes a trace directory, and does not move the mouse.
- `inspect-screen` writes `inspect-screen.json` and a screenshot when enabled.

## Opt-In Pytest Smoke Tests

After preparing the browser and native fixtures below, run the Windows smoke
tests explicitly:

```powershell
$env:DESKPILOT_WINDOWS_SMOKE = "1"
pytest -m windows_smoke tests\test_windows_smoke.py
```

Expected result:

- `inspect-screen` writes an unlocked desktop inspection report and screenshot.
- The browser fixture real `run` exits with status `passed`.
- The native fixture real `run` exits with status `passed`.
- These tests remain skipped unless `DESKPILOT_WINDOWS_SMOKE=1` is set.

## Browser Fixture

1. Open `examples\browser_fixture.html` in the browser.
2. Make the window title visible as `DeskPilot Browser Fixture`.
3. Run:

```powershell
dist\deskpilot.exe run examples\browser-task.yaml --config packaging\default-config.yaml
```

Expected result:

- The email field is filled with `qa@example.test`.
- The page scrolls to the submit button.
- The task clicks the submit button and verifies `Browser fixture success`.
- The final report status is `passed`.

## Native Fixture

1. Run `python examples\native_fixture.py`.
2. Confirm the window title is `DeskPilot Native Fixture`.
3. Run:

```powershell
dist\deskpilot.exe run examples\native-task.yaml --config packaging\default-config.yaml
```

Expected result:

- The input receives `DeskPilot native demo`.
- The submit action verifies `Native fixture success`.
- The menu-state action verifies `Menu opened`.
- The final report status is `passed`.

## Mixed Fixture

1. Open the browser fixture and start the native fixture.
2. Put the browser fixture in the foreground and the native fixture behind it.
3. Run:

```powershell
dist\deskpilot.exe run examples\mixed-task.yaml --config packaging\default-config.yaml
```

Expected result:

- The browser fixture completes first.
- `alt+tab` switches to the native fixture.
- The native fixture completes final verification.
- The final report status is `passed`.

## Safety And Reports

- Press `ctrl+alt+esc` during a run and confirm it stops within one second.
- Start a run with a different foreground window and confirm it fails before input.
- Inspect the trace directory for `config.json`, `task.json`, `action-log.jsonl`,
  `final-report.json`, `final-report.md`, screenshots, OCR output, and candidate
  overlays where enabled.
- Confirm failure reports include an abort reason, step message, candidate
  metadata, and screenshots sufficient to debug the run locally.
