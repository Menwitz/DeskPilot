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
Future cryptographic signing work is tracked in
`docs/signed-routine-pack-investigation.md`; signatures are not a current trust
source and do not bypass local safety gates.

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
desktop-agent test-routine-pack browser --output traces/browser-pack-test.json
desktop-agent write-routine-pack-proof browser --output traces/browser-pack-proof
```

`import-routine-pack` accepts a local directory or zip archive containing exactly
one `routine-pack.yaml`. It validates the manifest before copying the pack into
the target root and refuses to overwrite an installed pack unless `--replace` is
provided.
For a trusted local pack, the normal acceptance flow is `import-routine-pack`
followed by `test-routine-pack --output <report.json>`; the validation report
must pass with every routine and referenced task YAML counted as validated.
Before copying, import also scans the incoming pack against installed packs for
duplicate pack/version records, duplicate routine IDs, duplicate routine input
signatures, and duplicate task selector signatures. Duplicate pack/version and
routine IDs block install unless `--replace` is provided; input and selector
duplicates are surfaced as warnings for operator review.

`export-routine-pack` validates the installed manifest and writes either a
directory or `.zip` archive depending on the `--output` path.

`test-routine-pack` validates the manifest, routine YAML, and referenced task
YAML without real desktop input. `write-routine-pack-proof` writes
`pack-test-report.json`, `proof-checklist.md`, and a manifest copy so the pack's
proof status can be reviewed or attached to release evidence.
