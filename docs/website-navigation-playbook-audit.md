# Website Navigation Playbook Implementation Audit

This file records evidence before roadmap tasks are checked. A checkbox in
`docs/website-navigation-playbook-roadmap.md` is considered complete only after
the related code, docs, tests, monitoring, or report behavior is inspected or
implemented and the evidence is recorded here.

## Phase 0 Audit: Scope And Safety Contract

Phase 0 starts from the existing safety documentation and validates each public
website safety claim before the corresponding roadmap item is checked.

### Task 1/122: Confirm public-site scope in `docs/safety.md`

- Status: complete.
- Evidence:
  - `docs/safety.md` has a `Public Website Automation Scope` section.
  - The section limits public-site playbooks to operator-authorized navigation.
  - The section names allowed navigation surfaces: pages, search, profile or
    channel, notifications, settings, and composer surfaces that stop before
    externally visible submission.
  - The section requires public-site tasks to keep local task safety controls:
    allowed windows, explicit confirmation for sensitive steps, blocked-state
    stops, and local reports.
- Verification:
  - Reviewed `docs/safety.md` lines 21-40.

### Task 2/122: Document third-party website authorization and rule compliance

- Status: complete.
- Evidence:
  - `docs/safety.md` states that public-site playbooks are limited to websites
    where automation is allowed by the operator's account, organization, and
    the target site's rules.
  - `docs/safety.md` states that the operator is responsible for confirming
    that the account, organization, and site terms permit the intended
    automation.
  - The same section frames playbooks as navigation aids for authorized
    sessions, not a way to create access or ignore site restrictions.
- Verification:
  - Reviewed `docs/safety.md` lines 23-25 and 36-40.

### Task 3/122: Document unsupported behavior

- Status: complete.
- Evidence:
  - `docs/safety.md` has a `Public Site Unsupported Behaviors` section.
  - The section states that website playbooks must reject unsupported behaviors
    before they can be compiled or executed.
  - The section lists the behavior groups that Phase 0 audits individually:
    CAPTCHA/challenge bypass, bot-detection bypass, credential abuse, stealth
    automation, and unconfirmed externally visible actions.
- Verification:
  - Reviewed `docs/safety.md` lines 42-56.

### Task 4/122: Document CAPTCHA solving or bypass as unsupported

- Status: complete.
- Evidence:
  - `docs/safety.md` states that CAPTCHA solving, CAPTCHA bypass, and challenge
    workarounds are not supported.
  - The same unsupported-behavior section requires rejection before compile or
    execution, so CAPTCHA handling is framed as a stop condition rather than a
    recovery path.
- Verification:
  - Reviewed `docs/safety.md` lines 42-47.

### Task 5/122: Document bot-detection bypass as unsupported

- Status: complete.
- Evidence:
  - `docs/safety.md` states that bot-detection bypass, rate-limit evasion,
    fingerprint masking, and stealth automation techniques are not supported.
  - This keeps playbooks aligned with visible, authorized navigation rather than
    anti-abuse circumvention.
- Verification:
  - Reviewed `docs/safety.md` lines 42-49.

### Task 6/122: Document credential abuse as unsupported

- Status: complete.
- Evidence:
  - `docs/safety.md` states that credential abuse, credential harvesting,
    account takeover, password guessing, and automation against accounts without
    authorization are not supported.
  - This directly constrains public-site playbooks to authorized sessions.
- Verification:
  - Reviewed `docs/safety.md` lines 42-51.

### Task 7/122: Document stealth automation as unsupported

- Status: complete.
- Evidence:
  - `docs/safety.md` states that stealth automation is not supported.
  - It also states that runs must remain visible to the operator and must not
    disguise automation from the local user.
- Verification:
  - Reviewed `docs/safety.md` lines 42-53.

### Task 8/122: Document unconfirmed externally visible actions as unsupported

