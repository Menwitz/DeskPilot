# Example Workflows

DeskPilot ships three deterministic local fixtures:

- `examples/browser_fixture.html` with `examples/browser-task.yaml`
- `examples/adversarial_fixture.html` with `examples/adversarial-task.yaml`
- `examples/native_fixture.py` with `examples/native-task.yaml`
- `examples/mixed-task.yaml` for a browser-to-native handoff

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
