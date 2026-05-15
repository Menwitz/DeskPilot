# Examples

This directory contains deterministic, safe desktop automation examples.

## Browser Fixture

Open `browser_fixture.html` in a browser window. The page title is
`DeskPilot Browser Fixture`, which matches `browser-task.yaml`.

```bash
desktop-agent dry-run examples/browser-task.yaml
```

## Execution Profile Browser Fixtures

The profile tasks use the same browser fixture and demonstrate complete
execution-profile configs for `fast`, `normal`, and `careful` personas. They
include task-state dependencies, recovery rules, checkpoints before submission,
and confirmed sensitive steps so dry-run traces include monitoring and report
evidence for the full pipeline.

```bash
desktop-agent dry-run examples/execution-profile-fast-task.yaml
desktop-agent dry-run examples/execution-profile-normal-task.yaml
desktop-agent dry-run examples/execution-profile-careful-task.yaml
```

## Capability Showcase

`capability-showcase-task.yaml` is the broadest dry-run example. It combines
task-level configuration, careful execution-profile timing, dependencies,
expected state transitions, recovery rules, confirmation gates, branching,
scrolling, dragging, image matching, text/UIA clicks, typing, key chords, and
assertions in one maintained scenario.

```bash
desktop-agent dry-run examples/capability-showcase-task.yaml
```

## Site Publish Dry-Runs

The LinkedIn and Medium examples pair local content variables with matching
approval manifests. They are safe dry-run fixtures for validating publish-flow
compilation, approval metadata, checkpoints, and local trace output.

```bash
desktop-agent dry-run-site linkedin publish-post \
  --variables examples/linkedin-content-variables.yaml \
  --approval-manifest examples/linkedin-approval-manifest.yaml

desktop-agent dry-run-site medium publish-story \
  --variables examples/medium-content-variables.yaml \
  --approval-manifest examples/medium-approval-manifest.yaml
```

## Native Fixture

Run the Tkinter fixture on Windows with Python:

```bash
python examples/native_fixture.py
desktop-agent dry-run examples/native-task.yaml
```

## Mixed Fixture

Open the browser fixture and the native fixture, place the browser window in
front, then dry-run or run `mixed-task.yaml`.

```bash
desktop-agent dry-run examples/mixed-task.yaml
```

The examples do not call external services. Generated traces, screenshots, OCR
text, overlays, and reports stay under the configured local trace directory.

## Adversarial Fixture

Open `adversarial_fixture.html` in a browser window. The page title is
`DeskPilot Adversarial Fixture`, which matches `adversarial-task.yaml`.

This fixture intentionally includes duplicated controls, a disabled control that
becomes enabled after a delay, and a moving target.

```bash
desktop-agent dry-run examples/adversarial-task.yaml
```