- Status: complete.
- Evidence:
  - `docs/safety.md` states that unconfirmed posting, messaging, purchasing,
    applying, deleting, or settings changes are not supported.
  - The same bullet states those steps must stop until the operator confirms the
    exact step.
- Verification:
  - Reviewed `docs/safety.md` lines 42-56.

### Task 9/122: Define shared sensitive website action categories

- Status: complete.
- Evidence:
  - `docs/safety.md` has a `Sensitive Website Action Categories` section.
  - The section states that website playbooks must mark sensitive steps with
    `requires_confirmation: true`.
  - The section ties shared categories to validation, CLI prompts, traces, and
    reports so the pipeline uses consistent safety language.
- Verification:
  - Reviewed `docs/safety.md` lines 58-79.

### Task 10/122: Define login as a sensitive category

- Status: complete.
- Evidence:
  - `docs/safety.md` defines `login` as entering credentials, opening an
    authentication flow, approving sign-in, or switching accounts.
- Verification:
  - Reviewed `docs/safety.md` lines 64-65.

### Task 11/122: Define post, publish, upload, or submit as sensitive

- Status: complete.
- Evidence:
  - `docs/safety.md` defines `publish` as posting, publishing, uploading,
    submitting, or otherwise making content externally visible.
- Verification:
  - Reviewed `docs/safety.md` lines 66-67.

### Task 12/122: Define engagement actions as sensitive

- Status: complete.
- Evidence:
  - `docs/safety.md` defines `engage` as liking, reacting, clapping,
    reposting, subscribing, following, friending, connecting, joining, or
    similar account-visible engagement.
- Verification:
  - Reviewed `docs/safety.md` lines 68-69.

### Task 13/122: Define comment or reply as sensitive

- Status: complete.
- Evidence:
  - `docs/safety.md` defines `comment` as commenting, replying, reviewing,
    annotating, or otherwise adding visible text to another surface.
- Verification:
  - Reviewed `docs/safety.md` lines 70-71.

### Task 14/122: Define message or send as sensitive

- Status: complete.
- Evidence:
  - `docs/safety.md` defines `message` as composing, sending, replying to,
    forwarding, or otherwise changing direct or private messages.
- Verification:
  - Reviewed `docs/safety.md` lines 72-73.

### Task 15/122: Define transaction and application actions as sensitive

- Status: complete.
- Evidence:
  - `docs/safety.md` defines `transaction` as applying, purchasing, accepting
    offers, marketplace actions, or payment-adjacent account changes.
- Verification:
  - Reviewed `docs/safety.md` lines 74-75.

### Task 16/122: Define deleting content as sensitive

- Status: complete.
- Evidence:
  - `docs/safety.md` defines `delete` as deleting, removing, hiding, archiving,
    or retracting user or account content.
- Verification:
  - Reviewed `docs/safety.md` lines 76-77.

### Task 17/122: Define account and settings changes as sensitive

- Status: complete.
- Evidence:
  - `docs/safety.md` defines `account_settings` as changing account, privacy,
    notification, security, billing, identity, or permission settings.
- Verification:
  - Reviewed `docs/safety.md` lines 78-79.

### Phase 0 Boundary Verification

- Status: passed.
- Commands:
  - `.venv/bin/pytest`: 268 passed, 4 skipped.
  - `.venv/bin/ruff check .`: passed.
  - `.venv/bin/mypy`: passed.
  - `.venv/bin/python -m build`: built source distribution and wheel.

## Phase 1 Audit: Playbook Schema

Phase 1 starts by inspecting the existing playbook schema module and then
verifying each model, loader, validation rule, and safety comment before
checking roadmap items.

### Task 18/122: Add `src/desktop_agent/site_playbooks.py`

- Status: complete.
- Evidence:
  - `src/desktop_agent/site_playbooks.py` exists.
  - The module contains website playbook contracts, YAML loading helpers,
    validation helpers, and the site-task compiler entrypoint.
