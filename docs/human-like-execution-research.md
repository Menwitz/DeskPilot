# Human-Like Execution Research Brief

Last updated: 2026-05-14

DeskPilot should treat "human-like execution" as a safety-bounded engineering
property: authorized local automation should use natural timing, fresh
observations, confidence gates, recovery, and traceability while preserving the
operator's intent. It must not mean stealth behavior, bot-detection evasion, or
pretending to be a human where automation is not allowed.

## Actionable Findings

1. Keep the plan deterministic and make variability secondary.
   - Task intent, selected action, target constraints, allowed windows, and
     success criteria should remain deterministic.
   - Randomness should only affect safe timing choices or equivalent recovery
     pacing, never the intended outcome.

2. Model low-level timing with bounded distributions.
   - Fitts' Law shows that target distance and size affect human pointing time;
     this supports using target-aware timing later, once real actuation exists.
   - The Keystroke-Level Model decomposes expert routine work into low-level
     operators and predictable mental/system pauses; this supports an execution
     profile with pre-action and retry-delay ranges.

3. Use entropy as controlled uncertainty, not noise.
   - Maximum-entropy imitation learning uses probability distributions to
     represent noisy, imperfect demonstrations while still optimizing for a
     goal. DeskPilot should borrow the principle, not the whole model: preserve
     task success and add bounded variability only where safety and tests can
     prove the bounds.

4. Optimize reliability with repeated-run evidence.
   - OSWorld and Windows Agent Arena show that desktop agents fail on GUI
     grounding, operational knowledge, and long multi-step execution.
   - Recent computer-use reliability work shows that repeated runs expose
     failures hidden by one-off success. DeskPilot should track success rate,
     action count, retry count, ambiguity rate, recovery rate, and intervention
     rate across repeated executions.

5. Build trust through transparency and local control.
   - Human trust in automation changes after each success and failure.
     DeskPilot should keep traces local, expose why a step retried or stopped,
     and require explicit confirmation before sensitive actions.

## DeskPilot Recommendations

- Add an opt-in execution profile with action-delay bounds, retry-delay bounds,
  hesitation probability, movement smoothness, and an optional seed for
  repeatable tests.
- Record timing decisions in traces instead of hiding them inside adapters.
- Keep all timing decisions inside the same safety pipeline as normal actions.
- Reject unsafe or nonsensical bounds at configuration load time.
- Treat ambiguous targets as a confidence-gate failure rather than choosing a
  risky target.
- Use fresh observations on every retry so recovery responds to the current UI.
- Evaluate human-like execution by reliability and trace quality, not by whether
  it is hard to distinguish from a person.

## Concrete Model Choices

DeskPilot uses a bounded engineering model instead of an open-ended imitation
model. Each choice below has a checkable artifact in configuration, tracing,
monitoring, reports, or tests.

| Concern | Model choice | Actionable result |
| --- | --- | --- |
| Task intent | Deterministic task DSL plus compiled dependencies and expected state | The planner keeps action order, targets, verification rules, allowed windows, and success criteria stable. |
| Desktop grounding | Multi-source deep search with UIA, OCR, image, and dry-run candidate monitoring | Candidate counts, rankings, ambiguity, and selected IDs appear in trace events and benchmark contracts. |
| Target selection | Confidence threshold plus ambiguity gate | Low-confidence or ambiguous matches stop before timing and actuation instead of guessing. |
| Action timing | Bounded execution profile with `uniform` and `center_weighted` sampling | Variability stays inside configured lower and upper bounds and can be reproduced with `random_seed`. |
| Expert-task pacing | Keystroke-Level-Model style operator metadata | Traces expose mental, keying, pointing, homing, and system-wait components without expanding timing bounds. |
| Pointer behavior | Fitts-aware pointer timing metadata plus bounded `movement_smoothness` | Real pointer movement can feel less mechanical while preserving the same target and final safety checks. |
| Text entry | Bounded per-character keyboard cadence | Typed text remains byte-for-byte the same; only inter-character timing changes and is reported. |
| Scroll actions | Bounded same-direction wheel cadence | Total scroll distance is preserved while long scrolls are paced and reported. |
| Recovery | Explicit recovery policy with bounded retry backoff and fresh observations | Retries are explainable, limited by task/config budgets, and visible in monitoring output. |
| Sensitive actions | Policy presets, checkpoints, operator approval, and confirmed step IDs | Irreversible or externally visible actions stop before input unless the selected policy permits them. |
| Evaluation | Repeated dry-run benchmark harness with acceptance thresholds | Reliability, speed, ambiguity, recovery, grounding, and intervention rates decide whether a change improved the system. |

