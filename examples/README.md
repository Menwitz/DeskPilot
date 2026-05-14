# Examples

This directory contains deterministic, safe desktop automation examples.

## Browser Fixture

Open `browser_fixture.html` in a browser window. The page title is
`DeskPilot Browser Fixture`, which matches `browser-task.yaml`.

```bash
desktop-agent dry-run examples/browser-task.yaml
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
