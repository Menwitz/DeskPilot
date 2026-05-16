# Operator App

The native operator app is an optional PySide6 surface for local routine work.
Install it with `deskpilot[app]`; the CLI and execution pipeline remain usable
without PySide6.

## Shell

The Phase 8 shell defines these pages:

- Dashboard: daily status, recent runs, and next safe action.
- Routine Library: list, search, inspect, dry-run, and run routines.
- Routine Packs: install, replace, export, and remove local routine packs.
- Record: capture a demonstrated routine and review generated YAML.
- Run Queue: monitor scheduled, running, paused, and blocked routines.
- Approvals: review high-risk steps before local execution continues.
- Trace Viewer: inspect screenshots, action logs, evidence, reports, and
  review-only failed-run analysis proposals.
- Settings: configure local trace, safety, model, and proof options.
- Help: show local guidance, safety boundaries, and diagnostics.

The Dashboard includes the first live run panel. Its state contract tracks the
current routine, current step, screenshot preview path, selected target, next
action, elapsed seconds, run status, and stop controls: pause, resume, cancel,
and emergency stop.

The Approvals page includes the approval dialog contract. It shows routine ID,
step ID, risk class, checkpoint evidence, content fingerprint, current status,
and explicit approve/deny actions before high-risk work can continue.

The Record page includes the recorder review panel. It shows generated YAML,
selected targets, screenshot paths, verification suggestions, and review status
before the operator saves a routine.

The Routine Packs page includes the routine-pack manager contract. It shows
installed pack IDs, selected pack, install source, pending action, trust
warnings, and explicit install, replace, remove, and export actions. Install and
remove operations go through manifest validation and local pack operations
rather than ad hoc file copying.

The Trace Viewer page includes the trace timeline contract. It shows video,
screenshots, action log, candidate reasoning, state delta, final report, and
load status so failed runs can be inspected without rerunning desktop input.
The same page includes failure-analysis review state with proposal count,
rationale, YAML snippets, `review_required`, and `applies_automatically` fields
so proposed fixes remain manual until approved.

The Settings page includes trace root, screenshot saving, video capture, Ollama
enablement, emergency hotkey, default activity profile, and proof-mode fields.
The initial state can be built from `RuntimeConfig` so the app and CLI share
the same local defaults.

## State Transitions

`desktop_agent.operator_app_state` contains a small controller for UI state
transitions. Tests can inject fake runner services and verify page selection,
routine start, blocked runs, pause, resume, cancel, approval request, and
approval resolution without launching PySide6. The PySide shell should use the
same controller so UI behavior stays tied to the service boundary.

`deskpilot-app --describe-shell` prints this shell contract without importing
PySide6. `deskpilot-app --check` verifies that the entry point is installed and
reports whether PySide6 is available.

The first implementation keeps the page contract in
`desktop_agent.operator_app_shell` so the future service layer and PySide
widgets can share the same page IDs in tests, packaging, and documentation.

## Local Service Boundary

`desktop_agent.operator_services` defines the app-facing service boundary. The
initial concrete bundle is local-only and wraps existing project modules:

- Catalog service: list, search, and inspect routine definitions.
- Recorder service: expose supported recording operations.
- Runner service: apply the validated routine execution gate before runs.
- Scheduler service: expose immutable run queue metadata.
- Approval service: list active routines requiring operator approval.
- Trace service: list local trace directories and read JSON reports.
- Routine-pack service: list installed packs, install validated local packs,
  and remove installed packs.

The PySide widgets should use these services instead of shelling out to CLI
commands. This keeps the app, CLI, tests, and future packaging on the same local
safety and trace contracts.
