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

Unverified local packs produce trust warnings in manifest metadata,
`list-routine-packs`, `show-routine-pack`, `import-routine-pack`, and the
operator app routine-pack service. The warning tells the operator to review the
manifest, routines, docs, tests, and proof expectations before installing or
running the pack.

`safety.max_safety_class` records the highest allowed safety class for routines
in the pack. `external_mutation_allowed` and `approval_required` make the pack's
mutation posture explicit before import or installation work begins.

`proof.expected_artifacts` lists the trace/report files reviewers expect before
promoting routines from the pack. Windows proof may still be opt-in for tests,
but the manifest makes that requirement visible in reports and UI.

## CLI

Routine pack commands use `routine_packs/` by default and accept
`--routine-pack-root` for alternate local catalogs.

```bash
desktop-agent list-routine-packs
desktop-agent show-routine-pack browser
desktop-agent import-routine-pack ./local-pack --routine-pack-root routine_packs
desktop-agent export-routine-pack browser --output traces/browser-pack.zip
```

`import-routine-pack` accepts a local directory or zip archive containing exactly
one `routine-pack.yaml`. It validates the manifest before copying the pack into
the target root and refuses to overwrite an installed pack unless `--replace` is
provided.

`export-routine-pack` validates the installed manifest and writes either a
directory or `.zip` archive depending on the `--output` path.
