"""Perception contracts for UIA, OCR, and computer-vision candidate search."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from difflib import SequenceMatcher
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
MAX_SOURCE_PRIORITY = max(SOURCE_PRIORITY.values())
OVERLAP_DEDUPLICATION_THRESHOLD = 0.6


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


@dataclass(frozen=True)
class RankedCandidate:
    """Candidate plus ranking details used for selection and trace output."""

    candidate: ElementCandidate
    rank: int
    score: float
    source_priority: int
    target_match_score: float


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

    def __init__(
        self,
        engines: Iterable[PerceptionEngine],
        fusion: CandidateFusion | None = None,
    ) -> None:
        self._engines = tuple(engines)
        self._fusion = fusion or CandidateFusion()

    def detect(
        self,
        step: TaskStep,
        observation: ScreenObservation,
        config: RuntimeConfig,
    ) -> tuple[ElementCandidate, ...]:
        candidates: list[ElementCandidate] = []
        for engine in self._engines:
            candidates.extend(engine.detect(step, observation, config))
        return self._fusion.fuse(step, tuple(candidates), config)


class CandidateFusion:
    """Merges, deduplicates, and ranks UIA, OCR, and image candidates."""

    def fuse(
        self,
        step: TaskStep,
        candidates: tuple[ElementCandidate, ...],
        config: RuntimeConfig,
    ) -> tuple[ElementCandidate, ...]:
        _ = config
        deduplicated = deduplicate_candidates(step, candidates)
        ranked = rank_candidates(step, deduplicated, config)
        return tuple(_with_rank_metadata(candidate) for candidate in ranked)


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
    ambiguity_score_window: float = 0.02

    def select(
        self,
        step: TaskStep,
        candidates: tuple[ElementCandidate, ...],
        config: RuntimeConfig,
    ) -> ElementCandidate | None:
        ranked = [
            ranked_candidate
            for ranked_candidate in rank_candidates(step, candidates, config)
            if ranked_candidate.candidate.enabled
            and ranked_candidate.candidate.visible
            and ranked_candidate.candidate.confidence >= config.confidence_threshold
            and ranked_candidate.target_match_score > 0
        ]
        if not ranked:
            return None

        if (
            len(ranked) > 1
            and step.region is None
            and _is_ambiguous(
                ranked[0],
                ranked[1],
                self.ambiguity_score_window,
            )
        ):
            return None
        return ranked[0].candidate


def deduplicate_candidates(
    step: TaskStep,
    candidates: tuple[ElementCandidate, ...],
) -> tuple[ElementCandidate, ...]:
    ranked = rank_candidates(step, candidates, RuntimeConfig())
    kept: list[ElementCandidate] = []
    for ranked_candidate in ranked:
        candidate = ranked_candidate.candidate
        duplicate_index = _overlapping_candidate_index(candidate, kept)
        if duplicate_index is None:
            kept.append(candidate)
            continue
        kept[duplicate_index] = _merge_candidate_metadata(
            kept[duplicate_index],
            candidate,
        )
    return tuple(kept)


def rank_candidates(
    step: TaskStep,
    candidates: tuple[ElementCandidate, ...],
    config: RuntimeConfig,
) -> tuple[RankedCandidate, ...]:
    _ = config
    ranked = [
        RankedCandidate(
            candidate=candidate,
            rank=0,
            score=_ranking_score(step, candidate),
            source_priority=SOURCE_PRIORITY[candidate.source],
            target_match_score=_target_match_score(step.target, candidate.label),
        )
        for candidate in candidates
    ]
    ranked.sort(
        key=lambda ranked_candidate: (
            ranked_candidate.score,
            ranked_candidate.source_priority,
            ranked_candidate.candidate.confidence,
        ),
        reverse=True,
    )
    return tuple(
        replace(ranked_candidate, rank=rank)
        for rank, ranked_candidate in enumerate(ranked, start=1)
    )


def candidate_ranking_metadata(
    step: TaskStep,
    candidates: tuple[ElementCandidate, ...],
    config: RuntimeConfig,
) -> dict[str, object]:
    return {
        "candidate_rankings": [
            {
                "rank": ranked.rank,
                "id": ranked.candidate.id,
                "source": ranked.candidate.source,
                "label": ranked.candidate.label,
                "confidence": ranked.candidate.confidence,
                "score": ranked.score,
                "source_priority": ranked.source_priority,
                "target_match_score": ranked.target_match_score,
            }
            for ranked in rank_candidates(step, candidates, config)
        ],
    }


def _with_rank_metadata(ranked: RankedCandidate) -> ElementCandidate:
    metadata = {
        **ranked.candidate.metadata,
        "rank": ranked.rank,
        "ranking_score": ranked.score,
        "source_priority": ranked.source_priority,
        "target_match_score": ranked.target_match_score,
    }
    return replace(ranked.candidate, metadata=metadata)


def _ranking_score(step: TaskStep, candidate: ElementCandidate) -> float:
    visibility_score = 1.0 if candidate.visible and candidate.enabled else 0.0
    source_score = SOURCE_PRIORITY[candidate.source] / MAX_SOURCE_PRIORITY
    target_score = _target_match_score(step.target, candidate.label)
    return (
        (source_score * 0.35)
        + (candidate.confidence * 0.35)
        + (target_score * 0.2)
        + (visibility_score * 0.1)
    )


def _target_match_score(target: str | None, label: str) -> float:
    if target is None:
        return 1.0
    normalized_target = _normalize_text(target)
    normalized_label = _normalize_text(label)
    if not normalized_target or not normalized_label:
        return 0.0
    if normalized_target == normalized_label:
        return 1.0
    if normalized_target in normalized_label:
        return 0.95
    return SequenceMatcher(None, normalized_target, normalized_label).ratio()


def _overlapping_candidate_index(
    candidate: ElementCandidate,
    kept: list[ElementCandidate],
) -> int | None:
    for index, existing in enumerate(kept):
        if (
            _intersection_over_union(candidate.bounds, existing.bounds)
            >= OVERLAP_DEDUPLICATION_THRESHOLD
        ):
            return index
    return None


def _merge_candidate_metadata(
    kept: ElementCandidate,
    duplicate: ElementCandidate,
) -> ElementCandidate:
    merged_ids = list(_metadata_tuple(kept.metadata, "merged_candidate_ids", kept.id))
    merged_ids.append(duplicate.id)
    merged_sources = list(
        _metadata_tuple(kept.metadata, "merged_sources", kept.source),
    )
    merged_sources.append(duplicate.source)
    return replace(
        kept,
        metadata={
            **kept.metadata,
            "merged_candidate_ids": tuple(merged_ids),
            "merged_sources": tuple(merged_sources),
        },
    )


def _metadata_tuple(
    metadata: dict[str, object],
    key: str,
    fallback: str,
) -> tuple[str, ...]:
    value = metadata.get(key)
    if isinstance(value, tuple) and all(isinstance(item, str) for item in value):
        return value
    return (fallback,)


def _intersection_over_union(first: Bounds, second: Bounds) -> float:
    first_right = first.x + first.width
    first_bottom = first.y + first.height
    second_right = second.x + second.width
    second_bottom = second.y + second.height

    intersection_left = max(first.x, second.x)
    intersection_top = max(first.y, second.y)
    intersection_right = min(first_right, second_right)
    intersection_bottom = min(first_bottom, second_bottom)

    intersection_width = max(0, intersection_right - intersection_left)
    intersection_height = max(0, intersection_bottom - intersection_top)
    intersection = intersection_width * intersection_height
    if intersection == 0:
        return 0.0

    first_area = first.width * first.height
    second_area = second.width * second.height
    return intersection / (first_area + second_area - intersection)


def _is_ambiguous(
    first: RankedCandidate,
    second: RankedCandidate,
    score_window: float,
) -> bool:
    return (
        first.source_priority == second.source_priority
        and abs(first.score - second.score) <= score_window
    )


def _normalize_text(value: str) -> str:
    return " ".join(value.casefold().split())
