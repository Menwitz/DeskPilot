# Human-Like Execution Forward Roadmap

Last updated: 2026-05-14

This roadmap turns the research brief into forward implementation work. The
current codebase has a safe v1 foundation, but it does not yet have a complete
human-like execution system. The goal is authorized local automation that is
natural, adaptive, measurable, and transparent without stealth, bot-detection
evasion, or pretending to be a person where automation is not allowed.

## Completed Baseline

- [x] Add an opt-in `execution_profile` to runtime configuration.
- [x] Parse project-level and task-level execution-profile YAML.
- [x] Validate timing bounds, probability values, and confirmation IDs.
- [x] Add bounded trace-only timing decisions for actions and retries.
- [x] Add ambiguity/confidence gate failures for targeted actions.
- [x] Add active-window allowlist checks before action.
- [x] Add `requires_confirmation`, `confirmed_steps`, and `--confirm-step`.
- [x] Document the current execution-profile fields and safety boundary.
- [x] Add tests for the current config, timing, safety, retry, and trace
  behavior.
- [x] Add regression tests for safety-before-timing, ambiguity-before-actuation,
  confirmation-before-actuation, and seeded timing reproducibility.

## Phase 1: Research-Backed Evaluation Harness

- [x] Define benchmark task suites for browser, native Windows, and mixed
  workflows.
- [x] Add a repeated-run harness that executes the same task many times and
  stores per-run metrics.
- [x] Track success rate, median task time, step count, action count, retry
  count, ambiguity rate, recovery rate, and operator intervention rate.
- [x] Add run-to-run variance reports so timing and recovery behavior can be
  evaluated instead of guessed.
- [x] Add a fixture app with intentionally moving, delayed, disabled, and
  duplicated controls.
- [x] Add acceptance thresholds for each benchmark task before behavior is
  considered an improvement.

## Phase 2: Human Motor Timing Model

- [x] Implement target-aware action timing based on distance, target size, and
  action type.
- [x] Add a Fitts' Law-inspired pointer timing model behind a local interface.
- [x] Add minimum-jerk or spline-based pointer paths for real mouse movement.
- [x] Add configurable overshoot, correction, and settle behavior within safe
  bounds.
- [x] Add tests proving pointer paths stay inside the target window and never
  cross disallowed monitor or window regions.
- [x] Compare model timing against deterministic baseline runs in the benchmark
  harness.

## Phase 3: Task-Level Cognitive Timing

- [x] Add task-step categories such as navigation, recognition, data entry,
  verification, and submission.
- [x] Add Keystroke-Level-Model style timing operators for mental pauses,
  system waits, keying, pointing, and homing between input modes.
- [x] Let task authors choose an execution persona such as careful, normal, or
  fast while keeping all values inside safe bounds.
- [x] Add per-step timeout budgeting that accounts for planned waits and retry
  pacing.
- [x] Add tests proving persona changes affect timing only, not task outcome or
  target selection.

## Phase 4: Entropy And Controlled Randomness

- [x] Define an entropy budget per task and per step.
- [x] Add deterministic seeded sampling for every random decision.
- [x] Add distribution choices for timing, retry spacing, and equivalent safe
  action variants.
- [x] Reject profiles whose entropy budget could exceed timeout, max-step, or
  retry constraints.
- [x] Record every sampled value and random seed in trace metadata.
- [x] Add tests proving repeated seeded runs are reproducible and unseeded runs
  remain inside safety bounds.

## Phase 5: Adaptive Recovery

- [x] Add recovery policies for stale observations, missed targets, disabled
  controls, occluded controls, and transient loading states.
- [x] Add recovery trees to the task DSL with explicit allowed recovery actions.
- [x] Re-observe the screen after each failed attempt and explain the chosen
  recovery path in the trace.
- [x] Add backoff strategies that remain inside configured timing and retry
  limits.
- [x] Add tests for stale UI, duplicated labels, delayed controls, and
  disappearing targets.
- [x] Add failure reports that distinguish perception failure, selection
  ambiguity, safety stop, verification failure, and actuation failure.

## Phase 6: Perception And Grounding Quality

