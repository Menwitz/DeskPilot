# Website Navigation Playbook Roadmap

This roadmap turns the website-navigation playbook concept into checkable
implementation work. The system must stay inside DeskPilot's existing safety
boundary: authorized use only, no stealth automation, no CAPTCHA or
bot-detection bypass, no credential abuse, and no unconfirmed sensitive actions.

## OKRs

### Objective 1: Create a scalable website navigation catalog.

- [ ] KR1: Add a validated playbook schema that supports domains, window titles,
  landmarks, flows, sensitive steps, and known blocked states.
- [ ] KR2: Add seed playbooks for LinkedIn, X/Twitter, Instagram, Facebook,
  Medium, YouTube, and TikTok.
- [ ] KR3: Add documentation that lets a new engineer add a website without
  changing planner internals.

### Objective 2: Compile website playbooks into deterministic DeskPilot tasks.

- [ ] KR1: Add a loader that reads a site playbook and resolves a requested flow.
- [ ] KR2: Add a compiler that converts supported playbook flows into the
  existing `TaskDefinition` model.
- [ ] KR3: Add CLI commands to list sites, list flows, and run a selected flow.

### Objective 3: Keep public-site automation safe and debuggable.

- [ ] KR1: Require explicit confirmation for every sensitive step.
- [ ] KR2: Detect and stop on logged-out, consent, CAPTCHA, permission, and
  unsupported-layout states.
- [ ] KR3: Include site, flow, confirmation, blocked-state, and selector metadata
  in local traces.

### Objective 4: Make growth cheap and testable.

- [ ] KR1: Add regression tests that validate every playbook and compiled flow.
- [ ] KR2: Keep live-site checks opt-in so normal CI is deterministic.
- [ ] KR3: Provide a copyable new-site template with required checklist items.

## Phase 0: Scope And Safety Contract

- [x] Confirm public-site scope in `docs/safety.md`.
- [x] Document that third-party websites require operator authorization and
  compliance with the target site's rules.
- [x] Document unsupported behavior:
  - [x] CAPTCHA solving or bypass.
  - [x] Bot-detection bypass.
  - [x] Credential abuse.
  - [x] Stealth automation.
  - [x] Unconfirmed posting, messaging, purchasing, applying, deleting, or
    settings changes.
- [x] Define sensitive action categories shared by all site playbooks:
  - [x] Login.
  - [x] Post, publish, upload, or submit.
  - [x] Like, react, clap, repost, subscribe, follow, friend, connect, or join.
  - [x] Comment or reply.
  - [x] Message or send.
  - [x] Apply, purchase, marketplace action, or payment-adjacent action.
  - [x] Delete content.
  - [x] Change account, privacy, notification, security, or billing settings.

## Phase 1: Playbook Schema

- [x] Add `src/desktop_agent/site_playbooks.py`.
- [x] Add immutable data models:
  - [x] `SitePlaybook`.
  - [x] `SiteDomain`.
  - [x] `SiteLandmark`.
  - [x] `SiteFlow`.
  - [x] `SiteFlowStep`.
  - [x] `BlockedState`.
- [x] Add a YAML loader for `navigation_playbooks/*.yaml`.
- [x] Add schema validation:
  - [x] Site ID is required and slug-safe.
  - [x] At least one domain is required.
  - [x] At least one allowed window-title pattern is required.
  - [x] Flow IDs are unique.
  - [x] Step IDs are unique within each flow.
  - [x] Sensitive steps must declare `requires_confirmation: true`.
  - [x] References to landmarks must resolve.
  - [x] Unsupported actions fail validation before execution.
  - [x] Blocked-state definitions must include a detector and user-facing reason.
- [x] Add comments only around non-obvious validation and safety decisions.

## Phase 2: Catalog Layout And Seed Playbooks

- [x] Add `navigation_playbooks/README.md`.
- [x] Add `navigation_playbooks/_template.yaml`.
- [x] Add seed playbooks:
  - [x] `navigation_playbooks/linkedin.yaml`.
  - [x] `navigation_playbooks/x-twitter.yaml`.
  - [x] `navigation_playbooks/instagram.yaml`.
  - [x] `navigation_playbooks/facebook.yaml`.
  - [x] `navigation_playbooks/medium.yaml`.
  - [x] `navigation_playbooks/youtube.yaml`.
  - [x] `navigation_playbooks/tiktok.yaml`.
