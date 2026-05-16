# Routine Packs

Routine packs are the source directories for reviewed personal routines. Each
pack will hold `*.routine.yaml` definitions, generated task YAML, dry-run
evidence, proof notes, and pack-level documentation as Phase 5 expands the
catalog. Routine definition schema fields, catalog loading, validation, and
search behavior are documented in `docs/routines.md`.
Each pack has a `routine-pack.yaml` manifest with trust level, routine globs,
docs, fixtures, tests, safety metadata, and proof expectations. The manifest
schema is documented in `docs/routine-packs.md`.

## Packs

- `browser`: browser navigation, search, reading, forms, downloads, and settings.
- `native`: Windows desktop apps, File Explorer, clipboard, and window control.
- `social-content`: social and content surfaces for read, draft, and approved publish flows.
- `email-writing`: inbox review, drafting, summarization, and response prep.
- `files`: file organization, renaming, movement, cleanup, and local reporting.
- `research`: browsing, note capture, source review, and synthesis prep.
- `publishing`: approved publishing handoffs, final checks, and traceable submissions.

Every routine promoted into these packs should eventually carry metadata,
inputs, outputs, safety class, approval policy, dry-run coverage, trace
expectations, and Windows proof status when applicable.
