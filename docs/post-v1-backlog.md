# Post-v1 Backlog

These items are intentionally outside the v1 acceptance boundary. Each item must
preserve the v1 safety model: local-first operation, explicit allowed windows,
bounded execution, dry-run support, trace events, and final reports.

## Platform Expansion

### Linux X11 Adapter

- Add an X11 screen observer, active-window detector, and input backend behind
  the existing `screen`, `safety`, and `actuation` interfaces.
- Keep coordinate conversion explicit because X11 virtual desktops and scaling
  vary by window manager.
- Required evidence: fake X11 adapter tests, dry-run tests, and a manual
  unlocked-session checklist matching the Windows checklist.

### Linux Wayland Compatibility Investigation

- Research compositor-specific limitations for screenshots, active windows, and
  input injection.
- Decide whether the adapter should support only portal-mediated capture and
  application-owned automation contexts.
- Required evidence: findings doc, risk matrix, and a recommendation before any
  implementation starts.

## Authoring And Perception

### Visual Task Recorder

- Record operator-selected actions into YAML while preserving explicit
  `allowed_windows`, selectors, regions, and verification steps.
- Prefer selectors over raw coordinates when UIA/OCR/CV candidates are
  available.
- Required evidence: generated task validation tests and trace replay examples.

### Optional Local Vision Model

- Add a local-only model adapter behind `PerceptionEngine`.
- Keep deterministic UIA/OCR/CV ranking first unless the task opts into model
  candidates.
- Required evidence: fixture tests, confidence calibration notes, and candidate
  ranking trace metadata.

### Optional Cloud VLM Adapter Disabled By Default

- Treat this as an explicit enterprise integration, not a v1 default.
- Require redaction controls, opt-in config, and documentation of data leaving
  the machine.
- Required evidence: safety review, config validation tests, and trace fields
  that disclose when cloud inference is used.

## Trace And Reporting

### Redacted Trace Mode

- Add redaction policies for screenshots, OCR text, typed text, and report
  fields.
- Preserve enough metadata for debugging without storing sensitive content.
- Required evidence: unit tests for redaction boundaries and report snapshots.

### Team Report Server

- Build as an optional separate service that ingests local run artifacts.
- Keep the local file trace sink as the source of truth.
- Required evidence: authentication design, upload failure behavior, and local
  fallback tests.

## Distributed Execution

### Remote Worker Orchestration

- Keep remote workers scoped to owned machines and explicit task queues.
- Require per-worker allowed-window policy, local traces, and heartbeat status.
- Required evidence: queue contract tests, worker safety tests, and operator
  abort semantics.

## Operator Experience

### Rich Desktop Tray UI

- Surface run state, emergency stop, active trace directory, and recent reports.
- Do not hide safety prompts or whitelist decisions behind the tray.
- Required evidence: manual UX checklist and integration tests around run state
  transitions.

## Planning

### More Advanced Recovery Planning

- Expand recovery beyond the v1 fixed actions only when trace evidence shows
  repeated recoverable failures.
- Keep each recovery bounded by retries, timeouts, and allowed-window checks.
- Required evidence: planner tests for every recovery branch and report fields
  explaining why a recovery was chosen.

## Extensibility

### Plugin System For App-specific Task Libraries

- Define a plugin manifest for app selectors, reusable task fragments, fixtures,
  and documentation.
- Load plugins explicitly from trusted local paths.
- Required evidence: schema validation, conflict handling tests, and example
  plugin docs.
