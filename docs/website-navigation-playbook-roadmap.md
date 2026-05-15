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
  - [ ] Change account, privacy, notification, security, or billing settings.

## Phase 1: Playbook Schema

- [ ] Add `src/desktop_agent/site_playbooks.py`.
- [ ] Add immutable data models:
  - [ ] `SitePlaybook`.
  - [ ] `SiteDomain`.
  - [ ] `SiteLandmark`.
  - [ ] `SiteFlow`.
  - [ ] `SiteFlowStep`.
  - [ ] `BlockedState`.
- [ ] Add a YAML loader for `navigation_playbooks/*.yaml`.
- [ ] Add schema validation:
  - [ ] Site ID is required and slug-safe.
  - [ ] At least one domain is required.
  - [ ] At least one allowed window-title pattern is required.
  - [ ] Flow IDs are unique.
  - [ ] Step IDs are unique within each flow.
  - [ ] Sensitive steps must declare `requires_confirmation: true`.
  - [ ] References to landmarks must resolve.
  - [ ] Unsupported actions fail validation before execution.
  - [ ] Blocked-state definitions must include a detector and user-facing reason.
- [ ] Add comments only around non-obvious validation and safety decisions.

## Phase 2: Catalog Layout And Seed Playbooks

- [ ] Add `navigation_playbooks/README.md`.
- [ ] Add `navigation_playbooks/_template.yaml`.
- [ ] Add seed playbooks:
  - [ ] `navigation_playbooks/linkedin.yaml`.
  - [ ] `navigation_playbooks/x-twitter.yaml`.
  - [ ] `navigation_playbooks/instagram.yaml`.
  - [ ] `navigation_playbooks/facebook.yaml`.
  - [ ] `navigation_playbooks/medium.yaml`.
  - [ ] `navigation_playbooks/youtube.yaml`.
  - [ ] `navigation_playbooks/tiktok.yaml`.
- [ ] For each seed playbook, define domains:
  - [ ] Primary domain.
  - [ ] Common alternate domain when applicable.
  - [ ] Account or auth domain only when needed for recognition.
- [ ] For each seed playbook, define navigation flows:
  - [ ] Open home or feed.
  - [ ] Open search.
  - [ ] Open profile or channel page.
  - [ ] Open notifications.
  - [ ] Open messages when the site has messages.
  - [ ] Open settings.
  - [ ] Open composer, upload, or editor surface without final submission.
- [ ] For each seed playbook, define blocked states:
  - [ ] Logged out.
  - [ ] Consent or cookie interstitial.
  - [ ] CAPTCHA or suspicious-activity challenge.
  - [ ] Permission or account restriction.
  - [ ] Unsupported layout.
  - [ ] Ambiguous target.

## Phase 3: Compiler Into Existing Task DSL

- [ ] Add `SiteTaskCompiler`.
- [ ] Compile site domains and window-title patterns into task `allowed_windows`.
- [ ] Compile playbook steps into existing task actions:
  - [ ] `click_text`.
  - [ ] `click_image`.
  - [ ] `click_uia`.
  - [ ] `type_text`.
  - [ ] `press_key`.
  - [ ] `scroll`.
  - [ ] `scroll_until`.
  - [ ] `wait_for`.
  - [ ] `assert_visible`.
  - [ ] `branch_if_visible`.
- [ ] Preserve confirmation requirements when compiling sensitive steps.
- [ ] Add flow-level defaults:
  - [ ] Timeout.
  - [ ] Retry budget.
  - [ ] Confidence threshold.
  - [ ] Optional search region.
- [ ] Add blocked-state checks before irreversible actions.
- [ ] Add task metadata for trace readability:
  - [ ] Site ID.
  - [ ] Flow ID.
  - [ ] Domain.
  - [ ] Sensitive step IDs.
  - [ ] Playbook version.

## Phase 4: CLI Commands

