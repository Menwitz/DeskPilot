# DeskPilot

DeskPilot is a Windows-first local desktop automation framework for owned QA
workflows and personal automation.

The v1 goal is deterministic task execution on an unlocked, logged-in Windows
desktop session using YAML tasks, local screen capture, OCR, computer vision,
and Windows UI Automation. Screenshots, OCR output, traces, and reports stay
local by default.

## Safety Boundaries

DeskPilot is for controlled environments where the operator owns the desktop
session, the application under test, or the internal QA scope. v1 does not
support stealth automation, CAPTCHA bypass, bot-detection evasion, credential
abuse, or abusive third-party automation.

## Requirements

- Python 3.12 or newer.
- Windows for real desktop automation in v1.
- An unlocked, logged-in desktop session for any task that moves the mouse,
  sends keys, reads windows, or captures the screen.

## Quickstart

```bash
uv sync --extra dev
uv run pytest
uv run ruff check .
uv run mypy
uv build
```

The package verifies that the project installs, imports, exposes the CLI entry
point, and passes the quality pipeline.

## CLI

```bash
desktop-agent dry-run examples/task.yaml --allowed-window "DeskPilot Fixture"
desktop-agent run examples/task.yaml --allowed-window "DeskPilot Fixture"
desktop-agent inspect-screen --output traces/manual-inspection
desktop-agent replay traces/example-run
```

`dry-run` validates and plans through the local execution pipeline without
desktop input. `run` is wired into the same pipeline but intentionally fails
until real actuation adapters are implemented.

## Project Layout

- `src/desktop_agent/` contains the Python package.
- `tests/` contains unit and integration tests.
- `examples/` contains safe deterministic sample workflows and fixtures.
- `docs/` contains architecture, task DSL, safety, and roadmap documentation.
- `PLAN.md` is the implementation checklist updated as tasks are completed.

## Documentation

- [Project definition](docs/project-definition.md)
- [Architecture](docs/architecture.md)
- [Configuration](docs/configuration.md)
- [Screen layer](docs/screen.md)
- [Task DSL](docs/task-dsl.md)
- [Safety](docs/safety.md)
- [Roadmap](docs/roadmap.md)
