# Release Notes

## Ops Content Workflow Alignment

Date: 2026-05-15

This alignment update narrows v1 around Windows-first, local YAML/CLI
automation for approved ops content workflows.

- Added local approval manifests for sensitive site runs.
- Added local YAML content variables with redacted trace metadata and content
  fingerprints.
- Hardened active-window safety with shared planner/actuator matching.
- Added Windows UIA to the real perception pipeline alongside OCR and CV.
- Promoted only LinkedIn and Medium to publish-capable seed workflows.
- Added sample content-variable files and matching approval manifests.

Benchmark acceptance remains a threshold check, not a performance claim. Treat
baseline comparisons, repeated local traces, and Windows checklist evidence as
the source for any actual improvement claim.

## Windows Evidence Gate Status

Local CI, dry-runs, fixture tests, and benchmark acceptance prove the
cross-platform task, playbook, safety, tracing, and reporting foundation. They
do not prove that DeskPilot is a finished personal routine assistant or that the
real Windows desktop workflow is production-ready.

Real product proof still requires owned, unlocked Windows evidence bundles with
video, traces, pre-action and post-action screenshots, cursor readbacks,
active-window metadata, target reasoning, and final reports for browser,
native, mixed, and recovery workflows. Those gates are tracked in
[Personal Routine Assistant Roadmap](personal-routine-assistant-roadmap.md) and
must remain separate from local-only quality checks.

## Human-Like Execution Safety Release

Date: 2026-05-14

This release adds natural execution controls for authorized local desktop
automation. Natural execution means bounded timing, careful recovery,
transparent monitoring, and operator-controlled safety gates on an owned or
approved desktop session. It does not mean deceptive human impersonation.

## What Changed

- Added opt-in `execution_profile` settings for `fast`, `normal`, and
  `careful` personas.
- Added bounded action, retry, keyboard, scroll, and pointer movement timing.
- Added reproducible randomness through `random_seed` and traceable sample
  records.
- Added policy presets for `personal_automation`, `strict_qa`, and
  `exploratory_testing`.
- Added operator approval prompts for real runs before unconfirmed sensitive or
  submission steps.
- Added dry-run previews for timing bounds, worst-case waits, and recovery
  paths.
- Added safety audit artifacts for execution-profile runs.
- Added complete execution-profile example tasks and benchmark registration for
  dry-run/run, deep-search sources, monitoring phases, metrics, and report
  fields.
- Added troubleshooting guidance for ambiguity gates, recovery stops, and safety
  stops.

## Natural Execution

Natural execution is allowed only inside DeskPilot's existing safety boundary:

- The operator owns or is authorized to automate the desktop session.
- The task declares allowed windows, timeouts, retry limits, and verification.
- Randomness is bounded, configured, and recorded.
- Candidate search, timing, recovery, and safety decisions remain visible in
  local traces and final reports.
- Sensitive actions require checkpoints, confirmations, policy review, or
  explicit operator approval.
- Benchmark acceptance is based on reliability, grounding accuracy, ambiguity
  rate, recovery rate, intervention rate, and trace quality.

## Not Human Impersonation

This release is not for hiding automation or pretending to be a person. DeskPilot
does not support stealth automation, CAPTCHA bypass, bot-detection evasion,
credential abuse, abusive third-party automation, rate-limit avoidance, or
deceptive human impersonation.

The execution profile must not be used to:

- Mask automation from a system that prohibits automation.
- Randomize targets, click offsets, or action choices in ways that could change
  task outcome.
- Suppress traces, reports, safety audits, or timing metadata.
- Auto-confirm irreversible or externally visible steps.
- Continue after active-window rejection, ambiguity gates, emergency stop, final
  actuator guard blocks, or unsafe profile validation failures.

## Operator Impact

Existing tasks keep deterministic behavior unless `execution_profile.enabled` is
set to `true`. New profile-enabled tasks should be tuned in this order:

1. Run `desktop-agent dry-run <task.yaml>` and inspect the preview.
2. Review `config.json`, `task.json`, `action-log.jsonl`, `final-report.md`, and
   `safety-audit.md`.
3. Run `desktop-agent benchmark-run <task.yaml> --iterations <n> --output <dir>`
   for repeated evidence.
4. Reduce timing bounds or entropy budgets if ambiguity, recovery, retry, or
   operator-intervention rates increase.

## Verification

The release is covered by regression tests for unsafe profile validation,
unconfirmed sensitive actions, ambiguity gates, recovery reports, final
actuation guards, safety audit artifacts, profile examples, and documentation
boundaries. Windows smoke tests remain opt-in because they require an unlocked
owned Windows desktop session.