- [ ] Add `desktop-agent list-sites`.
- [ ] Add `desktop-agent list-flows <site>`.
- [ ] Add `desktop-agent compile-site <site> <flow> --output <task.yaml>`.
- [ ] Add `desktop-agent run-site <site> <flow>`.
- [ ] Add `desktop-agent dry-run-site <site> <flow>`.
- [ ] Support existing runtime safety flags:
  - [ ] `--config`.
  - [ ] `--verbose`.
  - [ ] `--no-screenshots`.
  - [ ] `--max-runtime-seconds`.
  - [ ] `--confidence-threshold`.
  - [ ] `--allowed-window`.
  - [ ] `--confirm-step`.
- [ ] Ensure CLI failures explain:
  - [ ] Unknown site.
  - [ ] Unknown flow.
  - [ ] Invalid playbook.
  - [ ] Missing confirmation.
  - [ ] Blocked state detected.
  - [ ] Unsupported live-site state.

## Phase 5: Tracing And Debuggability

- [ ] Extend trace output with site-playbook metadata.
- [ ] Record playbook validation results in trace metadata.
- [ ] Record compiled task path or in-memory task summary.
- [ ] Record blocked-state checks and outcomes.
- [ ] Record whether each sensitive step was confirmed or blocked.
- [ ] Update replay output to include site and flow when present.
- [ ] Update troubleshooting docs with public-site failure modes:
  - [ ] Logged-out session.
  - [ ] Consent dialog.
  - [ ] Site redesign.
  - [ ] CAPTCHA or suspicious-activity challenge.
  - [ ] Permission restriction.
  - [ ] Ambiguous selector.

## Phase 6: Regression Tests

### Schema Regression Tests

- [ ] Valid playbook loads successfully.
- [ ] Missing site ID is rejected.
- [ ] Invalid site ID is rejected.
- [ ] Empty domains are rejected.
- [ ] Empty window-title patterns are rejected.
- [ ] Duplicate flow IDs are rejected.
- [ ] Duplicate flow-step IDs are rejected.
- [ ] Unknown step action is rejected.
- [ ] Missing landmark reference is rejected.
- [ ] Sensitive step without confirmation is rejected.
- [ ] Blocked state without a reason is rejected.

### Compiler Regression Tests

- [ ] Basic navigation flow compiles to `TaskDefinition`.
- [ ] Compiled task passes `BasicTaskValidator`.
- [ ] Domain and title rules become `allowed_windows`.
- [ ] Flow timeout compiles into task timeout.
- [ ] Flow retry defaults compile into step retry values.
- [ ] Sensitive steps preserve `requires_confirmation`.
- [ ] Blocked-state checks compile before sensitive final actions.
- [ ] Unknown site flow fails before task execution.

### CLI Regression Tests

- [ ] `list-sites` prints all seed sites.
- [ ] `list-flows linkedin` prints LinkedIn flows.
- [ ] `compile-site youtube open-search` writes a valid task YAML.
- [ ] `dry-run-site medium open-editor` validates without desktop input.
- [ ] `run-site` returns nonzero when platform actuation is unavailable.
- [ ] Missing confirmation returns nonzero with a clear message.
- [ ] Invalid playbook returns nonzero with the validation error.

### Safety Regression Tests

- [ ] Login step is blocked without `--confirm-step`.
- [ ] Post or publish step is blocked without `--confirm-step`.
- [ ] Message-send step is blocked without `--confirm-step`.
- [ ] Delete step is blocked without `--confirm-step`.
- [ ] Settings-change step is blocked without `--confirm-step`.
- [ ] CAPTCHA state aborts with a no-bypass message.
- [ ] Active-window mismatch aborts before action.
- [ ] Emergency stop behavior remains unchanged.

### Trace Regression Tests

- [ ] Final report includes site ID and flow ID for site runs.
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

## Commit Plan

- [x] `docs: add website navigation playbook roadmap`
- [ ] `feat: add site playbook schema`
- [ ] `feat: compile site playbooks into tasks`
- [ ] `feat: add site playbook cli commands`
- [ ] `docs: document website playbook authoring`
- [ ] `test: cover website playbook validation`
- [ ] `test: cover site flow compilation`
- [ ] `test: cover site run safety gates`
