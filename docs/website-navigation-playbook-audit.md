# Website Navigation Playbook Implementation Audit

This file records evidence before roadmap tasks are checked. A checkbox in
`docs/website-navigation-playbook-roadmap.md` is considered complete only after
the related code, docs, tests, monitoring, or report behavior is inspected or
implemented and the evidence is recorded here.

Task numbering uses the 211 implementation checklist items that start at Phase
0. The OKR checkboxes above the phase roadmap are tracked separately as outcome
criteria.

## Phase 0 Audit: Scope And Safety Contract

Phase 0 starts from the existing safety documentation and validates each public
website safety claim before the corresponding roadmap item is checked.

### Task 1/211: Confirm public-site scope in `docs/safety.md`

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

### Task 2/211: Document third-party website authorization and rule compliance

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

### Task 3/211: Document unsupported behavior

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

### Task 4/211: Document CAPTCHA solving or bypass as unsupported

- Status: complete.
- Evidence:
  - `docs/safety.md` states that CAPTCHA solving, CAPTCHA bypass, and challenge
    workarounds are not supported.
  - The same unsupported-behavior section requires rejection before compile or
    execution, so CAPTCHA handling is framed as a stop condition rather than a
    recovery path.
- Verification:
  - Reviewed `docs/safety.md` lines 42-47.

### Task 5/211: Document bot-detection bypass as unsupported

- Status: complete.
- Evidence:
  - `docs/safety.md` states that bot-detection bypass, rate-limit evasion,
    fingerprint masking, and stealth automation techniques are not supported.
  - This keeps playbooks aligned with visible, authorized navigation rather than
    anti-abuse circumvention.
- Verification:
  - Reviewed `docs/safety.md` lines 42-49.

### Task 6/211: Document credential abuse as unsupported

- Status: complete.
- Evidence:
  - `docs/safety.md` states that credential abuse, credential harvesting,
    account takeover, password guessing, and automation against accounts without
    authorization are not supported.
  - This directly constrains public-site playbooks to authorized sessions.
- Verification:
  - Reviewed `docs/safety.md` lines 42-51.

### Task 7/211: Document stealth automation as unsupported

- Status: complete.
- Evidence:
  - `docs/safety.md` states that stealth automation is not supported.
  - It also states that runs must remain visible to the operator and must not
    disguise automation from the local user.
- Verification:
  - Reviewed `docs/safety.md` lines 42-53.

### Task 8/211: Document unconfirmed externally visible actions as unsupported

- Status: complete.
- Evidence:
  - `docs/safety.md` states that unconfirmed posting, messaging, purchasing,
    applying, deleting, or settings changes are not supported.
  - The same bullet states those steps must stop until the operator confirms the
    exact step.
- Verification:
  - Reviewed `docs/safety.md` lines 42-56.

### Task 9/211: Define shared sensitive website action categories

- Status: complete.
- Evidence:
  - `docs/safety.md` has a `Sensitive Website Action Categories` section.
  - The section states that website playbooks must mark sensitive steps with
    `requires_confirmation: true`.
  - The section ties shared categories to validation, CLI prompts, traces, and
    reports so the pipeline uses consistent safety language.
- Verification:
  - Reviewed `docs/safety.md` lines 58-79.

### Task 10/211: Define login as a sensitive category

- Status: complete.
- Evidence:
  - `docs/safety.md` defines `login` as entering credentials, opening an
    authentication flow, approving sign-in, or switching accounts.
- Verification:
  - Reviewed `docs/safety.md` lines 64-65.

### Task 11/211: Define post, publish, upload, or submit as sensitive

- Status: complete.
- Evidence:
  - `docs/safety.md` defines `publish` as posting, publishing, uploading,
    submitting, or otherwise making content externally visible.
- Verification:
  - Reviewed `docs/safety.md` lines 66-67.

### Task 12/211: Define engagement actions as sensitive

- Status: complete.
- Evidence:
  - `docs/safety.md` defines `engage` as liking, reacting, clapping,
    reposting, subscribing, following, friending, connecting, joining, or
    similar account-visible engagement.
- Verification:
  - Reviewed `docs/safety.md` lines 68-69.

### Task 13/211: Define comment or reply as sensitive

- Status: complete.
- Evidence:
  - `docs/safety.md` defines `comment` as commenting, replying, reviewing,
    annotating, or otherwise adding visible text to another surface.
- Verification:
  - Reviewed `docs/safety.md` lines 70-71.

### Task 14/211: Define message or send as sensitive

- Status: complete.
- Evidence:
  - `docs/safety.md` defines `message` as composing, sending, replying to,
    forwarding, or otherwise changing direct or private messages.
- Verification:
  - Reviewed `docs/safety.md` lines 72-73.

### Task 15/211: Define transaction and application actions as sensitive

- Status: complete.
- Evidence:
  - `docs/safety.md` defines `transaction` as applying, purchasing, accepting
    offers, marketplace actions, or payment-adjacent account changes.
- Verification:
  - Reviewed `docs/safety.md` lines 74-75.

### Task 16/211: Define deleting content as sensitive

- Status: complete.
- Evidence:
  - `docs/safety.md` defines `delete` as deleting, removing, hiding, archiving,
    or retracting user or account content.
- Verification:
  - Reviewed `docs/safety.md` lines 76-77.

### Task 17/211: Define account and settings changes as sensitive

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

### Task 18/211: Add `src/desktop_agent/site_playbooks.py`

- Status: complete.
- Evidence:
  - `src/desktop_agent/site_playbooks.py` exists.
  - The module contains website playbook contracts, YAML loading helpers,
    validation helpers, and the site-task compiler entrypoint.
- Verification:
  - Reviewed `src/desktop_agent/site_playbooks.py` module header and top-level
    contracts.

### Task 19/211: Add immutable data models

- Status: complete.
- Evidence:
  - `SiteDomain`, `SiteLandmark`, `SiteFlowStep`, `BlockedState`, `SiteFlow`,
    and `SitePlaybook` are all declared with `@dataclass(frozen=True)`.
  - Model fields use tuples for repeated child collections on aggregate models.
- Verification:
  - Reviewed `src/desktop_agent/site_playbooks.py` model declarations.

### Task 20/211: Add `SitePlaybook`

- Status: complete.
- Evidence:
  - `SitePlaybook` is an immutable dataclass.
  - It carries the site ID, version, domains, allowed window-title patterns,
    landmarks, flows, blocked states, and source path.
- Verification:
  - Reviewed `src/desktop_agent/site_playbooks.py` `SitePlaybook` declaration.

### Task 21/211: Add `SiteDomain`

- Status: complete.
- Evidence:
  - `SiteDomain` is an immutable dataclass.
  - It stores `host`, `include_subdomains`, and optional `purpose` so a
    playbook can describe recognized domains without embedding runtime logic.
- Verification:
  - Reviewed `src/desktop_agent/site_playbooks.py` `SiteDomain` declaration.

### Task 22/211: Add `SiteLandmark`

- Status: complete.
- Evidence:
  - `SiteLandmark` is an immutable dataclass.
  - It stores reusable navigation target data: ID, action, target, text, image,
    selector, and description.
- Verification:
  - Reviewed `src/desktop_agent/site_playbooks.py` `SiteLandmark` declaration.

### Task 23/211: Add `SiteFlow`

- Status: complete.
- Evidence:
  - `SiteFlow` is an immutable dataclass.
  - It stores flow ID, description, timeout, retry, confidence threshold,
    optional search region, and a tuple of `SiteFlowStep` items.
- Verification:
  - Reviewed `src/desktop_agent/site_playbooks.py` `SiteFlow` declaration.

### Task 24/211: Add `SiteFlowStep`

- Status: complete.
- Evidence:
  - `SiteFlowStep` is an immutable dataclass.
  - It stores step ID, action, optional landmark/target/text/image fields,
    confirmation requirement, sensitive category, timeout, and retry override.
- Verification:
  - Reviewed `src/desktop_agent/site_playbooks.py` `SiteFlowStep` declaration.

### Task 25/211: Add `BlockedState`

- Status: complete.
- Evidence:
  - `BlockedState` is an immutable dataclass.
  - It stores blocked-state ID, detector, user-facing reason, and optional
    recovery hint.
- Verification:
  - Reviewed `src/desktop_agent/site_playbooks.py` `BlockedState` declaration.

### Task 26/211: Add YAML loader for `navigation_playbooks/*.yaml`

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

### Task 27/211: Add schema validation

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

### Task 28/211: Validate site ID is required and slug-safe

- Status: complete.
- Evidence:
  - `validate_site_playbook` rejects any `site_id` that does not match the
    slug-safe pattern.
  - Regression tests cover blank and invalid site IDs.
- Verification:
  - Reviewed `src/desktop_agent/site_playbooks.py` site ID validation and
    `tests/test_site_playbooks.py` site ID tests.

### Task 29/211: Validate at least one domain is required

- Status: complete.
- Evidence:
  - `validate_site_playbook` rejects playbooks with no domains.
  - The same validation path rejects domain entries with blank hosts.
  - Regression tests cover empty domain lists.
- Verification:
  - Reviewed `src/desktop_agent/site_playbooks.py` domain validation and
    `tests/test_site_playbooks.py` domain validation test.

### Task 30/211: Validate at least one allowed window-title pattern is required

- Status: complete.
- Evidence:
  - `validate_site_playbook` rejects playbooks with no allowed window-title
    patterns.
  - The same validation path rejects blank title patterns.
  - Regression tests cover empty window-title lists.
- Verification:
  - Reviewed `src/desktop_agent/site_playbooks.py` window-title validation and
    `tests/test_site_playbooks.py` window-title validation test.

### Task 31/211: Validate flow IDs are unique

- Status: complete.
- Evidence:
  - `validate_site_playbook` applies `_validate_unique_ids` to every flow ID.
  - `_validate_unique_ids` reports duplicate flow IDs.
  - Regression tests cover duplicate flow IDs.
- Verification:
  - Reviewed `src/desktop_agent/site_playbooks.py` flow ID validation and
    `tests/test_site_playbooks.py` duplicate-flow test.

### Task 32/211: Validate step IDs are unique within each flow

- Status: complete.
- Evidence:
  - `_validate_flow` applies `_validate_unique_ids` to the IDs of steps in that
    specific flow.
  - Regression tests cover duplicate step IDs inside one flow.
- Verification:
  - Reviewed `src/desktop_agent/site_playbooks.py` flow-step ID validation and
    `tests/test_site_playbooks.py` duplicate-step test.

### Task 33/211: Validate sensitive steps require confirmation

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

### Task 34/211: Validate landmark references resolve

- Status: complete.
- Evidence:
  - `_validate_flow` checks each non-empty step landmark against the set of
    declared landmark IDs.
  - Regression tests cover missing landmark references.
- Verification:
  - Reviewed `src/desktop_agent/site_playbooks.py` landmark-reference
    validation and `tests/test_site_playbooks.py` missing-landmark test.

### Task 35/211: Validate unsupported actions fail before execution

- Status: complete.
- Evidence:
  - `_validate_landmarks` rejects landmark actions not in `SUPPORTED_ACTIONS`.
  - `_validate_flow` rejects flow-step actions not in `SUPPORTED_ACTIONS`.
  - Regression tests cover unknown actions.
- Verification:
  - Reviewed `src/desktop_agent/site_playbooks.py` action validation and
    `tests/test_site_playbooks.py` unknown-action test.

### Task 36/211: Validate blocked states include detector and reason

- Status: complete.
- Evidence:
  - `_validate_blocked_states` applies unique ID validation and rejects missing
    detectors or reasons.
  - Regression tests cover missing blocked-state reasons.
- Verification:
  - Reviewed `src/desktop_agent/site_playbooks.py` blocked-state validation and
    `tests/test_site_playbooks.py` blocked-state reason test.

### Task 37/211: Add comments only around non-obvious validation and safety decisions

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

### Task 38/211: Add `navigation_playbooks/README.md`

