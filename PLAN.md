# Desktop Automation Agent v1 Roadmap

## 0. Project Definition

- [x] Create a new standalone repository named normally, without `codex` in the branch or repo naming.
- [x] Define v1 as a Windows-first, local desktop automation framework.
- [x] Define the core use case as owned/internal QA and personal automation.
- [x] Exclude stealth automation, CAPTCHA bypass, bot-detection evasion, credential abuse, and abusive third-party automation.
- [x] Require v1 to run on an unlocked, logged-in Windows desktop session.
- [x] Keep all screenshots, OCR text, traces, and reports local by default.
- [x] Use Python 3.12 as the implementation language.
- [x] Use YAML as the v1 task authoring format.
- [x] Use deterministic task execution plus CV/OCR/UI Automation, with no cloud AI dependency in v1.

## 1. Repository Bootstrap

- [x] Add `README.md` with project purpose, constraints, quickstart, and safety boundaries.
- [x] Add `pyproject.toml` configured for Python 3.12.
- [x] Add `src/desktop_agent/` package.
- [x] Add `tests/` directory.
- [x] Add `examples/` directory.
- [x] Add `docs/architecture.md`.
- [x] Add `docs/task-dsl.md`.
- [x] Add `docs/safety.md`.
- [x] Add `docs/roadmap.md`.
- [x] Add `.gitignore` for Python caches, traces, screenshots, packaged builds, virtualenvs, and local config.
- [x] Configure `uv` for dependency management.
- [x] Configure `pytest`.
- [x] Configure `ruff` for linting and formatting.
- [x] Configure `mypy` for type checking.
- [x] Configure GitHub Actions for lint, type check, and tests.
- [x] Add comments only where code behavior is non-obvious, especially around safety, retries, coordinate transforms, and perception fusion.

## 2. Target Architecture

- [x] Implement the system as separate modules:
  - [x] `cli`
  - [x] `config`
  - [x] `task_dsl`
  - [x] `screen`
  - [x] `perception`
  - [x] `actuation`
  - [x] `planner`
  - [x] `safety`
  - [x] `tracing`
  - [x] `platforms/windows`
  - [x] `platforms/linux_placeholder`
- [x] Define the main execution loop:
  - [x] Load config.
  - [x] Load task YAML.
  - [x] Validate task.
  - [x] Prepare trace directory.
  - [x] Check safety preconditions.
  - [x] Observe screen.
  - [x] Detect candidate UI elements.
  - [x] Select target.
  - [x] Execute action.
  - [x] Verify result.
  - [x] Retry, recover, or abort.
  - [x] Write final report.
- [x] Define all platform-specific behavior behind interfaces so Linux can be added later.

## 3. CLI

- [x] Add command: `desktop-agent run <task.yaml> --config <config.yaml>`.
- [x] Add command: `desktop-agent dry-run <task.yaml> --config <config.yaml>`.
- [x] Add command: `desktop-agent inspect-screen --output <trace-dir>`.
- [x] Add command: `desktop-agent replay <trace-dir>`.
- [x] Add `--verbose`.
- [x] Add `--no-screenshots`.
- [x] Add `--max-runtime-seconds`.
- [x] Add `--confidence-threshold`.
- [x] Add `--allowed-window`.
- [x] Ensure CLI exits with nonzero status on failed task execution.
- [x] Ensure every CLI failure prints a clear human-readable reason.

## 4. Configuration

- [x] Support project-level config file.
- [x] Support task-level config overrides.
- [x] Support CLI overrides.
- [x] Define precedence: CLI > task YAML > config file > defaults.
- [x] Add config fields:
  - [x] `default_timeout_seconds`
  - [x] `confidence_threshold`
  - [x] `max_steps`
  - [x] `max_retries_per_step`
  - [x] `max_runtime_seconds`
  - [x] `trace_root`
  - [x] `save_screenshots`
  - [x] `save_ocr_text`
  - [x] `allowed_windows`
  - [x] `emergency_stop_hotkey`
  - [x] `primary_monitor_only`
- [x] Validate config at startup.
- [x] Reject unsafe config values such as zero timeouts, negative retries, or missing safety limits.

## 5. YAML Task DSL

- [x] Define a strict YAML schema.
- [x] Require every task to have:
  - [x] `name`
  - [x] `allowed_windows`
  - [x] `timeout_seconds`
  - [x] `steps`
- [x] Require every step to have:
  - [x] `id`
  - [x] `action`
- [x] Support optional step fields:
  - [x] `target`
  - [x] `text`
  - [x] `image`
  - [x] `region`
  - [x] `verify`
  - [x] `timeout_seconds`
  - [x] `retry`
  - [x] `on_failure`
- [x] Implement actions:
  - [x] `click_text`
  - [x] `click_image`
  - [x] `click_uia`
  - [x] `type_text`
  - [x] `press_key`
  - [x] `scroll`
  - [x] `scroll_until`
  - [x] `wait_for`
  - [x] `assert_visible`
  - [x] `branch_if_visible`
  - [x] `drag`
