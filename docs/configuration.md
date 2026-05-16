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
policy_preset: personal_automation
require_operator_approval: false
confirmed_steps: []
execution_profile:
  activity_profile: null
  persona: normal
  enabled: false
  action_delay_seconds: [0.0, 0.0]
  retry_delay_seconds: [0.0, 0.0]
  action_delay_distribution: uniform
  retry_delay_distribution: uniform
  action_variant_distribution: uniform
  hesitation_probability: 0.0
  movement_smoothness: 0.0
  keyboard_interval_seconds: [0.0, 0.0]
  scroll_interval_seconds: [0.0, 0.0]
  random_seed: null
local_model:
  enabled: false
  provider: ollama
  model: llama3.1
  endpoint: http://127.0.0.1:11434
  request_timeout_seconds: 10.0
  use_for_goal_ranking: false
redaction_policy:
  evidence_mode: full
  screenshots: full
  ocr_text: full
  typed_text: full
  content_variables: fingerprint_only
  video: full
  reports: full
  sensitive_zones: []
```

## Allowed Windows

`allowed_windows` entries are active-window title rules used by the planner and
the final desktop input guard. Plain entries match either the exact title or a
case-insensitive title substring, so `LinkedIn` matches
`LinkedIn - Google Chrome`. Entries prefixed with `regex:` are evaluated as
case-insensitive regular expressions, for example `regex:^Medium\b`.

At runtime, DeskPilot merges task-level `allowed_windows` with runtime
configuration or `--allowed-window` values. The merged allowlist is written into
the resolved runtime config and is what the real actuator checks immediately
before sending input.

## Local Artifacts

`trace_root` controls where run evidence is written. Each run creates a unique
local subdirectory containing normalized config, task JSON, action logs, final
reports, and optional screenshots/OCR/CV artifacts. Content variable files and
approval manifests remain at their original local paths; reports store only
their paths, approved step IDs, variable names, and fingerprints.

`redaction_policy` is part of the resolved runtime config and is written to
`config.json` for every run. The default keeps full local evidence available:
`evidence_mode: full`, screenshots/OCR/typed text/video/reports set to `full`,
and content variables represented by fingerprints. A project config supplies
the global policy, routine definitions can carry a routine-level policy, and
task `config.redaction_policy` can provide a run-level override.
Set `screenshots: blur_sensitive_zones` with `sensitive_zones` entries to define
coordinate blur masks for screenshot evidence. Each zone uses `id`, `x`, `y`,
`width`, `height`, and an optional `reason`; actual redaction must still be
requested by policy.

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
  policy_preset: strict_qa
  confirmed_steps:
    - submit-payment
  execution_profile:
    activity_profile: careful
    persona: careful
    enabled: true
    action_delay_seconds: [0.05, 0.25]
    retry_delay_seconds: [0.25, 1.0]
    action_delay_distribution: center_weighted
    retry_delay_distribution: uniform
    action_variant_distribution: uniform
    hesitation_probability: 0.1
    movement_smoothness: 0.6
    keyboard_interval_seconds: [0.01, 0.03]
    scroll_interval_seconds: [0.02, 0.05]
steps:
  - id: submit
    action: click_text
    target: Submit
```

## Execution Profile

`execution_profile` is an optional, safety-bounded timing profile for local
automation. It does not change task intent, action order, target text, typed
text, allowed windows, maximum steps, timeouts, or retry budgets.
It is for transparent owned-desktop reliability work, not stealth automation,
CAPTCHA bypass, bot-detection evasion, credential abuse, or abusive third-party
automation.

- `enabled` turns profile timing decisions on.
- `activity_profile` can be `focused`, `careful`, `background_assist`, or
  `batch_work`. It applies a named bounded preset for action timing, retry
  timing, keyboard cadence, scroll cadence, movement smoothness, distributions,
  and persona. Any explicitly supplied field in the same `execution_profile`
  block overrides the preset while keeping the activity profile name in traces.