- Status: complete.
- Evidence:
  - `navigation_playbooks/README.md` exists.
  - It explains that playbooks compile into the DeskPilot task DSL.
  - It documents the required playbook sections, deterministic CI expectation,
    domain scope, seed flow coverage, and blocked-state coverage.
- Verification:
  - Reviewed `navigation_playbooks/README.md` lines 1-42.

### Task 39/211: Add `navigation_playbooks/_template.yaml`

- Status: complete.
- Evidence:
  - `navigation_playbooks/_template.yaml` exists.
  - It is a copyable playbook scaffold with `site_id`, `version`, `domains`,
    `allowed_window_titles`, `landmarks`, `flows`, and `blocked_states`.
  - The catalog loader intentionally skips `_template.yaml` because files
    prefixed with `_` are templates, not runnable seed playbooks.
- Verification:
  - Reviewed `navigation_playbooks/_template.yaml` lines 1-29.

### Task 40/211: Add seed playbooks

- Status: complete.
- Evidence:
  - The catalog contains seed playbooks for Facebook, Instagram, LinkedIn,
    Medium, TikTok, X/Twitter, and YouTube.
  - `load_site_playbooks()` loads the seven seed playbooks and skips the
    `_template.yaml` scaffold.
  - `tests/test_site_playbooks.py` asserts the expected seed-site ID set.
- Verification:
  - Ran `load_site_playbooks()` and reviewed the seed catalog files.

### Task 41/211: Add `navigation_playbooks/linkedin.yaml`

- Status: complete.
- Evidence:
  - `navigation_playbooks/linkedin.yaml` exists.
  - It validates through `load_site_playbook`.
  - It defines the `linkedin` site ID, two domains, seven flows, and six blocked
    states.
- Verification:
  - Loaded `navigation_playbooks/linkedin.yaml` with `load_site_playbook`.

### Task 42/211: Add `navigation_playbooks/x-twitter.yaml`

- Status: complete.
- Evidence:
  - `navigation_playbooks/x-twitter.yaml` exists.
  - It validates through `load_site_playbook`.
  - It defines the `x-twitter` site ID, two domains, seven flows, and six
    blocked states.
- Verification:
  - Loaded `navigation_playbooks/x-twitter.yaml` with `load_site_playbook`.

### Task 43/211: Add `navigation_playbooks/instagram.yaml`

- Status: complete.
- Evidence:
  - `navigation_playbooks/instagram.yaml` exists.
  - It validates through `load_site_playbook`.
  - It defines the `instagram` site ID, two domains, seven flows, and six
    blocked states.
- Verification:
  - Loaded `navigation_playbooks/instagram.yaml` with `load_site_playbook`.

### Task 44/211: Add `navigation_playbooks/facebook.yaml`

- Status: complete.
- Evidence:
  - `navigation_playbooks/facebook.yaml` exists.
  - It validates through `load_site_playbook`.
  - It defines the `facebook` site ID, two domains, seven flows, and six
    blocked states.
- Verification:
  - Loaded `navigation_playbooks/facebook.yaml` with `load_site_playbook`.

### Task 45/211: Add `navigation_playbooks/medium.yaml`

- Status: complete.
- Evidence:
  - `navigation_playbooks/medium.yaml` exists.
  - It validates through `load_site_playbook`.
  - It defines the `medium` site ID, two domains, six flows, and six blocked
    states. The seed omits a message flow because Medium does not have a
    standard direct-message navigation surface in this catalog scope.
- Verification:
  - Loaded `navigation_playbooks/medium.yaml` with `load_site_playbook`.

### Task 46/211: Add `navigation_playbooks/youtube.yaml`

- Status: complete.
- Evidence:
  - `navigation_playbooks/youtube.yaml` exists.
  - It validates through `load_site_playbook`.
  - It defines the `youtube` site ID, three domains, six flows, and six blocked
    states. The seed includes the creator-studio domain for upload navigation
    recognition while stopping before any submit action.
- Verification:
  - Loaded `navigation_playbooks/youtube.yaml` with `load_site_playbook`.

### Task 47/211: Add `navigation_playbooks/tiktok.yaml`

- Status: complete.
- Evidence:
  - `navigation_playbooks/tiktok.yaml` exists.
  - It validates through `load_site_playbook`.
  - It defines the `tiktok` site ID, two domains, seven flows, and six blocked
    states. The seed includes an `open-messages` flow that navigates to the
    message surface without sending content.
- Verification:
  - Loaded `navigation_playbooks/tiktok.yaml` with `load_site_playbook`.

### Task 48/211: Define domains for each seed playbook

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

### Task 49/211: Define primary domains

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

### Task 50/211: Define common alternate domains when applicable

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

### Task 51/211: Define account or auth domains only when needed

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

### Task 52/211: Define navigation flows for each seed playbook

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

### Task 53/211: Define open home or feed flows

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

### Task 54/211: Define open search flows

- Status: complete.
- Evidence:
  - Every seed playbook defines an `open-search` flow.
  - The search-flow descriptions explicitly stop at opening the search surface
    without submitting a query.
  - The shared `open-search` flow ID gives deterministic smoke, deep-search,
    monitoring, and report hooks a read-only path for each seed site.
- Verification:
  - Loaded all seed playbooks and confirmed each contains `open-search`.

### Task 55/211: Define open profile or channel flows

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

### Task 56/211: Define open notifications flows

- Status: complete.
- Evidence:
  - Every seed playbook defines `open-notifications`.
  - TikTok maps the flow to its inbox/notification surface while retaining the
    shared flow ID for catalog-level checks.
  - This creates a consistent monitoring and report hook for notification
    navigation without sending, acknowledging, or modifying anything.
- Verification:
  - Loaded all seed playbooks and confirmed each contains `open-notifications`.

### Task 57/211: Define open messages flows when the site has messages

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

### Task 58/211: Define open settings flows

- Status: complete.
- Evidence:
  - Every seed playbook defines `open-settings`.
  - LinkedIn uses a two-step profile-menu to settings path, and schema
    validation confirms both landmark references resolve.
  - Settings navigation is separated from any actual account, privacy,
    notification, security, or billing change.
- Verification:
  - Loaded all seed playbooks and confirmed each contains `open-settings`.

### Task 59/211: Define composer, upload, or editor flows without final submission

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

### Task 60/211: Define blocked states for each seed playbook

- Status: complete.
- Evidence:
  - Every seed playbook has a validated `blocked_states` list.
  - The audited matrix includes `logged-out`, `consent`, `captcha`,
    `permission`, `unsupported-layout`, and `ambiguous-target` for each seed.
  - Each blocked state has both a detector and a user-facing reason, giving
    future runtime, monitoring, deep-search, and report layers enough context to
    stop and explain the condition.
- Verification:
  - Loaded all seed playbooks and printed each blocked-state ID by site.

### Task 61/211: Define logged-out blocked states

- Status: complete.
- Evidence:
  - Every seed playbook defines `logged-out`.
  - Detectors use site-specific visible text such as `Sign in` or `Log in`.
  - Reasons direct the operator to authenticate manually instead of automating
    credentials.
- Verification:
  - Loaded all seed playbooks and printed the `logged-out` detector and reason
    for each site.

### Task 62/211: Define consent or cookie interstitial blocked states

- Status: complete.
- Evidence:
  - Every seed playbook defines `consent`.
  - Detectors use site-specific consent text such as `Accept cookies`,
    `Allow all cookies`, `Accept`, `Accept all`, `cookie`, or `I agree`.
  - Reasons require manual resolution of the cookie or consent dialog.
- Verification:
  - Loaded all seed playbooks and printed the `consent` detector and reason for
    each site.

### Task 63/211: Define CAPTCHA or suspicious-activity blocked states

- Status: complete.
- Evidence:
  - Every seed playbook defines `captcha`.
  - Detectors cover site-specific challenge language such as security
    verification, suspicious activity, challenge, verification, security check,
    and unusual traffic.
  - Every reason states that CAPTCHA or suspicious-activity challenges are not
    automated.
- Verification:
  - Loaded all seed playbooks and printed the `captcha` detector and reason for
    each site.

### Task 64/211: Define permission or account-restriction blocked states

- Status: complete.
- Evidence:
  - Every seed playbook defines `permission`.
  - Detectors cover account-restriction language such as restricted, account
    suspended, access denied, temporarily blocked, try again later, account
    restricted, and action-not-allowed text.
  - Reasons require manual resolution of account or permission restrictions.
- Verification:
  - Loaded all seed playbooks and printed the `permission` detector and reason
    for each site.

### Task 65/211: Define unsupported-layout blocked states

- Status: complete.
- Evidence:
  - Every seed playbook defines `unsupported-layout`.
  - Detectors cover unsupported browser/layout text or a site-level failure
    surface such as X/Twitter's `Something went wrong`.
  - Reasons explain that the current layout does not match the playbook,
    allowing runtime, monitoring, and report layers to fail closed on redesigns.
- Verification:
  - Loaded all seed playbooks and printed the `unsupported-layout` detector and
    reason for each site.

### Task 66/211: Define ambiguous-target blocked states

- Status: complete.
- Evidence:
  - Every seed playbook defines `ambiguous-target`.
  - Detectors use `candidate_count:>1` to catch cases where a selector or
    visible-text target resolves to multiple choices.
  - Reasons require a narrower flow or manual choice, preventing the runtime
    from guessing when monitoring or reports need deterministic trace evidence.
- Verification:
  - Loaded all seed playbooks and printed the `ambiguous-target` detector and
    reason for each site.

## Phase 2 Boundary Verification

- Status: passed.
- Verification:
  - `.venv/bin/pytest`: 268 passed, 4 skipped.
  - `.venv/bin/ruff check .`: all checks passed.
  - `.venv/bin/mypy`: no issues in 67 source files.
  - `.venv/bin/python -m build`: built source distribution and wheel.

## Phase 3 Pre-Implementation Audit

- Status: ready to verify task-by-task.
- Scope:
  - Phase 3 covers compiling validated site playbooks into the existing
    `TaskDefinition` and `TaskStep` DSL used by runtime pipelines, safety gates,
    tracing, monitoring, and reports.
- Findings:
  - `src/desktop_agent/site_playbooks.py` already contains a `SiteTaskCompiler`
    implementation.
  - `tests/test_site_playbooks.py` already contains compiler-focused regression
    tests for task creation, allowed windows, defaults, confirmations, blocked
    checks, and seed-flow validation.
  - Phase 3 roadmap items are still unchecked, so each item will be verified,
    tested, documented here, checked in the roadmap, and committed separately.

### Task 67/211: Add `SiteTaskCompiler`

- Status: complete.
- Evidence:
  - `SiteTaskCompiler` is implemented in `src/desktop_agent/site_playbooks.py`.
  - The compiler validates a `SitePlaybook`, resolves the requested flow, and
    returns a `TaskDefinition` named as `<site_id>:<flow_id>`.
  - This keeps site navigation integrated with the existing task pipeline rather
    than introducing a parallel runtime.
- Verification:
  - Imported `SiteTaskCompiler`, compiled `linkedin:open-search`, and confirmed
    the result is a `TaskDefinition`.

### Task 68/211: Compile domains and window-title patterns into `allowed_windows`

- Status: complete.
- Evidence:
  - `SiteTaskCompiler.compile()` sets `TaskDefinition.allowed_windows` from
    `_compiled_allowed_windows(playbook)`.
  - `_compiled_allowed_windows()` combines `allowed_window_titles` and domain
    hosts while preserving order and de-duplicating entries.
  - Compiled seed tasks include titles and domains such as `YouTube`,
    `YouTube Studio`, `youtube.com`, `youtu.be`, and `studio.youtube.com`.
- Verification:
  - Compiled one flow for every seed playbook and printed each task's
    `allowed_windows`.

### Task 69/211: Compile playbook steps into existing task actions