- [x] Implement verification types:
  - [x] `visible_text`
  - [x] `not_visible_text`
  - [x] `visible_image`
  - [x] `focused`
  - [x] `window_title_contains`
  - [x] `uia_element_exists`
- [x] Validate duplicate step IDs.
- [x] Validate references to missing image templates.
- [x] Validate unknown actions.
- [x] Validate unknown verification types.
- [x] Document complete task examples in `docs/task-dsl.md`.

## 6. Screen Layer

- [x] Implement screenshot capture using `mss`.
- [x] Capture full primary monitor.
- [x] Capture active window region.
- [x] Save raw screenshots to trace directory when enabled.
- [x] Detect monitor dimensions.
- [x] Detect Windows DPI scaling.
- [x] Normalize coordinates between screenshot space and physical mouse space.
- [x] Add a clear warning when multiple monitors are detected but v1 is using primary monitor only.
- [x] Detect locked or unavailable desktop session and abort cleanly.
- [x] Add tests for coordinate normalization using synthetic monitor data.

## 7. Windows UI Automation Layer

- [x] Add Windows adapter using `pywinauto`.
- [x] Detect active window title and process.
- [x] Extract visible UIA elements.
- [x] Extract element name, control type, bounds, enabled state, and visible state.
- [x] Convert UIA elements into shared `ElementCandidate` objects.
- [x] Prefer UIA candidates over OCR/CV candidates when confidence is similar.
- [x] Add fallback behavior when UIA is unavailable or returns incomplete data.
- [x] Add inspection output for UIA tree snapshots.
- [x] Add tests using mocked UIA element data.

## 8. OCR Layer

- [x] Add offline OCR adapter.
- [x] Normalize OCR output into text candidates with bounds and confidence.
- [x] Support case-insensitive matching.
- [x] Support exact text matching.
- [x] Support contains matching.
- [x] Support simple fuzzy matching.
- [x] Filter OCR candidates below confidence threshold.
- [x] Save OCR text output to trace directory when enabled.
- [x] Add OCR tests using saved fixture screenshots.
- [x] Document OCR limitations around fonts, scaling, themes, and partial visibility.

## 9. Computer Vision Layer

- [x] Add OpenCV template matching.
- [x] Support image templates from `examples/assets/` or task-relative paths.
- [x] Return image candidates with bounds and confidence.
- [x] Support target region restriction.
- [x] Support grayscale matching.
- [x] Support scale-tolerant matching as a later v1 enhancement.
- [x] Save detection overlays to trace directory.
- [x] Add tests for template matching with fixture screenshots.
- [x] Document when image matching should be used instead of text/UIA.

## 10. Candidate Fusion

- [x] Define shared candidate model:
  - [x] `id`
  - [x] `source`
  - [x] `label`
  - [x] `bounds`
  - [x] `confidence`
  - [x] `visible`
  - [x] `enabled`
  - [x] `metadata`
- [x] Merge candidates from UIA, OCR, and template matching.
- [x] Deduplicate overlapping candidates.
- [x] Rank candidates by source reliability, confidence, visibility, and target match quality.
- [x] Reject ambiguous candidates unless the task provides a region or selector.
- [x] Include candidate ranking in trace logs.
- [x] Add unit tests for candidate ranking, deduplication, and ambiguity rejection.

## 11. Actuation Layer

- [x] Implement mouse move.
- [x] Implement click.
- [x] Implement double click.
- [x] Implement drag.
- [x] Implement scroll.
- [x] Implement keyboard typing.
- [x] Implement key press and key chord.
- [x] Add smooth movement using curved paths and acceleration/deceleration.
- [x] Add configurable movement duration.
- [x] Add tiny timing variation for natural reliability, not stealth.
- [x] Verify target window is still allowed immediately before every action.
- [x] Add fake input adapter for tests.
- [x] Add comments explaining coordinate conversion and safety checks.

## 12. Planner And Execution Engine

- [x] Implement step executor.
- [x] Implement per-step timeout.
- [x] Implement per-step retry budget.
- [x] Implement task-level timeout.
- [x] Implement max action count.
- [x] Implement abort reasons.
- [x] Implement verification after each action when configured.
- [x] Implement `wait_for` polling.
- [x] Implement `scroll_until` loop with max scroll count.
- [x] Implement `branch_if_visible` with explicit branch targets.
- [x] Implement recovery actions:
  - [x] wait and re-observe;
  - [x] refocus allowed window;
  - [x] scroll search region;
  - [x] retry alternate candidate;
  - [x] abort with trace.
- [x] Ensure every failure path writes enough trace data to debug the run.

## 13. Safety System

- [x] Require allowed window/app whitelist for every task.
- [x] Block actions when active window does not match whitelist.
- [x] Add global emergency stop hotkey.
- [x] Add task-level max runtime.
- [x] Add task-level max steps.
- [x] Add per-step retry limit.
- [x] Add confidence threshold enforcement.
- [x] Add dry-run mode that validates and plans without moving the mouse.
- [x] Add clear warning that v1 does not support locked-screen background automation.
- [x] Add local-only trace policy.
- [x] Add safety documentation in `docs/safety.md`.