- [x] For each seed playbook, define domains:
  - [x] Primary domain.
  - [x] Common alternate domain when applicable.
  - [x] Account or auth domain only when needed for recognition.
- [x] For each seed playbook, define navigation flows:
  - [x] Open home or feed.
  - [x] Open search.
  - [x] Open profile or channel page.
  - [x] Open notifications.
  - [x] Open messages when the site has messages.
  - [x] Open settings.
  - [x] Open composer, upload, or editor surface without final submission.
- [x] For each seed playbook, define blocked states:
  - [x] Logged out.
  - [x] Consent or cookie interstitial.
  - [x] CAPTCHA or suspicious-activity challenge.
  - [x] Permission or account restriction.
  - [x] Unsupported layout.
  - [x] Ambiguous target.

## Phase 3: Compiler Into Existing Task DSL

- [x] Add `SiteTaskCompiler`.
- [x] Compile site domains and window-title patterns into task `allowed_windows`.
- [x] Compile playbook steps into existing task actions:
  - [x] `click_text`.
  - [x] `click_image`.
  - [x] `click_uia`.
  - [x] `type_text`.
  - [x] `press_key`.
  - [x] `scroll`.
  - [x] `scroll_until`.
  - [x] `wait_for`.
  - [x] `assert_visible`.
  - [x] `branch_if_visible`.
- [x] Preserve confirmation requirements when compiling sensitive steps.
- [x] Add flow-level defaults:
  - [x] Timeout.
  - [x] Retry budget.
  - [x] Confidence threshold.
  - [x] Optional search region.
- [x] Add blocked-state checks before irreversible actions.
- [x] Add task metadata for trace readability:
  - [x] Site ID.
  - [x] Flow ID.
  - [x] Domain.
  - [x] Sensitive step IDs.
  - [x] Playbook version.

## Phase 4: CLI Commands

- [x] Add `desktop-agent list-sites`.
- [x] Add `desktop-agent list-flows <site>`.
- [x] Add `desktop-agent compile-site <site> <flow> --output <task.yaml>`.
- [x] Add `desktop-agent run-site <site> <flow>`.
- [x] Add `desktop-agent dry-run-site <site> <flow>`.
- [x] Support existing runtime safety flags:
  - [x] `--config`.
  - [x] `--verbose`.
  - [x] `--no-screenshots`.
  - [x] `--max-runtime-seconds`.
  - [x] `--confidence-threshold`.
  - [x] `--allowed-window`.
  - [x] `--confirm-step`.
- [x] Ensure CLI failures explain:
  - [x] Unknown site.
  - [x] Unknown flow.
  - [x] Invalid playbook.
  - [x] Missing confirmation.
  - [x] Blocked state detected.
  - [x] Unsupported live-site state.

## Phase 5: Tracing And Debuggability

- [x] Extend trace output with site-playbook metadata.
- [x] Record playbook validation results in trace metadata.
- [x] Record compiled task path or in-memory task summary.
- [x] Record blocked-state checks and outcomes.
- [x] Record whether each sensitive step was confirmed or blocked.
- [x] Update replay output to include site and flow when present.
- [x] Update troubleshooting docs with public-site failure modes:
  - [x] Logged-out session.
  - [x] Consent dialog.
  - [x] Site redesign.
  - [x] CAPTCHA or suspicious-activity challenge.
  - [x] Permission restriction.
  - [x] Ambiguous selector.

## Phase 6: Regression Tests

### Schema Regression Tests

- [x] Valid playbook loads successfully.
- [x] Missing site ID is rejected.
- [x] Invalid site ID is rejected.
- [x] Empty domains are rejected.
- [x] Empty window-title patterns are rejected.
- [x] Duplicate flow IDs are rejected.
- [x] Duplicate flow-step IDs are rejected.
- [x] Unknown step action is rejected.
- [x] Missing landmark reference is rejected.
- [x] Sensitive step without confirmation is rejected.
- [x] Blocked state without a reason is rejected.

### Compiler Regression Tests

- [x] Basic navigation flow compiles to `TaskDefinition`.
- [x] Compiled task passes `BasicTaskValidator`.
- [x] Domain and title rules become `allowed_windows`.
- [x] Flow timeout compiles into task timeout.
- [x] Flow retry defaults compile into step retry values.
- [x] Sensitive steps preserve `requires_confirmation`.
- [x] Blocked-state checks compile before sensitive final actions.
- [x] Unknown site flow fails before task execution.

### CLI Regression Tests