- Status: complete.
- Evidence:
  - `SiteTaskCompiler` compiles site steps into `TaskStep` objects using the
    same action names as the existing task DSL.
  - Added `SiteFlowStep.on_failure` parsing and compiler handoff so
    `branch_if_visible` can produce a valid DSL step with a fallback target.
  - Added a regression matrix that compiles and validates the roadmap action
    set through `BasicTaskValidator`.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbooks.py`: 33 passed.
  - `.venv/bin/ruff check src/desktop_agent/site_playbooks.py
    tests/test_site_playbooks.py`: all checks passed.
  - `.venv/bin/mypy src/desktop_agent/site_playbooks.py
    tests/test_site_playbooks.py`: no issues found.

### Task 70/211: Compile `click_text`

- Status: complete.
- Evidence:
  - The action regression matrix includes a `click_text` site step with a
    `target` value.
  - `SiteTaskCompiler` preserves the action and target in the compiled
    `TaskStep`, and `BasicTaskValidator` accepts the result.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbooks.py -k "supported_task_actions
    and click_text"`: 1 passed, 32 deselected.

### Task 71/211: Compile `click_image`

- Status: complete.
- Evidence:
  - The action regression matrix includes a `click_image` site step with an
    image path.
  - `SiteTaskCompiler` converts the image value into the compiled `TaskStep`
    image field, and `BasicTaskValidator` accepts the result.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbooks.py -k "supported_task_actions
    and click_image"`: 1 passed, 32 deselected.

### Task 72/211: Compile `click_uia`

- Status: complete.
- Evidence:
  - The action regression matrix includes a `click_uia` site step with a UIA
    target.
  - `SiteTaskCompiler` preserves the `click_uia` action and target in the
    compiled `TaskStep`, and `BasicTaskValidator` accepts the result.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbooks.py -k "supported_task_actions
    and click_uia"`: 1 passed, 32 deselected.

### Task 73/211: Compile `type_text`

- Status: complete.
- Evidence:
  - The action regression matrix includes a `type_text` site step with text.
  - `SiteTaskCompiler` preserves the text payload in the compiled `TaskStep`,
    and `BasicTaskValidator` accepts the result.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbooks.py -k "supported_task_actions
    and type_text"`: 1 passed, 32 deselected.

### Task 74/211: Compile `press_key`

- Status: complete.
- Evidence:
  - The action regression matrix includes a `press_key` site step with key text.
  - `SiteTaskCompiler` preserves the key text in the compiled `TaskStep`, and
    `BasicTaskValidator` accepts the result.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbooks.py -k "supported_task_actions
    and press_key"`: 1 passed, 32 deselected.

### Task 75/211: Compile `scroll`

- Status: complete.
- Evidence:
  - The action regression matrix includes a `scroll` site step.
  - `SiteTaskCompiler` preserves the `scroll` action in the compiled `TaskStep`,
    and `BasicTaskValidator` accepts the result.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbooks.py -k "supported_task_actions
    and scroll and not scroll_until"`: 1 passed, 32 deselected.

### Task 76/211: Compile `scroll_until`

- Status: complete.
- Evidence:
  - The action regression matrix includes a `scroll_until` site step.
  - The playbook flow supplies a `search_region`, which `SiteTaskCompiler`
    carries into the compiled `TaskStep.region`.
  - `BasicTaskValidator` accepts the compiled result.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbooks.py -k "supported_task_actions
    and scroll_until"`: 1 passed, 32 deselected.

### Task 77/211: Compile `wait_for`

- Status: complete.
- Evidence:
  - The action regression matrix includes a `wait_for` site step with a target.
  - `SiteTaskCompiler` preserves the target in the compiled `TaskStep`, and
    `BasicTaskValidator` accepts the result.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbooks.py -k "supported_task_actions
    and wait_for and not branch_if_visible"`: 1 passed, 32 deselected.

### Task 78/211: Compile `assert_visible`

- Status: complete.
- Evidence:
  - The action regression matrix includes an `assert_visible` site step with a
    target.
  - `SiteTaskCompiler` preserves the target in the compiled `TaskStep`, and
    `BasicTaskValidator` accepts the result.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbooks.py -k "supported_task_actions
    and assert_visible"`: 1 passed, 32 deselected.

### Task 79/211: Compile `branch_if_visible`

- Status: complete.
- Evidence:
  - The action regression matrix includes a `branch_if_visible` site step with a
    target and `on_failure` fallback.
  - `SiteTaskCompiler` preserves the target and fallback in the compiled
    `TaskStep`, and `BasicTaskValidator` accepts the result.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbooks.py -k "supported_task_actions
    and branch_if_visible"`: 1 passed, 32 deselected.

### Task 80/211: Preserve confirmation requirements for sensitive steps

- Status: complete.
- Evidence:
  - `SiteTaskCompiler` copies `SiteFlowStep.requires_confirmation` into the
    compiled `TaskStep`.
  - Compiled step metadata also records `site_requires_confirmation` for trace,
    monitoring, and report consumers.
  - Regression coverage asserts a sensitive publish step remains confirmed and
    categorized as a submission after compilation.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbooks.py -k
    "sensitive_steps_preserve_confirmation"`: 1 passed, 32 deselected.

### Task 81/211: Add flow-level defaults

- Status: complete.
- Evidence:
  - `SiteTaskCompiler` maps flow-level timeout to `TaskDefinition.timeout_seconds`.
  - It maps flow-level retry to compiled steps that do not override retry.
  - It maps flow-level confidence threshold into `TaskDefinition.config_overrides`.
  - It maps flow-level search region into compiled `TaskStep.region`.
- Verification:
  - Constructed an in-memory playbook with all four defaults and compiled it.
    The compiled task printed timeout `42`, retry `5`, confidence `0.77`, and
    search-region width `300`.

### Task 82/211: Compile flow timeout defaults

- Status: complete.
- Evidence:
  - `SiteTaskCompiler` assigns `flow.timeout_seconds` to
    `TaskDefinition.timeout_seconds`, with a safe default when omitted.
  - Regression coverage mutates a flow timeout to `45` and asserts the compiled
    task timeout is `45`.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbooks.py -k
    "flow_timeout_compiles_to_task_timeout"`: 1 passed, 32 deselected.

### Task 83/211: Compile flow retry budget defaults

- Status: complete.
- Evidence:
  - `SiteTaskCompiler` assigns `flow.retry` to compiled steps that do not set an
    explicit step retry.
  - Regression coverage mutates a flow retry budget to `3` and asserts the
    compiled step retry is `3`.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbooks.py -k
    "flow_retry_defaults_compile_to_steps"`: 1 passed, 32 deselected.

### Task 84/211: Compile flow confidence threshold defaults

- Status: complete.
- Evidence:
  - `SiteTaskCompiler` assigns `flow.confidence_threshold` to
    `TaskDefinition.config_overrides.confidence_threshold`.
  - Added dedicated regression coverage that compiles a flow with confidence
    threshold `0.84` and asserts the compiled config override preserves it.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbooks.py -k
    "flow_confidence_threshold_compiles_to_config_override"`: 1 passed,
    33 deselected.
  - `.venv/bin/ruff check tests/test_site_playbooks.py`: all checks passed.
  - `.venv/bin/mypy tests/test_site_playbooks.py`: no issues found.

### Task 85/211: Compile optional search region defaults

- Status: complete.
- Evidence:
  - `SiteTaskCompiler` assigns `flow.search_region` to compiled step `region`.
  - The `scroll_until` action regression supplies a flow-level search region
    and asserts the compiled step preserves the region width.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbooks.py -k "supported_task_actions
    and scroll_until"`: 1 passed, 33 deselected.

### Task 86/211: Add blocked-state checks before irreversible actions

- Status: complete.
- Evidence:
  - `SiteTaskCompiler.compile()` calls `_blocked_state_checks()` before appending
    each compiled step.
  - `_blocked_state_checks()` returns checks only for confirmed sensitive steps,
    so read-only navigation remains simple while irreversible actions fail
    closed.
  - Regression coverage asserts the first compiled step before `publish-post` is
    `blocked-state-logged-out-before-publish-post`.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbooks.py -k
    "blocked_state_checks_compile_before_sensitive_final_actions"`: 1 passed,
    33 deselected.

### Task 87/211: Add task metadata for trace readability

- Status: complete.
- Evidence:
  - Compiled tasks include `site_id`, `site_flow_id`, `site_playbook_version`,
    `site_domains`, `site_sensitive_step_ids`, `site_blocked_state_ids`,
    validation status, compilation source, compiled step count, and summary.
  - Compiled steps also include site and flow metadata, so downstream traces,
    monitoring, deep-search output, and reports can identify the playbook
    context at both task and action levels.
- Verification:
  - Compiled `linkedin:open-search` and printed the resulting task metadata.

### Task 88/211: Add site ID metadata

- Status: complete.
- Evidence:
  - Compiled task metadata includes `site_id`.
  - Compiled step metadata also includes `site_id`.
  - Tracing/report coverage verifies site ID is present in final report
    metadata for site-playbook runs.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_tracing.py -k
    "final_report_includes_site_id_and_flow_id"`: 1 passed, 4 deselected.

### Task 89/211: Add flow ID metadata

- Status: complete.
- Evidence:
  - Compiled task metadata includes `site_flow_id`.
  - Compiled step metadata also includes `site_flow_id`.
  - Tracing/report coverage verifies flow ID is present in final report metadata
    for site-playbook runs.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_tracing.py -k
    "final_report_includes_site_id_and_flow_id"`: 1 passed, 4 deselected.

### Task 90/211: Add domain metadata

- Status: complete.
- Evidence:
  - Compiled task metadata includes `site_domains`, populated from the validated
    playbook domain hosts.
  - Added dedicated regression coverage that compiles a playbook with
    `example.com` and asserts `site_domains == ["example.com"]`.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbooks.py -k
    "compiled_task_metadata_includes_site_domains"`: 1 passed, 34 deselected.
  - `.venv/bin/ruff check tests/test_site_playbooks.py`: all checks passed.
  - `.venv/bin/mypy tests/test_site_playbooks.py`: no issues found.

### Task 91/211: Add sensitive step ID metadata

- Status: complete.
- Evidence:
  - Compiled task metadata includes `site_sensitive_step_ids`, derived from
    compiled steps where `requires_confirmation` is true.
  - Added dedicated regression coverage that compiles a sensitive publish flow
    and asserts the metadata contains `publish-post`.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbooks.py -k
    "compiled_task_metadata_includes_sensitive_step_ids"`: 1 passed,
    35 deselected.
  - `.venv/bin/ruff check tests/test_site_playbooks.py`: all checks passed.
  - `.venv/bin/mypy tests/test_site_playbooks.py`: no issues found.

### Task 92/211: Add playbook version metadata

- Status: complete.
- Evidence:
  - Compiled task metadata includes `site_playbook_version`.
  - Compiled step metadata also includes `site_playbook_version`.
  - Tracing coverage verifies selected playbook version is included in site-run
    action metadata.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_tracing.py -k
    "action_log_includes_selected_playbook_version"`: 1 passed, 4 deselected.

## Phase 3 Boundary Verification

- Status: passed.
- Verification:
  - `.venv/bin/pytest`: 281 passed, 4 skipped.
  - `.venv/bin/ruff check .`: all checks passed.
  - `.venv/bin/mypy`: no issues in 67 source files.
  - `.venv/bin/python -m build`: built source distribution and wheel.

## Phase 4 Pre-Implementation Audit

- Status: ready to verify task-by-task.
- Scope:
  - Phase 4 covers `desktop-agent` site-playbook commands, runtime safety flag
    passthrough, and user-facing failure messages.
- Findings:
  - `src/desktop_agent/cli.py` defines `list-sites`, `list-flows`,
    `compile-site`, `run-site`, and `dry-run-site`.
  - Site-run commands share existing runtime options through `_add_runtime_options`.
  - `tests/test_site_playbook_cli.py` already covers seed listing, flow listing,
    task compilation, dry-run, unavailable actuation, missing confirmation, and
    invalid playbook handling.
  - Unknown-site, unknown-flow, blocked-state, and unsupported-live-state
    messages will be verified before their roadmap items are checked.

### Task 93/211: Add `desktop-agent list-sites`

