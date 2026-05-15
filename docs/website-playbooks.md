# Website Playbooks

Website playbooks define authorized public-site navigation in a catalog format
that compiles into the existing DeskPilot task DSL. They do not replace task
YAML; they provide a safer, reusable layer for common site navigation flows.

For an end-to-end demonstration of the implemented capabilities, see
[Website Playbook Capability Demo](website-playbook-demo.md).

## Authoring Rules

- Use a slug-safe `site_id`, for example `example-site`.
- Declare at least one domain and one allowed window-title pattern.
- Define landmarks for stable navigation labels or selectors.
- Keep read-only navigation flows separate from sensitive flows.
- Mark every sensitive step with `requires_confirmation: true` and a
  `sensitive_category`.
- Add blocked states for logged-out sessions, consent dialogs, CAPTCHA or
  suspicious-activity challenges, permission restrictions, unsupported layouts,
  and ambiguous targets.
- Keep live checks opt-in; normal CI must validate playbooks and compiled tasks
  without contacting public websites.

## New-Site Checklist

- Copy `navigation_playbooks/_template.yaml` to
  `navigation_playbooks/<site-id>.yaml`.
- Fill in `site_id`, `version`, `domains`, and `allowed_window_titles`.
- Add landmarks for home/feed, search, profile or channel, notifications,
  settings, and composer/upload/editor surfaces when the site has them.
- Add message navigation only when the site has a message surface.
- Add blocked-state detectors and user-facing reasons.
- Compile at least one read-only flow with `desktop-agent compile-site`.
- Add or update schema/compiler tests for the new playbook.
- Run normal CI without live-site dependencies.

## Read-Only Navigation Flow

```yaml
flows:
  - id: open-home
    description: Open the site feed without changing account state.
    timeout_seconds: 30
    retry: 1
    steps:
      - id: open-home
        action: click_text
        landmark: home
```

## Search Flow

```yaml
landmarks:
  - id: search
    action: click_text
    target: Search
flows:
  - id: open-search
    description: Open search without submitting a query.
    timeout_seconds: 30
    steps:
      - id: open-search
        action: click_text
        landmark: search
```

## Composer-Open Flow

```yaml
landmarks:
  - id: composer
    action: click_text
    target: Write
flows:
  - id: open-editor
    description: Open the editor without publishing.
    timeout_seconds: 30
    steps:
      - id: open-editor
        action: click_text
        landmark: composer
```

## Sensitive Confirmed Flow

```yaml
flows:
  - id: publish-post
    description: Requires explicit operator confirmation.
    timeout_seconds: 30
    steps:
      - id: publish-post
        action: click_text
        landmark: publish
        requires_confirmation: true
        sensitive_category: publish
```

Run it only after reviewing the task and confirming the exact step:

```bash
desktop-agent dry-run-site example-site publish-post --confirm-step publish-post
```

## Blocked-State Detection

```yaml
blocked_states:
  - id: captcha
    detector: "visible_text:challenge"
    reason: CAPTCHA or suspicious-activity challenges are not automated.
  - id: ambiguous-target
    detector: "candidate_count:>1"
    reason: Multiple matching targets require a narrower flow or manual choice.
```

Blocked states are stop conditions. They should explain what the operator must
resolve manually; they must not describe bypasses.