## 14. Tracing And Reports

- [x] Create one trace directory per run.
- [x] Save normalized task config.
- [x] Save action log as JSONL.
- [x] Save final report as JSON.
- [x] Save human-readable report as HTML or Markdown.
- [x] Save screenshots before and after each step when enabled.
- [x] Save OCR output when enabled.
- [x] Save candidate overlays when enabled.
- [x] Include final status:
  - [x] passed;
  - [x] failed;
  - [x] aborted;
  - [x] emergency_stopped.
- [x] Include abort reason.
- [x] Include step timings.
- [x] Include candidate confidence values.
- [x] Implement `replay` command that summarizes a trace without rerunning actions.

## 15. Example Workflows

- [x] Create browser fixture HTML app.
- [x] Add browser task that:
  - [x] opens or targets browser window;
  - [x] clicks email field;
  - [x] types email;
  - [x] scrolls to submit button;
  - [x] clicks submit;
  - [x] verifies success text.
- [x] Create native Windows fixture app.
- [x] Add native task that:
  - [x] targets app window;
  - [x] clicks text input;
  - [x] types text;
  - [x] clicks button;
  - [x] opens menu;
  - [x] verifies changed state.
- [x] Create mixed workflow task that:
  - [x] interacts with browser fixture;
  - [x] switches to native fixture;
  - [x] completes a final verification.
- [x] Keep all demo workflows deterministic and safe.

## 16. Packaging

Current status: implementation assets are complete; executable build and packaged
runtime verification require Windows because PyInstaller cannot produce a
Windows desktop executable from this macOS workspace.

- [x] Add PyInstaller config.
- [ ] Package Windows executable. **Blocked: requires Windows.**
- [x] Include default config template.
- [x] Include example tasks.
- [x] Include troubleshooting docs.
- [ ] Verify packaged executable can run `--help`. **Blocked: requires Windows package.**
- [ ] Verify packaged executable can run `dry-run`. **Blocked: requires Windows package.**
- [ ] Verify packaged executable can run demo task on a logged-in Windows desktop. **Blocked: requires unlocked Windows desktop.**

## 17. Testing

- [x] Add unit tests for config precedence.
- [x] Add unit tests for YAML validation.
- [x] Add unit tests for invalid task failures.
- [x] Add unit tests for candidate ranking.
- [x] Add unit tests for retry policy.
- [x] Add unit tests for timeout handling.
- [x] Add unit tests for safety aborts.
- [x] Add unit tests for coordinate normalization.
- [x] Add OCR fixture tests.
- [x] Add template matching fixture tests.
- [x] Add fake-screen integration tests.
- [x] Add fake-input integration tests.
- [x] Add planner integration tests without real mouse movement.
- [x] Add manual Windows e2e checklist for real desktop execution.

## 18. V1 Acceptance Criteria

Current status: local implementation and local verification are complete. The
remaining unchecked acceptance items require real desktop input on an unlocked,
logged-in Windows session.

- [ ] `desktop-agent run` executes a YAML task end to end. **Blocked: requires unlocked Windows desktop.**
- [x] `desktop-agent dry-run` validates and explains the planned task without actions.
- [x] `desktop-agent inspect-screen` captures screenshot, OCR, UIA, and candidate data.
- [ ] Browser demo completes unattended on an unlocked Windows desktop. **Blocked: requires unlocked Windows desktop.**
- [ ] Native Windows demo completes unattended on an unlocked Windows desktop. **Blocked: requires unlocked Windows desktop.**
- [ ] Mixed demo completes unattended on an unlocked Windows desktop. **Blocked: requires unlocked Windows desktop.**
- [ ] Emergency hotkey stops execution within one second. **Blocked: requires unlocked Windows desktop.**
- [x] Failed runs produce useful screenshots, logs, candidates, and abort reason.
- [x] No cloud service is required.
- [x] No task can act outside the allowed window whitelist.
- [x] Documentation is sufficient for a new engineer to install, run, debug, and extend v1.

Windows-only acceptance items remain unchecked until they are verified on an unlocked, logged-in Windows desktop. Use `docs/windows-e2e-checklist.md` for the exact commands and expected evidence.

## 19. Post-v1 Backlog

Post-v1 items are intentionally future work, not unfinished v1 implementation.
They are triaged in `docs/post-v1-backlog.md` and should be promoted into a new
scoped implementation plan before becoming checklist tasks.

- Linux X11 adapter.
- Linux Wayland compatibility investigation.
- Visual task recorder.
- Optional local vision model.
- Optional cloud VLM adapter disabled by default.
- Redacted trace mode.
- Team report server.
- Remote worker orchestration.
- Rich desktop tray UI.
- More advanced recovery planning.
- Plugin system for app-specific task libraries.