- Status: complete.
- Evidence:
  - The CLI parser registers `list-sites`.
  - `_list_sites()` loads the playbook catalog and prints each site ID.
  - Regression coverage asserts all seven seed site IDs are printed.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_cli.py -k
    "list_sites_prints_all_seed_sites"`: 1 passed, 6 deselected.

### Task 94/211: Add `desktop-agent list-flows <site>`

- Status: complete.
- Evidence:
  - The CLI parser registers `list-flows` with a required site argument.
  - `_list_flows()` loads the named site and prints flow IDs with descriptions.
  - Regression coverage asserts LinkedIn flow output includes `open-search` and
    its description.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_cli.py -k
    "list_flows_linkedin_prints_flows"`: 1 passed, 6 deselected.

### Task 95/211: Add `desktop-agent compile-site <site> <flow> --output <task.yaml>`

- Status: complete.
- Evidence:
  - The CLI parser registers `compile-site` with site, flow, and required
    `--output`.
  - `_compile_site()` compiles the named playbook flow, records the output path
    in metadata, writes task YAML, and prints the compiled site/flow.
  - Regression coverage loads the generated YAML and validates it with
    `BasicTaskValidator`.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_cli.py -k
    "compile_site_writes_valid_task_yaml"`: 1 passed, 6 deselected.

### Task 96/211: Add `desktop-agent run-site <site> <flow>`

- Status: complete.
- Evidence:
  - The CLI parser registers `run-site` with site and flow arguments.
  - `_run_site_task()` compiles the site flow and routes it through the existing
    task runtime with `site_run=True`.
  - Regression coverage confirms `run-site` returns nonzero with a clear message
    when platform actuation is unavailable.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_cli.py -k
    "run_site_returns_nonzero_when_platform_actuation_is_unavailable"`:
    1 passed, 6 deselected.

### Task 97/211: Add `desktop-agent dry-run-site <site> <flow>`

- Status: complete.
- Evidence:
  - The CLI parser registers `dry-run-site` with site and flow arguments.
  - `_run_site_task(..., dry_run=True)` compiles the site flow and routes it
    through existing dry-run validation without desktop input.
  - Regression coverage validates `medium open-editor` with config and
    `--no-screenshots` and asserts a passed status.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_cli.py -k
    "dry_run_site_validates_without_desktop_input"`: 1 passed, 6 deselected.

### Task 98/211: Support existing runtime safety flags

- Status: complete.
- Evidence:
  - `run-site` and `dry-run-site` share `_add_runtime_options()`.
  - Runtime options include `--config`, `--verbose`, `--no-screenshots`,
    `--max-runtime-seconds`, `--confidence-threshold`, `--allowed-window`,
    and `--confirm-step`.
  - Added regression coverage that runs `dry-run-site` with all listed runtime
    flags and confirms the command passes with verbose output.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_cli.py -k
    "dry_run_site_accepts_runtime_safety_flags"`: 1 passed, 7 deselected.
  - `.venv/bin/ruff check tests/test_site_playbook_cli.py`: all checks passed.
  - `.venv/bin/mypy tests/test_site_playbook_cli.py`: no issues found.

### Task 99/211: Support `--config`

- Status: complete.
- Evidence:
  - `--config` is registered through `_add_runtime_options()`.
  - `_run_loaded_task()` loads the provided config path through
    `YamlConfigLoader`.
  - The runtime-flag regression passes a config file to `dry-run-site`.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_cli.py -k
    "dry_run_site_accepts_runtime_safety_flags"`: 1 passed, 7 deselected.

### Task 100/211: Support `--verbose`

- Status: complete.
- Evidence:
  - `--verbose` is registered through `_add_runtime_options()`.
  - `_print_report()` emits event details when verbose mode is enabled.
  - The runtime-flag regression passes `--verbose` and asserts event output is
    present.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_cli.py -k
    "dry_run_site_accepts_runtime_safety_flags"`: 1 passed, 7 deselected.

### Task 101/211: Support `--no-screenshots`

- Status: complete.
- Evidence:
  - `--no-screenshots` is registered through `_add_runtime_options()`.
  - `_cli_overrides_from_args()` maps it to `save_screenshots=False`.
  - The runtime-flag regression passes `--no-screenshots` to `dry-run-site`.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_cli.py -k
    "dry_run_site_accepts_runtime_safety_flags"`: 1 passed, 7 deselected.

### Task 102/211: Support `--max-runtime-seconds`

- Status: complete.
- Evidence:
  - `--max-runtime-seconds` is registered through `_add_runtime_options()`.
  - `_cli_overrides_from_args()` maps it to `max_runtime_seconds`.
  - The runtime-flag regression passes `--max-runtime-seconds 5`.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_cli.py -k
    "dry_run_site_accepts_runtime_safety_flags"`: 1 passed, 7 deselected.

### Task 103/211: Support `--confidence-threshold`

- Status: complete.
- Evidence:
  - `--confidence-threshold` is registered through `_add_runtime_options()`.
  - `_cli_overrides_from_args()` maps it to `confidence_threshold`.
  - The runtime-flag regression passes `--confidence-threshold 0.75`.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_cli.py -k
    "dry_run_site_accepts_runtime_safety_flags"`: 1 passed, 7 deselected.

### Task 104/211: Support `--allowed-window`

- Status: complete.
- Evidence:
  - `--allowed-window` is registered through `_add_runtime_options()` and may be
    provided more than once.
  - `_cli_overrides_from_args()` maps it to `allowed_windows`.
  - The runtime-flag regression passes `--allowed-window Medium`.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_cli.py -k
    "dry_run_site_accepts_runtime_safety_flags"`: 1 passed, 7 deselected.

### Task 105/211: Support `--confirm-step`

- Status: complete.
- Evidence:
  - `--confirm-step` is registered through `_add_runtime_options()` and may be
    provided more than once.
  - `_cli_overrides_from_args()` maps it to `confirmed_steps`.
  - Added regression coverage that dry-runs a sensitive site flow successfully
    only when `--confirm-step publish-post` is supplied.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_cli.py -k
    "confirm_step_allows_sensitive_site_dry_run"`: 1 passed, 8 deselected.
  - `.venv/bin/ruff check tests/test_site_playbook_cli.py`: all checks passed.
  - `.venv/bin/mypy tests/test_site_playbook_cli.py`: no issues found.

### Task 106/211: Ensure CLI failures explain

- Status: complete.
- Evidence:
  - Added CLI regressions for unknown site and unknown flow messages.
  - Existing CLI coverage verifies invalid playbook, missing confirmation, and
    unavailable platform actuation messages.
  - Existing site safety coverage verifies blocked-state abort messages.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_cli.py
    tests/test_site_playbook_safety.py`: 19 passed.
  - `.venv/bin/ruff check tests/test_site_playbook_cli.py
    tests/test_site_playbook_safety.py`: all checks passed.
  - `.venv/bin/mypy tests/test_site_playbook_cli.py
    tests/test_site_playbook_safety.py`: no issues found.

### Task 107/211: Explain unknown site failures

- Status: complete.
- Evidence:
  - `_load_named_site()` raises `SitePlaybookValidationError` with
    `unknown site: <site>` when the requested site is absent.
  - CLI error handling prints the message and returns status `2`.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_cli.py -k
    "unknown_site_returns_clear_message"`: 1 passed, 10 deselected.

### Task 108/211: Explain unknown flow failures

- Status: complete.
- Evidence:
  - `resolve_site_flow()` raises `SitePlaybookValidationError` with
    `unknown flow: <flow>` when a requested flow is absent.
  - CLI error handling prints the message and returns status `2`.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_cli.py -k
    "unknown_flow_returns_clear_message"`: 1 passed, 10 deselected.

### Task 109/211: Explain invalid playbook failures

- Status: complete.
- Evidence:
  - CLI error handling catches `SitePlaybookValidationError` raised by catalog
    loading.
  - Regression coverage writes an invalid playbook and asserts the slug-safe
    validation message is printed with nonzero status.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_cli.py -k
    "invalid_playbook_returns_validation_error"`: 1 passed, 10 deselected.

### Task 110/211: Explain missing confirmation failures

- Status: complete.
- Evidence:
  - Site flows preserve confirmation requirements through compilation.
  - Runtime safety rejects unconfirmed sensitive steps with a clear
    `requires explicit confirmation` message.
  - CLI regression coverage asserts the message is printed for an unconfirmed
    sensitive site dry-run.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_cli.py -k
    "missing_confirmation_returns_clear_message"`: 1 passed, 10 deselected.

### Task 111/211: Explain blocked-state detected failures

- Status: complete.
- Evidence:
  - Blocked-state checks compile before confirmed sensitive steps.
  - The runtime abort reason includes `blocked state detected` and the
    playbook-authored blocked-state reason.
  - Safety regression coverage verifies CAPTCHA/challenge states fail with a
    no-bypass message.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_safety.py -k
    "captcha_state_aborts_with_no_bypass_message"`: 1 passed, 7 deselected.

### Task 112/211: Explain unsupported live-site state failures

- Status: complete.
- Evidence:
  - `run-site` uses the live platform actuator path when not in dry-run mode.
  - When platform actuation is unavailable, the CLI returns nonzero and prints a
    clear `desktop actuation is unavailable on this platform` message.
  - This gives unsupported live execution states an explicit failure instead of
    silently falling back to dry-run behavior.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_cli.py -k
    "run_site_returns_nonzero_when_platform_actuation_is_unavailable"`:
    1 passed, 10 deselected.

## Phase 4 Boundary Verification

- Status: passed.
- Verification:
  - `.venv/bin/pytest`: 285 passed, 4 skipped.
  - `.venv/bin/ruff check .`: all checks passed.
  - `.venv/bin/mypy`: no issues in 67 source files.
  - `.venv/bin/python -m build`: built source distribution and wheel.

## Phase 5 Pre-Implementation Audit: Tracing And Debuggability

- Status: ready.
- Scope:
  - Phase 5 covers trace metadata, replay output, and troubleshooting guidance
    for website playbook runs.
- Evidence:
  - `FileTraceSink.prepare_run()` writes compiled `task.json` before execution
    and stores task metadata for the final report.
  - `FileTraceSink.record_event()` writes event metadata to `action-log.jsonl`.
  - `FileTraceSink.write_final_report()` writes task metadata to
    `final-report.json` and renders a Markdown report.
  - `_run_report_markdown()` prints the site and flow when both are present.
  - `_replay()` prints site and flow fields from final-report metadata.
  - `SiteTaskCompiler` currently records site ID, flow ID, domain, version,
    validation status, compilation summary, sensitive-step IDs, and
    blocked-state IDs in compiled task metadata.
  - The planner records confirmation events for sensitive steps and blocked
    state reasons on failed step reports.
  - `docs/troubleshooting.md` already has a public-site troubleshooting section
    that names the requested failure modes.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_tracing.py`: 5 passed.
- Plan:
  - Each Phase 5 item will be checked only after its trace/report/docs evidence
    is recorded below and committed separately.

### Task 113/211: Extend trace output with site-playbook metadata

- Status: complete.
- Evidence:
  - `SiteTaskCompiler` writes site ID, flow ID, playbook version, and domain
    metadata into the compiled task.
  - `FileTraceSink.prepare_run()` persists that metadata in `task.json`.
  - The planner's `load_task` trace event includes task metadata in
    `action-log.jsonl`.
  - `FileTraceSink.write_final_report()` persists task metadata in
    `final-report.json`.
  - Added regression coverage that compares these fields across all three trace
    artifacts for a seed YouTube site run.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_tracing.py -k
    "trace_artifacts_include_site_playbook_metadata"`: 1 passed, 5 deselected.
  - `.venv/bin/ruff check tests/test_site_playbook_tracing.py`: all checks
    passed.
  - `.venv/bin/mypy tests/test_site_playbook_tracing.py`: no issues found.

### Task 114/211: Record playbook validation results in trace metadata

