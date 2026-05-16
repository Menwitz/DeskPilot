# DeskPilot Personal Routine Assistant Roadmap

Last updated: 2026-05-16

This roadmap tracks the work to evolve DeskPilot from a deterministic
YAML/playbook desktop automation engine into a personal local routine assistant.
The core product direction is visible, authorized, local automation over the
real Windows desktop. Natural timing, spacing, and routine selection are product
features; stealth automation, CAPTCHA bypass, bot-detection evasion, credential
abuse, and hidden automation are not supported.

## Product Contract

- [x] DeskPilot has a deterministic YAML task execution engine.
- [x] DeskPilot has a website playbook layer that compiles into task YAML.
- [x] DeskPilot is Windows-first for real desktop automation.
- [x] DeskPilot has a real Windows `SendInput` backend for cursor, keyboard,
      scroll, and drag actions.
- [x] DeskPilot uses UIA, OCR, and computer-vision candidate fusion.
- [x] DeskPilot supports dry-run planning without desktop input.
- [x] DeskPilot writes local traces, screenshots, action logs, and reports.
- [x] DeskPilot supports approval manifests for sensitive site workflows.
- [x] DeskPilot has seed playbooks for LinkedIn, Medium, X/Twitter, Instagram,
      Facebook, YouTube, and TikTok.
- [ ] DeskPilot becomes a personal local routine assistant.
- [x] DeskPilot ships a native PySide6 operator app.
- [ ] DeskPilot supports a 300-routine catalog.
- [ ] DeskPilot supports recorder-generated editable YAML and playbooks.
- [x] DeskPilot supports goal-to-routine planning.
- [x] DeskPilot supports optional local Ollama planning and ranking.
- [ ] DeskPilot provides video plus trace proof for real Windows workflows.
- [x] DeskPilot supports human-paced visible routine scheduling over time.
- [x] DeskPilot supports trace redaction controls for screenshots, OCR text,
      typed text, variables, and video.

## Product Vocabulary

- [x] Define `task` as the strict YAML execution unit run by the planner.
- [x] Define `site playbook` as a reusable website catalog entry that compiles
      into a task.
- [x] Define `routine` as a user-facing reusable workflow with metadata, inputs,
      outputs, safety class, schedule policy, and trace expectations.
- [x] Define `skill` as a reusable routine fragment or capability that a
      routine can reference.
- [x] Define `goal plan` as the planner output that maps a user goal to one or
      more known routines.
- [x] Define `manual handoff` as a planned pause where the operator must inspect,
      approve, or complete a step.
- [x] Define `proof bundle` as a Windows run package containing command,
      environment metadata, video, trace, screenshots, and final report.

## Release Ladder

- [ ] Proof demo: real Windows browser, native, mixed, and recovery workflows
      with video plus traces.
- [x] Alpha assistant: recorder, routine library, and native app can run local
      routines manually.
- [ ] Beta catalog: 300 routines validate, dry-run, and carry safety metadata.
- [x] Planner release: goal-to-routine planning selects routines and asks for
      missing inputs.
- [x] UI release: PySide6 app supports library, approvals, run queue, pause,
      stop, recorder review, and trace replay.
- [ ] Hardened local product: redaction, packaging, routine packs, failure
      analysis, and Windows proof gates are complete.

## Phase 0: Roadmap Reset And Product Contract

### Goals

- [x] Reframe the next product direction as a personal local routine assistant.
- [x] Preserve YAML tasks and website playbooks as the execution substrate.
- [x] Define human-paced visible automation without stealth or evasion.
- [x] Make this roadmap the active source of truth for post-v1 implementation.

### OKRs

- [x] O1: Make the product promise concrete.
- [x] KR1: Add this roadmap as a checkable implementation tracker.
- [x] KR2: Update top-level docs to point to this roadmap.
- [x] KR3: Move recorder, planner, UI, catalog, proof, and redaction work into
      active planning milestones.
- [x] KR4: Document allowed and unsupported automation behavior in product
      language.

### Tasks

- [x] Add glossary entries for task, playbook, routine, skill, trace, approval,
      handoff, verification, and goal plan.
- [x] Add release ladder for proof demo, alpha assistant, beta catalog, planner
      release, UI release, and hardened product.
- [x] Update `README.md` to link this roadmap.
- [x] Update `docs/roadmap.md` to distinguish the completed v1 roadmap from this
      product roadmap.
