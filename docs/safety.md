# Safety

DeskPilot v1 is designed for owned and controlled automation. It assumes the
operator has permission to automate the target desktop session and target
applications.

## Required Operating Conditions

- The Windows desktop must be unlocked.
- The user must be logged in.
- Tasks must declare allowed windows.
- Runtime configuration must include timeouts, retry limits, and maximum step
  limits.
- Reports, screenshots, OCR text, and traces are local by default.

## Explicitly Unsupported Uses

DeskPilot does not support stealth automation, CAPTCHA bypass, bot-detection
evasion, credential abuse, or abusive third-party automation.

## Public Website Automation Scope

Public-site playbooks are limited to operator-authorized navigation on websites
where automation is allowed by the operator's account, organization, and the
target site's rules. They may open pages, search surfaces, profile or channel
surfaces, notification views, settings pages, and composer surfaces that stop
before externally visible submission.

Public-site tasks must keep the same safety contract as local desktop tasks:
allowed windows are required, sensitive steps need explicit confirmation, and
blocked states such as logged-out sessions, consent dialogs, CAPTCHA
challenges, permission restrictions, unsupported layouts, or ambiguous targets
must stop execution with a local report.

For third-party websites, the operator is responsible for confirming that the
account, organization, and target site's terms permit the intended automation.
DeskPilot playbooks must be treated as navigation aids for authorized sessions,
not a way to create access, ignore site restrictions, or automate behavior that
the site or account owner does not permit.

## Public Site Unsupported Behaviors

Website playbooks must reject unsupported behaviors before they can be compiled
or executed.

## Safety Controls Planned For v1

- Active-window allowlist checks before every action, with a final actuator
  re-check before real input is sent.
- Dry-run mode that validates and plans without moving the mouse.
- Emergency stop hotkey polling on Windows, shared by the planner and real
  actuator boundary.
- Final step-region blocking for targeted click and scroll actions before real
  input is sent.
- Runtime policy presets for strict QA, personal automation, and exploratory
  testing.
- Operator approval prompts for real runs before unconfirmed irreversible or
  externally visible steps.
- Safety audit artifacts for execution-profile runs.
- Maximum runtime, maximum steps, and per-step retry limits.
- Confidence thresholds for OCR, image, and UIA candidate selection.
- Failure reports that explain why a task stopped.
- Step-level explicit confirmation for task actions marked as sensitive.

## Locked Screen Boundary

v1 does not support locked-screen or background desktop automation. The desktop
must be unlocked and visible because screenshot capture, UI Automation,
computer vision, OCR, and input actuation all depend on the active interactive
session.

## Local Trace Policy

Screenshots, OCR text, candidate data, action logs, and reports are written to
the configured local trace directory. v1 does not upload traces or call cloud AI
services.

## Emergency Stop

`emergency_stop_hotkey` defaults to `ctrl+alt+esc`. On Windows the planner polls
the configured key chord between bounded actions and writes an
`emergency_stopped` report when it is pressed. Real desktop actuation receives
the same monitor and blocks before sending input if the stop chord is active.
Unsupported platforms use a safe no-op monitor until their input adapters exist.

## Human-Like Execution Profile Boundary

The optional execution profile is limited to bounded timing decisions and trace
metadata. It must not change the user's intended task outcome, choose a
different action, leave the allowed window scope, bypass confidence gates, or
hide that automation is running.

Invalid execution profile bounds fail configuration validation before any
desktop action can run. Timing decisions are recorded in traces so failed runs
can be diagnosed without guessing why the planner waited or retried.
Target-aware timing can use selected target geometry and action type to choose
where a delay falls inside the configured bounds, but it does not pick new
targets, bypass confidence checks, or expand allowed timing limits.

Sensitive task steps can declare `requires_confirmation: true`. The planner
stops before the action unless the operator confirms the step ID through runtime
configuration or `--confirm-step`.
For real `run` commands, the CLI also prompts before unconfirmed
`requires_confirmation` or `submission` category steps. If the operator declines
or the prompt cannot read input, the run continues to the planner with
`require_operator_approval` enabled and stops with a report before input.
Sensitive or irreversible steps can also declare `checkpoint`; the planner must
pass that read-only verification before timing or action execution.

## Policy Presets

`policy_preset` defaults to `personal_automation`, which keeps only explicit
`requires_confirmation` gates. `strict_qa` adds a confirmation gate for
`submission` category steps. `exploratory_testing` blocks `submission` category
steps entirely so exploratory runs can inspect and navigate without crossing
into final actions.

## Safety Audit

When `execution_profile.enabled` is true, the trace directory includes
`safety-audit.json` and `safety-audit.md`. The audit records the active policy
preset, operator approval requirement, allowed windows, emergency stop hotkey,
sensitive steps, checkpoint coverage, and findings such as missing checkpoints
or unconfirmed confirmation-required steps.