- Status: complete.
- Evidence:
  - `_compiled_task_metadata()` now records
    `site_playbook_validation_status: passed`.
  - `_compiled_task_metadata()` also records
    `site_playbook_validation_errors: []` for successful validation so the
    trace shape has an explicit result field and error-list field.
  - Added regression coverage that checks the validation result in `task.json`,
    the `load_task` action-log event, and `final-report.json`.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_tracing.py -k
    "validation_result"`: 1 passed, 6 deselected.
  - `.venv/bin/ruff check src/desktop_agent/site_playbooks.py
    tests/test_site_playbook_tracing.py`: all checks passed.
  - `.venv/bin/mypy src/desktop_agent/site_playbooks.py
    tests/test_site_playbook_tracing.py`: no issues found.

### Task 115/211: Record compiled task path or in-memory task summary

- Status: complete.
- Evidence:
  - `run-site` and `dry-run-site` compile the site flow directly into an
    in-memory `TaskDefinition`.
  - `_compiled_task_metadata()` records `site_compilation_source: in_memory`,
    `site_compiled_step_count`, and `site_compiled_task_summary`.
  - `compile-site` still records `site_compiled_task_path` in generated task
    YAML when an output file is requested.
  - Added regression coverage that checks the in-memory summary metadata in
    `task.json`, the `load_task` action-log event, and `final-report.json`.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_tracing.py -k
    "compiled_task_summary"`: 1 passed, 7 deselected.
  - `.venv/bin/ruff check tests/test_site_playbook_tracing.py`: all checks
    passed.
  - `.venv/bin/mypy tests/test_site_playbook_tracing.py`: no issues found.

### Task 116/211: Record blocked-state checks and outcomes

- Status: complete.
- Evidence:
  - `SiteTaskCompiler` inserts blocked-state check steps before sensitive
    public-site actions.
  - Blocked-state check steps carry `site_blocked_state_check`,
    `site_blocked_state_id`, detector, and reason metadata.
  - The planner records failed blocked-state checks as failed step reports and
    emits a `failure` trace event with the same blocked-state metadata.
  - Added regression coverage that verifies the failed report step and action
    log failure event both identify the blocked-state check and outcome.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_tracing.py -k
    "blocked_state_check_outcome"`: 1 passed, 8 deselected.
  - `.venv/bin/ruff check tests/test_site_playbook_tracing.py`: all checks
    passed.
  - `.venv/bin/mypy tests/test_site_playbook_tracing.py`: no issues found.

### Task 117/211: Record whether each sensitive step was confirmed or blocked

- Status: complete.
- Evidence:
  - The planner emits a `confirmation` trace event before each sensitive step.
  - The event includes `sensitive_step_confirmed` and
    `sensitive_step_confirmation_state`.
  - Existing coverage verifies the blocked state for an unconfirmed sensitive
    step.
  - Added regression coverage that confirms a sensitive step with
    `--confirm-step` and verifies the confirmed state in both `action-log.jsonl`
    and final-report events.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_tracing.py -k
    "sensitive_confirmed_step"`: 1 passed, 9 deselected.
  - `.venv/bin/ruff check tests/test_site_playbook_tracing.py`: all checks
    passed.
  - `.venv/bin/mypy tests/test_site_playbook_tracing.py`: no issues found.

### Task 118/211: Update replay output to include site and flow when present

- Status: complete.
- Evidence:
  - `_replay()` reads `final-report.json`, extracts `site_id` and
    `site_flow_id` from report metadata, and prints `site:` and `flow:` lines
    when both are present.
  - Regression coverage dry-runs a seed site flow, replays the generated trace,
    and asserts the replay output includes `site: youtube` and
    `flow: open-search`.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_tracing.py -k
    "replay_prints_site_and_flow"`: 1 passed, 9 deselected.
  - `.venv/bin/ruff check tests/test_site_playbook_tracing.py
    src/desktop_agent/cli.py`: all checks passed.
  - `.venv/bin/mypy tests/test_site_playbook_tracing.py
    src/desktop_agent/cli.py`: no issues found.

### Task 119/211: Update troubleshooting docs with public-site failure modes

- Status: complete.
- Evidence:
  - `docs/troubleshooting.md` contains a `Public Site Playbook Stops` section.
  - The section documents trace/report metadata locations and replay output for
    website playbook failures.
  - Added a docs regression that requires the public-site section and all six
    required failure-mode labels.
- Verification:
  - `.venv/bin/pytest tests/test_safety_docs.py -k
    "public_site_failure_modes"`: 1 passed, 5 deselected.
  - `.venv/bin/ruff check tests/test_safety_docs.py`: all checks passed.
  - `.venv/bin/mypy tests/test_safety_docs.py`: no issues found.

### Task 120/211: Logged-out session

- Status: complete.
- Evidence:
  - `docs/troubleshooting.md` now identifies logged-out failures by the
    `logged-out` blocked-state signal or sign-in text.
  - The remediation directs the operator to authenticate manually in the
    browser and rerun the same flow, without bypass behavior.
- Verification:
  - `.venv/bin/pytest tests/test_safety_docs.py -k
    "public_site_failure_modes"`: 1 passed, 5 deselected.
  - `.venv/bin/ruff check tests/test_safety_docs.py`: all checks passed.
  - `.venv/bin/mypy tests/test_safety_docs.py`: no issues found.

### Task 121/211: Consent dialog

- Status: complete.
- Evidence:
  - `docs/troubleshooting.md` now identifies consent failures by consent,
    cookie, or privacy text.
  - The remediation directs the operator to resolve the dialog manually
    according to their preference and rerun the flow.
- Verification:
  - `.venv/bin/pytest tests/test_safety_docs.py -k
    "public_site_failure_modes"`: 1 passed, 5 deselected.
  - `.venv/bin/ruff check tests/test_safety_docs.py`: all checks passed.
  - `.venv/bin/mypy tests/test_safety_docs.py`: no issues found.

### Task 122/211: Site redesign

- Status: complete.
- Evidence:
  - `docs/troubleshooting.md` now identifies redesign failures through
    unsupported-layout blocked states, missing landmarks, or repeated target
    mismatches in the action log.
  - The remediation directs maintainers to inspect the changed page and update
    playbook landmarks or the flow.
- Verification:
  - `.venv/bin/pytest tests/test_safety_docs.py -k
    "public_site_failure_modes"`: 1 passed, 5 deselected.
  - `.venv/bin/ruff check tests/test_safety_docs.py`: all checks passed.
  - `.venv/bin/mypy tests/test_safety_docs.py`: no issues found.

### Task 123/211: CAPTCHA or suspicious-activity challenge

- Status: complete.
- Evidence:
  - `docs/troubleshooting.md` now states that CAPTCHA or suspicious-activity
    challenges are not automated by DeskPilot.
  - The remediation explicitly prohibits solving or bypassing the challenge
    with DeskPilot and directs the operator to resolve it manually or abandon
    the run.
- Verification:
  - `.venv/bin/pytest tests/test_safety_docs.py -k
    "public_site_failure_modes"`: 1 passed, 5 deselected.
  - `.venv/bin/ruff check tests/test_safety_docs.py`: all checks passed.
  - `.venv/bin/mypy tests/test_safety_docs.py`: no issues found.

### Task 124/211: Permission restriction

- Status: complete.
- Evidence:
  - `docs/troubleshooting.md` now identifies permission failures through
    account, policy, restricted, or unavailable-action text in blocked-state
    reasons.
  - The remediation directs the operator to use an authorized account or choose
    a permitted flow rather than working around the restriction.
- Verification:
  - `.venv/bin/pytest tests/test_safety_docs.py -k
    "public_site_failure_modes"`: 1 passed, 5 deselected.
  - `.venv/bin/ruff check tests/test_safety_docs.py`: all checks passed.
  - `.venv/bin/mypy tests/test_safety_docs.py`: no issues found.

### Task 125/211: Ambiguous selector

- Status: complete.
- Evidence:
  - `docs/troubleshooting.md` now identifies ambiguous selector failures by
    candidate rankings or `candidate_count` checks with multiple matches.
  - The remediation directs maintainers to narrow the landmark, search region,
    or flow-specific target before rerunning.
- Verification:
  - `.venv/bin/pytest tests/test_safety_docs.py -k
    "public_site_failure_modes"`: 1 passed, 5 deselected.
  - `.venv/bin/ruff check tests/test_safety_docs.py`: all checks passed.
  - `.venv/bin/mypy tests/test_safety_docs.py`: no issues found.

## Phase 5 Boundary Verification

- Status: passed.
- Verification:
  - `.venv/bin/pytest`: 291 passed, 4 skipped.
  - `.venv/bin/ruff check .`: all checks passed.
  - `.venv/bin/mypy`: no issues in 67 source files.
  - `.venv/bin/python -m build`: built source distribution and wheel.

## Phase 6 Pre-Implementation Audit: Regression Tests

- Status: ready.
- Scope:
  - Phase 6 covers schema, compiler, CLI, safety, trace, and opt-in live smoke
    regression coverage for website playbooks.
- Evidence:
  - `tests/test_site_playbooks.py` contains schema and compiler regression
    tests for playbook loading, validation failures, compiler output, seed
    catalog validation, and compiled task validation.
  - `tests/test_site_playbook_cli.py` contains CLI regressions for catalog
    commands, compilation, dry-runs, platform-actuation failures, missing
    confirmation, and invalid playbooks.
  - `tests/test_site_playbook_safety.py` contains safety regressions for
    sensitive categories, CAPTCHA blocked states, active-window mismatch, and
    emergency stop behavior.
  - `tests/test_site_playbook_tracing.py` contains trace regressions for site
    metadata, playbook version, confirmation state, blocked-state reports, and
    replay output.
  - `tests/test_site_playbook_live_smoke.py` contains opt-in live smoke
    coverage for seed read-only flows and explicit environment gating.
- Verification:
  - Phase 5 boundary verification just ran the full suite successfully:
    291 passed, 4 skipped.
- Plan:
  - Each Phase 6 checklist item will be checked only after the exact regression
    evidence and focused command are recorded below.

### Task 126/211: Valid playbook loads successfully

- Status: complete.
- Evidence:
  - `tests/test_site_playbooks.py::test_valid_playbook_loads_successfully`
    writes a valid playbook fixture and loads it through `load_site_playbook`.
  - The assertion verifies the loaded site ID and first flow ID.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbooks.py -k
    "valid_playbook_loads_successfully"`: 1 passed, 35 deselected.

### Task 127/211: Missing site ID is rejected

- Status: complete.
- Evidence:
  - `tests/test_site_playbooks.py::test_missing_site_id_is_rejected` writes a
    playbook with an empty `site_id`.
  - The assertion verifies `load_site_playbook` raises
    `SitePlaybookValidationError` mentioning `site_id`.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbooks.py -k
    "missing_site_id_is_rejected"`: 1 passed, 35 deselected.

### Task 128/211: Invalid site ID is rejected

- Status: complete.
- Evidence:
  - `tests/test_site_playbooks.py::test_invalid_site_id_is_rejected` writes a
    playbook whose `site_id` contains spaces and uppercase characters.
  - The assertion verifies `SitePlaybookValidationError` mentions the
    slug-safe requirement.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbooks.py -k
    "invalid_site_id_is_rejected"`: 1 passed, 35 deselected.

### Task 129/211: Empty domains are rejected

- Status: complete.
- Evidence:
  - `tests/test_site_playbooks.py::test_empty_domains_are_rejected` writes a
    playbook with `domains: []`.
  - The assertion verifies `SitePlaybookValidationError` mentions the domain
    requirement.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbooks.py -k
    "empty_domains_are_rejected"`: 1 passed, 35 deselected.

### Task 130/211: Empty window-title patterns are rejected

- Status: complete.
- Evidence:
  - `tests/test_site_playbooks.py::test_empty_window_title_patterns_are_rejected`
    writes a playbook with `allowed_window_titles: []`.
  - The assertion verifies the window-title validation error is raised.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbooks.py -k
    "empty_window_title_patterns_are_rejected"`: 1 passed, 35 deselected.

### Task 131/211: Duplicate flow IDs are rejected

