"""Execution-path decisions for sharp but safe task execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from desktop_agent.config import RuntimeConfig
from desktop_agent.perception import ElementCandidate
from desktop_agent.task_dsl import TaskStep, step_category

ExecutionPathMode = Literal["fast", "standard", "careful"]

FAST_PATH_ACTIONS: frozenset[str] = frozenset(
    {
        "click_text",
        "click_image",
        "click_uia",
        "assert_visible",
    }
)
FAST_PATH_MIN_CONFIDENCE = 0.95
UNSTABLE_CANDIDATE_STATES: frozenset[str] = frozenset(
    {"loading", "stale", "occluded", "disabled"}
)


@dataclass(frozen=True)
class ExecutionPathDecision:
    """Selected execution path for one step attempt."""

    mode: ExecutionPathMode
    reason: str
    required_confidence: float
    target_confidence: float | None
    candidate_count: int
    attempt: int

    @property
    def fast(self) -> bool:
        return self.mode == "fast"

    @property
    def careful(self) -> bool:
        return self.mode == "careful"

    def metadata(self) -> dict[str, object]:
        timing_policy = "profile_sample"
        if self.fast:
            timing_policy = "lower_bound"
        elif self.careful:
            timing_policy = "upper_bound"
        return {
            "execution_path": self.mode,
            "execution_path_reason": self.reason,
            "execution_path_timing_policy": timing_policy,
            "fast_path_required_confidence": self.required_confidence,
            "fast_path_target_confidence": self.target_confidence,
            "fast_path_candidate_count": self.candidate_count,
            "fast_path_attempt": self.attempt,
            "fast_path_timing_policy": timing_policy,
            "safety_checks_required": True,
        }


def choose_execution_path(
    step: TaskStep,
    candidates: tuple[ElementCandidate, ...],
    target: ElementCandidate | None,
    config: RuntimeConfig,
    attempt: int,
) -> ExecutionPathDecision:
    """Choose whether a step attempt can use the stable high-confidence path."""

    required_confidence = max(config.confidence_threshold, FAST_PATH_MIN_CONFIDENCE)
    target_confidence = target.confidence if target is not None else None
    candidate_count = len(candidates)

    if attempt != 1:
        return _careful(
            "retry_attempt",
            required_confidence,
            target_confidence,
            candidate_count,
            attempt,
        )
    if (
        config.execution_profile.enabled
        and config.execution_profile.persona == "careful"
    ):
        return _careful(
            "careful_persona",
            required_confidence,
            target_confidence,
            candidate_count,
            attempt,
        )
    if step.requires_confirmation:
        return _careful(
            "confirmation_required",
            required_confidence,
            target_confidence,
            candidate_count,
            attempt,
        )
    if step_category(step) == "submission":
        return _careful(
            "submission_requires_checkpoint",
            required_confidence,
            target_confidence,
            candidate_count,
            attempt,
        )
    if target is None:
        return _standard(
            "no_selected_target",
            required_confidence,
            target_confidence,
            candidate_count,
            attempt,
        )
    if step.action not in FAST_PATH_ACTIONS:
        return _careful(
            "risky_or_unsupported_action",
            required_confidence,
            target_confidence,
            candidate_count,
            attempt,
        )
    if not target.visible or not target.enabled:
        return _careful(
            "target_not_visible_or_enabled",
            required_confidence,
            target_confidence,
            candidate_count,
            attempt,
        )
    if _candidate_state(target) in UNSTABLE_CANDIDATE_STATES:
        return _careful(
            "unstable_candidate_state",
            required_confidence,
            target_confidence,
            candidate_count,
            attempt,
        )
    if target.confidence < required_confidence:
        return _careful(
            "low_confidence_selected_target",
            required_confidence,
            target_confidence,
            candidate_count,
            attempt,
        )
    if _visible_enabled_candidate_count(candidates) != 1:
        return _careful(
            "multiple_visible_enabled_candidates",
            required_confidence,
            target_confidence,
            candidate_count,
            attempt,
        )
    return ExecutionPathDecision(
        mode="fast",
        reason="stable_high_confidence_segment",
        required_confidence=required_confidence,
        target_confidence=target_confidence,
        candidate_count=candidate_count,
        attempt=attempt,
    )


def _standard(
    reason: str,
    required_confidence: float,
    target_confidence: float | None,
    candidate_count: int,
    attempt: int,
) -> ExecutionPathDecision:
    return ExecutionPathDecision(
        mode="standard",
        reason=reason,
        required_confidence=required_confidence,
        target_confidence=target_confidence,
        candidate_count=candidate_count,
        attempt=attempt,
    )


def _careful(
    reason: str,
    required_confidence: float,
    target_confidence: float | None,
    candidate_count: int,
    attempt: int,
) -> ExecutionPathDecision:
    return ExecutionPathDecision(
        mode="careful",
        reason=reason,
        required_confidence=required_confidence,
        target_confidence=target_confidence,
        candidate_count=candidate_count,
        attempt=attempt,
    )


def _candidate_state(candidate: ElementCandidate) -> str:
    return str(candidate.metadata.get("state", "")).strip().lower()


def _visible_enabled_candidate_count(candidates: tuple[ElementCandidate, ...]) -> int:
    return sum(1 for candidate in candidates if candidate.visible and candidate.enabled)
