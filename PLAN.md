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

- [ ] Add OpenCV template matching.
- [ ] Support image templates from `examples/assets/` or task-relative paths.
- [ ] Return image candidates with bounds and confidence.
- [ ] Support target region restriction.
- [ ] Support grayscale matching.
- [ ] Support scale-tolerant matching as a later v1 enhancement.
- [ ] Save detection overlays to trace directory.
- [ ] Add tests for template matching with fixture screenshots.
- [ ] Document when image matching should be used instead of text/UIA.

## 10. Candidate Fusion

- [ ] Define shared candidate model:
  - [ ] `id`
  - [ ] `source`
  - [ ] `label`
  - [ ] `bounds`
  - [ ] `confidence`
  - [ ] `visible`
  - [ ] `enabled`
  - [ ] `metadata`
- [ ] Merge candidates from UIA, OCR, and template matching.
- [ ] Deduplicate overlapping candidates.
- [ ] Rank candidates by source reliability, confidence, visibility, and target match quality.
- [ ] Reject ambiguous candidates unless the task provides a region or selector.
- [ ] Include candidate ranking in trace logs.
- [ ] Add unit tests for candidate ranking, deduplication, and ambiguity rejection.

## 11. Actuation Layer

- [ ] Implement mouse move.
- [ ] Implement click.
- [ ] Implement double click.
- [ ] Implement drag.
- [ ] Implement scroll.
- [ ] Implement keyboard typing.
- [ ] Implement key press and key chord.
- [ ] Add smooth movement using curved paths and acceleration/deceleration.
- [ ] Add configurable movement duration.
- [ ] Add tiny timing variation for natural reliability, not stealth.
- [ ] Verify target window is still allowed immediately before every action.
- [ ] Add fake input adapter for tests.
- [ ] Add comments explaining coordinate conversion and safety checks.

## 12. Planner And Execution Engine

- [ ] Implement step executor.
- [ ] Implement per-step timeout.
- [ ] Implement per-step retry budget.
- [ ] Implement task-level timeout.
- [ ] Implement max action count.
- [ ] Implement abort reasons.
- [ ] Implement verification after each action when configured.
- [ ] Implement `wait_for` polling.
- [ ] Implement `scroll_until` loop with max scroll count.
- [ ] Implement `branch_if_visible` with explicit branch targets.
- [ ] Implement recovery actions:
  - [ ] wait and re-observe;
  - [ ] refocus allowed window;
  - [ ] scroll search region;
  - [ ] retry alternate candidate;
  - [ ] abort with trace.
- [ ] Ensure every failure path writes enough trace data to debug the run.

## 13. Safety System

- [ ] Require allowed window/app whitelist for every task.
- [ ] Block actions when active window does not match whitelist.
- [ ] Add global emergency stop hotkey.
- [ ] Add task-level max runtime.
- [ ] Add task-level max steps.
- [ ] Add per-step retry limit.
- [ ] Add confidence threshold enforcement.
- [ ] Add dry-run mode that validates and plans without moving the mouse.
- [ ] Add clear warning that v1 does not support locked-screen background automation.
- [ ] Add local-only trace policy.
- [ ] Add safety documentation in `docs/safety.md`.

## 14. Tracing And Reports

- [ ] Create one trace directory per run.
- [ ] Save normalized task config.
- [ ] Save action log as JSONL.
- [ ] Save final report as JSON.
- [ ] Save human-readable report as HTML or Markdown.
- [ ] Save screenshots before and after each step when enabled.
- [ ] Save OCR output when enabled.
- [ ] Save candidate overlays when enabled.
- [ ] Include final status:
  - [ ] passed;
  - [ ] failed;
  - [ ] aborted;
  - [ ] emergency_stopped.
- [ ] Include abort reason.
- [ ] Include step timings.
- [ ] Include candidate confidence values.
- [ ] Implement `replay` command that summarizes a trace without rerunning actions.

## 15. Example Workflows

- [ ] Create browser fixture HTML app.
- [ ] Add browser task that:
  - [ ] opens or targets browser window;
  - [ ] clicks email field;
  - [ ] types email;
  - [ ] scrolls to submit button;
  - [ ] clicks submit;
  - [ ] verifies success text.
- [ ] Create native Windows fixture app.
- [ ] Add native task that:
  - [ ] targets app window;
  - [ ] clicks text input;
  - [ ] types text;
  - [ ] clicks button;
  - [ ] opens menu;
  - [ ] verifies changed state.
- [ ] Create mixed workflow task that:
  - [ ] interacts with browser fixture;
  - [ ] switches to native fixture;
  - [ ] completes a final verification.
- [ ] Keep all demo workflows deterministic and safe.

## 16. Packaging

- [ ] Add PyInstaller config.
- [ ] Package Windows executable.
- [ ] Include default config template.
- [ ] Include example tasks.
- [ ] Include troubleshooting docs.
- [ ] Verify packaged executable can run `--help`.
- [ ] Verify packaged executable can run `dry-run`.
- [ ] Verify packaged executable can run demo task on a logged-in Windows desktop.

## 17. Testing

- [ ] Add unit tests for config precedence.
- [ ] Add unit tests for YAML validation.
- [ ] Add unit tests for invalid task failures.
- [ ] Add unit tests for candidate ranking.
- [ ] Add unit tests for retry policy.
- [ ] Add unit tests for timeout handling.
- [ ] Add unit tests for safety aborts.
- [ ] Add unit tests for coordinate normalization.
- [ ] Add OCR fixture tests.
- [ ] Add template matching fixture tests.
- [ ] Add fake-screen integration tests.
- [ ] Add fake-input integration tests.
- [ ] Add planner integration tests without real mouse movement.
- [ ] Add manual Windows e2e checklist for real desktop execution.

## 18. V1 Acceptance Criteria

- [ ] `desktop-agent run` executes a YAML task end to end.
- [ ] `desktop-agent dry-run` validates and explains the planned task without actions.
- [ ] `desktop-agent inspect-screen` captures screenshot, OCR, UIA, and candidate data.
- [ ] Browser demo completes unattended on an unlocked Windows desktop.
- [ ] Native Windows demo completes unattended on an unlocked Windows desktop.
- [ ] Mixed demo completes unattended on an unlocked Windows desktop.
- [ ] Emergency hotkey stops execution within one second.
- [ ] Failed runs produce useful screenshots, logs, candidates, and abort reason.
- [ ] No cloud service is required.
- [ ] No task can act outside the allowed window whitelist.
- [ ] Documentation is sufficient for a new engineer to install, run, debug, and extend v1.

## 19. Post-v1 Backlog

- [ ] Linux X11 adapter.
- [ ] Linux Wayland compatibility investigation.
- [ ] Visual task recorder.
- [ ] Optional local vision model.
- [ ] Optional cloud VLM adapter disabled by default.
- [ ] Redacted trace mode.
- [ ] Team report server.
- [ ] Remote worker orchestration.
- [ ] Rich desktop tray UI.
- [ ] More advanced recovery planning.
- [ ] Plugin system for app-specific task libraries.
