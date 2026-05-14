"""Bounded timing decisions for optional human-like execution profiles."""

from __future__ import annotations

import random
from dataclasses import dataclass

from desktop_agent.config import ExecutionProfile


@dataclass(frozen=True)
class TimingDecision:
    """A traceable delay decision made before an action or retry."""

    phase: str
    delay_seconds: float
    lower_bound_seconds: float
    upper_bound_seconds: float
    hesitation_applied: bool
    movement_smoothness: float
    reason: str

    def metadata(self) -> dict[str, object]:
        return {
            "timing_phase": self.phase,
            "delay_seconds": self.delay_seconds,
            "lower_bound_seconds": self.lower_bound_seconds,
            "upper_bound_seconds": self.upper_bound_seconds,
            "hesitation_applied": self.hesitation_applied,
            "movement_smoothness": self.movement_smoothness,
        }


class ExecutionTimingController:
    """Samples safe timing values without changing task intent or action order."""

    def __init__(self, profile: ExecutionProfile) -> None:
        self._profile = profile
        self._rng = random.Random(profile.random_seed)

    def before_action(self) -> TimingDecision:
        return self._sample("action", self._profile.action_delay_seconds)

    def before_retry(self) -> TimingDecision:
        return self._sample("retry", self._profile.retry_delay_seconds)

    def _sample(
        self,
        phase: str,
        bounds: tuple[float, float],
    ) -> TimingDecision:
        lower, upper = bounds
        if not self._profile.enabled:
            return TimingDecision(
                phase=phase,
                delay_seconds=0.0,
                lower_bound_seconds=0.0,
                upper_bound_seconds=0.0,
                hesitation_applied=False,
                movement_smoothness=0.0,
                reason="execution profile disabled",
            )

        hesitation_applied = phase == "action" and (
            self._rng.random() < self._profile.hesitation_probability
        )
        sample_lower = lower
        if hesitation_applied:
            # Hesitation is modeled by sampling the upper half of the same safe
            # range, so the decision never exceeds configured bounds.
            sample_lower = lower + ((upper - lower) / 2)

        return TimingDecision(
            phase=phase,
            delay_seconds=self._rng.uniform(sample_lower, upper),
            lower_bound_seconds=lower,
            upper_bound_seconds=upper,
            hesitation_applied=hesitation_applied,
            movement_smoothness=self._profile.movement_smoothness,
            reason=f"{phase} timing decided",
        )
