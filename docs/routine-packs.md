# Routine Packs

Routine packs are trusted local directories that group reviewed routine YAML,
tasks, docs, fixtures, tests, safety metadata, and proof expectations. They are
the installation unit for the future local routine ecosystem.

## Manifest

Each pack should include `routine-pack.yaml`:

```yaml
pack_schema_version: "1"
id: browser
name: Browser Routine Pack
description: Reviewed browser navigation and reading routines.
version: "0.1.0"
publisher: DeskPilot
trust_level: builtin
routine_globs:
  - "*.routine.yaml"
docs:
  - README.md
fixtures: []
tests:
  - tests/test_routine_packs.py::test_browser_routine_pack_contains_seed_categories
safety:
  max_safety_class: medium
  requires_review: true
  external_mutation_allowed: false
  approval_required: true
proof:
  windows_proof_required: true
  expected_artifacts:
    - final-report.json
    - action-log.jsonl
    - trace-schema.json
    - replay-summary.md
```

The schema is implemented by
`desktop_agent.routine_pack_manifest.RoutinePackManifest`. Manifest paths must
stay relative to the pack and must not contain `..` parent traversal.

Supported `trust_level` values are:

- `builtin`: shipped with DeskPilot and covered by repo tests.
- `trusted_local`: installed from a local source the operator has reviewed.
- `unverified_local`: present locally but not trusted for automatic promotion.

`safety.max_safety_class` records the highest allowed safety class for routines
in the pack. `external_mutation_allowed` and `approval_required` make the pack's
mutation posture explicit before import or installation work begins.

`proof.expected_artifacts` lists the trace/report files reviewers expect before
promoting routines from the pack. Windows proof may still be opt-in for tests,
but the manifest makes that requirement visible in reports and UI.
