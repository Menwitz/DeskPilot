# Example Workflows

DeskPilot ships deterministic local fixtures and task examples:

- `examples/browser_fixture.html` with `examples/browser-task.yaml`
- `examples/adversarial_fixture.html` with `examples/adversarial-task.yaml`
- `examples/native_fixture.py` with `examples/native-task.yaml`
- `examples/mixed-task.yaml` for a browser-to-native handoff
- `examples/execution-profile-fast-task.yaml`,
  `examples/execution-profile-normal-task.yaml`, and
  `examples/execution-profile-careful-task.yaml` for profile-specific browser
  fixture runs

The browser fixture is a static HTML form with a submit button below the fold so
`scroll_until` is exercised. The native fixture is a small Tkinter app with a
text input, submit button, and menu-state button. The mixed task finishes the
browser fixture, uses `alt+tab` to switch windows, then completes the native
fixture.

The adversarial fixture is a browser page with duplicated controls, a delayed
disabled control, and a moving target. It is intended for benchmark and recovery
work rather than simple smoke tests.

Run `desktop-agent dry-run <task.yaml>` first to validate the task and produce a
local trace without sending desktop input. Real `run` execution requires an
unlocked Windows desktop with the relevant fixture window already visible.

## Execution Profile Examples

The profile examples are complete browser fixture tasks with task-state
dependencies, recovery rules, submission checkpoints, confirmed sensitive
steps, and execution-profile config blocks:

- `execution-profile-fast-task.yaml` uses short bounded waits, low hesitation,
  and lighter movement smoothing for high-confidence local workflows.
- `execution-profile-normal-task.yaml` uses centered timing, moderate keyboard
  and scroll cadence, and `strict_qa` with an explicitly confirmed submission.
- `execution-profile-careful-task.yaml` uses wider timing bounds, higher
  hesitation probability, stronger smoothing, and the same confirmed
  submission gate.

Each profile task runs through the same dry-run/run pipeline as the other
examples. Benchmark registration covers UIA, OCR, image, and dry-run
deep-search sources, required monitoring phases, final report fields, and
acceptance metrics.

```bash
desktop-agent dry-run examples/execution-profile-fast-task.yaml
desktop-agent dry-run examples/execution-profile-normal-task.yaml
desktop-agent dry-run examples/execution-profile-careful-task.yaml
```