- [x] Add candidate-fusion scoring across UIA, OCR, and image-template sources.
- [x] Add region-aware disambiguation rules for repeated labels and repeated
  icons.
- [x] Add UI state snapshots that summarize visible controls, selected
  candidates, confidence values, and blocked candidates.
- [x] Add a calibration command that shows why a target was selected or rejected.
- [x] Add tests for conflicting perception sources and low-confidence candidate
  sets.
- [x] Add benchmark metrics for grounding accuracy and ambiguity rate.

## Phase 7: Regression Test Matrix

- [x] Add a regression test proving active-window safety stops happen before
  timing traces and actuation.
- [x] Add a regression test proving ambiguity gate failures happen before timing
  traces and actuation.
- [x] Add a regression test proving unconfirmed sensitive steps stop before
  timing traces and actuation.
- [x] Add a regression test proving seeded timing decisions are reproducible.
- [x] Add regression tests for real elapsed waits once desktop actuation consumes
  timing decisions.
- [x] Add regression tests proving pointer paths stay inside allowed window and
  monitor regions.
- [x] Add regression tests proving keyboard cadence never changes typed text.
- [x] Add regression tests proving scroll cadence stops at the intended target.
- [x] Add regression tests for trace report rendering of timing, ambiguity,
  recovery, and safety-stop decisions.
- [x] Add regression tests for benchmark metric aggregation and variance
  reporting.

## Phase 8: Sharp Task Execution

- [x] Add a task compiler that validates step dependencies and expected UI state
  transitions before execution.
- [x] Add fast-path execution for stable, high-confidence task segments.
- [x] Add careful-path execution for risky, sensitive, or low-confidence
  segments.
- [x] Add explicit verification checkpoints before irreversible actions.
- [x] Add local task-state tracking so the planner knows what it believes has
  already happened.
- [x] Add tests proving sharp execution reduces unnecessary waits without
  reducing safety checks.

## Phase 9: Real Actuation Integration

- [x] Apply real elapsed waits from the timing controller before desktop input.
- [x] Wire `movement_smoothness` into real pointer actuation adapters.
- [x] Add keyboard cadence profiles for text entry without changing typed text.
- [x] Add scroll cadence profiles for long pages and lists.
- [x] Ensure all real actuation checks active window, allowed region, and
  emergency stop before sending input.
- [x] Add Windows smoke tests on an unlocked owned desktop session.

## Phase 10: Operator Control And Safety

- [x] Add policy presets for strict QA, personal automation, and exploratory
  testing.
- [x] Add a dry-run preview that shows planned timing bounds and recovery paths.
- [ ] Add an operator approval prompt for irreversible or externally visible
  actions.
- [ ] Add a safety audit report for every execution-profile run.
- [ ] Document that the feature is not for stealth automation, CAPTCHA bypass,
  bot-detection evasion, credential abuse, or abusive third-party automation.
- [ ] Add tests proving unsafe profile values and unconfirmed sensitive actions
  stop before actuation.

## Phase 11: Documentation And Rollout

- [ ] Expand the research brief with concrete model choices, tradeoffs, and
  rejected unsafe approaches.
- [ ] Add complete example tasks for each execution profile.
- [ ] Add operator guidance for choosing delay bounds and entropy budgets.
- [ ] Add troubleshooting docs for ambiguity gates, recovery stops, and safety
  stops.
- [ ] Add release notes that explain the difference between natural execution
  and deceptive human impersonation.
- [ ] Keep this roadmap updated as each phase lands.

## Acceptance Criteria

- [ ] The benchmark harness proves improved reliability or speed against the
  deterministic baseline without reducing safety.
- [ ] All randomness is bounded, traceable, and reproducible when seeded.
- [ ] Real pointer and keyboard actuation consume the execution profile safely.
- [ ] Recovery decisions are explicit, test-covered, and visible in reports.
- [ ] Safety stops happen before actuation for disallowed windows, unsafe
  profiles, ambiguous targets, and unconfirmed sensitive actions.
- [ ] Documentation explains what the system does, what it does not do, and how
  operators should configure it safely.
