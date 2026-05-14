# Tracing And Reports

DeskPilot writes local trace artifacts for every CLI run. The trace sink creates
a unique run directory under `trace_root` and then hands that directory back to
the execution pipeline as the active `config.trace_root`.

## Files

- `config.json` stores the normalized runtime configuration used by the run.
- `task.json` stores the normalized task definition.
- `action-log.jsonl` stores every trace event as newline-delimited JSON.
- `final-report.json` stores the machine-readable final report.
- `final-report.md` stores a human-readable report.
- `screenshots/` receives screen captures when `save_screenshots` is enabled.
- `ocr/` receives OCR output when `save_ocr_text` is enabled.
- `overlays/` receives computer-vision candidate overlays when screenshot
  saving is enabled.

## Report Contents

The final report includes the task name, final status, abort reason when
present, step reports, selected candidate IDs, event metadata, candidate
rankings, confidence values, screenshot paths, timing decisions, and the trace
directory. Step reports and step-related trace events include `step_category`
metadata so benchmark and timing analysis can group navigation, recognition,
data-entry, verification, and submission work. Enabled `execution_timing` events
also include `execution_persona`, `persona_timing_bias`, `klm_operators`,
`klm_operator_counts`, `klm_total_seconds`, and input-mode metadata for the
bounded cognitive timing model.

Each executed step also emits `step_timeout_budget` metadata with the planned
action wait, retry wait, total planned wait, remaining timeout, and whether the
budget fits before any desktop action is attempted.

## Replay

`desktop-agent replay <trace-dir>` reads `final-report.json` and prints a
summary without rerunning actions.