- `persona` can be `fast`, `normal`, or `careful`. It biases sampled timing
  toward the lower, middle, or upper part of configured timing bounds without
  changing actions, targets, retries, or maximum allowed delays.
- `action_delay_seconds` sets the inclusive lower and upper bounds for a
  pre-action timing decision.
- `retry_delay_seconds` sets the inclusive lower and upper bounds for retry
  pacing.
- Retry pacing applies bounded backoff inside `retry_delay_seconds`. Recovery
  reasons that are usually transient use exponential backoff; other retries use
  linear backoff. Both strategies stay inside the configured retry range and
  retry budget.
- `action_delay_distribution`, `retry_delay_distribution`, and
  `action_variant_distribution` can be `uniform` or `center_weighted`.
  Distribution choices only affect where a sampled timing value or approved
  safe action variant lands inside an already validated option set.
- Per-step timeout budgeting uses the upper action and retry delay bounds, the
  step retry budget, and the step timeout. DeskPilot fails a step before
  desktop action when the configured timeout cannot fit the planned waits.
- `hesitation_probability` chooses the upper half of the configured action
  delay range with that probability.
- Enabled action timing is target-aware inside the same bounds: selected target
  distance, selected target size, and action type bias where the sampled delay
  lands between the configured lower and upper limits.
- Enabled action and retry timing is consumed by the planner clock before
  desktop actuation and before retry loops continue. Disabled profiles still
  produce zero-second timing decisions.
- Enabled action and retry timing also records Keystroke-Level-Model style
  operator metadata for mental pauses, system waits, keying, pointing, and
  homing between keyboard and pointer modes. These operators can bias where a
  sampled delay lands inside the configured bounds, but they never expand those
  bounds or change the selected action.
- `movement_smoothness` controls the real pointer path smoothness used by the
  desktop actuation adapter.
- `keyboard_interval_seconds` sets bounded sleeps between typed characters.
  Text content and character order are not changed, and the intervals are
  recorded on `execute_action` metadata and final reports.
- `scroll_interval_seconds` sets bounded sleeps between same-direction wheel
  units for multi-click scroll actions. The total scroll distance is preserved,
  and the emitted steps are recorded on `execute_action` metadata and final
  reports.
- `random_seed` makes timing decisions reproducible through the shared seeded
  sampler used by bounded runtime randomness.

Built-in activity profiles:

| Activity profile | Intended use | Persona | Action bounds | Retry bounds |
| --- | --- | --- | --- | --- |
| `focused` | Active assisted work where the operator is watching. | `normal` | `[0.08, 0.25]` | `[0.25, 0.9]` |
| `careful` | Slower local workflows that need extra visual confirmation time. | `careful` | `[0.18, 0.65]` | `[0.8, 2.4]` |
| `background_assist` | Low-priority scheduled work with wider spacing and conservative retries. | `careful` | `[0.45, 1.4]` | `[2.0, 6.0]` |
| `batch_work` | Repeated low-risk catalog routines with tight bounded pacing. | `fast` | `[0.04, 0.16]` | `[0.2, 0.8]` |

The CLI can apply a profile for one run:

```bash
desktop-agent dry-run-routine browser.read-page --activity-profile focused
```

## Operator Guidance

Choose delay bounds and entropy budgets from measured local behavior, not from a
goal of appearing indistinguishable from a person. Start with `dry-run`, inspect
the preview and reports, then use `benchmark-run` when a task is important
enough to compare repeated executions.

### Choosing Delay Bounds

Use the smallest bounds that make the workflow reliable and readable in traces:

| Workflow risk | Suggested profile | Starting bounds |
| --- | --- | --- |
| Stable owned fixture, high confidence | `fast` | `action_delay_seconds: [0.01, 0.05]`, `retry_delay_seconds: [0.08, 0.25]` |
| Routine personal automation | `normal` | `action_delay_seconds: [0.05, 0.18]`, `retry_delay_seconds: [0.2, 0.6]` |
| Sensitive QA or flaky UI | `careful` | `action_delay_seconds: [0.15, 0.45]`, `retry_delay_seconds: [0.5, 1.2]` |

