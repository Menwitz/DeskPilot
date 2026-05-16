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
entropy_budget: 2.0
steps:
  - id: enter-email
    action: click_text
    target: "Email"
  - id: type-email
    action: type_text
    depends_on:
      - enter-email
    expected_state:
      before: email-focused
      after: email-entered
    text: "qa@example.test"
  - id: submit
    action: click_text
    target: "Submit"
    category: submission
    entropy_budget: 0.5
    safe_action_variants:
      - click_uia
    recovery:
      - reason: transient_loading
        actions:
          - wait_for_loading
          - abort_with_trace
    checkpoint:
      type: visible_text
      text: "Submit"
    requires_confirmation: true
    verify:
      type: visible_text
      text: "Success"
```

## Guarantees

- Every task must declare a name, allowed windows, timeout, and steps.
- Allowed-window entries are matched against the active window title by exact
  match, case-insensitive substring match, or `regex:` regular expression.
- Every step must declare an ID and action.
- Unknown actions and verification types fail validation before execution.
- Duplicate step IDs fail validation before execution.
- Image templates must resolve before execution starts.
- Explicit `depends_on` references must point to earlier steps, which prevents
  impossible dependency graphs before any screen observation or desktop input.
- Adjacent `expected_state` declarations must form a coherent UI state
  transition chain when authored.
- Step `category` values must be one of `navigation`, `recognition`,
  `data_entry`, `verification`, or `submission` when provided.
- Task and step `entropy_budget` values must be non-negative. When a task-level
  budget is set, the total of explicit step budgets must not exceed it.
- At runtime, entropy budgets are also rejected when they exceed the random
  decision capacity allowed by max-step, retry, and timeout constraints.

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
- `manual_handoff`

The task compiler preserves these semantic action names and also emits a
`desktop_io_v1` plan for monitoring and reports. Current mappings are:

- `click_text`, `click_image`, and `click_uia`: `observe`, `move`, `click`,
  `verify`
- `type_text`: `observe`, `type`, `verify`
- `press_key`: `observe`, `hotkey`, `verify`
- `scroll`: `observe`, `wheel`, `verify`
- `scroll_until`: `observe`, `wheel`, `observe`, `verify`
- `wait_for`: `observe`, `wait`, `verify`
- `assert_visible` and `branch_if_visible`: `observe`, `verify`
- `drag`: `observe`, `move`, `drag`, `verify`
- `manual_handoff`: `handoff`, `verify`

`manual_handoff` pauses the run for operator work and then resumes with a
read-only verification. It requires `handoff_prompt` or `text`,
`expected_operator_work`, and `verify`. The compiled handoff action records
the prompt, expected operator work, and resume verification in trace metadata.

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
- `checkpoint` declares a read-only verification that must pass before action
  timing and actuation. Use it for irreversible or sensitive actions such as
  submissions.
- `timeout_seconds` overrides the step timeout. Enabled execution profiles
  budget planned action and retry waits against this value before desktop input.
- `retry` overrides the per-step retry budget.
- `entropy_budget` reserves part of the task's bounded randomness budget for
  this step. Later entropy-controlled runtime work consumes this checked value.
- `safe_action_variants` lists task-author-approved equivalent actions that may
  be selected by the execution profile. Today this is limited to the conservative
  `click_text` / `click_uia` equivalence class.
- `depends_on` lists prior step IDs that must be part of the compiled execution
  plan before this step can run.
- `expected_state` declares an optional `{before, after}` UI state boundary for
  a step. The compiler checks that adjacent authored states do not contradict
  each other.
- `recovery` declares explicit allowed recovery actions for a recovery reason.
  Supported reasons include `stale_observation`, `missed_target`,
  `disabled_control`, `occluded_control`, `focus_loss`, `layout_change`,
  `transient_loading`, and `verification_failure`. Supported recovery actions
  include refocus, reobserve, retry alternate candidates, retry alternate
  selector families, retry fresh candidates, scroll search, wait and reobserve,
  wait for enabled, wait for loading, reopen surface, manual handoff, and abort
  with trace.
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

## Website Playbooks Compile Into Tasks

Website playbooks are an authoring layer above this DSL. `desktop-agent
compile-site <site> <flow> --output <task.yaml>` resolves a site flow into the
same strict task YAML shape documented here. The compiled task keeps
`allowed_windows`, step actions, retry defaults, confidence-threshold overrides,
confirmation gates, blocked-state checks, and site metadata visible to the
planner and trace reports.
Do not add runtime behavior that exists only in playbook YAML. If a website
flow needs a new behavior, add it to the task DSL or compiler contract, then
cover the compiled task, trace metadata, and final reports with regressions.

Site playbook steps may use content variables in `target`, `text`, or `image`
fields with `{{variable_name}}` placeholders. Pass a local YAML variable file
with `--variables <content.yaml>` when compiling or running the site flow.
Variables are resolved before execution; traces record variable names and a
content fingerprint instead of raw payload values.

## Complete Example

```yaml
name: browser-fixture-submit
allowed_windows:
  - DeskPilot Browser Fixture
timeout_seconds: 120
entropy_budget: 4.0
config:
  confidence_threshold: 0.85
  max_retries_per_step: 2
  policy_preset: strict_qa
  confirmed_steps:
    - click-submit
  execution_profile:
    persona: careful
    enabled: true
    action_delay_seconds: [0.05, 0.25]
    retry_delay_seconds: [0.25, 1.0]
    hesitation_probability: 0.1
    movement_smoothness: 0.6
    keyboard_interval_seconds: [0.01, 0.03]
    scroll_interval_seconds: [0.02, 0.05]
steps:
  - id: click-email
    action: click_text
    target: Email
    category: navigation
    entropy_budget: 0.5
    timeout_seconds: 10

  - id: type-email
    action: type_text
    text: qa@example.test
    category: data_entry
    entropy_budget: 0.5

  - id: find-submit
    action: scroll_until
    target: Submit
    category: recognition
    entropy_budget: 1.0
    retry: 3

  - id: click-submit
    action: click_text
    target: Submit
    category: submission
    entropy_budget: 1.0
    safe_action_variants:
      - click_uia
    recovery:
      - reason: transient_loading
        actions:
          - wait_for_loading
          - abort_with_trace
    checkpoint:
      type: visible_text
      text: Submit
    requires_confirmation: true
    verify:
      type: visible_text
      text: Success
```

## CLI Support

The current CLI accepts this YAML shape for `dry-run` planning. Dry-run output
starts with a preview of each step's timing bounds, worst-case planned wait
against timeout, and recovery paths before running the safe planner pipeline.
Later DSL work will add strict action and verification schemas,
image-template validation, branching, and richer failure messages.