- Status: complete.
- Evidence:
  - `tests/test_site_playbooks.py::test_duplicate_flow_ids_are_rejected` writes
    a playbook with two `open-search` flows.
  - The assertion verifies validation raises a duplicate flow ID error.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbooks.py -k
    "duplicate_flow_ids_are_rejected"`: 1 passed, 35 deselected.

### Task 132/211: Duplicate flow-step IDs are rejected

- Status: complete.
- Evidence:
  - `tests/test_site_playbooks.py::test_duplicate_flow_step_ids_are_rejected`
    writes a flow with two `open-search` steps.
  - The assertion verifies validation raises a duplicate step ID error.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbooks.py -k
    "duplicate_flow_step_ids_are_rejected"`: 1 passed, 35 deselected.

### Task 133/211: Unknown step action is rejected

- Status: complete.
- Evidence:
  - `tests/test_site_playbooks.py::test_unknown_step_action_is_rejected` writes
    a playbook using unsupported action `teleport`.
  - The assertion verifies validation raises an `unknown action` error before
    compilation or execution.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbooks.py -k
    "unknown_step_action_is_rejected"`: 1 passed, 35 deselected.

### Task 134/211: Missing landmark reference is rejected

- Status: complete.
- Evidence:
  - `tests/test_site_playbooks.py::test_missing_landmark_reference_is_rejected`
    writes a playbook whose step references `landmark: missing`.
  - The assertion verifies validation raises `landmark does not exist`.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbooks.py -k
    "missing_landmark_reference_is_rejected"`: 1 passed, 35 deselected.

### Task 135/211: Sensitive step without confirmation is rejected

- Status: complete.
- Evidence:
  - `tests/test_site_playbooks.py::test_sensitive_step_without_confirmation_is_rejected`
    adds `sensitive_category: publish` without `requires_confirmation: true`.
  - The assertion verifies validation rejects the playbook before compilation.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbooks.py -k
    "sensitive_step_without_confirmation_is_rejected"`: 1 passed, 35 deselected.

### Task 136/211: Blocked state without a reason is rejected

- Status: complete.
- Evidence:
  - `tests/test_site_playbooks.py::test_blocked_state_without_reason_is_rejected`
    writes a blocked state with an empty `reason`.
  - The assertion verifies validation raises a `reason is required` error.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbooks.py -k
    "blocked_state_without_reason_is_rejected"`: 1 passed, 35 deselected.

### Task 137/211: Basic navigation flow compiles to `TaskDefinition`

- Status: complete.
- Evidence:
  - `tests/test_site_playbooks.py::test_basic_navigation_flow_compiles_to_task_definition`
    loads a valid playbook and compiles `open-search`.
  - The assertions verify the result is a `TaskDefinition` named
    `example-site:open-search`.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbooks.py -k
    "basic_navigation_flow_compiles_to_task_definition"`: 1 passed,
    35 deselected.

### Task 138/211: Compiled task passes `BasicTaskValidator`

- Status: complete.
- Evidence:
  - `tests/test_site_playbooks.py::test_compiled_task_passes_basic_task_validator`
    compiles a valid site flow and validates it with `BasicTaskValidator`.
  - This proves the compiler output conforms to the existing task DSL contract.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbooks.py -k
    "compiled_task_passes_basic_task_validator"`: 1 passed, 35 deselected.

### Task 139/211: Domain and title rules become `allowed_windows`

- Status: complete.
- Evidence:
  - `tests/test_site_playbooks.py::test_domain_and_title_rules_compile_to_allowed_windows`
    compiles a valid flow.
  - The assertion verifies the compiled task has `("Example", "example.com")`
    as `allowed_windows`.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbooks.py -k
    "domain_and_title_rules_compile_to_allowed_windows"`: 1 passed,
    35 deselected.

### Task 140/211: Flow timeout compiles into task timeout

- Status: complete.
- Evidence:
  - `tests/test_site_playbooks.py::test_flow_timeout_compiles_to_task_timeout`
    changes the flow timeout to `45`.
  - The assertion verifies the compiled task timeout is `45`.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbooks.py -k
    "flow_timeout_compiles_to_task_timeout"`: 1 passed, 35 deselected.

### Task 141/211: Flow retry defaults compile into step retry values

- Status: complete.
- Evidence:
  - `tests/test_site_playbooks.py::test_flow_retry_defaults_compile_to_steps`
    changes the flow retry default to `3`.
  - The assertion verifies the compiled step retry value is `3`.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbooks.py -k
    "flow_retry_defaults_compile_to_steps"`: 1 passed, 35 deselected.

### Task 142/211: Sensitive steps preserve `requires_confirmation`

- Status: complete.
- Evidence:
  - `tests/test_site_playbooks.py::test_sensitive_steps_preserve_confirmation`
    compiles a sensitive publish flow.
  - The assertions verify the final compiled step keeps
    `requires_confirmation: true` and compiles into the submission category.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbooks.py -k
    "sensitive_steps_preserve_confirmation"`: 1 passed, 35 deselected.

### Task 143/211: Blocked-state checks compile before sensitive final actions

- Status: complete.
- Evidence:
  - `tests/test_site_playbooks.py::test_blocked_state_checks_compile_before_sensitive_final_actions`
    compiles a sensitive publish flow.
  - The assertions verify the blocked-state check step is first and the
    sensitive action remains last.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbooks.py -k
    "blocked_state_checks_compile_before_sensitive_final_actions"`: 1 passed,
    35 deselected.

### Task 144/211: Unknown site flow fails before task execution

- Status: complete.
- Evidence:
  - `tests/test_site_playbooks.py::test_unknown_site_flow_fails_before_task_execution`
    compiles a valid playbook with missing flow ID `missing-flow`.
  - The assertion verifies `SitePlaybookValidationError` is raised before any
    task execution path can run.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbooks.py -k
    "unknown_site_flow_fails_before_task_execution"`: 1 passed, 35 deselected.

### Task 145/211: `list-sites` prints all seed sites

- Status: complete.
- Evidence:
  - `tests/test_site_playbook_cli.py::test_list_sites_prints_all_seed_sites`
    runs `main(["list-sites"])`.
  - The assertion verifies the printed set matches every seed site:
    Facebook, Instagram, LinkedIn, Medium, TikTok, X/Twitter, and YouTube.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_cli.py -k
    "list_sites_prints_all_seed_sites"`: 1 passed, 10 deselected.

### Task 146/211: `list-flows linkedin` prints LinkedIn flows

- Status: complete.
- Evidence:
  - `tests/test_site_playbook_cli.py::test_list_flows_linkedin_prints_flows`
    runs `main(["list-flows", "linkedin"])`.
  - The assertion verifies `open-search` and the LinkedIn flow description are
    printed.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_cli.py -k
    "list_flows_linkedin_prints_flows"`: 1 passed, 10 deselected.

### Task 147/211: `compile-site youtube open-search` writes a valid task YAML

- Status: complete.
- Evidence:
  - `tests/test_site_playbook_cli.py::test_compile_site_writes_valid_task_yaml`
    runs `compile-site youtube open-search --output <path>`.
  - The test loads the generated YAML, validates it with `BasicTaskValidator`,
    and checks site metadata.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_cli.py -k
    "compile_site_writes_valid_task_yaml"`: 1 passed, 10 deselected.

### Task 148/211: `dry-run-site medium open-editor` validates without desktop input

- Status: complete.
- Evidence:
  - `tests/test_site_playbook_cli.py::test_dry_run_site_validates_without_desktop_input`
    runs `dry-run-site medium open-editor` with a temporary trace config and
    `--no-screenshots`.
  - The assertions verify status `0`, task output, and a passed run.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_cli.py -k
    "dry_run_site_validates_without_desktop_input"`: 1 passed, 10 deselected.

### Task 149/211: `run-site` returns nonzero when platform actuation is unavailable

- Status: complete.
- Evidence:
  - `tests/test_site_playbook_cli.py::test_run_site_returns_nonzero_when_platform_actuation_is_unavailable`
    runs a temporary `run-site` flow using a keypress action.
  - The assertions verify status `1` and the platform actuation unavailable
    message.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_cli.py -k
    "run_site_returns_nonzero_when_platform_actuation_is_unavailable"`:
    1 passed, 10 deselected.

### Task 150/211: Missing confirmation returns nonzero with a clear message

- Status: complete.
- Evidence:
  - `tests/test_site_playbook_cli.py::test_missing_confirmation_returns_clear_message`
    dry-runs a sensitive site flow without `--confirm-step`.
  - The assertions verify status `1` and a `requires explicit confirmation`
    message.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_cli.py -k
    "missing_confirmation_returns_clear_message"`: 1 passed, 10 deselected.

### Task 151/211: Invalid playbook returns nonzero with the validation error

- Status: complete.
- Evidence:
  - `tests/test_site_playbook_cli.py::test_invalid_playbook_returns_validation_error`
    points `list-sites` at a temporary invalid catalog.
  - The assertions verify status `2` and the slug-safe validation message.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_cli.py -k
    "invalid_playbook_returns_validation_error"`: 1 passed, 10 deselected.

### Task 152/211: Login step is blocked without `--confirm-step`

- Status: complete.
- Evidence:
  - `tests/test_site_playbook_safety.py::test_sensitive_site_steps_are_blocked_without_confirmation`
    parameterizes sensitive categories, including `login`.
  - The focused login case verifies `LocalSafetyPolicy` rejects the step with a
    `requires explicit confirmation` reason.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_safety.py -k
    "sensitive_site_steps_are_blocked_without_confirmation and login"`:
    1 passed, 7 deselected.

### Task 153/211: Post or publish step is blocked without `--confirm-step`

- Status: complete.
- Evidence:
  - `tests/test_site_playbook_safety.py::test_sensitive_site_steps_are_blocked_without_confirmation`
    includes the `publish` sensitive category.
  - The focused publish case verifies safety rejection before action.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_safety.py -k
    "sensitive_site_steps_are_blocked_without_confirmation and publish"`:
    1 passed, 7 deselected.

### Task 154/211: Message-send step is blocked without `--confirm-step`

- Status: complete.
- Evidence:
  - `tests/test_site_playbook_safety.py::test_sensitive_site_steps_are_blocked_without_confirmation`
    includes the `message` sensitive category.
  - The focused message case verifies safety rejection before action.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_safety.py -k
    "sensitive_site_steps_are_blocked_without_confirmation and message"`:
    1 passed, 7 deselected.

### Task 155/211: Delete step is blocked without `--confirm-step`

- Status: complete.
- Evidence:
  - `tests/test_site_playbook_safety.py::test_sensitive_site_steps_are_blocked_without_confirmation`
    includes the `delete` sensitive category.
  - The focused delete case verifies safety rejection before action.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_safety.py -k
    "sensitive_site_steps_are_blocked_without_confirmation and delete"`:
    1 passed, 7 deselected.

### Task 156/211: Settings-change step is blocked without `--confirm-step`

- Status: complete.
- Evidence:
  - `tests/test_site_playbook_safety.py::test_sensitive_site_steps_are_blocked_without_confirmation`
    includes the `account_settings` sensitive category.
  - The focused account-settings case verifies safety rejection before action.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_safety.py -k
    "sensitive_site_steps_are_blocked_without_confirmation and account_settings"`:
    1 passed, 7 deselected.

### Task 157/211: CAPTCHA state aborts with a no-bypass message

- Status: complete.
- Evidence:
  - `tests/test_site_playbook_safety.py::test_captcha_state_aborts_with_no_bypass_message`
    compiles a sensitive flow with a visible-text challenge blocked state.
  - The assertions verify the run fails with `blocked state detected` and the
    authored `CAPTCHA challenges are not automated` message.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_safety.py -k
    "captcha_state_aborts_with_no_bypass_message"`: 1 passed, 7 deselected.

### Task 158/211: Active-window mismatch aborts before action

- Status: complete.
- Evidence:
  - `tests/test_site_playbook_safety.py::test_active_window_mismatch_aborts_before_site_action`
    runs a read-only site task while the active window title is outside
    `allowed_windows`.
  - The assertions verify failure category `safety_stop` and an
    `allowed_windows` abort reason.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_safety.py -k
    "active_window_mismatch_aborts_before_site_action"`: 1 passed,
    7 deselected.