- Verification:
  - Reviewed `src/desktop_agent/site_playbooks.py` module header and top-level
    contracts.

### Task 19/122: Add immutable data models

- Status: complete.
- Evidence:
  - `SiteDomain`, `SiteLandmark`, `SiteFlowStep`, `BlockedState`, `SiteFlow`,
    and `SitePlaybook` are all declared with `@dataclass(frozen=True)`.
  - Model fields use tuples for repeated child collections on aggregate models.
- Verification:
  - Reviewed `src/desktop_agent/site_playbooks.py` model declarations.

### Task 20/122: Add `SitePlaybook`

- Status: complete.
- Evidence:
  - `SitePlaybook` is an immutable dataclass.
  - It carries the site ID, version, domains, allowed window-title patterns,
    landmarks, flows, blocked states, and source path.
- Verification:
  - Reviewed `src/desktop_agent/site_playbooks.py` `SitePlaybook` declaration.

### Task 21/122: Add `SiteDomain`

- Status: complete.
- Evidence:
  - `SiteDomain` is an immutable dataclass.
  - It stores `host`, `include_subdomains`, and optional `purpose` so a
    playbook can describe recognized domains without embedding runtime logic.
- Verification:
  - Reviewed `src/desktop_agent/site_playbooks.py` `SiteDomain` declaration.

### Task 22/122: Add `SiteLandmark`

- Status: complete.
- Evidence:
  - `SiteLandmark` is an immutable dataclass.
  - It stores reusable navigation target data: ID, action, target, text, image,
    selector, and description.
- Verification:
  - Reviewed `src/desktop_agent/site_playbooks.py` `SiteLandmark` declaration.

### Task 23/122: Add `SiteFlow`

- Status: complete.
- Evidence:
  - `SiteFlow` is an immutable dataclass.
  - It stores flow ID, description, timeout, retry, confidence threshold,
    optional search region, and a tuple of `SiteFlowStep` items.
- Verification:
  - Reviewed `src/desktop_agent/site_playbooks.py` `SiteFlow` declaration.

### Task 24/122: Add `SiteFlowStep`

- Status: complete.
- Evidence:
  - `SiteFlowStep` is an immutable dataclass.
  - It stores step ID, action, optional landmark/target/text/image fields,
    confirmation requirement, sensitive category, timeout, and retry override.
- Verification:
  - Reviewed `src/desktop_agent/site_playbooks.py` `SiteFlowStep` declaration.

### Task 25/122: Add `BlockedState`

- Status: complete.
- Evidence:
  - `BlockedState` is an immutable dataclass.
  - It stores blocked-state ID, detector, user-facing reason, and optional
    recovery hint.
- Verification:
  - Reviewed `src/desktop_agent/site_playbooks.py` `BlockedState` declaration.

### Task 26/122: Add YAML loader for `navigation_playbooks/*.yaml`

- Status: complete.
- Evidence:
  - `load_site_playbook` reads YAML with `yaml.safe_load`, maps it into
    `SitePlaybook`, and validates before returning.
  - `load_site_playbooks` defaults to `navigation_playbooks`, loads sorted
    `*.yaml` files, and skips files prefixed with `_` such as the template.
  - CLI catalog commands use these loader functions.
- Verification:
  - Reviewed `src/desktop_agent/site_playbooks.py` loader functions and loader
    call sites in `src/desktop_agent/cli.py`.

### Task 27/122: Add schema validation

- Status: complete.
- Evidence:
  - `validate_site_playbook` aggregates validation errors for site identity,
    domains, allowed window titles, landmarks, flows, flow steps, sensitive
    steps, and blocked states.
  - Loader functions call validation before returning playbooks.
  - `tests/test_site_playbooks.py` contains validation regressions for the
    individual schema rules audited below.
- Verification:
  - Reviewed `src/desktop_agent/site_playbooks.py` validation entrypoint and
    `tests/test_site_playbooks.py`.

