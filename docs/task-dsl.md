# Task DSL

DeskPilot tasks are authored as YAML. The DSL is intentionally strict so tasks
can be validated before the runtime moves the mouse, types text, or captures
task artifacts.

## Planned Minimal Shape

```yaml
name: browser-login-fixture
allowed_windows:
  - "DeskPilot Browser Fixture"
timeout_seconds: 120
steps:
  - id: enter-email
    action: click_text
    target: "Email"
  - id: type-email
    action: type_text
    text: "qa@example.test"
  - id: submit
    action: click_text
    target: "Submit"
    verify:
      type: visible_text
      text: "Success"
```

## Planned Guarantees

- Every task must declare a name, allowed windows, timeout, and steps.
- Every step must declare an ID and action.
- Unknown actions and verification types fail validation before execution.
- Duplicate step IDs fail validation before execution.
- Image templates must resolve before execution starts.

Complete examples will be added as the task DSL implementation lands.