- [x] Keep `docs/desktop-io-control-roadmap.md` as the lower-level desktop I/O
      proof roadmap.
- [x] Add a short product-contract section to `docs/project-definition.md`.
- [x] Add release-note language that stops presenting external Windows evidence
      gates as completed product proof.

### Acceptance Criteria

- [x] A new engineer can understand the product direction without reading prior
      chat.
- [x] The roadmap distinguishes implemented foundation from future product work.
- [x] Top-level docs link to this roadmap.
- [x] Safety docs explicitly separate human-paced local automation from stealth
      or evasion.

## Phase 1: Real Windows I/O Proof Pack

### Goals

- [ ] Prove DeskPilot controls a real unlocked Windows desktop end to end.
- [ ] Capture video plus trace evidence for browser, native, mixed, and recovery
      workflows.
- [ ] Package proof artifacts so failures can be reviewed without rerunning the
      desktop action.

### OKRs

- [ ] O1: Demonstrate real OS input across representative workflows.
- [ ] KR1: Browser workflow completes with video, screenshots, cursor readback,
      active-window metadata, and final report.
- [ ] KR2: Native Windows workflow completes with video, screenshots, cursor
      readback, active-window metadata, and final report.
- [ ] KR3: Mixed browser-to-native workflow completes with real window switching.
- [ ] KR4: Recovery workflow demonstrates stale, delayed, occluded, or missed
      target handling.
- [ ] KR5: Every proof run writes a proof manifest linking command, environment,
      video, trace, screenshots, and report.

### Tasks

- [x] Keep existing `demo-input`, `demo-linkedin`, and
      `windows-smoke-checklist` commands as low-level proof entry points.
- [x] Add `desktop-agent proof browser-fixture` for real browser form/navigation
      proof.
- [x] Add `desktop-agent proof native-fixture` for real native Windows app proof.
- [x] Add `desktop-agent proof mixed-fixture` for browser-to-native handoff
      proof.
- [x] Add `desktop-agent proof recovery-fixture` for delayed, duplicated,
      disabled, occluded, or moving target proof.
- [x] Add local Windows video capture support and store recordings in the trace
      directory.
- [x] Add `proof-manifest.json` with command, executable version, Python version,
      Windows version, monitor geometry, DPI, started-at time, completed-at time,
      and artifact paths.
- [x] Add a proof replay command that prints proof status and opens artifact
      paths without re-executing input.
- [x] Fix unsupported-platform real `run` behavior so it fails early with a
      platform-unavailable reason before target selection.
- [x] Add a Windows manual evidence checklist for each proof command.

### Acceptance Criteria

- [ ] Browser, native, mixed, and recovery proof commands pass on an owned,
      unlocked Windows desktop.
- [ ] Each proof includes video, action log, final report, pre/post screenshots,
      and cursor readback.
- [ ] A reviewer can verify from artifacts that real OS input occurred.
- [x] Non-Windows real `run` exits with a clear unsupported-platform message.
- [x] Proof commands do not use browser DevTools, Playwright, app APIs, or
      fixture-only fake cursors.

## Phase 2: Closed-Loop Verification Upgrade

### Goals

- [x] Make each real input action auditable from intent to observed result.
- [x] Explain target choice, competing candidates, input sent, and verification
      outcome.
- [x] Make trace replay useful for debugging without rerunning the task.

### OKRs

- [x] O1: Turn observe-decide-act-verify into a first-class trace contract.
- [x] KR1: 100% of real input actions have pre-action and post-action evidence.
- [x] KR2: Verification supports `passed`, `failed`, and `inconclusive`.
- [x] KR3: Replay summarizes screenshots, focus state, cursor readback, target
      reasoning, and state delta for each step.
- [x] KR4: Failed actions include enough evidence to diagnose target, focus,
      timing, safety, or verification failure.

### Tasks

- [x] Keep existing final reports, action logs, candidate rankings, and trace
      directories.
- [x] Add `TraceSchemaV2` with explicit observation, target reasoning, input,
      verification, and state-delta sections.
- [x] Capture pre-action screenshot, active window title, process metadata,
      focused element, cursor position, monitor geometry, and DPI.
- [x] Capture post-action screenshot, active window title, process metadata,
      focused element, cursor position, and warnings.
- [x] Record selected candidate, rejected candidates, rejection reasons,
      confidence values, and coordinate conversion.
