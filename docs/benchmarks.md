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
- `execution-profile-examples-suite` uses
  `examples/execution-profile-fast-task.yaml`,
  `examples/execution-profile-normal-task.yaml`, and
  `examples/execution-profile-careful-task.yaml` with
  `examples/browser_fixture.html` to verify each execution profile through the
  same dry-run/run, deep-search, monitoring, and report contract.
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
The `task_state` phase is part of the same monitoring contract, covering local
dependency completion and believed UI-state transitions during each run.
`input_wait` evidence records requested and elapsed waits before desktop input
when execution profiles are enabled.

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
  aggregate summary metrics, acceptance status, per-run metrics, and the
  benchmark observability contract when the task is a built-in benchmark.
- `benchmark-summary.md` with a human-readable acceptance, baseline comparison,
  summary metric, and observability-contract summary.
- `trace-health.json` with local trace-health counts for the generated
  per-iteration trace directories.
- `baseline-runs.jsonl` with one deterministic baseline metrics record per
  iteration. The baseline preserves safety settings and disables execution
  profile timing.
- `variance-report.json` with run-to-run distribution values.
- `baseline-comparison.json` comparing candidate runs against the deterministic
  baseline for success rate, median task time, grounding accuracy, ambiguity
  rate, recovery rate, and operator intervention rate.
- `pointer-timing-comparison.json` with deterministic baseline-vs-Fitts pointer
  timing comparisons for representative movement scenarios.
- Per-iteration trace directories under `<output>/traces/`.

Per-run metrics currently include status, elapsed task time, step count, action
count, retry count, grounding attempt count, grounded selection count, grounding
accuracy, ambiguity count, recovery count, operator intervention count, trace
directory, and abort reason.

For built-in benchmark tasks, `benchmark-report.json` also includes
`observability_contract` with the benchmark task ID, pipeline modes,
deep-search sources, required trace phases, required final-report fields, and
required metrics. Ad hoc benchmark runs keep the same field with
`configured: false`.
The report also stores `monitoring_coverage`, which compares required trace
phases with the phases observed across the generated run traces.
`benchmark-summary.md` repeats the same contract in Markdown for review without
opening the JSON payload. It also links `trace-health.json` and shows the
trace-health status plus attention-trace count.

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
before a behavior change is eligible for improvement review. Acceptance passing
is not proof of improvement by itself; it only means the run stayed inside the
configured reliability and safety thresholds. Ad hoc task files can still use
the harness, but their report is marked `not_configured` until a task spec adds
thresholds.

## Baseline Comparison

Every benchmark run also executes the same task with execution-profile timing
disabled and writes `baseline-comparison.json`. A change is marked
`improved` only when the candidate run improves success rate or median task time
and does not reduce grounding accuracy or increase ambiguity, recovery, or
operator intervention rates. If safety is preserved but reliability and speed
are unchanged, the comparison is `neutral`. If safety or reliability regresses,
the comparison is `regressed`.

Treat `baseline-comparison.json`, repeated local traces, and any manual Windows
evidence as the improvement evidence. Do not cite a single acceptance pass as a
measured performance or reliability gain.
