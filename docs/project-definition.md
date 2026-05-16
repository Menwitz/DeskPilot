# Project Definition

DeskPilot v1 is a Windows-first local desktop automation system for ops teams
running approved content workflows and controlled desktop tasks on an unlocked,
logged-in desktop session.

The v1 implementation language is Python 3.12. Task authors write deterministic
automation tasks, site playbooks, approval records, and content variables in
YAML. The runtime combines task execution with local screen capture, computer
vision, OCR, and Windows UI Automation.

## Product Contract

The next product milestone is a personal local routine assistant built on the
existing YAML task and website playbook foundation. DeskPilot should help an
operator record, review, schedule, approve, run, and replay authorized desktop
routines through visible local Windows input. Human-paced timing, routine
selection, and activity spacing are allowed only inside explicit safety,
approval, trace, and allowed-window boundaries.

The personal assistant roadmap is tracked in
[Personal Routine Assistant Roadmap](personal-routine-assistant-roadmap.md).
That roadmap is the source of truth for recorder, routine catalog, goal
planning, native operator UI, Windows proof bundles, local model assistance,
redaction, and routine-pack work.
The local AI boundary is documented in [Local AI Assistance](local-ai.md).

## Safety Boundary

DeskPilot is intended for controlled environments where the operator owns or is
authorized to automate the desktop session, target account, application, or
content workflow. Sensitive public-site actions require explicit run
preapproval and local trace evidence. The project does not support stealth
automation, CAPTCHA bypass, bot-detection evasion, credential abuse, or abusive
third-party automation.

## Local-First Data Policy

Screenshots, OCR output, traces, and reports stay local by default. v1 has no
cloud AI dependency, and external services are not required for core execution.

## Product Scope

The v1 product is YAML/CLI first. LinkedIn and Medium are the initial
publish-capable content playbooks; other seed site playbooks stay read-only or
open-surface until they are promoted with approval, variables, blocked-state,
and live-smoke evidence.

## Platform Scope

v1 targets Windows desktop automation first. Platform-specific behavior must be
kept behind interfaces so future Linux support can be added without changing the
task DSL or planner contracts.