### Task 28/122: Validate site ID is required and slug-safe

- Status: complete.
- Evidence:
  - `validate_site_playbook` rejects any `site_id` that does not match the
    slug-safe pattern.
  - Regression tests cover blank and invalid site IDs.
- Verification:
  - Reviewed `src/desktop_agent/site_playbooks.py` site ID validation and
    `tests/test_site_playbooks.py` site ID tests.

### Task 29/122: Validate at least one domain is required

- Status: complete.
- Evidence:
  - `validate_site_playbook` rejects playbooks with no domains.
  - The same validation path rejects domain entries with blank hosts.
  - Regression tests cover empty domain lists.
- Verification:
  - Reviewed `src/desktop_agent/site_playbooks.py` domain validation and
    `tests/test_site_playbooks.py` domain validation test.

### Task 30/122: Validate at least one allowed window-title pattern is required

- Status: complete.
- Evidence:
  - `validate_site_playbook` rejects playbooks with no allowed window-title
    patterns.
  - The same validation path rejects blank title patterns.
  - Regression tests cover empty window-title lists.
- Verification:
  - Reviewed `src/desktop_agent/site_playbooks.py` window-title validation and
    `tests/test_site_playbooks.py` window-title validation test.

### Task 31/122: Validate flow IDs are unique

- Status: complete.
- Evidence:
  - `validate_site_playbook` applies `_validate_unique_ids` to every flow ID.
  - `_validate_unique_ids` reports duplicate flow IDs.
  - Regression tests cover duplicate flow IDs.
- Verification:
  - Reviewed `src/desktop_agent/site_playbooks.py` flow ID validation and
    `tests/test_site_playbooks.py` duplicate-flow test.

### Task 32/122: Validate step IDs are unique within each flow

- Status: complete.
- Evidence:
  - `_validate_flow` applies `_validate_unique_ids` to the IDs of steps in that
    specific flow.
  - Regression tests cover duplicate step IDs inside one flow.
- Verification:
  - Reviewed `src/desktop_agent/site_playbooks.py` flow-step ID validation and
    `tests/test_site_playbooks.py` duplicate-step test.

### Task 33/122: Validate sensitive steps require confirmation

- Status: complete.
- Evidence:
  - `_validate_flow` checks `sensitive_category` and rejects sensitive steps
    that do not set `requires_confirmation`.
  - The validation block has an inline safety comment explaining why this is
    enforced before compilation.
  - Regression tests cover sensitive steps without confirmation.
- Verification:
  - Reviewed `src/desktop_agent/site_playbooks.py` sensitive-step validation and
    `tests/test_site_playbooks.py` sensitive confirmation test.

### Task 34/122: Validate landmark references resolve

- Status: complete.
- Evidence:
  - `_validate_flow` checks each non-empty step landmark against the set of
    declared landmark IDs.
  - Regression tests cover missing landmark references.
- Verification:
  - Reviewed `src/desktop_agent/site_playbooks.py` landmark-reference
    validation and `tests/test_site_playbooks.py` missing-landmark test.

### Task 35/122: Validate unsupported actions fail before execution

- Status: complete.
- Evidence:
  - `_validate_landmarks` rejects landmark actions not in `SUPPORTED_ACTIONS`.
  - `_validate_flow` rejects flow-step actions not in `SUPPORTED_ACTIONS`.
  - Regression tests cover unknown actions.
- Verification:
  - Reviewed `src/desktop_agent/site_playbooks.py` action validation and
    `tests/test_site_playbooks.py` unknown-action test.

### Task 36/122: Validate blocked states include detector and reason

- Status: complete.
- Evidence:
  - `_validate_blocked_states` applies unique ID validation and rejects missing
    detectors or reasons.
  - Regression tests cover missing blocked-state reasons.
- Verification:
  - Reviewed `src/desktop_agent/site_playbooks.py` blocked-state validation and
    `tests/test_site_playbooks.py` blocked-state reason test.