Checklist:

- Keep the upper action and retry bounds comfortably inside each step timeout.
  The dry-run preview shows the worst-case planned wait and the planner stops
  before input when waits cannot fit.
- Make retry bounds larger than action bounds so recovery waits are visibly
  separate from routine pacing in `action-log.jsonl` and `final-report.md`.
- Use `center_weighted` for normal and careful work when most waits should land
  near the middle of the range. Use `uniform` only when the full configured
  range is equally acceptable.
- Keep `keyboard_interval_seconds` low enough that long text fields do not
  dominate runtime. It changes typing cadence only, never text content.
- Keep `scroll_interval_seconds` low enough that long pages still fit task
  timeouts. It changes wheel pacing only, never total scroll distance.
- Prefer `random_seed` while tuning so repeated traces can be compared. Remove
  it only after benchmark variance is understood.

### Choosing Entropy Budgets

Use `entropy_budget` to document where bounded variability is allowed, then let
the planner reject budgets that exceed runtime capacity.

| Budget | Use when | Typical placement |
| --- | --- | --- |
| `0.0` or omitted | The step should be deterministic. | Submissions, irreversible actions, exact data entry. |
| `0.25` to `0.5` | A small timing or equivalent-action choice is acceptable. | Simple navigation, one safe `click_text` / `click_uia` variant. |
| `1.0` | A retry or recovery path may be needed. | `scroll_until`, delayed controls, transient loading. |
| `2.0+` | A multi-step fixture has several safe variability points. | Whole task budgets after benchmark evidence supports them. |

Checklist:

- Set the task-level `entropy_budget` at or above the sum of explicit step
  budgets, but below what max steps, retries, and timeouts can support.
- Put step budgets on recognition, navigation, and recovery-heavy steps before
  putting them on data-entry or submission steps.
- Pair any entropy-bearing submission with `checkpoint`, `verify`,
  `requires_confirmation`, and a policy preset that matches the run.
- Check the `entropy_budget` trace event, `task.json`, and step metadata in the
  final report to confirm the budget was accepted and attributed to the intended
  steps.
- If `benchmark-report.json` shows higher ambiguity, recovery, retry, or
  intervention rates after adding entropy, reduce the budget or return to a
  deterministic profile.

### Report Review

After tuning a profile, inspect these artifacts before treating it as safe:

- `dry-run` preview for timing bounds, worst-case waits, and recovery paths.
- `action-log.jsonl` for `execution_timing`, `input_wait`,
  `action_variant`, `recover`, and `entropy_budget` events.
- `final-report.md` for failed-step categories, selected candidates, timing
  delay rows, keyboard cadence, scroll cadence, and final actuator guard stops.
- `safety-audit.md` for policy preset, operator approval, allowed windows,
  sensitive steps, checkpoint coverage, and findings.
- `benchmark-report.json` and `variance-report.json` for repeated-run success
  rate, median task time, grounding accuracy, ambiguity rate, recovery rate,
  retry count, and operator intervention rate.

## Policy Presets

`policy_preset` chooses the operator-control boundary used by the safety policy:

- `personal_automation` is the default and preserves existing task behavior.
  Steps only require confirmation when `requires_confirmation: true`.
- `strict_qa` requires explicit confirmation for `submission` category steps,
  even when the task did not mark the step with `requires_confirmation`.
- `exploratory_testing` blocks `submission` category steps. Use it for
  read-only navigation, recognition, and discovery runs that must stop before
  final actions.

The active preset is written to `config.json` and the `load_config` trace event.

## Local Model Assistance