- [x] Add visual state delta summaries for focus changes, visible text changes,
      target appearance/disappearance, and scroll movement.
- [x] Add verification outcome `inconclusive` and route it to retry or manual
      handoff.
- [x] Add trace replay timeline output for each step.
- [x] Add trace replay Markdown or HTML summary with screenshots and state
      deltas.

### Acceptance Criteria

- [x] A failed click shows what was visible before the click and what changed
      after it.
- [x] A failed type shows the focused window and focused element before typing.
- [x] A failed scroll shows whether the viewport moved.
- [x] A passed action includes concrete evidence of the resulting state.
- [x] Trace replay can explain each executed step without live desktop access.

## Phase 3: Low-Level Desktop I/O Task Model

### Goals

- [x] Make real desktop operations explicit below semantic YAML actions.
- [x] Track mutation risk, approval needs, reversibility, and app/window scope
      per action.
- [x] Preserve existing YAML compatibility while adding a lower-level compiled
      execution model.

### OKRs

- [x] O1: Introduce a first-class desktop I/O action schema.
- [x] KR1: Support `observe`, `move`, `click`, `double_click`, `drag`, `wheel`,
      `type`, `hotkey`, `wait`, `verify`, and `handoff`.
- [x] KR2: Every low-level action carries safety metadata.
- [x] KR3: Emergency stop checks run between bounded low-level input events.
- [x] KR4: Existing task YAML still runs through the current planner contract.

### Tasks

- [x] Add `DesktopIoAction` dataclasses and validation.
- [x] Compile existing `click_text`, `click_image`, `click_uia`, `type_text`,
      `press_key`, `scroll`, `scroll_until`, `wait_for`, `assert_visible`,
      `branch_if_visible`, and `drag` into low-level I/O actions.
- [x] Add action safety classes: `read_only`, `local_mutation`,
      `external_mutation`, `credential`, `payment`, `delete`, and
      `message_or_publish`.
- [x] Add action metadata for approval requirement, reversibility,
      idempotence, allowed windows, and allowed regions.
- [x] Add manual handoff action with prompt text, expected operator work, and
      resume verification.
- [x] Add emergency-stop checks between mouse path points, drag path points,
      typed characters, scroll chunks, and retry waits.
- [x] Add final active-window and allowed-region checks at the low-level action
      boundary.

### Acceptance Criteria

- [x] A task author can tell which actions mutate state before running.
- [x] Risky actions stop before input unless confirmation or manifest approval
      is present.
- [x] Emergency stop can interrupt long movement, drag, typing, scroll, and wait
      actions.
- [x] Existing examples continue to validate and dry-run.

## Phase 4: Recorder Alpha

### Goals

- [x] Turn a demonstrated routine into editable YAML or website playbook steps.
- [x] Prefer stable selectors over raw coordinates.
- [x] Let the operator review and correct generated routines before saving.

### OKRs

- [x] O1: Ship a Windows recorder that generates valid editable tasks.
- [x] KR1: Recorder captures clicks, typing, hotkeys, scrolls, waits, active
      windows, screenshots, and candidate context.
- [x] KR2: Generated YAML includes allowed windows, targets, regions,
      verification suggestions, and sensitive-step markers.
- [x] KR3: Generated YAML passes `BasicTaskValidator`.
- [x] KR4: A recorded fixture routine can be rerun successfully after review.

### Tasks

- [x] Add `desktop-agent record` with start, pause, stop, save, and discard
      controls.
- [x] Add a recorder event model for observation, input event, selected point,
      active window, screenshot path, candidate context, and timestamp.
- [x] Capture UIA element name/control type/bounds around clicked points.
- [x] Capture OCR text blocks around clicked points.
- [x] Capture image-template snippets only when UIA/OCR cannot identify a
      stable target.
- [x] Generate `click_uia`, `click_text`, `click_image`, `type_text`,
      `press_key`, `scroll`, `wait_for`, and `assert_visible` steps.
- [x] Infer allowed windows from observed active windows and require operator
      confirmation before save.
- [x] Infer verification suggestions from post-action state deltas.
- [x] Add review metadata for routine name, description, inputs, outputs, tags,
      risk class, and expected duration.
- [x] Add tests using fake recorder event streams.

### Acceptance Criteria

- [x] Recorder generates valid YAML from a browser fixture recording.
- [x] Recorder generates valid YAML from a native fixture recording.
- [x] Recorder avoids raw coordinates when UIA, OCR, or image candidates are
      available.
