# Project Definition

DeskPilot v1 is a Windows-first local desktop automation framework for owned
QA workflows and personal automation on an unlocked, logged-in desktop session.

The v1 implementation language is Python 3.12. Task authors write deterministic
automation tasks in YAML, and the runtime combines task execution with local
screen capture, computer vision, OCR, and Windows UI Automation.

## Safety Boundary

DeskPilot is intended for controlled environments where the operator owns the
desktop session, the applications under automation, or the QA scope. The project
does not support stealth automation, CAPTCHA bypass, bot-detection evasion,
credential abuse, or abusive third-party automation.

## Local-First Data Policy

Screenshots, OCR output, traces, and reports stay local by default. v1 has no
cloud AI dependency, and external services are not required for core execution.

## Platform Scope

v1 targets Windows desktop automation first. Platform-specific behavior must be
kept behind interfaces so future Linux support can be added without changing the
task DSL or planner contracts.
