"""Perception contracts for UIA, OCR, and computer-vision candidate search."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Literal, Protocol

from desktop_agent.config import RuntimeConfig
from desktop_agent.screen import Bounds, ScreenObservation
from desktop_agent.task_dsl import TaskStep

CandidateSource = Literal["uia", "ocr", "image", "unknown"]
SOURCE_PRIORITY: dict[CandidateSource, int] = {
    "uia": 3,
    "ocr": 2,
    "image": 1,
    "unknown": 0,
}


@dataclass(frozen=True)
class ElementCandidate:
    """A normalized UI target discovered by one perception source."""

    id: str
    source: CandidateSource
    label: str
    bounds: Bounds
    confidence: float
    visible: bool = True
    enabled: bool = True
    metadata: dict[str, object] = field(default_factory=dict)


class PerceptionEngine(Protocol):
    """Interface for candidate discovery adapters."""

    def detect(
        self,
        step: TaskStep,
        observation: ScreenObservation,
        config: RuntimeConfig,
    ) -> tuple[ElementCandidate, ...]: ...


class EmptyPerceptionEngine(PerceptionEngine):
    """Perception engine used when no candidate source is configured yet."""

    def detect(
        self,
        step: TaskStep,
        observation: ScreenObservation,
        config: RuntimeConfig,
    ) -> tuple[ElementCandidate, ...]:
        _ = step, observation, config
        return ()


class CompositePerceptionEngine(PerceptionEngine):
    """Runs the deep-search pipeline across all configured perception engines."""

    def __init__(self, engines: Iterable[PerceptionEngine]) -> None:
        self._engines = tuple(engines)

    def detect(
        self,
        step: TaskStep,
        observation: ScreenObservation,
        config: RuntimeConfig,
    ) -> tuple[ElementCandidate, ...]:
        candidates: list[ElementCandidate] = []
        for engine in self._engines:
            candidates.extend(engine.detect(step, observation, config))
        return tuple(candidates)


class TargetSelector(Protocol):
    """Interface for choosing one candidate for an action."""

    def select(
        self,
        step: TaskStep,
        candidates: tuple[ElementCandidate, ...],
        config: RuntimeConfig,
    ) -> ElementCandidate | None: ...


class ConfidenceTargetSelector(TargetSelector):
    """Selects the highest-confidence enabled and visible candidate."""

    similarity_window: float = 0.05

    def select(
        self,
        step: TaskStep,
        candidates: tuple[ElementCandidate, ...],
        config: RuntimeConfig,
    ) -> ElementCandidate | None:
        _ = step
        eligible = [
            candidate
            for candidate in candidates
            if candidate.enabled
            and candidate.visible
            and candidate.confidence >= config.confidence_threshold
        ]
        if not eligible:
            return None
        best_confidence = max(candidate.confidence for candidate in eligible)
        similar = [
            candidate
            for candidate in eligible
            if best_confidence - candidate.confidence <= self.similarity_window
        ]
        return max(
            similar,
            key=lambda candidate: (
                SOURCE_PRIORITY[candidate.source],
                candidate.confidence,
            ),
        )