### Task 37/122: Add comments only around non-obvious validation and safety decisions

- Status: complete.
- Evidence:
  - `src/desktop_agent/site_playbooks.py` contains one inline comment.
  - The comment explains why sensitive category validation must enforce
    confirmation before the compiler sees a step.
  - There are no broad narrative comments around self-explanatory field mapping.
- Verification:
  - Reviewed comment usage in `src/desktop_agent/site_playbooks.py`.

### Phase 1 Boundary Verification

- Status: passed.
- Commands:
  - `.venv/bin/pytest`: 268 passed, 4 skipped.
  - `.venv/bin/ruff check .`: passed.
  - `.venv/bin/mypy`: passed.
  - `.venv/bin/python -m build`: built source distribution and wheel.

## Phase 2 Audit: Catalog Layout And Seed Playbooks

Phase 2 starts by inspecting the catalog files and seed playbooks before
checking layout, domain, flow, and blocked-state coverage.

### Task 38/122: Add `navigation_playbooks/README.md`

- Status: complete.
- Evidence:
  - `navigation_playbooks/README.md` exists.
  - It explains that playbooks compile into the DeskPilot task DSL.
  - It documents the required playbook sections, deterministic CI expectation,
    domain scope, seed flow coverage, and blocked-state coverage.
- Verification:
  - Reviewed `navigation_playbooks/README.md` lines 1-42.

### Task 39/122: Add `navigation_playbooks/_template.yaml`

- Status: complete.
- Evidence:
  - `navigation_playbooks/_template.yaml` exists.
  - It is a copyable playbook scaffold with `site_id`, `version`, `domains`,
    `allowed_window_titles`, `landmarks`, `flows`, and `blocked_states`.
  - The catalog loader intentionally skips `_template.yaml` because files
    prefixed with `_` are templates, not runnable seed playbooks.
- Verification:
  - Reviewed `navigation_playbooks/_template.yaml` lines 1-29.

### Task 40/122: Add seed playbooks

- Status: complete.
- Evidence:
  - The catalog contains seed playbooks for Facebook, Instagram, LinkedIn,
    Medium, TikTok, X/Twitter, and YouTube.
  - `load_site_playbooks()` loads the seven seed playbooks and skips the
    `_template.yaml` scaffold.
  - `tests/test_site_playbooks.py` asserts the expected seed-site ID set.
- Verification:
  - Ran `load_site_playbooks()` and reviewed the seed catalog files.

### Task 41/122: Add `navigation_playbooks/linkedin.yaml`

- Status: complete.
- Evidence:
  - `navigation_playbooks/linkedin.yaml` exists.
  - It validates through `load_site_playbook`.
  - It defines the `linkedin` site ID, two domains, seven flows, and six blocked
    states.
- Verification:
  - Loaded `navigation_playbooks/linkedin.yaml` with `load_site_playbook`.

### Task 42/122: Add `navigation_playbooks/x-twitter.yaml`

- Status: complete.
- Evidence:
  - `navigation_playbooks/x-twitter.yaml` exists.
  - It validates through `load_site_playbook`.
  - It defines the `x-twitter` site ID, two domains, seven flows, and six
    blocked states.
- Verification:
  - Loaded `navigation_playbooks/x-twitter.yaml` with `load_site_playbook`.

### Task 43/122: Add `navigation_playbooks/instagram.yaml`

- Status: complete.
- Evidence:
  - `navigation_playbooks/instagram.yaml` exists.
  - It validates through `load_site_playbook`.
  - It defines the `instagram` site ID, two domains, seven flows, and six
    blocked states.
- Verification:
  - Loaded `navigation_playbooks/instagram.yaml` with `load_site_playbook`.

### Task 44/122: Add `navigation_playbooks/facebook.yaml`

- Status: complete.
- Evidence:
  - `navigation_playbooks/facebook.yaml` exists.
  - It validates through `load_site_playbook`.
  - It defines the `facebook` site ID, two domains, seven flows, and six
    blocked states.