### Task 159/211: Emergency stop behavior remains unchanged

- Status: complete.
- Evidence:
  - `tests/test_site_playbook_safety.py::test_emergency_stop_behavior_remains_unchanged_for_site_tasks`
    runs a read-only site task with a triggered emergency-stop monitor.
  - The assertions verify status `emergency_stopped` and the unchanged abort
    reason `emergency stop requested`.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_safety.py -k
    "emergency_stop_behavior_remains_unchanged_for_site_tasks"`: 1 passed,
    7 deselected.

### Task 160/211: Final report includes site ID and flow ID for site runs

- Status: complete.
- Evidence:
  - `tests/test_site_playbook_tracing.py::test_final_report_includes_site_id_and_flow_id`
    dry-runs a seed site trace and reads `final-report.json`.
  - The assertions verify `metadata.site_id` and `metadata.site_flow_id`.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_tracing.py -k
    "final_report_includes_site_id_and_flow_id"`: 1 passed, 9 deselected.

### Task 161/211: Action log includes selected playbook version

- Status: complete.
- Evidence:
  - `tests/test_site_playbook_tracing.py::test_action_log_includes_selected_playbook_version`
    dry-runs a seed site trace and reads `actions.jsonl`.
  - The assertions verify the selected playbook version is recorded for the
    site action log.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_tracing.py -k
    "action_log_includes_selected_playbook_version"`: 1 passed,
    9 deselected.

### Task 162/211: Sensitive blocked step appears in trace metadata

- Status: complete.
- Evidence:
  - `tests/test_site_playbook_tracing.py::test_sensitive_blocked_step_appears_in_trace_metadata`
    runs a site flow with an unconfirmed sensitive action.
  - The assertions verify the trace metadata records the blocked sensitive step
    instead of hiding the stop condition.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_tracing.py -k
    "sensitive_blocked_step_appears_in_trace_metadata"`: 1 passed,
    9 deselected.

### Task 163/211: Blocked-state reason appears in final report

- Status: complete.
- Evidence:
  - `tests/test_site_playbook_tracing.py::test_blocked_state_reason_appears_in_final_report`
    dry-runs a site task that stops on a configured blocked state.
  - The assertions verify `final-report.json` carries the blocked-state reason
    for monitoring and report consumers.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_tracing.py -k
    "blocked_state_reason_appears_in_final_report"`: 1 passed,
    9 deselected.

### Task 164/211: Replay prints site and flow fields when available

- Status: complete.
- Evidence:
  - `tests/test_site_playbook_tracing.py::test_replay_prints_site_and_flow_when_present`
    replays a site trace with site and flow metadata.
  - The assertions verify replay output includes the site ID and site flow ID
    for report review.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_tracing.py -k
    "replay_prints_site_and_flow_when_present"`: 1 passed,
    9 deselected.

### Task 165/211: Live smoke tests are skipped by default

- Status: complete.
- Evidence:
  - `tests/test_site_playbook_live_smoke.py::test_live_site_smoke_tests_require_explicit_environment_flag`
    is marked `live_site_smoke` and guarded by `DESKPILOT_LIVE_SITE_SMOKE`.
  - Running the selected test without the environment flag produced a skip with
    the authorized live-site smoke reason.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_live_smoke.py -k
    "require_explicit_environment_flag"`: 1 skipped, 2 deselected.

### Task 166/211: Live smoke tests require an explicit environment flag

- Status: complete.
- Evidence:
  - `tests/test_site_playbook_live_smoke.py::test_live_site_smoke_tests_require_explicit_environment_flag`
    asserts the opt-in environment variable is present before live-site smoke
    execution is allowed.
  - Running the selected test with `DESKPILOT_LIVE_SITE_SMOKE=1` passed.
- Verification:
  - `env DESKPILOT_LIVE_SITE_SMOKE=1 .venv/bin/pytest
    tests/test_site_playbook_live_smoke.py -k
    "require_explicit_environment_flag"`: 1 passed, 2 deselected.

### Task 167/211: Live smoke tests never run final actions by default

- Status: complete.
- Evidence:
  - `tests/test_site_playbook_live_smoke.py::test_live_site_smoke_flows_never_run_final_actions_by_default`
    resolves every seed smoke flow.
  - The assertions verify default smoke steps have no confirmation requirement
    and no sensitive category, preventing final submit, post, message,
    purchase, apply, or delete actions from running as smoke defaults.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_live_smoke.py -k
    "never_run_final_actions_by_default"`: 1 passed, 2 deselected.

### Task 168/211: Each seed site has one read-only smoke flow

- Status: complete.
- Evidence:
  - `tests/test_site_playbook_live_smoke.py::test_each_seed_site_has_one_read_only_smoke_flow`
    verifies the live smoke catalog covers exactly the seed site set.
  - `tests/test_site_playbook_live_smoke.py::test_seed_site_read_only_smoke_flow`
    adds parameterized per-site read-only checks so each seed site can be
    selected independently.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_live_smoke.py`: 9 passed,
    1 skipped.
  - `.venv/bin/pytest tests/test_site_playbook_live_smoke.py -k
    "each_seed_site_has_one_read_only_smoke_flow"`: 1 passed, 9 deselected.

### Task 169/211: LinkedIn read-only smoke flow

- Status: complete.
- Evidence:
  - `tests/test_site_playbook_live_smoke.py::test_seed_site_read_only_smoke_flow[linkedin]`
    resolves the LinkedIn `open-search` smoke flow.
  - The parameterized assertions verify the flow has steps and each step is
    non-sensitive and does not require confirmation.
- Verification:
  - `.venv/bin/pytest
    'tests/test_site_playbook_live_smoke.py::test_seed_site_read_only_smoke_flow[linkedin]'`:
    1 passed.

### Task 170/211: X/Twitter read-only smoke flow

- Status: complete.
- Evidence:
  - `tests/test_site_playbook_live_smoke.py::test_seed_site_read_only_smoke_flow[x-twitter]`
    resolves the X/Twitter `open-search` smoke flow.
  - The parameterized assertions verify the flow has steps and each step is
    non-sensitive and does not require confirmation.
- Verification:
  - `.venv/bin/pytest
    'tests/test_site_playbook_live_smoke.py::test_seed_site_read_only_smoke_flow[x-twitter]'`:
    1 passed.

### Task 171/211: Instagram read-only smoke flow

- Status: complete.
- Evidence:
  - `tests/test_site_playbook_live_smoke.py::test_seed_site_read_only_smoke_flow[instagram]`
    resolves the Instagram `open-search` smoke flow.
  - The parameterized assertions verify the flow has steps and each step is
    non-sensitive and does not require confirmation.
- Verification:
  - `.venv/bin/pytest
    'tests/test_site_playbook_live_smoke.py::test_seed_site_read_only_smoke_flow[instagram]'`:
    1 passed.

### Task 172/211: Facebook read-only smoke flow

- Status: complete.
- Evidence:
  - `tests/test_site_playbook_live_smoke.py::test_seed_site_read_only_smoke_flow[facebook]`
    resolves the Facebook `open-search` smoke flow.
  - The parameterized assertions verify the flow has steps and each step is
    non-sensitive and does not require confirmation.
- Verification:
  - `.venv/bin/pytest
    'tests/test_site_playbook_live_smoke.py::test_seed_site_read_only_smoke_flow[facebook]'`:
    1 passed.

### Task 173/211: Medium read-only smoke flow

- Status: complete.
- Evidence:
  - `tests/test_site_playbook_live_smoke.py::test_seed_site_read_only_smoke_flow[medium]`
    resolves the Medium `open-editor` smoke flow.
  - The parameterized assertions verify the editor surface can be opened as a
    non-sensitive, no-confirmation smoke flow without publishing.
- Verification:
  - `.venv/bin/pytest
    'tests/test_site_playbook_live_smoke.py::test_seed_site_read_only_smoke_flow[medium]'`:
    1 passed.

### Task 174/211: YouTube read-only smoke flow

- Status: complete.
- Evidence:
  - `tests/test_site_playbook_live_smoke.py::test_seed_site_read_only_smoke_flow[youtube]`
    resolves the YouTube `open-search` smoke flow.
  - The parameterized assertions verify the flow has steps and each step is
    non-sensitive and does not require confirmation.
- Verification:
  - `.venv/bin/pytest
    'tests/test_site_playbook_live_smoke.py::test_seed_site_read_only_smoke_flow[youtube]'`:
    1 passed.

### Task 175/211: TikTok read-only smoke flow

- Status: complete.
- Evidence:
  - `tests/test_site_playbook_live_smoke.py::test_seed_site_read_only_smoke_flow[tiktok]`
    resolves the TikTok `open-search` smoke flow.
  - The parameterized assertions verify the flow has steps and each step is
    non-sensitive and does not require confirmation.
- Verification:
  - `.venv/bin/pytest
    'tests/test_site_playbook_live_smoke.py::test_seed_site_read_only_smoke_flow[tiktok]'`:
    1 passed.

## Phase 6 Verification

- Status: complete.
- Scope:
  - Schema, compiler, CLI, safety, trace, and opt-in live smoke regression
    tasks are checked in the roadmap.
  - Roadmap implementation count is `175/211`.
- Verification:
  - `.venv/bin/pytest`: 316 passed, 4 skipped.
  - `.venv/bin/ruff check .`: all checks passed.
  - `.venv/bin/mypy`: no issues found in 71 source files.
  - `.venv/bin/python -m build`: built `deskpilot-0.1.0.tar.gz` and
    `deskpilot-0.1.0-py3-none-any.whl`.

## Phase 7 Audit

- Status: ready to execute.
- Roadmap range: Tasks 176-187 of 211.
- Current documentation surfaces:
  - `docs/website-playbooks.md` covers playbook authoring, new-site setup,
    content variables, sensitive confirmations, approval manifests, and
    blocked states.
  - `docs/website-playbook-demo.md` covers command-level examples, tests,
    traces, reports, and live-smoke notes.
  - `README.md` links to website navigation roadmap and playbook docs.
  - `docs/task-dsl.md` and `docs/safety.md` already mention the playbook layer
    and third-party site guardrails.
- Audit decision:
  - Verify and tighten each documentation item task by task before checking it.
  - Keep examples grounded in local validation, traces, monitoring artifacts,
    and reports rather than live public-site dependencies.

### Task 176/211: Add playbook authoring docs

- Status: complete.
- Evidence:
  - `docs/website-playbooks.md` now includes an `Authoring Workflow` section with
    the required top-level YAML shape.
  - The workflow tells authors where playbooks live, how landmarks and flows fit
    together, how to keep smoke flows read-only, and which regression suites to
    update for schema, CLI, safety, tracing, monitoring, and reports.
- Verification:
  - `rg -n "Authoring Workflow|site_id: example-site|test_site_playbook_tracing"
    docs/website-playbooks.md`: matched the new authoring section and test
    guidance.

### Task 177/211: Add a new-site checklist

- Status: complete.
- Evidence:
  - `docs/website-playbooks.md` now expands `New-Site Checklist` with catalog
    discovery, dry-run trace/report inspection, live-smoke opt-in, and normal CI
    expectations.
  - The checklist ties new site onboarding to pipelines, monitoring artifacts,
    and final reports instead of only YAML authoring.
- Verification:
  - `rg -n "New-Site Checklist|list-flows <site-id>|DESKPILOT_LIVE_SITE_SMOKE"
    docs/website-playbooks.md`: matched the checklist and opt-in smoke guidance.

### Task 178/211: Add examples section

- Status: complete.
- Evidence:
  - `docs/website-playbooks.md` now introduces the examples as copyable,
    testable snippets for read-only navigation, search, composer/editor opening,
    confirmed sensitive actions, and blocked-state detection.
  - The examples section directs authors to validate compiled tasks and
    trace/report metadata before using snippets as live-site playbooks.
- Verification:
  - `rg -n "## Examples|compiled task and generated trace/report|deep-search examples"
    docs/website-playbooks.md`: matched the examples section, verification
    guidance, and search guardrail.

### Task 179/211: Read-only navigation flow example

- Status: complete.
- Evidence:
  - `docs/website-playbooks.md` includes a self-contained `Read-Only Navigation
    Flow` YAML snippet with a reusable `home` landmark and `open-home` flow.
  - The example stays navigation-only and describes opening the site feed without
    changing account state.
- Verification:
  - `rg -n "Read-Only Navigation Flow|id: home|without changing account state"
    docs/website-playbooks.md`: matched the read-only example.

### Task 180/211: Search flow example

- Status: complete.
- Evidence:
  - `docs/website-playbooks.md` includes a `Search Flow` YAML snippet with a
    reusable `search` landmark and an `open-search` flow.
  - The example explicitly stops before typing or submitting a query, preserving
    read-only search and deep-search discovery behavior.
- Verification:
  - `rg -n "Search Flow|id: open-search|before typing or submitting a query"
    docs/website-playbooks.md`: matched the search example and guardrail.

### Task 181/211: Composer-open flow example stops before submission

- Status: complete.
- Evidence:
  - `docs/website-playbooks.md` includes a `Composer-Open Flow` YAML snippet with
    a reusable composer landmark and `open-editor` flow.
  - The example states that final `Post`, `Publish`, `Send`, or `Submit` actions
    must move into a separate confirmed sensitive flow.
- Verification:
  - `rg -n "Composer-Open Flow|id: open-editor|confirmed sensitive flow|inspect the final report"
    docs/website-playbooks.md`: matched the composer-open example, stop rule,
    and report inspection guidance.

### Task 182/211: Sensitive confirmed flow example

- Status: complete.
- Evidence:
  - `docs/website-playbooks.md` includes a `Sensitive Confirmed Flow` YAML
    snippet with a reusable `publish` landmark and `publish-post` flow.
  - The example requires `requires_confirmation: true`, `sensitive_category:
    publish`, approval manifests for real runs, and trace/final-report review.
- Verification:
  - `rg -n "Sensitive Confirmed Flow|requires_confirmation: true|approval manifest|confirmation state"
    docs/website-playbooks.md`: matched the sensitive example and approval
    guidance.

### Task 183/211: Blocked-state detection example

- Status: complete.
- Evidence:
  - `docs/website-playbooks.md` includes a `Blocked-State Detection` YAML
    snippet for CAPTCHA and ambiguous-target stop conditions.
  - The documentation states blocked states are reportable stops and that traces
    and final reports must include blocked-state ID and reason for monitoring and
    support review.
- Verification:
  - `rg -n "Blocked-State Detection|blocked-state ID and reason|must not describe bypasses"
    docs/website-playbooks.md`: matched the blocked-state example and reporting
    guidance.

### Task 184/211: Update README documentation links

- Status: complete.
- Evidence:
  - `README.md` links the website navigation roadmap, playbook catalog,
    authoring docs, and capability demo from the main documentation index.
  - The added catalog link points directly at `navigation_playbooks/README.md`
    so the growable site selection is discoverable from the project root.
- Verification:
  - `rg -n "Website Navigation Playbook Catalog|Website Playbooks|Website Playbook Capability Demo"
    README.md`: matched the README documentation links.

### Task 185/211: Update architecture docs with the playbook layer

- Status: complete.
- Evidence:
  - `docs/architecture.md` documents the website playbook layer, compiler
    metadata, CLI boundary, and unchanged execution/safety/tracing/reporting
    pipeline.
  - The architecture now states that traces and reports carry selected playbook
    version, site/flow IDs, blocked-state outcomes, sensitive confirmation
    state, and approved step metadata.
- Verification:
  - `rg -n "Website Playbook Layer|compile-site|blocked-state outcomes|approved step metadata"
    docs/architecture.md`: matched the architecture layer and reporting
    metadata.

### Task 186/211: Update task DSL docs for playbook compilation

- Status: complete.
- Evidence:
  - `docs/task-dsl.md` states that website playbooks compile into the same strict
    task YAML shape and keep allowed windows, retries, confirmations, blocked
    states, and metadata visible to planner traces and reports.
  - The docs now explicitly forbid behavior that exists only in playbook YAML;
    new behavior must be added to the DSL/compiler contract and covered with
    compiled-task, trace, and final-report regressions.
- Verification:
  - `rg -n "Website Playbooks Compile Into Tasks|Do not add runtime behavior|final reports"
    docs/task-dsl.md`: matched the compile-to-DSL contract.

### Task 187/211: Update safety docs with third-party website guardrails

- Status: complete.
- Evidence:
  - `docs/safety.md` documents public website automation scope, unsupported
    CAPTCHA/bot/credential behaviors, sensitive action categories, approval
    manifest requirements, and local traces/final reports.
  - The guardrails now explicitly state that normal CI uses deterministic schema,
    compiler, dry-run, safety, tracing, and reporting regressions, while live-site
    smoke checks require `DESKPILOT_LIVE_SITE_SMOKE=1` and remain read-only unless
    an approval manifest authorizes a sensitive flow.
- Verification:
  - `rg -n "DESKPILOT_LIVE_SITE_SMOKE|schema, compiler, dry-run|CAPTCHA bypass"
    docs/safety.md`: matched the third-party website guardrails.

## Phase 7 Verification

- Status: complete.
- Scope:
  - Documentation tasks for authoring, new-site onboarding, examples, README,
    architecture, task DSL, and public-site safety guardrails are checked.
  - Roadmap implementation count is `187/211`.
- Verification:
  - `.venv/bin/pytest`: 327 passed, 4 skipped.
  - `.venv/bin/ruff check .`: all checks passed.
  - `.venv/bin/mypy`: no issues found in 71 source files.
  - `.venv/bin/python -m build`: built `deskpilot-0.1.0.tar.gz` and
    `deskpilot-0.1.0-py3-none-any.whl`.

## Phase 8 Audit

- Status: ready to execute.
- Roadmap range: Tasks 188-195 of 211.
- Acceptance coverage map:
  - New-site onboarding is documented in `docs/website-playbooks.md` and
    `navigation_playbooks/README.md`.
  - Seed validation, read-only flow coverage, sensitive confirmation coverage,
    and compiled-flow task validation are covered in
    `tests/test_site_playbooks.py`.
  - Deterministic normal CI and opt-in live smoke behavior are covered by the
    phase verification pipeline and `tests/test_site_playbook_live_smoke.py`.
  - Failed site traces and final reports are covered in
    `tests/test_site_playbook_tracing.py`.
- Audit decision:
  - Verify each acceptance criterion with its focused test or documentation
    lookup before checking the roadmap item.

### Task 188/211: New engineer can add a website from template

- Status: complete.
- Evidence:
  - `docs/website-playbooks.md` documents copying
    `navigation_playbooks/_template.yaml`, filling landmarks and flows, and
    adding schema/compiler tests for the new playbook.
  - `navigation_playbooks/README.md` documents the catalog fields and new-site
    template path.
- Verification:
  - `rg -n "_template.yaml|landmarks|flows|schema/compiler tests"
    docs/website-playbooks.md navigation_playbooks/README.md`: matched the
    onboarding requirements.

### Task 189/211: All seven seed playbooks validate

- Status: complete.
- Evidence:
  - `tests/test_site_playbooks.py::test_all_seed_playbooks_validate` loads the
    seed catalog and asserts the seven supported site IDs.
  - The validation covers LinkedIn, X/Twitter, Instagram, Facebook, Medium,
    YouTube, and TikTok.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbooks.py -k
    "all_seed_playbooks_validate"`: 1 passed, 41 deselected.