- [x] Generated routines can be edited and rerun through dry-run and Windows
      proof flows.

## Phase 5: Routine Catalog Scale-Out

### Goals

- [ ] Build a broad catalog of reusable routines on top of YAML and playbooks.
- [ ] Reach 300 validated routines across browser, native Windows, and
      social/content workflows.
- [ ] Make routine quality measurable and reviewable.

### OKRs

- [ ] O1: Ship a 300-routine catalog.
- [ ] KR1: Add 100 browser routines.
- [ ] KR2: Add 100 native Windows routines.
- [ ] KR3: Add 100 social/content routines.
- [ ] KR4: Every routine has metadata, inputs, outputs, safety class, dry-run
      coverage, and trace expectations.
- [ ] KR5: High-risk routines require approval and checkpoint coverage.

### Tasks

- [x] Add routine pack directories for `browser`, `native`, `social-content`,
      `email-writing`, `files`, `research`, and `publishing`.
- [x] Add `RoutineDefinition` schema with ID, name, description, goal,
      required app/site, tags, inputs, outputs, safety class, schedule policy,
      approval policy, expected duration, and task/playbook reference.
- [x] Add catalog loader, validator, and search index.
- [x] Add commands: `list-routines`, `show-routine`, `compile-routine`,
      `dry-run-routine`, `run-routine`, and `export-routine`.
- [x] Add routine promotion gates: schema validation, dry-run, fixture test,
      Windows proof when applicable, trace replay review, and documentation.
- [x] Add routine quarantine status for routines with repeated failed evidence.
- [x] Add browser routines for navigation, forms, search, reading, content
      extraction, writing surfaces, downloads, and settings pages.
- [x] Add native routines for Notepad, Calculator, Settings, File Explorer,
      clipboard, app switching, window management, and simple Office-like
      surfaces.
- [x] Add social/content routines for LinkedIn, Medium, X/Twitter, Instagram,
      Facebook, YouTube, and TikTok read-only, draft, and approved publish
      surfaces.
- [x] Add routine documentation templates and generated catalog index docs.

### Acceptance Criteria

- [ ] 300 routines validate.
- [ ] Every routine has dry-run coverage.
- [ ] Every high-risk routine has approval metadata and checkpoint coverage.
- [ ] Every routine can be listed, inspected, and compiled from the CLI.
- [ ] Catalog quality report shows validation, proof, and quarantine status.

## Phase 6: Human-Paced Scheduling And Activity Layer

### Goals

- [x] Execute routines over time with visible, bounded, traceable timing.
- [x] Support daily routine batches, cooldowns, allowed time windows, and
      operator check-ins.
- [x] Keep human-paced behavior inside safety, approval, and allowed-window
      limits.

### OKRs

- [x] O1: Add routine scheduling and activity pacing.
- [x] KR1: Routines can define allowed time windows, cooldowns, max actions per
      hour, and stop-after conditions.
- [x] KR2: Scheduler supports pause, resume, cancel, retry later, and manual
      handoff.
- [x] KR3: Timing decisions are recorded and reproducible when a seed is set.
- [x] KR4: The operator can see why the assistant waited, resumed, skipped, or
      asked for approval.

### Tasks

- [x] Reuse existing execution profile concepts for bounded timing, keyboard
      cadence, scroll cadence, and seeded sampling.
- [x] Add activity profiles: `focused`, `careful`, `background_assist`, and
      `batch_work`.
- [x] Add routine schedule schema with time windows, cooldowns, run limits,
      max external mutations, and stop conditions.
- [x] Add run queue model with pending, running, paused, blocked, completed,
      failed, canceled, and handed-off states.
- [x] Add scheduler trace events for selected time, wait reason, skip reason,
      pause, resume, retry-later, and operator intervention.
- [x] Add safety gate that blocks scheduled runs when the active desktop or
      allowed app context is not ready.
- [x] Add manual approval before scheduled external mutation actions.
- [x] Add tests for deterministic seeded schedules and bounded unseeded
      schedules.

### Acceptance Criteria

- [x] A routine can be scheduled for an allowed time window.
- [x] A routine can pause, resume, cancel, and retry later.
- [x] Scheduler stops before unapproved high-risk actions.
- [x] Reports explain all timing and scheduling decisions.

## Phase 7: Goal/Planning Layer

### Goals