- Verification:
  - Loaded `navigation_playbooks/facebook.yaml` with `load_site_playbook`.

### Task 45/122: Add `navigation_playbooks/medium.yaml`

- Status: complete.
- Evidence:
  - `navigation_playbooks/medium.yaml` exists.
  - It validates through `load_site_playbook`.
  - It defines the `medium` site ID, two domains, six flows, and six blocked
    states. The seed omits a message flow because Medium does not have a
    standard direct-message navigation surface in this catalog scope.
- Verification:
  - Loaded `navigation_playbooks/medium.yaml` with `load_site_playbook`.

### Task 46/122: Add `navigation_playbooks/youtube.yaml`

- Status: complete.
- Evidence:
  - `navigation_playbooks/youtube.yaml` exists.
  - It validates through `load_site_playbook`.
  - It defines the `youtube` site ID, three domains, six flows, and six blocked
    states. The seed includes the creator-studio domain for upload navigation
    recognition while stopping before any submit action.
- Verification:
  - Loaded `navigation_playbooks/youtube.yaml` with `load_site_playbook`.

### Task 47/122: Add `navigation_playbooks/tiktok.yaml`

- Status: complete.
- Evidence:
  - `navigation_playbooks/tiktok.yaml` exists.
  - It validates through `load_site_playbook`.
  - It defines the `tiktok` site ID, two domains, seven flows, and six blocked
    states. The seed includes an `open-messages` flow that navigates to the
    message surface without sending content.
- Verification:
  - Loaded `navigation_playbooks/tiktok.yaml` with `load_site_playbook`.

### Task 48/122: Define domains for each seed playbook

- Status: complete.
- Evidence:
  - Every seed playbook includes a non-empty `domains` list validated by the
    schema loader.
  - Domain entries are purpose-tagged so later compile, monitoring, deep-search,
    and report layers can distinguish primary, alternate, account, message, and
    creator surfaces without hard-coded site exceptions.
  - The audited catalog contains domain definitions for LinkedIn, X/Twitter,
    Instagram, Facebook, Medium, YouTube, and TikTok.
- Verification:
  - Loaded all seed playbooks and printed each domain host with its purpose.

### Task 49/122: Define primary domains

- Status: complete.
- Evidence:
  - Each seed playbook has a `purpose: primary` domain.
  - Primary domains are `linkedin.com`, `x.com`, `instagram.com`,
    `facebook.com`, `medium.com`, `youtube.com`, and `tiktok.com`.
  - The template also demonstrates the required primary-domain format for future
    site additions.
- Verification:
  - Loaded all seed playbooks and printed domains filtered to `purpose ==
    "primary"`.

### Task 50/122: Define common alternate domains when applicable

- Status: complete.
- Evidence:
  - Non-primary domains are present where the seed site has a common alternate
    surface needed for recognition.
  - Audited alternates include `linkedin.cn`, `twitter.com`, `mirror.xyz`,
    `tiktokv.com`, `youtu.be`, `studio.youtube.com`, `messenger.com`, and
    `accountscenter.instagram.com`.
  - Each alternate is purpose-tagged so downstream pipeline, monitoring, and
    report code can explain why the host is allowed.
- Verification:
  - Loaded all seed playbooks and printed domains where `purpose != "primary"`.

### Task 51/122: Define account or auth domains only when needed

- Status: complete.
- Evidence:
  - `instagram.yaml` includes `accountscenter.instagram.com` with
    `purpose: account-settings` because Instagram settings can hand off to the
    account center surface.
  - The other seed playbooks do not add account or auth-only domains because
    their current navigation flows are recognized through primary or documented
    alternate surfaces.
  - This keeps allowed-window scope narrow for later compile, monitoring, and
    report output.
- Verification:
  - Loaded all seed playbooks and filtered domains whose purpose contains
    `account` or `auth`.

