# Human-Like Execution Roadmap

Last updated: 2026-05-14

DeskPilot's goal is safe, local automation for tasks the user is authorized to
run in their own environment. In this roadmap, "human-like execution" means
natural timing, robust perception, controlled variability, clear recovery, and
sharp task completion.

This roadmap does not support stealth automation, CAPTCHA bypass, bot-detection
evasion, credential abuse, abusive third-party automation, or pretending to be a
human on systems where automation is not allowed.

## Completed Baseline

- [x] Create this actionable roadmap file.
- [x] Align the roadmap with DeskPilot's existing authorized-use safety boundary.
- [x] Keep future research, implementation, runtime, safety, and verification
  work unchecked until it is actually finished.

## Phase 1: Research Brief

- [x] Create `docs/human-like-execution-research.md`.
- [x] Define the safe meaning of human-like execution.
- [x] Summarize human motor timing using Fitts' Law.
- [x] Summarize routine task timing using the Keystroke-Level Model.
- [x] Summarize bounded randomness and entropy-based modeling.
- [x] Summarize computer-use agent reliability findings from OSWorld, Windows
  Agent Arena, and recent reliability research.
- [x] Summarize human trust and safety requirements for automation.
- [x] End with DeskPilot-specific recommendations.

## Phase 2: Implementation Plan

- [x] Create `docs/human-like-execution-implementation-plan.md`.
- [x] Define a human-like execution profile for timing, hesitation, retry
  spacing, and movement smoothness.
- [x] Require randomness to stay inside allowed windows, allowed actions, max
  steps, and timeouts.
- [x] Define deterministic task success as the core invariant.
- [x] Define metrics for success rate, task time, action count, retry count,
  ambiguity rate, recovery rate, and intervention rate.
- [x] Define testing scenarios for repeatability, bounds enforcement, failure
  recovery, and safety controls.

## Phase 3: Runtime Design

- [x] Add execution profile configuration to the task/runtime model.
- [x] Add bounded stochastic timing for safe delays and retry spacing.
- [x] Add confidence gates before ambiguous actions.
- [x] Add recovery behavior for missed targets, stale observations, and
  transient UI changes.
- [x] Add trace fields for timing decisions, candidate confidence, retry
  reasons, and recovery decisions.
- [x] Document every new public config field and behavior.

## Phase 4: Safety Controls

- [x] Ensure all human-like behavior respects window allowlists.
- [x] Ensure randomness never changes the task's intended outcome.
- [x] Require explicit confirmation for sensitive actions.
- [x] Keep screenshots, OCR output, traces, and reports local by default.
- [x] Add failure messages when randomness bounds or confidence gates stop
  execution.
- [x] Update safety documentation with the new execution-profile boundary.

## Phase 5: Verification

- [x] Add unit tests for execution profile validation.
- [x] Add unit tests proving timing randomness stays inside configured bounds.
- [x] Add tests proving actions cannot escape allowed windows.
- [x] Add repeated-run tests for deterministic task completion.
- [x] Add trace assertions for timing, retries, confidence, and recovery
  metadata.
- [x] Run the project quality pipeline before marking the roadmap complete.

## Research Sources To Use

- [OSWorld: Benchmarking Multimodal Agents for Open-Ended Tasks in Real Computer Environments](https://arxiv.org/abs/2404.07972)
- [Windows Agent Arena: Evaluating Multi-Modal OS Agents at Scale](https://arxiv.org/abs/2409.08264)
- [On the Reliability of Computer Use Agents](https://arxiv.org/abs/2604.17849)
- [Maximum Entropy Inverse Reinforcement Learning](https://www.cs.cmu.edu/~bziebart/publications/maximum-entropy-inverse-reinforcement-learning.html)
- [The Keystroke-Level Model for User Performance Time with Interactive Systems](https://cacm.acm.org/research/the-keystroke-level-model-for-user-performance-time-with-interactive-systems/)
- [The Information Capacity of the Human Motor System in Controlling the Amplitude of Movement](https://doi.org/10.1037/h0055392)
- [Toward Quantifying Trust Dynamics: How People Adjust Their Trust After Moment-to-Moment Interaction With Automation](https://arxiv.org/abs/2107.07374)

## Acceptance Criteria

- [x] Research doc exists and cites primary or research-oriented sources.
- [x] Implementation plan exists and is specific enough to implement without
  major design decisions.
- [x] Runtime behavior remains safe, local-first, and authorized-use only.
- [x] Human-like variability improves resilience without hiding automation
  identity.
- [x] Tests cover configuration, safety bounds, stochastic behavior, and
  repeated execution.
- [x] Documentation explains the feature, safety limits, and expected operator
  controls.