- [x] Let the user state a goal and have DeskPilot choose a known routine.
- [x] Keep deterministic rules authoritative for execution eligibility.
- [x] Use optional local Ollama only for ranking, explanation, and draft input
      extraction.

### OKRs

- [x] O1: Add goal-to-routine planning.
- [x] KR1: Deterministic rules match goals to routines by app, site, tags,
      input/output types, safety class, and historical success.
- [x] KR2: Planner asks for missing required inputs before execution.
- [x] KR3: Planner shows selected routine, alternatives, risk, approvals,
      expected evidence, and abort conditions.
- [x] KR4: Optional Ollama output cannot bypass validation, safety checks, or
      approvals.

### Tasks

- [x] Add `GoalPlan` schema with user goal, normalized intent, candidate
      routines, selected routine, missing inputs, approvals, explanation, and
      execution status.
- [x] Add routine index search by ID, name, app, site, tags, inputs, outputs,
      risk class, and schedule eligibility.
- [x] Add deterministic router with exact app/site matching, tag matching,
      input compatibility, risk filtering, and confidence ranking.
- [x] Add missing-input prompts for routine variables and required session
      state.
- [x] Add planner dry-run that never moves the desktop.
- [x] Add optional Ollama ranking and explanation behind a disabled-by-default
      config flag.
- [x] Add model disclosure fields to traces: provider, model, prompt class,
      input artifact references, output hash, and whether the output affected
      routine selection.
- [x] Add safety rule that only validated routine IDs can be executed.

### Acceptance Criteria

- [x] A user goal can select a routine from the catalog.
- [x] Ambiguous goals show alternatives instead of guessing.
- [x] Missing inputs block execution until provided.
- [x] Local model suggestions never execute raw actions directly.
- [x] Goal plans are traceable and replayable.

## Phase 8: Native Operator App

### Goals

- [x] Ship a native PySide6 app for routine library, recorder, approvals,
      status, pause/stop, and trace review.
- [x] Make daily local use possible without remembering CLI commands.
- [x] Keep all safety and trace behavior shared with the CLI.

### OKRs

- [x] O1: Build a usable local operator app.
- [x] KR1: App can list, search, inspect, dry-run, and run routines.
- [x] KR2: App can start, pause, resume, cancel, and emergency-stop a run.
- [x] KR3: App can review and approve high-risk actions.
- [x] KR4: App can record a routine and review generated YAML before saving.
- [x] KR5: App can replay traces with screenshots, video, target reasoning,
      action log, and verification results.

### Tasks

- [x] Add PySide6 optional dependency group and packaging path.
- [x] Add `deskpilot-app` entry point.
- [x] Add app shell with Dashboard, Routine Library, Record, Run Queue,
      Approvals, Trace Viewer, Settings, and Help pages.
- [x] Add local service boundary for catalog, recorder, runner, scheduler,
      approvals, and trace APIs.
- [x] Add live run panel with current routine, current step, screenshot preview,
      selected target, next action, elapsed time, status, and stop controls.
- [x] Add approval dialog with routine ID, step ID, risk class, checkpoint
      evidence, content fingerprint, and approve/deny actions.
- [x] Add recorder review UI with generated YAML, selected targets, screenshots,
      and verification suggestions.
- [x] Add trace viewer timeline with video, screenshots, action log, candidate
      reasoning, state delta, and final report.
- [x] Add settings for trace root, screenshots, video capture, Ollama enablement,
      emergency hotkey, default activity profile, and proof mode.
- [x] Add UI integration tests around app state transitions with fake services.

### Acceptance Criteria

- [x] A user can run a routine without CLI.
- [x] A user can approve or deny a sensitive step in the app.
- [x] A user can pause, resume, cancel, and stop a run.
- [x] A user can record, review, save, and rerun a simple routine.
- [x] A user can inspect a failed trace and understand why it failed.

## Phase 9: Recovery And Self-Healing

### Goals

- [x] Improve routine resilience against ordinary UI variance.
- [x] Keep recovery explicit, bounded, safe, and auditable.
- [x] Use failed traces to improve routines without silently changing outcomes.

### OKRs

- [x] O1: Add robust recovery planning.
- [x] KR1: Recover from loading delays, stale observations, duplicated labels,
      disabled controls, occlusion, focus loss, and minor layout changes.
- [x] KR2: Recovery choices stay inside retry, timeout, approval, and
      allowed-window bounds.
- [x] KR3: Failed-run analysis can propose YAML selector, region, checkpoint, or
      recovery improvements.
