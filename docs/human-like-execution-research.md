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

## Sources

- [OSWorld: Benchmarking Multimodal Agents for Open-Ended Tasks in Real Computer Environments](https://arxiv.org/abs/2404.07972)
- [Windows Agent Arena: Evaluating Multi-Modal OS Agents at Scale](https://arxiv.org/abs/2409.08264)
- [On the Reliability of Computer Use Agents](https://arxiv.org/abs/2604.17849)
- [Maximum Entropy Inverse Reinforcement Learning](https://www.cs.cmu.edu/~bziebart/publications/maximum-entropy-inverse-reinforcement-learning.html)
- [The Keystroke-Level Model for User Performance Time with Interactive Systems](https://cacm.acm.org/research/the-keystroke-level-model-for-user-performance-time-with-interactive-systems/)
- [The Information Capacity of the Human Motor System in Controlling the Amplitude of Movement](https://doi.org/10.1037/h0055392)
- [Toward Quantifying Trust Dynamics: How People Adjust Their Trust After Moment-to-Moment Interaction With Automation](https://arxiv.org/abs/2107.07374)