### Task 190/211: Every seed playbook has a read-only navigation flow

- Status: complete.
- Evidence:
  - `tests/test_site_playbooks.py::test_every_seed_playbook_has_read_only_navigation_flow`
    iterates every seed playbook and requires at least one flow with no
    confirmation requirement and no sensitive category.
  - This keeps the seed catalog usable for deterministic read-only navigation and
    opt-in smoke checks.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbooks.py -k
    "every_seed_playbook_has_read_only_navigation_flow"`: 1 passed,
    41 deselected.

### Task 191/211: Seed sensitive actions require explicit confirmation

- Status: complete.
- Evidence:
  - `tests/test_site_playbooks.py::test_seed_sensitive_actions_require_confirmation`
    iterates every seed flow and checks each step with `sensitive_category`.
  - The assertions require `requires_confirmation` to be true for every
    sensitive seed action.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbooks.py -k
    "seed_sensitive_actions_require_confirmation"`: 1 passed, 41 deselected.

### Task 192/211: Compiled flows pass the existing task validator

- Status: complete.
- Evidence:
  - `tests/test_site_playbooks.py::test_all_seed_flows_compile_and_validate`
    compiles every flow from every seed playbook.
  - Each compiled task is validated with `BasicTaskValidator`, keeping the
    playbook compiler inside the existing task validation pipeline.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbooks.py -k
    "all_seed_flows_compile_and_validate"`: 1 passed, 41 deselected.

### Task 193/211: Normal CI remains deterministic without live public sites

- Status: complete.
- Evidence:
  - Phase 7 full-suite verification ran normal CI with live-site smoke skipped.
  - `tests/test_site_playbook_live_smoke.py::test_live_site_smoke_tests_require_explicit_environment_flag`
    skips unless `DESKPILOT_LIVE_SITE_SMOKE=1` is set.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_live_smoke.py -k
    "require_explicit_environment_flag"`: 1 skipped, 9 deselected.

### Task 194/211: Opt-in live smoke tests can run manually

- Status: complete.
- Evidence:
  - `tests/test_site_playbook_live_smoke.py` can be run with
    `DESKPILOT_LIVE_SITE_SMOKE=1`.
  - The file validates the explicit opt-in gate and every seed site's read-only
    smoke flow selection.
- Verification:
  - `env DESKPILOT_LIVE_SITE_SMOKE=1 .venv/bin/pytest
    tests/test_site_playbook_live_smoke.py`: 10 passed.

### Task 195/211: Failed site runs produce clear local traces and final reports

- Status: complete.
- Evidence:
  - `tests/test_site_playbook_tracing.py::test_blocked_state_reason_appears_in_final_report`
    verifies failed blocked-state site runs carry the reason in
    `final-report.json`.
  - `tests/test_site_playbook_tracing.py::test_blocked_state_check_outcome_appears_in_trace`
    verifies the trace action log records the blocked-state check outcome.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_tracing.py -k
    "blocked_state_reason_appears_in_final_report or blocked_state_check_outcome_appears_in_trace"`:
    2 passed, 8 deselected.

## Phase 8 Verification

- Status: complete.
- Scope:
  - Acceptance criteria for new-site onboarding, seed validation, read-only
    coverage, sensitive confirmations, compiled task validation, deterministic
    CI, opt-in live smoke, and failed-run reports are checked.
  - Roadmap implementation count is `195/211`.
- Verification:
  - `.venv/bin/pytest`: 327 passed, 4 skipped.
  - `.venv/bin/ruff check .`: all checks passed.
  - `.venv/bin/mypy`: no issues found in 71 source files.
  - `.venv/bin/python -m build`: built `deskpilot-0.1.0.tar.gz` and
    `deskpilot-0.1.0-py3-none-any.whl`.

## Phase 9 Audit

- Status: ready to execute.
- Roadmap range: Tasks 196-202 of 211.
- Current implementation surfaces:
  - `src/desktop_agent/approval_manifest.py` defines the manifest contract,
    validation, metadata, required-manifest gate, and runtime confirmation merge.
  - `src/desktop_agent/cli.py` exposes `--approval-manifest` for site runs.
  - `tests/test_approval_manifest.py`, `tests/test_site_playbook_cli.py`, and
    `tests/test_examples.py` cover missing, invalid, accepted, recorded, and
    sample-manifest behavior.
  - `docs/website-playbooks.md`, `docs/safety.md`, `docs/troubleshooting.md`,
    `docs/tracing.md`, and `examples/README.md` document usage and evidence.
- Audit decision:
  - Verify each approval-manifest roadmap item with focused tests or doc lookups
    before checking it.
