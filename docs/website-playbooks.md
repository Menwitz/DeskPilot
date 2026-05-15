# Website Playbooks

Website playbooks define authorized public-site navigation in a catalog format
that compiles into the existing DeskPilot task DSL. They do not replace task
YAML; they provide a safer, reusable layer for common site navigation flows.

For an end-to-end demonstration of the implemented capabilities, see
[Website Playbook Capability Demo](website-playbook-demo.md).

## Authoring Rules

- Use a slug-safe `site_id`, for example `example-site`.
- Declare at least one domain and one allowed window-title pattern. Plain
  title patterns match exact titles or case-insensitive substrings; use
  `regex:` only when a site needs a stable regular-expression boundary.
- Define landmarks for stable navigation labels or selectors.
- Keep read-only navigation flows separate from sensitive flows.
- Mark every sensitive step with `requires_confirmation: true` and a
  `sensitive_category`.
- Add blocked states for logged-out sessions, consent dialogs, CAPTCHA or
  suspicious-activity challenges, permission restrictions, unsupported layouts,
  and ambiguous targets.
- Keep live checks opt-in; normal CI must validate playbooks and compiled tasks
  without contacting public websites.

## Authoring Workflow

1. Start from `navigation_playbooks/_template.yaml` and save the copy as
   `navigation_playbooks/<site-id>.yaml`.
2. Fill the required top-level fields: `site_id`, `version`, `domains`,
   `allowed_window_titles`, `landmarks`, `flows`, and `blocked_states`.
3. Model landmarks before flows. Flow steps should reference a landmark whenever
   a stable label, selector, or image target can be reused across flows.
4. Add at least one read-only smoke flow before sensitive flows. Search,
   profile, channel, notification, editor, composer, upload, and settings
   surfaces should stop at navigation unless the operator explicitly approves a
   sensitive step.
5. Compile the flow with `desktop-agent compile-site <site-id> <flow-id>` and
   verify the generated task metadata, allowed-window rules, blocked-state
   checks, and final report fields.
6. Add regression coverage in `tests/test_site_playbooks.py`,
   `tests/test_site_playbook_cli.py`, `tests/test_site_playbook_safety.py`, or
   `tests/test_site_playbook_tracing.py` depending on the behavior changed.

```yaml
site_id: example-site
version: "1"
domains: []
allowed_window_titles: []
landmarks: []
flows: []
blocked_states: []
```

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
- Run `desktop-agent list-sites` and `desktop-agent list-flows <site-id>` to
  confirm catalog discovery.
- Dry-run the read-only smoke flow and inspect the trace directory, action log,
  and final reports for `site_id`, `site_flow_id`, blocked-state, and
  confirmation metadata.
- Add the site to `tests/test_site_playbook_live_smoke.py` only when the smoke
  flow is read-only and still skipped unless `DESKPILOT_LIVE_SITE_SMOKE=1`.
- Run normal CI without live-site dependencies.

## Examples

The examples below are minimal snippets that show the supported public-site
patterns: read-only navigation, search, composer/editor opening, confirmed
sensitive actions, and blocked-state detection. Keep examples small enough to
copy into tests, then validate the compiled task and generated trace/report
metadata before using them as live-site playbooks.
Search and deep-search examples should open discovery surfaces only; submitting
queries or changing site state belongs in a separate confirmed flow.

## Read-Only Navigation Flow

```yaml
landmarks:
  - id: home
    action: click_text
    target: Home
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

Use this pattern for search or deep-search discovery surfaces that should stop
before typing or submitting a query.

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

This flow opens the writing surface only. It must not include final `Post`,
`Publish`, `Send`, or `Submit` actions unless those actions move into a separate
confirmed sensitive flow.
Dry-run the composer-open flow and inspect the final report before adding any
publish-capable variant.

## Sensitive Confirmed Flow

```yaml
landmarks:
  - id: publish
    action: click_text
    target: Publish
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

Real `run-site` execution for this flow requires an approval manifest. Dry-run
and trace replay should show the sensitive step, confirmation state, and final
report metadata before any live run is attempted.

## Content Variables

Publish-capable playbooks can use `{{variable_name}}` placeholders in step
`target`, `text`, or `image` fields. Operators provide values through a local
YAML variables file, and the compiler resolves placeholders before execution.
The compiled task records variable names and a stable content fingerprint in
trace metadata, but treats the variable values as redacted content payloads.

```yaml
variables:
  post_text: "Reviewed launch note."
  post_url: "https://example.test/launch"
  post_tags:
    - "#ops"
    - "#automation"
```

```yaml
flows:
  - id: publish-post
    steps:
      - id: fill-post
        action: type_text
        text: "{{post_text}} {{post_url}} {{post_tags}}"
      - id: publish-post
        action: click_text
        target: Publish
        requires_confirmation: true
        sensitive_category: publish
```

```bash
desktop-agent compile-site example-site publish-post \
  --variables content.yaml \
  --output /private/tmp/example-publish.yaml
```

Run it only after reviewing the task and confirming the exact step:

```bash
desktop-agent dry-run-site example-site publish-post --confirm-step publish-post
```

For real `run-site` execution of a sensitive public-site flow, use an approval
manifest instead of an interactive prompt. The manifest is a local preapproval
record that names the site, flow, approved step IDs, approver, reason,
timestamp, and content fingerprint. DeskPilot validates it before real input is
sent, merges the approved step IDs into runtime confirmation, and records the
approval metadata in traces and final reports.

```yaml
site_id: example-site
flow_id: publish-post
approved_steps:
  - publish-post
approver: qa-lead@example.test
reason: Approved content workflow for the current run.
approved_at: 2026-05-15T00:00:00Z
content_fingerprint: reviewed-content-v1
```

```bash
desktop-agent run-site example-site publish-post \
  --variables content.yaml \
  --approval-manifest approval.yaml
```

## V1 Publish-Capable Seed Flows

Only `linkedin/publish-post` and `medium/publish-story` are publish-capable seed
flows in v1. Both flows use local YAML content variables, run blocked-state
checks before the final publish action, require confirmation on that final
action, and declare a checkpoint that must pass before input is sent. Real
`run-site` execution also requires a matching approval manifest.

Sample local payloads and manifests live in `examples/`:

- `examples/linkedin-content-variables.yaml`
- `examples/linkedin-approval-manifest.yaml`
- `examples/medium-content-variables.yaml`
- `examples/medium-approval-manifest.yaml`

All other seed sites remain limited to read-only navigation or opening a
composer/editor surface without submitting content.

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
When a blocked state fires, the trace and final report should include the
blocked-state ID and reason so monitoring and support review can diagnose the
stop without rerunning the site flow.
