# DeskPilot Vision Alignment Action Plan

This file tracks the work to align DeskPilot v1 with the current product
direction: Windows-first, local-only, deterministic YAML/CLI automation for ops
teams running approved content workflows.

## Target Vision

- [x] Ops-team content automation is the primary v1 product direction.
- [x] Real execution is Windows-first.
- [x] Approvals, traces, screenshots, OCR output, and reports stay local by
  default.
- [x] Task and site workflow authoring stay YAML/CLI first.
- [x] LinkedIn and Medium are the first publish-capable content sites.
- [x] Sensitive site actions require explicit run preapproval.
- [x] Core execution has no cloud AI dependency.
- [x] The product excludes stealth automation, CAPTCHA bypass, bot-detection
  evasion, credential abuse, and abusive third-party automation.

## Current Status

- [x] Local test suite passed during the audit: 262 passed, 4 expected skips.
- [x] Ruff passed during the audit.
- [x] Mypy passed during the audit.
- [x] CLI dry-run works.
- [x] Site playbook compile and dry-run work.
- [x] Benchmark harness runs locally.
- [x] Product docs identify the revised ops-team content-automation vision.
- [x] Seed playbooks support publish-capable LinkedIn and Medium workflows.
- [x] Real run path includes Windows UIA perception.
- [x] Active-window safety is consistently enforced in real runs.
- [x] Approval manifest exists for ops-team preapproval.
- [ ] Windows package and live smoke evidence are complete.

## P0 Release Blockers

- [x] Add `docs/vision-alignment-action-plan.md` as the tracking source for
  this alignment work.
- [x] Rewrite `README.md` and `docs/project-definition.md` around the revised
  v1 vision.
- [x] Add local approval manifest support via `--approval-manifest <path>`.
- [x] Require approval manifests for sensitive `run-site` flows.
- [x] Add YAML variable support for content payloads.
- [x] Add LinkedIn publish-capable flow using YAML variables.
- [x] Add Medium publish-capable flow using YAML variables.
- [x] Add checkpoints before externally visible publish actions.
- [x] Keep all other seed sites read-only/open-surface until promoted.
- [x] Wire Windows UIA into non-dry-run perception.
- [x] Fix active-window allowlist enforcement for real runs.
- [ ] Pass Windows package verification.
- [ ] Pass Windows fixture e2e checks.
- [ ] Pass authorized live smoke checks for LinkedIn and Medium.

## P1 Product Alignment

- [x] Update `docs/website-playbooks.md` to distinguish read-only, draft, and
  publish-capable flows.
- [x] Update `navigation_playbooks/README.md` with promotion criteria for
  publish-capable sites.
- [x] Document the approval manifest schema.
- [x] Document YAML variable schema for content payloads.
- [x] Document local artifact locations for approvals, traces, and reports.
- [x] Update troubleshooting docs for approval-manifest failures.
- [x] Update release notes to remove benchmark overclaims.
- [x] Move non-v1 content ops actions into a clearly marked backlog.

## P1 Safety Hardening

- [x] Implement one shared allowlist matcher for planner and actuator.
- [x] Support exact, case-insensitive contains, and optional `regex:` window
  matching.
- [x] Populate active window title during Windows screen observation.
- [x] Pass effective task and runtime allowlists into final actuator guards.
- [x] Add regression test: wrong active window stops before timing.
- [x] Add regression test: wrong active window stops before actuation.
- [x] Add regression test: task allowlist works without duplicating config
  allowlist.
- [x] Add regression test: sensitive site action fails without approval
  manifest.
- [x] Add regression test: manifest scope mismatch fails before input.

## P2 Evidence And Ops Readiness

- [x] Add sample approval manifest files under `examples/`.
- [x] Add sample LinkedIn content variables file.
- [x] Add sample Medium content variables file.
- [x] Add dry-run examples for publish-capable flows.
- [x] Add trace assertions for approval manifest metadata.
- [x] Add trace assertions for variable redaction/fingerprints.
- [x] Add opt-in Windows smoke command for LinkedIn publish dry-run/live-safe
  path.
- [x] Add opt-in Windows smoke command for Medium publish dry-run/live-safe
  path.
- [x] Record manual Windows evidence in `docs/windows-e2e-checklist.md`.

## Acceptance Criteria

- [x] `desktop-agent dry-run-site linkedin <publish-flow>` validates variables
  and approval requirements.
- [x] `desktop-agent dry-run-site medium <publish-flow>` validates variables and
  approval requirements.
- [x] Sensitive site flow without approval manifest exits nonzero with a clear
  message.
- [x] Approval manifest with wrong site, flow, step, or content fingerprint
  exits nonzero.
- [x] Real run uses UIA, OCR, and CV candidate fusion.
- [x] Real run cannot act outside task/config allowed windows.
- [x] LinkedIn and Medium publish flows stop on logged-out, consent, CAPTCHA,
  permission, unsupported-layout, or ambiguous-target states.
- [x] All artifacts remain local by default.
- [ ] Full local quality gate passes.
- [ ] Windows package verification passes.
- [ ] Authorized live smoke evidence exists for LinkedIn and Medium.

## Out Of Scope For This Pass

- [x] Cross-platform desktop actuation.
- [x] Cloud model adapters.
- [x] Report server.
- [x] Visual recorder.
- [x] Full publish support for X, Instagram, Facebook, YouTube, and TikTok.
- [x] Message, delete, settings-change, transaction, and engagement flows unless
  separately promoted.
