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
steps:
  - id: submit
    action: click_text
    target: Submit
```

## Validation

Startup rejects unsafe values before any desktop action can run:

- Timeouts and maximum step counts must be greater than zero.
- Retry limits must not be negative.
- Confidence threshold must be greater than `0` and at most `1`.
- Emergency stop hotkey and trace root must be present.
- Window names must not be blank.
