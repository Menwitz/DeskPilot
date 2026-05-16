# Local AI Assistance

DeskPilot local AI is optional and disabled by default. It is limited to
advisory selection and review workflows. The execution engine remains
deterministic: validated routines, task YAML, safety policies, approvals,
scheduler gates, and allowed-window checks decide what can run.

## Allowed Roles

- Goal planning can ask local Ollama to rank already-discovered routine
  candidates.
- Missing-input extraction can draft values for known routine inputs.
- Trace summarization can explain local trace artifacts for review.
- Screen summary can describe supplied screenshots, OCR, UIA, and candidate
  metadata for review and routine authoring.
- YAML improvement suggestions can draft review-only snippets after failed
  traces.

## Hard Boundary

Local model output cannot execute raw desktop actions. It cannot create new
routine IDs, issue commands, choose click targets, bypass approvals, bypass
routine validation, or bypass safety gates. Any accepted model output must stay
inside known routines, known input keys, known evidence references, or known
step IDs.

The model can assist only before deterministic checks rerun. For example,
goal-to-routine planning may accept a model-proposed routine order only when
every routine ID already exists in the deterministic candidate list. DeskPilot
then recomputes missing inputs, approvals, schedule eligibility, and safety
class before the plan can become ready.

## Local-Only Operation

`local_model.enabled` defaults to `false`. When enabled, DeskPilot accepts only
loopback Ollama endpoints such as `http://127.0.0.1:11434`. Core execution,
dry-runs, trace replay, proof replay, and routine validation do not require a
model.

Use these local checks before enabling model-assisted planning:

```bash
desktop-agent local-model status --config config.yaml
desktop-agent local-model list --config config.yaml
```

## Validation And Reporting

Each local model prompt has a prompt class and a structured response validator:

- `goal_routine_ranking`
- `missing_input_extraction`
- `trace_summarization`
- `screen_summary`
- `yaml_improvement_suggestions`

Invalid model output is rejected and the deterministic result remains in force.
Model-assisted traces disclose provider, model name, prompt class, input
artifact references, output hash, structured output status, and accepted or
rejected status. Local status checks can write JSON reports with `--output`.

Tests use `FakeLocalModelProvider` for deterministic model inventory and
preauthored JSON responses without network access or a running Ollama process.