- [x] `list-sites` prints all seed sites.
- [x] `list-flows linkedin` prints LinkedIn flows.
- [x] `compile-site youtube open-search` writes a valid task YAML.
- [x] `dry-run-site medium open-editor` validates without desktop input.
- [x] `run-site` returns nonzero when platform actuation is unavailable.
- [x] Missing confirmation returns nonzero with a clear message.
- [x] Invalid playbook returns nonzero with the validation error.

### Safety Regression Tests

- [x] Login step is blocked without `--confirm-step`.
- [x] Post or publish step is blocked without `--confirm-step`.
- [x] Message-send step is blocked without `--confirm-step`.
- [x] Delete step is blocked without `--confirm-step`.
- [x] Settings-change step is blocked without `--confirm-step`.
- [x] CAPTCHA state aborts with a no-bypass message.
- [x] Active-window mismatch aborts before action.
- [x] Emergency stop behavior remains unchanged.

### Trace Regression Tests

- [x] Final report includes site ID and flow ID for site runs.
- [ ] Action log includes selected playbook version.
- [ ] Sensitive blocked step appears in trace metadata.
- [ ] Blocked-state reason appears in final report.
- [ ] Replay prints site and flow fields when available.

### Opt-In Live Smoke Tests

- [ ] Live smoke tests are skipped by default.
- [ ] Live smoke tests require an explicit environment flag.
- [ ] Live smoke tests never run final submit, post, message, purchase, apply, or
  delete actions unless a separate confirmation flag is present.
- [ ] Each seed site has one read-only smoke flow:
  - [ ] LinkedIn: open search or profile surface.
  - [ ] X/Twitter: open search or notifications surface.
  - [ ] Instagram: open search or profile surface.
  - [ ] Facebook: open search or notifications surface.
  - [ ] Medium: open search or editor surface without publishing.
  - [ ] YouTube: open search or channel surface.
  - [ ] TikTok: open search or profile surface.

## Phase 7: Documentation

- [ ] Add playbook authoring docs.
- [ ] Add a new-site checklist.
- [ ] Add examples for:
  - [ ] Read-only navigation flow.
  - [ ] Search flow.
  - [ ] Composer-open flow that stops before submission.
  - [ ] Sensitive confirmed flow.
  - [ ] Blocked-state detection.
- [ ] Update `README.md` documentation links.
- [ ] Update `docs/architecture.md` with the playbook layer.
- [ ] Update `docs/task-dsl.md` to explain that playbooks compile into existing
  tasks rather than replacing the DSL.
- [ ] Update `docs/safety.md` with third-party website guardrails.

## Phase 8: Acceptance Criteria

- [ ] A new engineer can add a website by copying `_template.yaml`, filling in
  landmarks and flows, and adding schema/compiler tests.
- [ ] All seven seed playbooks validate.
- [ ] Every seed playbook has at least one read-only navigation flow.
- [ ] Every seed playbook has sensitive actions marked with explicit
  confirmation.
- [ ] Compiled flows pass the existing task validator.
- [ ] Normal CI remains deterministic and does not depend on live public sites.
- [ ] Opt-in live smoke tests can be run manually for the seed sites.
- [ ] Failed site runs produce clear local traces and final reports.

## Phase 9: Approval Manifests For Sensitive Site Runs

- [ ] Add a local YAML approval manifest contract for sensitive public-site
  workflows.
- [ ] Validate manifest site ID, flow ID, approved step IDs, approver, reason,
  ISO timestamp, and content fingerprint before execution.
- [ ] Require approval manifests for real `run-site` execution when a compiled
  site task contains sensitive or submission steps.
- [ ] Merge approved step IDs into runtime confirmation without interactive
  prompts for site runs.
- [ ] Record manifest validation, approved step IDs, approver, reason,
  timestamp, and content fingerprint in local traces and reports.
- [ ] Add regression coverage for missing, invalid, and accepted approval
  manifests.
- [ ] Document approval manifest usage in website playbook and safety docs.

## Commit Plan

- [ ] `docs: add website navigation playbook roadmap`
- [ ] `feat: add site playbook schema`
- [ ] `feat: compile site playbooks into tasks`
- [ ] `feat: add site playbook cli commands`
- [ ] `docs: document website playbook authoring`
- [ ] `test: cover website playbook validation`
- [ ] `test: cover site flow compilation`
- [ ] `test: cover site run safety gates`
- [ ] `feat: require approval manifests for site runs`
