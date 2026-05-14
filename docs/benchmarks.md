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
  aggregate summary metrics, and per-run metrics.
- `variance-report.json` with run-to-run distribution values.
- Per-iteration trace directories under `<output>/traces/`.

Per-run metrics currently include status, elapsed task time, step count, action
count, retry count, ambiguity count, recovery count, operator intervention
count, trace directory, and abort reason.

Summary metrics currently include success rate, median task time, total step
count, total action count, total retry count, ambiguity rate, recovery rate, and
operator intervention rate.

Variance reports include minimum, maximum, mean, and population standard
deviation for task time, step count, action count, retry count, ambiguity count,
recovery count, and operator intervention count.
