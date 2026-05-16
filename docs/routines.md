# Routines

Routine definitions are the reviewed catalog records that sit above task YAML
and website playbooks. A routine definition describes what the routine is for,
what it needs, what it produces, how risky it is, and which executable task or
playbook flow implements it.

## Schema

```yaml
id: browser.search
name: Browser search
description: Search from a browser input.
goal: Submit a search query and verify results.
required_app: Microsoft Edge
required_site: example.com
tags:
  - browser
  - search
inputs:
  - query
outputs:
  - results page
safety_class: low
schedule_policy: manual
approval_policy: none
expected_duration_seconds: 30
reference:
  type: task
  path: tasks/browser-search.yaml
```

`reference` can point at task YAML:

```yaml
reference:
  type: task
  path: tasks/browser-search.yaml
```

Or at an existing website playbook flow:

```yaml
reference:
  type: playbook
  site: linkedin
  flow: open-search
```

The schema is implemented by `desktop_agent.routines.RoutineDefinition`.
Supported safety classes are `low`, `medium`, `high`, and `sensitive`.
Supported schedule policies are `manual`, `on_demand`, and `scheduled`.
Supported approval policies are `none`, `confirm`, `manifest_required`, and
`manual_handoff`.

`RoutineDefinition.report_metadata()` returns JSON-safe fields for future trace,
monitoring, search, and catalog quality reports.

## Catalog Loading

Routine catalogs load files named `*.routine.yaml` or `*.routine.yml` under
`routine_packs/`:

```python
from pathlib import Path

from desktop_agent.routines import load_routine_catalog

catalog = load_routine_catalog(Path("routine_packs"))
results = catalog.search("browser search")
```

The catalog validator rejects duplicate routine IDs and reuses the
`RoutineDefinition` validation rules for every loaded file. Search is a local
token index over routine IDs, names, tags, required app/site, description, goal,
inputs, and outputs.

## CLI

Routine catalog commands use `routine_packs/` by default and accept
`--routine-pack-root` for tests or alternate catalogs.

```bash
desktop-agent list-routines
desktop-agent list-routines --query "browser search"
desktop-agent show-routine browser.search
desktop-agent compile-routine browser.search --output traces/browser-search.yaml
desktop-agent export-routine browser.search --output traces/browser-search.routine.yaml
desktop-agent dry-run-routine browser.search --no-screenshots
desktop-agent run-routine browser.search
```

`compile-routine`, `dry-run-routine`, and `run-routine` attach
`RoutineDefinition.report_metadata()` to the resulting task so traces and
reports preserve the routine ID, safety class, policies, and reference kind.
