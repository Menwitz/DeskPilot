# Task DSL

DeskPilot tasks are authored as YAML. The DSL is intentionally strict so tasks
can be validated before the runtime moves the mouse, types text, or captures
task artifacts.

## Minimal Shape

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
    category: submission
    requires_confirmation: true
    verify:
      type: visible_text
      text: "Success"
```

## Guarantees

- Every task must declare a name, allowed windows, timeout, and steps.
- Every step must declare an ID and action.
- Unknown actions and verification types fail validation before execution.
- Duplicate step IDs fail validation before execution.
- Image templates must resolve before execution starts.
- Step `category` values must be one of `navigation`, `recognition`,
  `data_entry`, `verification`, or `submission` when provided.

## Actions

Supported actions:

- `click_text`
- `click_image`
- `click_uia`
- `type_text`
- `press_key`
- `scroll`
- `scroll_until`
- `wait_for`
- `assert_visible`
- `branch_if_visible`
- `drag`

## Verification Types

Supported verification types:

- `visible_text`
- `not_visible_text`
- `visible_image`
- `focused`
- `window_title_contains`
- `uia_element_exists`

## Optional Step Fields

- `target` identifies text, UIA labels, or future selectors.
- `text` provides typed text, key names, or text verification content.
- `image` references a task-relative image template or `examples/assets/`.
- `region` restricts perception to `{x, y, width, height}`.
- `verify` declares a post-action verification.
- `timeout_seconds` overrides the step timeout.
- `retry` overrides the per-step retry budget.
- `on_failure` names a future recovery or branch target.
- `requires_confirmation` blocks the step unless its ID is explicitly confirmed
  in runtime configuration or with `--confirm-step`.
- `category` labels the step for timing, reporting, and cognitive timing
  operators. If omitted, DeskPilot records a stable action-based default
  category.

## Task-Level Configuration

Task YAML can include a `config` block for task-level runtime overrides. The
final precedence is CLI overrides, then task `config`, then project config, then
defaults.

## Complete Example

```yaml
name: browser-fixture-submit
allowed_windows:
  - DeskPilot Browser Fixture
timeout_seconds: 120
config:
  confidence_threshold: 0.85
  max_retries_per_step: 2
  execution_profile:
    enabled: true
    action_delay_seconds: [0.05, 0.25]
    retry_delay_seconds: [0.25, 1.0]
    hesitation_probability: 0.1
    movement_smoothness: 0.6
steps:
  - id: click-email
    action: click_text
    target: Email
    category: navigation
    timeout_seconds: 10

  - id: type-email
    action: type_text
    text: qa@example.test
    category: data_entry

  - id: find-submit
    action: scroll_until
    target: Submit
    category: recognition
    retry: 3

  - id: click-submit
    action: click_text
    target: Submit
    category: submission
    requires_confirmation: true
    verify:
      type: visible_text
      text: Success
```

## CLI Support

The current CLI accepts this basic YAML shape for `dry-run` planning. Later DSL
work will add strict action and verification schemas, image-template validation,
branching, and richer failure messages.