- [x] KR4: Brittle routines are flagged or quarantined after repeated failures.

### Tasks

- [x] Reuse existing recovery policies for stale observation, missed target,
      disabled control, occluded control, transient loading, and verification
      failure.
- [x] Add recovery tree execution for refocus, reobserve, alternate candidate,
      scroll search, wait for enabled, wait for loading, reopen surface, and
      manual handoff.
- [x] Add focus-loss recovery with allowed-window refocus and post-refocus
      verification.
- [x] Add layout-change recovery with alternate selector families.
- [x] Add historical failure counters per routine.
- [x] Add routine quarantine status after configured failure thresholds.
- [x] Add failed-run analyzer that proposes YAML updates but does not apply them
      without review.
- [x] Add app UI for reviewing failure analysis suggestions.

### Acceptance Criteria

- [x] Recoverable fixture failures pass after bounded recovery.
- [x] Non-recoverable failures stop with clear handoff or abort reason.
- [x] Recovery reports show chosen policy, rejected policies, attempts, and
      evidence.
- [x] Suggested routine fixes are review-only until accepted by the operator.

## Phase 10: Local AI Expansion

### Goals

- [x] Add optional local AI for routine selection, trace summarization, screen
      explanation, and routine authoring assistance.
- [x] Keep deterministic validation and safety gates authoritative.
- [x] Keep all model use local by default through Ollama.

### OKRs

- [x] O1: Integrate optional local model assistance safely.
- [x] KR1: Add `LocalModelProvider` interface and Ollama implementation.
- [x] KR2: Model output can rank routines, summarize traces, extract draft
      inputs, and suggest YAML improvements.
- [x] KR3: Model output cannot execute raw desktop actions directly.
- [ ] KR4: Every model-assisted decision is disclosed in the trace.

### Tasks

- [x] Add local model config with disabled default.
- [x] Add Ollama health check and model listing.
- [x] Add prompt classes for routine ranking, missing-input extraction, trace
      summarization, screen summary, and YAML improvement suggestions.
- [x] Add local screenshot captioning path only for review and authoring, not
      direct action execution.
- [x] Add output validation for structured model responses.
- [x] Add trace fields for provider, model name, prompt class, input artifact
      references, output hash, and accepted/rejected status.
- [x] Add fake model provider for tests.
- [x] Add docs explaining that local AI assists selection and review but never
      bypasses routine validation or safety gates.

### Acceptance Criteria

- [x] DeskPilot works with local AI disabled.
- [x] Ollama-assisted routine ranking can be enabled locally.
- [x] Invalid model output is rejected safely.
- [x] Model-assisted plans are traceable.
- [x] No model output sends raw desktop input outside validated routines.

## Phase 11: Privacy, Redaction, And Packaging Hardening

### Goals

- [ ] Keep full local evidence available by default.
- [ ] Add redaction controls for sensitive personal data.
- [ ] Package the CLI and native app for repeatable Windows installation.

### OKRs

- [ ] O1: Harden privacy and packaging.
- [ ] KR1: Redaction policies cover screenshots, OCR text, typed text,
      variables, reports, and video.
- [ ] KR2: Users can choose full evidence, metadata-only traces, or routine-level
      redaction rules.
- [ ] KR3: Windows installer includes CLI, PySide6 app, default config, examples,
      and docs.
- [ ] KR4: Trace and routine schema migrations are versioned and tested.

### Tasks

- [x] Add redaction policy schema at global, routine, and run levels.
- [x] Add screenshot blur masks and sensitive-zone definitions.
- [x] Add typed-text masking and content-variable masking.
- [x] Add OCR suppression and metadata-only trace mode.
- [x] Add video redaction or video-disable options.
- [x] Add trace schema migration tests.
- [x] Add routine catalog migration tests.
- [x] Add Windows installer build script for the CLI and PySide6 app.
- [x] Add packaged-app smoke tests for help, dry-run, routine listing, and trace
      replay.
- [x] Add troubleshooting docs for missing Windows permissions, locked screen,
      OCR absence, video capture failure, and model absence.

### Acceptance Criteria

- [x] Redacted traces preserve enough metadata to debug failures.
- [x] Full-evidence traces remain available when explicitly selected or left as
      default.
- [x] Packaged Windows app launches and can run dry-run workflows.
- [x] Schema migrations preserve old traces and routines.