### Task 52/122: Define navigation flows for each seed playbook

- Status: complete.
- Evidence:
  - Each seed playbook has a validated `flows` list.
  - The audited flow matrix covers home/feed, search, profile or channel,
    notifications, settings, and composer/upload/editor navigation where the
    site exposes those surfaces.
  - Message flows are present only for sites with a message surface in the
    current playbook scope.
- Verification:
  - Loaded all seed playbooks and printed each flow ID by site.

### Task 53/122: Define open home or feed flows

- Status: complete.
- Evidence:
  - Every seed playbook defines an `open-home` flow.
  - The flow descriptions map site-specific labels to the shared home/feed
    navigation intent, including LinkedIn feed, X timeline, Facebook feed,
    Instagram home feed, Medium home feed, YouTube home feed, and TikTok feed.
  - This gives pipeline, deep-search, monitoring, and report code one stable
    flow ID for basic entry-surface checks across sites.
- Verification:
  - Loaded all seed playbooks and confirmed each contains `open-home`.

### Task 54/122: Define open search flows

- Status: complete.
- Evidence:
  - Every seed playbook defines an `open-search` flow.
  - The search-flow descriptions explicitly stop at opening the search surface
    without submitting a query.
  - The shared `open-search` flow ID gives deterministic smoke, deep-search,
    monitoring, and report hooks a read-only path for each seed site.
- Verification:
  - Loaded all seed playbooks and confirmed each contains `open-search`.

### Task 55/122: Define open profile or channel flows

- Status: complete.
- Evidence:
  - LinkedIn, X/Twitter, Instagram, Facebook, Medium, and TikTok define
    `open-profile`.
  - YouTube defines `open-channel`, matching its channel terminology while
    preserving the same profile/channel navigation intent.
  - These flow IDs give reports and monitoring a stable way to describe the
    identity-surface navigation path without mixing it with account settings.
- Verification:
  - Loaded all seed playbooks and filtered flows to `open-profile` or
    `open-channel`.

### Task 56/122: Define open notifications flows

- Status: complete.
- Evidence:
  - Every seed playbook defines `open-notifications`.
  - TikTok maps the flow to its inbox/notification surface while retaining the
    shared flow ID for catalog-level checks.
  - This creates a consistent monitoring and report hook for notification
    navigation without sending, acknowledging, or modifying anything.
- Verification:
  - Loaded all seed playbooks and confirmed each contains `open-notifications`.

### Task 57/122: Define open messages flows when the site has messages

- Status: complete.
- Evidence:
  - LinkedIn, X/Twitter, Instagram, Facebook, and TikTok define
    `open-messages`.
  - Each message-flow description stops at opening the message surface without
    sending content.
  - Medium and YouTube intentionally omit `open-messages` because the seed scope
    does not include a standard direct-message navigation surface for those
    sites.
- Verification:
  - Loaded all seed playbooks and printed whether each contains
    `open-messages`.

### Task 58/122: Define open settings flows

- Status: complete.
- Evidence:
  - Every seed playbook defines `open-settings`.
  - LinkedIn uses a two-step profile-menu to settings path, and schema
    validation confirms both landmark references resolve.
  - Settings navigation is separated from any actual account, privacy,
    notification, security, or billing change.
- Verification:
  - Loaded all seed playbooks and confirmed each contains `open-settings`.

### Task 59/122: Define composer, upload, or editor flows without final submission

- Status: complete.
- Evidence:
  - LinkedIn, X/Twitter, Instagram, and Facebook define `open-composer`.
  - Medium defines `open-editor`.
  - YouTube and TikTok define `open-upload`.
  - Flow descriptions explicitly stop before publishing, posting, or submitting,
    preserving the public-site safety boundary for later runtime, monitoring,
    deep-search, and reporting work.
- Verification:
  - Loaded all seed playbooks and filtered flows to `open-composer`,
    `open-editor`, or `open-upload`.
