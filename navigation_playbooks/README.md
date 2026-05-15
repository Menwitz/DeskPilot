# Website Navigation Playbooks

This catalog contains public-site navigation playbooks that compile into the
existing DeskPilot task DSL. Playbooks are for operator-authorized sessions only:
they must not bypass CAPTCHA or bot detection, hide automation, abuse
credentials, or perform sensitive website actions without explicit step
confirmation.

Each playbook defines:

- `site_id`: a slug-safe site identifier.
- `domains`: recognized hosts for the site.
- `allowed_window_titles`: title patterns passed into task safety checks.
- `landmarks`: reusable navigation targets.
- `flows`: read-only or confirmation-gated navigation sequences.
- `blocked_states`: known states where execution must stop or report a clear
  reason.

Copy `_template.yaml` when adding a new site, keep normal CI deterministic, and
put any live checks behind an explicit opt-in flag.

## Domain Scope

Every seed playbook declares a primary public domain and any common alternate
domain that is needed for recognition, such as legacy, regional, messaging, or
creator-studio hosts. Account or auth-related domains should appear only when a
playbook needs them to recognize an allowed settings or account surface.