## Phase 12: Beta Release And Ecosystem

### Goals

- [ ] Make DeskPilot extensible beyond the first built-in routine catalog.
- [ ] Support trusted local routine packs.
- [ ] Prepare for optional team/reporting features after local product
      stability.

### OKRs

- [ ] O1: Ship a beta-ready local routine ecosystem.
- [ ] KR1: Routine packs can be imported, validated, listed, run, exported, and
      removed.
- [ ] KR2: Routine packs include manifest, routines, fixtures, docs, tests,
      safety metadata, and proof expectations.
- [ ] KR3: Conflicts and trust warnings are surfaced before installation.
- [ ] KR4: Optional team/report server remains separate from local execution.

### Tasks

- [x] Add routine-pack manifest schema.
- [x] Add routine-pack import/export commands.
- [x] Add app UI for installing and removing routine packs.
- [x] Add trust warnings for unverified local packs.
- [x] Add conflict detection for duplicate routine IDs, selectors, inputs, and
      pack versions.
- [x] Add pack-level test runner and proof bundle generator.
- [x] Add signed-pack investigation for later releases.
- [x] Add optional local report-server design after native app and trace schema
      stabilize.
- [x] Add Linux X11 adapter plan after Windows beta proof is complete.
- [x] Keep Wayland support as a research track until screenshot and input
      constraints are resolved.

### Acceptance Criteria

- [x] A trusted local routine pack can be installed and validated.
- [x] Duplicate or unsafe routine packs are rejected or quarantined.
- [x] Pack routines appear in CLI and native app catalog search.
- [x] Pack-level proof status is visible in reports.
- [x] Local execution remains fully functional without any report server.

## Public Interfaces To Add

- [x] `RoutineDefinition`: user-facing routine metadata and task/playbook
      reference.
- [x] `DesktopIoAction`: compiled low-level observe, input, verify, and handoff
      action model.
- [x] `TraceSchemaV2`: versioned evidence model for video, before/after
      observations, target reasoning, input events, verification, state deltas,
      and redaction.
- [x] `RecorderSession`: raw recorder event stream plus generated routine output.
- [x] `GoalPlan`: user goal, candidate routines, selected routine, missing
      inputs, approval needs, and explanation.
- [x] `LocalModelProvider`: optional local model adapter interface with Ollama
      as the first implementation.
- [x] `OperatorAppService`: Python service boundary used by the PySide6 app.
- [x] `ProofManifest`: Windows proof artifact index for command, environment,
      video, trace, screenshots, and reports.
- [x] `RoutinePackManifest`: trusted local pack metadata, routines, fixtures,
      docs, tests, and safety declarations.

## Cross-Phase Test Matrix

- [x] Unit tests for routine, desktop I/O action, trace, recorder, goal plan,
      model provider, proof manifest, and routine pack schemas.
- [x] Planner tests for goal-to-routine selection, missing inputs, approvals,
      manual handoff, schedule windows, cooldowns, and stop reasons.
- [x] Recorder tests with fake UIA/OCR/CV event streams that generate valid YAML.
- [x] Trace tests proving every real action has before/after evidence and replay
      output.
- [x] Redaction tests for screenshots, OCR text, typed text, variables, reports,
      and video metadata.
- [x] App service tests for catalog, run queue, approvals, recorder review, and
      trace viewer state transitions.
- [x] Windows smoke tests for proof commands behind `DESKPILOT_WINDOWS_SMOKE=1`.
- [x] Live public-site smoke tests remain opt-in and never perform final
      external mutations without explicit approval evidence.
- [x] Full local quality gate remains `.venv/bin/python -m pytest`,
      `.venv/bin/ruff check .`, and `.venv/bin/mypy`.

## Global Acceptance Criteria

- [ ] DeskPilot can prove real Windows browser, native, mixed, and recovery
      workflows with video plus traces.
- [x] A user can record a routine, review generated YAML, save it, and rerun it.
- [x] A user can state a goal and get a selected known routine or a clear
      missing-input prompt.
- [ ] A user can run, pause, resume, stop, approve, and replay routines from the
      native app.
- [ ] A 300-routine catalog validates and carries safety metadata.
- [x] Optional local Ollama assistance is useful but never required.
- [x] All high-risk external mutations require approval and checkpoint evidence.
- [x] Failed runs are diagnosable from local artifacts without rerunning desktop
      input.
- [x] The product remains local-first and authorized-use only.
