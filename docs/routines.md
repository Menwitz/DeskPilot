# Routines

Routine definitions are the reviewed catalog records that sit above task YAML
and website playbooks. A routine definition describes what the routine is for,
what it needs, what it produces, how risky it is, and which executable task or
playbook flow implements it.

## Schema

```yaml
id: browser.search
name: Browser search
description: Search from a browser input.
goal: Submit a search query and verify results.
required_app: Microsoft Edge
required_site: example.com
tags:
  - browser
  - search
inputs:
  - query
outputs:
  - results page
safety_class: low
schedule_policy: manual
approval_policy: none
expected_duration_seconds: 30
schedule:
  allowed_time_windows:
    - days: [mon, tue, wed, thu, fri]
      start: "09:00"
      end: "17:00"
      timezone: local
  cooldown_seconds: 1800
  max_runs_per_day: 3
  max_runs_per_week: 10
  max_external_mutations: 1
  stop_conditions:
    - active_window_not_allowed
    - operator_check_in_required
failed_evidence_count: 0
quarantine_status: active
reference:
  type: task
  path: tasks/browser-search.yaml
```

`reference` can point at task YAML:

```yaml
reference:
  type: task
  path: tasks/browser-search.yaml
```

Or at an existing website playbook flow:

```yaml
reference:
  type: playbook
  site: linkedin
  flow: open-search
```

The schema is implemented by `desktop_agent.routines.RoutineDefinition`.
Supported safety classes are `low`, `medium`, `high`, and `sensitive`.
Supported schedule policies are `manual`, `on_demand`, and `scheduled`.
Supported approval policies are `none`, `confirm`, `manifest_required`, and
`manual_handoff`.

`RoutineDefinition.report_metadata()` returns JSON-safe fields for future trace,
monitoring, search, and catalog quality reports.

## Schedule Constraints

The optional `schedule` block describes when a future scheduler may consider a
routine eligible. It is metadata only until the scheduler is enabled, but it is
validated, searchable, exported, shown by `show-routine`, and copied into trace
report metadata when a routine is compiled.

- `allowed_time_windows` entries use `HH:MM` `start` and `end` values, optional
  `days` from `mon` through `sun`, and a `timezone` label. Omit `days` for every
  day.
- `cooldown_seconds` must be non-negative.
- `max_runs_per_day` and `max_runs_per_week` must be positive when present.
- `max_external_mutations` must be non-negative when present.
- `stop_conditions` are reviewed strings such as `active_window_not_allowed`,
  `operator_check_in_required`, or `approval_missing`.

## Quarantine

Routine definitions can carry `failed_evidence_count`, `quarantine_status`, and
`quarantine_reason`. `quarantine_status` supports `active` and `quarantined`.
Routines are computed as quarantined when they are explicitly marked
`quarantined` or when `failed_evidence_count` reaches three failed evidence
records. Quarantined status is included in compiled task metadata and
`show-routine` output so catalog reports can hold unstable routines back from
promotion or unattended use.

## Historical Counters

`routine_failure_counters_from_trace_root()` scans local `final-report.json`
artifacts, groups reports by `metadata.routine_id`, and counts passed, failed,
aborted, and emergency-stopped runs. `generate-routine-docs` can receive
`--failure-history-root <trace-root>` to include historical failure counts in
the routine catalog index without rewriting reviewed routine YAML.

## Catalog Loading

Routine catalogs load files named `*.routine.yaml` or `*.routine.yml` under
`routine_packs/`:

```python
from pathlib import Path

from desktop_agent.routines import load_routine_catalog

catalog = load_routine_catalog(Path("routine_packs"))
results = catalog.search("browser search")
```

The catalog validator rejects duplicate routine IDs and reuses the
`RoutineDefinition` validation rules for every loaded file. Search is a local
token index over routine IDs, names, tags, required app/site, description, goal,
inputs, and outputs.

## CLI

Routine catalog commands use `routine_packs/` by default and accept
`--routine-pack-root` for tests or alternate catalogs.

```bash
desktop-agent list-routines
desktop-agent list-routines --query "browser search"
desktop-agent show-routine browser.search
desktop-agent compile-routine browser.search --output traces/browser-search.yaml
desktop-agent export-routine browser.search --output traces/browser-search.routine.yaml
desktop-agent generate-routine-docs
desktop-agent dry-run-routine browser.search --no-screenshots
desktop-agent run-routine browser.search
```

`compile-routine`, `dry-run-routine`, and `run-routine` attach
`RoutineDefinition.report_metadata()` to the resulting task so traces and
reports preserve the routine ID, safety class, policies, and reference kind.

Before `dry-run-routine` or `run-routine` can enter the execution pipeline,
DeskPilot applies `routine_execution_gate()`. The gate allows only slug-safe
routine IDs that exist in the loaded, validated catalog and are not
quarantined. Unknown IDs, malformed IDs, invalid routine definitions, and
quarantined routines stop before task compilation or desktop input.

`generate-routine-docs` writes `docs/routine-catalog-index.md` and
`docs/routine-documentation-template.md` by default. The generated catalog index
summarizes routine counts, approval gaps, Windows proof requirements,
quarantine status, promotion gates, report metadata, and search seed coverage.
The template is the checklist copied when a routine needs its own review page.

## Promotion Gates

Every routine exposes promotion gates through `routine_promotion_gates()` and in
`RoutineDefinition.report_metadata()`:

- `schema_validation`: the routine definition validates.
- `dry_run`: the compiled routine passes dry-run without desktop input.
- `fixture_test`: the routine has browser, native, or synthetic fixture coverage.
- `trace_replay_review`: a replay summary is reviewed.
- `documentation`: inputs, outputs, risk, and proof expectations are documented.
- `windows_proof`: an owned Windows proof is required when the routine needs a
  native app or has `high`/`sensitive` safety class.