## Tradeoffs Accepted

- Bounded stochastic timing over full behavioral imitation. This keeps runs
  reproducible, testable, and auditable while still avoiding brittle fixed
  sleeps.
- Local heuristic models over learned imitation or reinforcement learning. The
  current system has no safe demonstration corpus, and learned policies would be
  harder to constrain before actuation.
- Stop-before-actuation gates over best-effort completion. Ambiguity,
  disallowed windows, unsafe profile values, timeout-budget failures, and
  unconfirmed sensitive actions should fail loudly instead of trying a risky
  fallback.
- Traceability over invisibility. Timing, candidate search, recovery, policy,
  and safety decisions are written to local reports even when that makes the
  automation easier to identify as automation.
- Safety-bounded naturalness over maximum speed. Fast paths can reduce waits
  only after safety checks and only inside configured timing bounds; careful
  paths can add wait when risk signals justify it.
- Explicit policy presets over implicit context guessing. Operators choose
  `strict_qa`, `personal_automation`, or `exploratory_testing`; the planner does
  not infer permission from page appearance or target text alone.

## Rejected Unsafe Approaches

The research brief explicitly rejects approaches that would make DeskPilot
less transparent, less controllable, or useful for abuse:

- Stealth automation, CAPTCHA bypass, bot-detection evasion, credential abuse,
  and abusive third-party automation.
- Random target jitter, random click offsets, or random action substitutions
  that could change the selected control or task outcome.
- Using entropy to bypass rate limits, platform rules, access controls, or
  monitoring systems.
- Hiding automation by suppressing traces, deleting reports, masking timing
  decisions, or avoiding audit artifacts.
- Auto-confirming `requires_confirmation` or `submission` steps without an
  explicit operator decision.
- Continuing after active-window allowlist failure, final actuator guard
  failure, emergency stop, or unsupported execution-profile values.
- Optimizing for "indistinguishable from a person" as a benchmark. DeskPilot's
  success criteria are reliability, recoverability, bounded timing, trace
  quality, and operator control.

## Evidence To Check

- `docs/configuration.md` documents each execution-profile field, policy
  preset, validation rule, and operator approval path.
- `docs/safety.md` documents the operating boundary, final safety checks,
  emergency stop behavior, safety audit, and unsupported uses.
- `docs/benchmarks.md` defines the repeated-run metrics, deep-search monitoring
  contract, report artifacts, and acceptance thresholds.
- Regression tests prove unsafe profile values, ambiguity gates, disallowed
  windows, unconfirmed sensitive actions, and final real-actuation guards stop
  before desktop input.

## Sources

- [OSWorld: Benchmarking Multimodal Agents for Open-Ended Tasks in Real Computer Environments](https://arxiv.org/abs/2404.07972)
- [Windows Agent Arena: Evaluating Multi-Modal OS Agents at Scale](https://arxiv.org/abs/2409.08264)
- [On the Reliability of Computer Use Agents](https://arxiv.org/abs/2604.17849)
- [Maximum Entropy Inverse Reinforcement Learning](https://www.cs.cmu.edu/~bziebart/publications/maximum-entropy-inverse-reinforcement-learning.html)
- [The Keystroke-Level Model for User Performance Time with Interactive Systems](https://cacm.acm.org/research/the-keystroke-level-model-for-user-performance-time-with-interactive-systems/)
- [The Information Capacity of the Human Motor System in Controlling the Amplitude of Movement](https://doi.org/10.1037/h0055392)
- [Toward Quantifying Trust Dynamics: How People Adjust Their Trust After Moment-to-Moment Interaction With Automation](https://arxiv.org/abs/2107.07374)