`local_model` is disabled by default. When explicitly enabled, DeskPilot can use
local Ollama only as an advisory planner helper. For Phase 7, the supported use
is `use_for_goal_ranking`, which lets the `plan-goal` dry-run ask Ollama to
rank already-discovered routine candidates and explain the choice.
See [Local AI Assistance](local-ai.md) for the product boundary across planning,
screen review, trace review, and YAML suggestion workflows.

The local model cannot create actions, URLs, commands, or new routine IDs. Its
output is accepted only when every suggested ID already exists in the
deterministic candidate list. DeskPilot then reruns missing-input, approval,
safety-class, and schedule checks before reporting the selected routine. Invalid
or unavailable model output is recorded in the goal plan and the deterministic
plan remains in force.

Example opt-in config:

```yaml
local_model:
  enabled: true
  provider: ollama
  model: llama3.1
  endpoint: http://127.0.0.1:11434
  request_timeout_seconds: 10
  use_for_goal_ranking: true
```

Only local loopback Ollama endpoints are accepted: `127.0.0.1`, `localhost`, or
`::1`.

Local model health can be checked without running a routine:

```bash
desktop-agent local-model status --config config.yaml
desktop-agent local-model status --probe-disabled --output traces/local-model.json
desktop-agent local-model list --config config.yaml
```

`status` does not contact Ollama while `local_model.enabled` is false unless
`--probe-disabled` is passed. `list` is an explicit inventory command, so it
probes the configured local endpoint and prints the model names advertised by
Ollama. `--output` writes the same status as JSON for local monitoring reports.

Local model prompts are explicit classes so traces can disclose what assistance
was requested:

- `goal_routine_ranking`: rank already-known routine candidates.
- `missing_input_extraction`: draft values for known missing routine inputs.
- `trace_summarization`: summarize local trace artifacts for review.
- `screen_summary`: explain supplied screenshots/OCR for review and authoring.
- `yaml_improvement_suggestions`: draft review-only YAML improvement snippets.

Every prompt class keeps the same boundary: return structured JSON only, do not
execute desktop input, do not invent executable actions, and wait for
deterministic validation before any suggestion can affect a run.
Structured response validators reject unknown routine IDs, unknown missing-input
keys, unknown evidence references, malformed screen summaries, and YAML
improvement proposals that are not explicitly review-only.
Tests use an in-memory `FakeLocalModelProvider` that reports deterministic
model inventory and returns preauthored JSON by prompt class, so local-model
paths can be covered without network access or a running Ollama process.

For screen review, `desktop-agent inspect-screen --caption-output <path>` writes
a local caption prompt report from the captured screenshot, OCR text, UIA tree,
and fused candidates. The report is marked `review_only`, `authoring_only`, and
`direct_action_allowed: false`; it is never consumed by target selection or the
actuation pipeline.

## Sensitive Step Confirmation

Tasks can mark a step with `requires_confirmation: true`. Those steps are
blocked unless their step ID appears in `confirmed_steps` or is passed with the
CLI `--confirm-step` option. This keeps sensitive actions opt-in at run time
instead of relying only on task authoring.
Real `run` commands also prompt for operator approval before unconfirmed
`requires_confirmation` or `submission` category steps. Approved prompts are
added to the runtime `confirmed_steps`; declined prompts leave the step
unconfirmed so the planner writes a safety-stop report before input.

## Validation

Startup rejects unsafe values before any desktop action can run:

- Timeouts and maximum step counts must be greater than zero.
- Retry limits must not be negative.
- Confidence threshold must be greater than `0` and at most `1`.
- Execution profile timing bounds must be non-negative and ordered from lower
  to upper.
- Execution profile probability and smoothness values must be between `0` and
  `1`.
- Policy preset must be `strict_qa`, `personal_automation`, or
  `exploratory_testing`.
- Confirmed step IDs must not be blank.
- Local model assistance must use provider `ollama`, a local endpoint, a
  non-empty model name, and a positive request timeout. Goal ranking requires
  `local_model.enabled: true`.
- Emergency stop hotkey and trace root must be present.
- Window names must not be blank.
