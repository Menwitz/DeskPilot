# Configuration

DeskPilot resolves runtime configuration with this precedence:

1. CLI overrides.
2. Task YAML `config` block.
3. Project-level config file.
4. Built-in defaults.

The CLI resolves the final `RuntimeConfig` before the planner starts, so safety
limits and report settings are stable for the full run.

## Fields

```yaml
default_timeout_seconds: 30
confidence_threshold: 0.8
max_steps: 100
max_retries_per_step: 1
max_runtime_seconds: 600
trace_root: traces
save_screenshots: true
save_ocr_text: true
allowed_windows:
  - DeskPilot Fixture
emergency_stop_hotkey: ctrl+alt+esc
primary_monitor_only: true
confirmed_steps: []
execution_profile:
  enabled: false
  action_delay_seconds: [0.0, 0.0]
  retry_delay_seconds: [0.0, 0.0]
  hesitation_probability: 0.0
  movement_smoothness: 0.0
  random_seed: null
```

## Task Overrides

Tasks can override runtime settings in a `config` block:

```yaml
name: fixture
allowed_windows:
  - DeskPilot Fixture
timeout_seconds: 30
config:
  confidence_threshold: 0.9
  max_retries_per_step: 2
  confirmed_steps:
    - submit-payment
  execution_profile:
    enabled: true
    action_delay_seconds: [0.05, 0.25]
    retry_delay_seconds: [0.25, 1.0]
    hesitation_probability: 0.1
    movement_smoothness: 0.6
steps:
  - id: submit
    action: click_text
    target: Submit
```

## Execution Profile

`execution_profile` is an optional, safety-bounded timing profile for local
automation. It does not change task intent, action order, target text, typed
text, allowed windows, maximum steps, timeouts, or retry budgets.

- `enabled` turns profile timing decisions on.
- `action_delay_seconds` sets the inclusive lower and upper bounds for a
  pre-action timing decision.
- `retry_delay_seconds` sets the inclusive lower and upper bounds for retry
  pacing.
- `hesitation_probability` chooses the upper half of the configured action
  delay range with that probability.
- Enabled action timing is target-aware inside the same bounds: selected target
  distance, selected target size, and action type bias where the sampled delay
  lands between the configured lower and upper limits.
- Enabled action and retry timing also records Keystroke-Level-Model style
  operator metadata for mental pauses, system waits, keying, pointing, and
  homing between keyboard and pointer modes. These operators can bias where a
  sampled delay lands inside the configured bounds, but they never expand those
  bounds or change the selected action.
- `movement_smoothness` is reserved for future real pointer actuation adapters.
- `random_seed` makes timing decisions reproducible for tests and diagnostics.

## Sensitive Step Confirmation

Tasks can mark a step with `requires_confirmation: true`. Those steps are
blocked unless their step ID appears in `confirmed_steps` or is passed with the
CLI `--confirm-step` option. This keeps sensitive actions opt-in at run time
instead of relying only on task authoring.

## Validation

Startup rejects unsafe values before any desktop action can run:

- Timeouts and maximum step counts must be greater than zero.
- Retry limits must not be negative.
- Confidence threshold must be greater than `0` and at most `1`.
- Execution profile timing bounds must be non-negative and ordered from lower
  to upper.
- Execution profile probability and smoothness values must be between `0` and
  `1`.
- Confirmed step IDs must not be blank.
- Emergency stop hotkey and trace root must be present.
- Window names must not be blank.
