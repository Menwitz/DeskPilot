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

### Task 60/122: Define blocked states for each seed playbook

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

### Task 61/122: Define logged-out blocked states

- Status: complete.
- Evidence:
  - Every seed playbook defines `logged-out`.
  - Detectors use site-specific visible text such as `Sign in` or `Log in`.
  - Reasons direct the operator to authenticate manually instead of automating
    credentials.
- Verification:
  - Loaded all seed playbooks and printed the `logged-out` detector and reason
    for each site.

### Task 62/122: Define consent or cookie interstitial blocked states

- Status: complete.
- Evidence:
  - Every seed playbook defines `consent`.
  - Detectors use site-specific consent text such as `Accept cookies`,
    `Allow all cookies`, `Accept`, `Accept all`, `cookie`, or `I agree`.
  - Reasons require manual resolution of the cookie or consent dialog.
- Verification:
  - Loaded all seed playbooks and printed the `consent` detector and reason for
    each site.

### Task 63/122: Define CAPTCHA or suspicious-activity blocked states

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

### Task 64/122: Define permission or account-restriction blocked states

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

### Task 65/122: Define unsupported-layout blocked states

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

### Task 66/122: Define ambiguous-target blocked states

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

### Task 67/122: Add `SiteTaskCompiler`

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

### Task 68/122: Compile domains and window-title patterns into `allowed_windows`

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

### Task 69/122: Compile playbook steps into existing task actions

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

### Task 70/122: Compile `click_text`

- Status: complete.
- Evidence:
  - The action regression matrix includes a `click_text` site step with a
    `target` value.
  - `SiteTaskCompiler` preserves the action and target in the compiled
    `TaskStep`, and `BasicTaskValidator` accepts the result.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbooks.py -k "supported_task_actions
    and click_text"`: 1 passed, 32 deselected.

### Task 71/122: Compile `click_image`

- Status: complete.
- Evidence:
  - The action regression matrix includes a `click_image` site step with an
    image path.
  - `SiteTaskCompiler` converts the image value into the compiled `TaskStep`
    image field, and `BasicTaskValidator` accepts the result.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbooks.py -k "supported_task_actions
    and click_image"`: 1 passed, 32 deselected.

### Task 72/122: Compile `click_uia`

- Status: complete.
- Evidence:
  - The action regression matrix includes a `click_uia` site step with a UIA
    target.
  - `SiteTaskCompiler` preserves the `click_uia` action and target in the
    compiled `TaskStep`, and `BasicTaskValidator` accepts the result.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbooks.py -k "supported_task_actions
    and click_uia"`: 1 passed, 32 deselected.

### Task 73/122: Compile `type_text`

- Status: complete.
- Evidence:
  - The action regression matrix includes a `type_text` site step with text.
  - `SiteTaskCompiler` preserves the text payload in the compiled `TaskStep`,
    and `BasicTaskValidator` accepts the result.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbooks.py -k "supported_task_actions
    and type_text"`: 1 passed, 32 deselected.

### Task 74/122: Compile `press_key`

- Status: complete.
- Evidence:
  - The action regression matrix includes a `press_key` site step with key text.
  - `SiteTaskCompiler` preserves the key text in the compiled `TaskStep`, and
    `BasicTaskValidator` accepts the result.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbooks.py -k "supported_task_actions
    and press_key"`: 1 passed, 32 deselected.

### Task 75/122: Compile `scroll`

- Status: complete.
- Evidence:
  - The action regression matrix includes a `scroll` site step.
  - `SiteTaskCompiler` preserves the `scroll` action in the compiled `TaskStep`,
    and `BasicTaskValidator` accepts the result.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbooks.py -k "supported_task_actions
    and scroll and not scroll_until"`: 1 passed, 32 deselected.

### Task 76/122: Compile `scroll_until`

- Status: complete.
- Evidence:
  - The action regression matrix includes a `scroll_until` site step.
  - The playbook flow supplies a `search_region`, which `SiteTaskCompiler`
    carries into the compiled `TaskStep.region`.
  - `BasicTaskValidator` accepts the compiled result.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbooks.py -k "supported_task_actions
    and scroll_until"`: 1 passed, 32 deselected.

### Task 77/122: Compile `wait_for`

- Status: complete.
- Evidence:
  - The action regression matrix includes a `wait_for` site step with a target.
  - `SiteTaskCompiler` preserves the target in the compiled `TaskStep`, and
    `BasicTaskValidator` accepts the result.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbooks.py -k "supported_task_actions
    and wait_for and not branch_if_visible"`: 1 passed, 32 deselected.

### Task 78/122: Compile `assert_visible`

- Status: complete.
- Evidence:
  - The action regression matrix includes an `assert_visible` site step with a
    target.
  - `SiteTaskCompiler` preserves the target in the compiled `TaskStep`, and
    `BasicTaskValidator` accepts the result.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbooks.py -k "supported_task_actions
    and assert_visible"`: 1 passed, 32 deselected.

### Task 79/122: Compile `branch_if_visible`

- Status: complete.
- Evidence:
  - The action regression matrix includes a `branch_if_visible` site step with a
    target and `on_failure` fallback.
  - `SiteTaskCompiler` preserves the target and fallback in the compiled
    `TaskStep`, and `BasicTaskValidator` accepts the result.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbooks.py -k "supported_task_actions
    and branch_if_visible"`: 1 passed, 32 deselected.

