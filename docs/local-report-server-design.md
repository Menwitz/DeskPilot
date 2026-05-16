# Optional Local Report Server Design

This is a post-native-app design track. DeskPilot local execution must remain
fully functional without a report server. The report server, if built later,
should only index and display local artifacts that already exist on disk.

## Boundary

- No execution authority: the server cannot start runs, click, type, approve,
  bypass approvals, or mutate routine packs.
- Read-only by default: it reads trace directories, routine-pack proof bundles,
  catalog indexes, and generated reports.
- Local-first: the default bind address is loopback only.
- Optional: CLI, recorder, planner, operator app, and proof replay work without
  the server.
- Redaction-aware: it must respect metadata-only traces, screenshot policies,
  OCR suppression, typed-text masking, and video disable policy.

Regression coverage must keep local fake-input execution, dry-run validation,
trace writing, routine-pack testing, and proof replay independent from any
report-server process or endpoint. A configured report-server URL must not
become part of the local execution path.

## Candidate Inputs

- `traces/*/final-report.json`
- `traces/*/action-log.jsonl`
- `traces/*/replay-summary.md`
- `traces/*/proof-manifest.json`
- `traces/*/proof-finalization-status.json`
- `traces/*/pack-test-report.json`
- `docs/routine-catalog-index.md`
- routine-pack proof bundles from `write-routine-pack-proof`

## Candidate Views

- Routine health: latest status, failure count, quarantine status, and proof
  status by routine ID.
- Pack health: manifest trust level, trust warnings, conflict warnings,
  pack-level test result, and proof checklist status.
- Trace review: final report, replay summary, screenshots, video paths,
  target reasoning, state deltas, and redaction mode.
- Goal planning review: selected routine, candidates, missing inputs, approval
  needs, schedule eligibility, and local model disclosure.

## Security Notes

- Bind to `127.0.0.1` by default and require an explicit opt-in for any other
  interface.
- Do not serve raw screenshots, OCR text, typed text, or videos when the trace
  policy is redacted or metadata-only.
- Treat report import as untrusted local file parsing: reject path traversal,
  symlinks outside configured roots, and unexpected schema versions.
- Keep any future team/reporting sync separate from the local execution engine.

## Open Questions

- Whether the first implementation should be a static report exporter, a small
  loopback HTTP server, or a page inside the native app.
- How to authenticate a browser view without adding account management to the
  local product.
- Whether report annotations should write sidecar files or remain in the
  operator app state only.
- How long trace indexes should be retained before the user archives or deletes
  them.
