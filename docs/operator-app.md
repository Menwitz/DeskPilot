# Operator App

The native operator app is an optional PySide6 surface for local routine work.
Install it with `deskpilot[app]`; the CLI and execution pipeline remain usable
without PySide6.

## Shell

The Phase 8 shell defines these pages:

- Dashboard: daily status, recent runs, and next safe action.
- Routine Library: list, search, inspect, dry-run, and run routines.
- Record: capture a demonstrated routine and review generated YAML.
- Run Queue: monitor scheduled, running, paused, and blocked routines.
- Approvals: review high-risk steps before local execution continues.
- Trace Viewer: inspect screenshots, action logs, evidence, and reports.
- Settings: configure local trace, safety, model, and proof options.
- Help: show local guidance, safety boundaries, and diagnostics.

`deskpilot-app --describe-shell` prints this shell contract without importing
PySide6. `deskpilot-app --check` verifies that the entry point is installed and
reports whether PySide6 is available.

The first implementation keeps the page contract in
`desktop_agent.operator_app_shell` so the future service layer and PySide
widgets can share the same page IDs in tests, packaging, and documentation.