### Task 80/122: Preserve confirmation requirements for sensitive steps

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

### Task 81/122: Add flow-level defaults

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

### Task 82/122: Compile flow timeout defaults

- Status: complete.
- Evidence:
  - `SiteTaskCompiler` assigns `flow.timeout_seconds` to
    `TaskDefinition.timeout_seconds`, with a safe default when omitted.
  - Regression coverage mutates a flow timeout to `45` and asserts the compiled
    task timeout is `45`.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbooks.py -k
    "flow_timeout_compiles_to_task_timeout"`: 1 passed, 32 deselected.

### Task 83/122: Compile flow retry budget defaults

- Status: complete.
- Evidence:
  - `SiteTaskCompiler` assigns `flow.retry` to compiled steps that do not set an
    explicit step retry.
  - Regression coverage mutates a flow retry budget to `3` and asserts the
    compiled step retry is `3`.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbooks.py -k
    "flow_retry_defaults_compile_to_steps"`: 1 passed, 32 deselected.

### Task 84/122: Compile flow confidence threshold defaults

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

### Task 85/122: Compile optional search region defaults

- Status: complete.
- Evidence:
  - `SiteTaskCompiler` assigns `flow.search_region` to compiled step `region`.
  - The `scroll_until` action regression supplies a flow-level search region
    and asserts the compiled step preserves the region width.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbooks.py -k "supported_task_actions
    and scroll_until"`: 1 passed, 33 deselected.

### Task 86/122: Add blocked-state checks before irreversible actions

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

### Task 87/122: Add task metadata for trace readability

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

### Task 88/122: Add site ID metadata

- Status: complete.
- Evidence:
  - Compiled task metadata includes `site_id`.
  - Compiled step metadata also includes `site_id`.
  - Tracing/report coverage verifies site ID is present in final report
    metadata for site-playbook runs.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_tracing.py -k
    "final_report_includes_site_id_and_flow_id"`: 1 passed, 4 deselected.

### Task 89/122: Add flow ID metadata

- Status: complete.
- Evidence:
  - Compiled task metadata includes `site_flow_id`.
  - Compiled step metadata also includes `site_flow_id`.
  - Tracing/report coverage verifies flow ID is present in final report metadata
    for site-playbook runs.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_tracing.py -k
    "final_report_includes_site_id_and_flow_id"`: 1 passed, 4 deselected.

### Task 90/122: Add domain metadata

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

### Task 91/122: Add sensitive step ID metadata

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

### Task 92/122: Add playbook version metadata

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

### Task 93/122: Add `desktop-agent list-sites`

- Status: complete.
- Evidence:
  - The CLI parser registers `list-sites`.
  - `_list_sites()` loads the playbook catalog and prints each site ID.
  - Regression coverage asserts all seven seed site IDs are printed.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_cli.py -k
    "list_sites_prints_all_seed_sites"`: 1 passed, 6 deselected.

### Task 94/122: Add `desktop-agent list-flows <site>`

- Status: complete.
- Evidence:
  - The CLI parser registers `list-flows` with a required site argument.
  - `_list_flows()` loads the named site and prints flow IDs with descriptions.
  - Regression coverage asserts LinkedIn flow output includes `open-search` and
    its description.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_cli.py -k
    "list_flows_linkedin_prints_flows"`: 1 passed, 6 deselected.

### Task 95/122: Add `desktop-agent compile-site <site> <flow> --output <task.yaml>`

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

### Task 96/122: Add `desktop-agent run-site <site> <flow>`

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

### Task 97/122: Add `desktop-agent dry-run-site <site> <flow>`

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

### Task 98/122: Support existing runtime safety flags

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

### Task 99/122: Support `--config`

- Status: complete.
- Evidence:
  - `--config` is registered through `_add_runtime_options()`.
  - `_run_loaded_task()` loads the provided config path through
    `YamlConfigLoader`.
  - The runtime-flag regression passes a config file to `dry-run-site`.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_cli.py -k
    "dry_run_site_accepts_runtime_safety_flags"`: 1 passed, 7 deselected.

### Task 100/122: Support `--verbose`

- Status: complete.
- Evidence:
  - `--verbose` is registered through `_add_runtime_options()`.
  - `_print_report()` emits event details when verbose mode is enabled.
  - The runtime-flag regression passes `--verbose` and asserts event output is
    present.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_cli.py -k
    "dry_run_site_accepts_runtime_safety_flags"`: 1 passed, 7 deselected.

### Task 101/122: Support `--no-screenshots`

- Status: complete.
- Evidence:
  - `--no-screenshots` is registered through `_add_runtime_options()`.
  - `_cli_overrides_from_args()` maps it to `save_screenshots=False`.
  - The runtime-flag regression passes `--no-screenshots` to `dry-run-site`.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_cli.py -k
    "dry_run_site_accepts_runtime_safety_flags"`: 1 passed, 7 deselected.

### Task 102/122: Support `--max-runtime-seconds`

- Status: complete.
- Evidence:
  - `--max-runtime-seconds` is registered through `_add_runtime_options()`.
  - `_cli_overrides_from_args()` maps it to `max_runtime_seconds`.
  - The runtime-flag regression passes `--max-runtime-seconds 5`.
- Verification:
  - `.venv/bin/pytest tests/test_site_playbook_cli.py -k
    "dry_run_site_accepts_runtime_safety_flags"`: 1 passed, 7 deselected.
