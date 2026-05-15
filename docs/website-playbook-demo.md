# Website Playbook Capability Demo

This guide walks through a local demonstration of the website playbook work:
catalog discovery, flow compilation, dry-run planning, trace/report replay,
regression coverage, and optional real desktop execution.

The commands assume you are using the repository at
`/Users/roshi/Documents/DeskPilot`.

## Before You Start

Open a terminal and move into the project directory:

```bash
cd /Users/roshi/Documents/DeskPilot
```

Confirm you are in the right directory:

```bash
pwd
```

Expected output:

```text
/Users/roshi/Documents/DeskPilot
```

All commands below use the local virtual environment executable
`.venv/bin/desktop-agent`. That means you do not need to activate the virtual
environment first; the command points directly at the installed DeskPilot CLI.

Confirm the CLI is available:

```bash
.venv/bin/desktop-agent --help
```

You should see commands such as `list-sites`, `list-flows`, `compile-site`,
`dry-run-site`, `run-site`, and `replay`.

## 1. Show The Playbook Catalog

List every seed website playbook:

```bash
.venv/bin/desktop-agent list-sites
```

Expected sites:

```text
facebook
instagram
linkedin
medium
tiktok
x-twitter
youtube
```

This proves the playbook loader can find the catalog under
`navigation_playbooks/` and validate each seed site well enough to list it.

Now list flows for a few representative sites:

```bash
.venv/bin/desktop-agent list-flows linkedin
.venv/bin/desktop-agent list-flows youtube
.venv/bin/desktop-agent list-flows medium
```

Example LinkedIn output:

```text
open-home          Open the LinkedIn feed.
open-search        Open LinkedIn search without submitting a query.
open-profile       Open the profile menu or profile surface.
open-notifications Open notification navigation.
open-messages      Open LinkedIn messaging without sending content.
open-settings      Open account settings navigation.
open-composer      Open the post composer without publishing.
```

This demonstrates the site-specific flow registry. It also shows the separation
between read-only navigation flows, search flows, settings flows, message flows,
and composer/editor/upload flows.

## 2. Compile A Website Flow Into A Task

Compile YouTube's search navigation flow into a normal DeskPilot task YAML:

```bash
.venv/bin/desktop-agent compile-site youtube open-search --output /private/tmp/deskpilot-youtube-open-search.yaml
```

Expected output:

```text
compiled: youtube open-search
task: /private/tmp/deskpilot-youtube-open-search.yaml
```

Inspect the generated task:

```bash
sed -n '1,220p' /private/tmp/deskpilot-youtube-open-search.yaml
```

Look for these fields:

- `name: youtube:open-search`
- `allowed_windows` containing YouTube domains and window titles
- `steps` containing the compiled `click_text` navigation action
- `metadata.site_id: youtube`
- `metadata.site_flow_id: open-search`
- `metadata.site_playbook_validation_status: passed`
- `metadata.site_blocked_state_ids`
- `metadata.site_compiled_task_summary`

This proves the playbook compiler converts a reusable website flow into the
existing DeskPilot task DSL instead of creating a separate execution path.

## 3. Demonstrate Dry-Run Planning

Run a safe dry-run for Medium's editor-opening flow:

```bash
.venv/bin/desktop-agent dry-run-site medium open-editor
```

The command does not click your desktop. It validates the playbook, compiles the
flow, plans the step, and writes a trace.

Expected output includes:

```text
dry-run preview:
  policy preset: personal_automation
  step open-editor (click_text, navigation)
task: medium:open-editor
status: passed
trace: traces/<timestamp>-medium-open-editor
step open-editor: passed (planned click_text)
```

The exact trace directory changes every run because it includes a timestamp.
Copy the `trace:` value from your terminal for the replay step.

Now demonstrate a confirmation-aware flow:

```bash
.venv/bin/desktop-agent dry-run-site linkedin open-composer --confirm-step open-composer
```

This demonstrates the confirmation pipeline. The flow opens a composer surface
but does not publish, send, follow, delete, buy, or submit anything. Sensitive
steps in playbooks must be marked with confirmation metadata before they can run.

## 4. Replay A Trace And Inspect Reports

After a dry-run, replay the trace directory printed by the command. Replace
`<trace-dir>` with the path shown after `trace:`.

```bash
.venv/bin/desktop-agent replay traces/<trace-dir>
```

Example:

```bash
.venv/bin/desktop-agent replay traces/20260515T075014278952Z-medium-open-editor
```

Expected replay output:

```text
trace: traces/20260515T075014278952Z-medium-open-editor
site: medium
flow: open-editor
task: medium:open-editor
status: passed
```

