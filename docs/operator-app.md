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
run ID, current routine, current step, screenshot preview path, selected target,
next action, elapsed seconds, run status, and stop controls: pause, resume,
cancel, normal stop, and emergency stop. Emergency stop is represented as the
terminal `emergency_stopped` run-queue state. The dashboard also includes trace
health state with local trace counts by report kind and status, plus an
attention status and attention trace count when failed or unknown local reports
need review.

The Approvals page includes the approval dialog contract. It shows routine ID,
step ID, risk class, checkpoint evidence, content fingerprint, current status,
approver, decision reason, decision timestamp, and explicit approve/deny
actions before high-risk work can continue.

The Record page includes the recorder review panel. It shows generated YAML,
selected targets, screenshot paths, verification suggestions, and review status
before the operator saves a routine. The recorder service can save the reviewed
capture into the local `recorded` routine pack and hand the saved routine ID
back to the runner for rerun through the same app service boundary.

The Routine Packs page includes the routine-pack manager contract. It shows
installed pack IDs, selected pack, install source, pending action, trust
warnings, and explicit install, replace, remove, and export actions. Install and
remove operations go through manifest validation and local pack operations
rather than ad hoc file copying.

The Trace Viewer page includes the trace timeline contract. It shows video,
screenshots, action log, candidate reasoning, state delta, verification results,
report kind, final report, and load status so failed runs can be inspected
without rerunning desktop input. Proof-suite finalization reports surface their
suite, promotion, and archive gate statuses as proof-gate lines in the same
timeline state. Goal-plan reports surface ranked candidate routines as
candidate-reasoning lines for planner review.
The same page includes failure-analysis review state with proposal count,
rationale, YAML snippets, `review_required`, and `applies_automatically` fields
so proposed fixes remain manual until approved.
The trace service can analyze a failed trace, write
`failed-run-analysis.json` and `failed-run-analysis.md`, and return concise
failure reasons for the app timeline. The app controller can also hydrate the
trace-viewer state directly from a local trace report, including proof-suite
finalization reports discovered by the trace service.

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

`desktop_agent.operator_services.OperatorAppService` defines the app-facing
service boundary. The initial concrete bundle is local-only and wraps existing
project modules:

- Catalog service: list, search, and inspect routine definitions.
- Recorder service: start capture, append captured events, generate editable
  YAML for review, save the reviewed capture as a routine, and expose the saved
  routine for rerun.
- Runner service: apply the validated routine execution gate, start approved
  app run requests, and publish the first `observe_screen` action for the live
  run panel. Its `dry_run_routine` preflight compiles the selected routine,
  renders the shared dry-run preview, and returns compiled task metadata without
  desktop input. It also handles pause, resume, cancel, and stop requests so the
  app state and run queue monitoring stay synchronized.
- Scheduler service: expose shared run queue metadata so app-started runs are
  visible in monitoring without using CLI commands.
- Approval service: list active routines requiring operator approval and record
  evidence-backed approve or deny decisions with checkpoint evidence, content
  fingerprint, approver, reason, and decision timestamp.
- Trace service: list local trace directories, read run, goal-plan, benchmark,
  and proof-suite finalization JSON reports, and inspect failed traces with
  local review-only analysis artifacts. It also exposes trace health counts by
  kind, status, attention state, attention trace count, and artifact trace
  count for dashboard monitoring, including trace-health schema/timestamp
  metadata and any local `replay-summary.md` artifact path. Benchmark trace
  summaries also expose the report artifact manifest and compact trace-health
  summary from `benchmark-report.json`.
- Trace health panel state: renders the trace-health schema version and
  generation timestamp beside trace, attention, artifact, and benchmark
  health counts from artifact or latest trace metadata so dashboard screenshots
  identify the monitoring contract in use.
- Trace viewer state: benchmark reports render with benchmark kind, acceptance
  status, baseline comparison status, monitoring coverage status, and
  schema/timestamp metadata, compact trace-health status, plus benchmark report
  artifact links.
- Routine-pack service: list installed packs, install validated local packs,
  and remove installed packs.

The PySide widgets should use these services instead of shelling out to CLI
commands. This keeps the app, CLI, tests, and future packaging on the same local
safety and trace contracts.
