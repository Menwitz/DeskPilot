# DeskPilot

DeskPilot is a Windows-first local desktop automation system for ops teams
running approved content workflows and controlled desktop tasks.

The v1 goal is deterministic YAML/CLI execution on an unlocked, logged-in
Windows desktop session. The runtime combines local screen capture, OCR,
computer vision, and Windows UI Automation so approved site playbooks and local
desktop tasks can run with local evidence. Approval records, screenshots, OCR
output, traces, and reports stay local by default.

## Safety Boundaries

DeskPilot is for controlled environments where the operator owns or is
authorized to automate the desktop session, target account, application, or
content workflow. v1 does not support stealth automation, CAPTCHA bypass,
bot-detection evasion, credential abuse, or abusive third-party automation.

## Requirements

- Python 3.12 or newer.
- Windows for real desktop automation in v1.
- An unlocked, logged-in desktop session for any task that moves the mouse,
  sends keys, reads windows, or captures the screen.
- YAML-authored tasks, site playbooks, approval records, and content variables
  for repeatable ops-team workflows.

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
desktop-agent demo-input
desktop-agent demo-linkedin
desktop-agent windows-smoke-checklist
desktop-agent dry-run-site linkedin open-search
desktop-agent inspect-screen --output traces/manual-inspection
desktop-agent replay traces/example-run
```

`dry-run` validates and plans through the local execution pipeline without
desktop input. `run` and `run-site` use the platform actuator on Windows and
fail with a clear unavailable message on unsupported platforms.

## Project Layout

- `src/desktop_agent/` contains the Python package.
- `tests/` contains unit and integration tests.
- `examples/` contains safe deterministic sample workflows and fixtures.
- `docs/` contains architecture, task DSL, safety, and roadmap documentation.
- `PLAN.md` is the implementation checklist updated as tasks are completed.
- `docs/vision-alignment-action-plan.md` tracks the ops content workflow
  alignment work.

## Documentation

- [Project definition](docs/project-definition.md)
- [Actuation](docs/actuation.md)
- [Architecture](docs/architecture.md)
- [V1 Acceptance](docs/acceptance.md)
- [Candidate Fusion](docs/candidate-fusion.md)
- [Computer Vision](docs/computer-vision.md)
- [Configuration](docs/configuration.md)
- [Desktop I/O Control Roadmap](docs/desktop-io-control-roadmap.md)
- [Examples](docs/examples.md)
- [LinkedIn Edge Demo](docs/linkedin-demo.md)
- [Real Input Demo](docs/mouse-demo.md)
- [OCR](docs/ocr.md)
- [Packaging](docs/packaging.md)
- [Planner](docs/planner.md)
- [Post-v1 Backlog](docs/post-v1-backlog.md)
- [Screen layer](docs/screen.md)
- [Task DSL](docs/task-dsl.md)
- [Website Navigation Playbook Roadmap](docs/website-navigation-playbook-roadmap.md)
- [Website Navigation Playbook Catalog](navigation_playbooks/README.md)
- [Website Playbooks](docs/website-playbooks.md)
- [Website Playbook Capability Demo](docs/website-playbook-demo.md)
- [Vision Alignment Action Plan](docs/vision-alignment-action-plan.md)
- [Safety](docs/safety.md)
- [Tracing](docs/tracing.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Windows Smoke Checklist Command](docs/windows-smoke-checklist.md)
- [Windows E2E Checklist](docs/windows-e2e-checklist.md)
- [Windows UI Automation](docs/windows-uia.md)
- [Roadmap](docs/roadmap.md)
