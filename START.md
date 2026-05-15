# Start Here

This file is the practical runbook for installing, testing, and trying
DeskPilot from the repository root.

## 1. Install Dependencies

From `/Users/roshi/Documents/DeskPilot`:

```bash
uv sync --extra dev --extra cv --extra ocr
```

For real Windows desktop automation, install the Windows extra too:

```powershell
uv sync --extra dev --extra windows --extra ocr --extra cv
```

## 2. Run Local Quality Checks

These checks should pass on macOS, Linux, and Windows:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
uv build
uv run desktop-agent --help
```

Expected result:

- Lint, formatting, and type checks pass.
- The test suite passes.
- The package build creates source and wheel distributions.
- `desktop-agent --help` lists `run`, `dry-run`, `inspect-screen`, and `replay`.

## 3. Try Safe Dry-runs

Dry-run validates YAML tasks and runs the planner without moving the mouse or
typing keys.

```bash
uv run desktop-agent dry-run examples/browser-task.yaml --config packaging/default-config.yaml
uv run desktop-agent dry-run examples/native-task.yaml --config packaging/default-config.yaml
uv run desktop-agent dry-run examples/mixed-task.yaml --config packaging/default-config.yaml
```

Expected result:

- Each command prints `status: passed`.
- Each command writes a trace directory under `traces/`.
- No desktop input is sent.

## 4. Inspect The Current Screen

```bash
uv run desktop-agent inspect-screen --output traces/manual-inspection
```

Expected result:

- `traces/manual-inspection/inspect-screen.json` is written.
- Screenshot metadata is included when screen capture is available.
- OCR data is included when local Tesseract is installed.
- Windows UIA data is only available on Windows.

## 5. Demonstrate Mouse Manipulation On Windows

This validates the real Windows mouse actuator without relying on OCR, UIA, or
target selection:

```powershell
uv run desktop-agent demo-mouse
```

Expected result:

- A `DeskPilot Mouse Demo` window opens.
- The pointer visibly follows smooth paths, clicks, drags, scrolls, and clicks
  finish inside the local fixture.
- A report is written under `traces\<timestamp>-mouse-demo\`.

## 6. Real Desktop Runs On Windows

Real mouse and keyboard automation is Windows-first in v1. Keep the Windows
session unlocked, use the primary monitor, and make the relevant fixture window
visible.

Run the checks first:

```powershell
uv sync --extra dev --extra windows --extra ocr --extra cv
uv run pytest
uv run desktop-agent --help
```

### Browser Fixture

```powershell
start examples\browser_fixture.html
uv run desktop-agent run examples\browser-task.yaml --config packaging\default-config.yaml
```

Expected result:

- The browser fixture email field is filled.
- The page scrolls to the submit button.
- The task verifies `Browser fixture success`.

### Native Fixture

```powershell
python examples\native_fixture.py
uv run desktop-agent run examples\native-task.yaml --config packaging\default-config.yaml
```

Expected result:

- The native fixture input is filled.
- The submit action verifies `Native fixture success`.
- The menu-state action verifies `Menu opened`.

### Mixed Fixture

```powershell
start examples\browser_fixture.html
python examples\native_fixture.py
uv run desktop-agent run examples\mixed-task.yaml --config packaging\default-config.yaml
```

Expected result:

- The browser fixture completes first.
- `alt+tab` switches to the native fixture.
- The native fixture completes final verification.

## 7. Package And Test The Windows Executable

Run these from PowerShell on Windows:

```powershell
scripts\build-windows-exe.ps1
scripts\verify-windows-package.ps1
dist\deskpilot.exe --help
dist\deskpilot.exe dry-run examples\browser-task.yaml --config packaging\default-config.yaml
```

For the full manual checklist, use:

- `docs/windows-e2e-checklist.md`

## 8. Read Traces And Reports

Every run writes local trace artifacts under `traces/` unless configured
otherwise.

Common files:

- `config.json`
- `task.json`
- `action-log.jsonl`
- `final-report.json`
- `final-report.md`
- screenshots, OCR output, and candidate overlays when enabled

Replay a trace summary:

```bash
uv run desktop-agent replay traces/<trace-directory>
```

## 9. Platform Expectations

On macOS or Linux, this command should fail clearly because real actuation is
not available there in v1:

```bash
uv run desktop-agent run examples/browser-task.yaml --config packaging/default-config.yaml
```

That is expected. Use `dry-run` for local planning checks on non-Windows
machines.
