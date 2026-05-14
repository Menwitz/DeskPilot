# Benchmarks

DeskPilot benchmark suites define the task fixtures used to evaluate
human-like execution changes. They are local-only and cover browser, native
Windows, and mixed browser-to-native workflows.

The source of truth is `desktop_agent.benchmarks`. Each benchmark task declares:

- Task YAML path.
- Fixture files that must exist before the task runs.
- Allowed window titles.
- Pipeline modes to evaluate: `dry_run` and `run`.
- Deep-search sources to monitor: UIA, OCR, image, and dry-run candidates.
- Trace phases that must appear in monitoring output.
- Final report fields that must be available to later analysis.
- Metrics expected from the future repeated-run harness.
- Acceptance thresholds that decide whether a repeated run is good enough to
  count as an implementation improvement.

## Built-In Suites

- `browser-fixture-suite` uses `examples/browser-task.yaml` and
  `examples/browser_fixture.html`, plus `examples/adversarial-task.yaml` and
  `examples/adversarial_fixture.html` for delayed, disabled, duplicated, and
  moving controls.
- `native-windows-fixture-suite` uses `examples/native-task.yaml` and
  `examples/native_fixture.py`.
- `mixed-fixture-suite` uses `examples/mixed-task.yaml` plus both fixture files.

These definitions do not execute the benchmarks yet. They provide stable inputs
for the repeated-run harness, monitoring, and report aggregation phases.
The monitoring contract includes the `compile_task` phase so dependency and
expected-state compiler checks are present before perception, deep-search, and
actuation phases are evaluated.
It also includes the `execution_path` phase so benchmark traces can separate
standard actions from fast-path high-confidence segments and careful-path risky
segments.
Built-in submission fixture tasks declare pre-action checkpoints, so benchmark
reports also cover `verification_checkpoint` evidence before final actions.

## Repeated Dry-Run Harness

Use `desktop-agent benchmark-run` to execute one task repeatedly through the
safe dry-run pipeline:

```bash
desktop-agent benchmark-run examples/browser-task.yaml \
  --iterations 5 \
  --output traces/benchmarks/browser-fixture
```

The harness writes:

- `runs.jsonl` with one per-run metrics record per line.
- `benchmark-report.json` with the task path, output paths, iteration count,
  aggregate summary metrics, acceptance status, and per-run metrics.
- `variance-report.json` with run-to-run distribution values.
- `pointer-timing-comparison.json` with deterministic baseline-vs-Fitts pointer
  timing comparisons for representative movement scenarios.
- Per-iteration trace directories under `<output>/traces/`.

Per-run metrics currently include status, elapsed task time, step count, action
count, retry count, grounding attempt count, grounded selection count, grounding
accuracy, ambiguity count, recovery count, operator intervention count, trace
directory, and abort reason.

Summary metrics currently include success rate, median task time, total step
count, total action count, total retry count, grounding accuracy, ambiguity
rate, recovery rate, and operator intervention rate.

Variance reports include minimum, maximum, mean, and population standard
deviation for task time, step count, action count, retry count, grounding
accuracy, ambiguity count, recovery count, and operator intervention count.

Pointer timing comparison reports compare the current `FittsLawPointerTimingModel`
against a fixed deterministic baseline. The harness records baseline duration,
model duration, delta, pointer distance, effective target width, and model index
of difficulty for near-large, far-small, and diagonal-medium target scenarios.

## Acceptance Thresholds

Each built-in benchmark task has explicit thresholds in
`desktop_agent.benchmarks`. The repeated-run harness evaluates those thresholds
after summary and variance metrics are computed, then stores the result in
`benchmark-report.json` under `acceptance`.

Current acceptance gates cover:

- Minimum success rate.
- Maximum median task time.
- Maximum task time for any single run.
- Maximum per-run step, action, and retry counts.
- Maximum ambiguity, recovery, and operator-intervention rates.

The CLI prints `acceptance: passed`, `acceptance: failed`, or
`acceptance: not_configured`. Built-in benchmark task files must pass acceptance
before a behavior change should be treated as an improvement. Ad hoc task files
can still use the harness, but their report is marked `not_configured` until a
task spec adds thresholds.