List the files produced by the run:

```bash
ls -la traces/<trace-dir>
```

Important files:

- `task.json` shows the compiled task that was executed or planned.
- `action-log.jsonl` shows step-level events.
- `final-report.json` contains structured run metadata.
- `final-report.md` contains a human-readable report.
- `config.json` records the runtime configuration used for the run.

This demonstrates monitoring and reporting. The reports carry site metadata,
flow metadata, blocked-state metadata, and confirmation state so failures can be
debugged after the run.

## 5. Demonstrate Regression Coverage

Run the targeted website playbook test groups:

```bash
.venv/bin/pytest tests/test_site_playbooks.py
.venv/bin/pytest tests/test_site_playbook_cli.py
.venv/bin/pytest tests/test_site_playbook_safety.py
.venv/bin/pytest tests/test_site_playbook_tracing.py
.venv/bin/pytest tests/test_site_playbook_live_smoke.py
```

What these tests cover:

- schema validation and invalid-playbook rejection
- flow compilation into valid DeskPilot tasks
- CLI commands for listing, compiling, dry-running, and run failure behavior
- safety gates for sensitive actions and unsupported blocked states
- trace metadata in reports and replay output
- live-site smoke guard behavior without contacting public websites by default

Run the full local gate:

```bash
.venv/bin/pytest
.venv/bin/ruff check .
.venv/bin/mypy
.venv/bin/python -m build
```

This demonstrates that the website playbook implementation still passes the
project test suite, style checks, type checks, and package build.

## 6. Optional Live Desktop Demonstration

Only run live desktop commands when all of these are true:

- you are using an account/session you are authorized to automate;
- the target website is already open in an allowed browser window;
- macOS desktop automation permissions are enabled for the terminal or app;
- you are prepared for the run to stop on login, consent, CAPTCHA, permission,
  unsupported-layout, or ambiguous-target states.

Run a read-only search-navigation flow:

```bash
.venv/bin/desktop-agent run-site youtube open-search
```

Run a confirmation-aware composer flow:

```bash
.venv/bin/desktop-agent run-site linkedin open-composer --confirm-step open-composer
```

Expected safe behavior:

- The run acts only inside allowed windows for the target site.
- The run stops before unsupported states instead of attempting bypasses.
- The run writes a trace directory with `action-log.jsonl`,
  `final-report.json`, and `final-report.md`.
- Sensitive flows require explicit `--confirm-step` values.

If platform actuation is unavailable, `run-site` should return nonzero. That is
expected on machines without the required desktop permissions or automation
backend.

## 7. What Each Capability Proves

Catalog:

- `list-sites`
- `list-flows <site>`

These prove seed playbooks can be discovered, loaded, and exposed through the
CLI.

Compilation:

- `compile-site <site> <flow> --output <task.yaml>`

This proves website playbooks compile into existing DeskPilot task YAML with
allowed-window constraints, action steps, retry settings, blocked states, and
metadata.

Search and navigation:

- `open-search` flows on LinkedIn, YouTube, X/Twitter, Instagram, Facebook, and
  TikTok
- `open-editor` on Medium

These prove site-specific navigation flows can be represented without hardcoding
new task runner behavior.

Safety:

- blocked-state metadata in compiled tasks
- confirmation metadata on sensitive steps
- non-bypass policy in the playbook docs and validation tests

These prove the implementation stops on login walls, consent dialogs, CAPTCHA
or suspicious-activity challenges, permission restrictions, unsupported layouts,
and ambiguous targets.

Monitoring and reports:

- trace directories under `traces/`
- `desktop-agent replay <trace-dir>`
- `final-report.json`
- `final-report.md`

These prove site, flow, blocked-state, and confirmation information reaches the
reporting pipeline.

Regression tests:

- targeted `tests/test_site_playbook_*.py` files
- full pytest, ruff, mypy, and build gate

These prove the implementation is checkable and can be guarded against
regressions.

## Troubleshooting

If `.venv/bin/desktop-agent` is missing, confirm you are in the repository root:

```bash
pwd
ls -la .venv/bin/desktop-agent
```

If `replay` cannot find a trace, copy the exact value printed after `trace:` in
the dry-run output.

If a live `run-site` stops immediately, inspect the generated
`final-report.md`. Common causes are logged-out sessions, consent prompts,
permission restrictions, CAPTCHA or suspicious-activity challenges, unsupported
site layouts, and ambiguous targets.

If a dry-run passes but a live run fails, the playbook schema is valid and the
runner can plan the task, but the visible website state does not match the
landmarks expected by the playbook.
