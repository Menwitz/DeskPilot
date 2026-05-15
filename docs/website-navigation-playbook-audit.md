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
