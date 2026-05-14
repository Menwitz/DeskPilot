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
SOURCE_RELIABILITY_SCORE: dict[CandidateSource, float] = {
    "uia": 1.0,
    "ocr": 0.78,
    "image": 0.68,
    "unknown": 0.35,
}
SOURCE_SUPPORT_WEIGHT: dict[CandidateSource, float] = {
    "uia": 0.45,
    "ocr": 0.30,
    "image": 0.20,
    "unknown": 0.05,
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
    region_match_score: float
    source_reliability_score: float
    source_support_score: float
    confidence_score: float
    visibility_score: float


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


class DryRunPerceptionEngine(PerceptionEngine):
    """Produces synthetic candidates so dry-run can plan without live screen data."""

    def detect(
        self,
        step: TaskStep,
        observation: ScreenObservation,
        config: RuntimeConfig,
    ) -> tuple[ElementCandidate, ...]:
        _ = observation, config
        label = _dry_run_label(step)
        if label is None:
            return ()
        return (
            ElementCandidate(
                id=f"dry-run-{step.id}",
                source="unknown",
                label=label,
                bounds=Bounds(x=0, y=0, width=1, height=1),
                confidence=1.0,
                metadata={"dry_run": True},
            ),
        )


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
            and _candidate_matches_region(step, ranked_candidate)
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
        _ranked_candidate(step, candidate)
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
                "fusion_score": ranked.score,
                "source_priority": ranked.source_priority,
                "source_reliability_score": ranked.source_reliability_score,
                "source_support_score": ranked.source_support_score,
                "confidence_score": ranked.confidence_score,
                "target_match_score": ranked.target_match_score,
                "region_match_score": ranked.region_match_score,
                "visibility_score": ranked.visibility_score,
            }
            for ranked in rank_candidates(step, candidates, config)
        ],
    }


def ui_state_snapshot_metadata(
    step: TaskStep,
    candidates: tuple[ElementCandidate, ...],
    selected: ElementCandidate | None,
    config: RuntimeConfig,
    *,
    selection_blocked: str | None = None,
) -> dict[str, object]:
    ranked = rank_candidates(step, candidates, config)
    selected_id = selected.id if selected is not None else None
    return {
        "visible_controls": [
            _candidate_snapshot(ranked_candidate)
            for ranked_candidate in ranked
            if ranked_candidate.candidate.visible
        ],
        "selected_candidate": _candidate_snapshot_for_id(ranked, selected_id),
        "blocked_candidates": [
            {
                **_candidate_snapshot(ranked_candidate),
                "blocked_reason": _candidate_block_reason(
                    step,
                    ranked_candidate,
                    config,
                    selected_id,
                    selection_blocked,
                ),
            }
            for ranked_candidate in ranked
            if ranked_candidate.candidate.id != selected_id
        ],
    }


def _with_rank_metadata(ranked: RankedCandidate) -> ElementCandidate:
    metadata = {
        **ranked.candidate.metadata,
        "rank": ranked.rank,
        "ranking_score": ranked.score,
        "fusion_score": ranked.score,
        "source_priority": ranked.source_priority,
        "source_reliability_score": ranked.source_reliability_score,
        "source_support_score": ranked.source_support_score,
        "confidence_score": ranked.confidence_score,
        "target_match_score": ranked.target_match_score,
        "region_match_score": ranked.region_match_score,
        "visibility_score": ranked.visibility_score,
    }
    return replace(ranked.candidate, metadata=metadata)


def _candidate_snapshot_for_id(
    ranked: tuple[RankedCandidate, ...],
    candidate_id: str | None,
) -> dict[str, object] | None:
    if candidate_id is None:
        return None
    for ranked_candidate in ranked:
        if ranked_candidate.candidate.id == candidate_id:
            return _candidate_snapshot(ranked_candidate)
    return None


def _candidate_snapshot(ranked: RankedCandidate) -> dict[str, object]:
    candidate = ranked.candidate
    return {
        "id": candidate.id,
        "source": candidate.source,
        "label": candidate.label,
        "confidence": candidate.confidence,
        "enabled": candidate.enabled,
        "visible": candidate.visible,
        "rank": ranked.rank,
        "fusion_score": ranked.score,
        "target_match_score": ranked.target_match_score,
        "region_match_score": ranked.region_match_score,
    }


def _candidate_block_reason(
    step: TaskStep,
    ranked: RankedCandidate,
    config: RuntimeConfig,
    selected_id: str | None,
    selection_blocked: str | None,
) -> str:
    candidate = ranked.candidate
    if not candidate.visible:
        return "not_visible"
    if not candidate.enabled:
        return "disabled"
    if candidate.confidence < config.confidence_threshold:
        return "below_confidence_threshold"
    if ranked.target_match_score <= 0:
        return "target_mismatch"
    if step.region is not None and ranked.region_match_score <= 0:
        return "outside_region"
    if selected_id is None and selection_blocked is not None:
        return selection_blocked
    return "lower_ranked_candidate"


def _ranked_candidate(step: TaskStep, candidate: ElementCandidate) -> RankedCandidate:
    visibility_score = 1.0 if candidate.visible and candidate.enabled else 0.0
    source_reliability_score = _source_reliability_score(candidate)
    source_support_score = _source_support_score(candidate)
    target_score = _target_match_score(step.target, candidate.label)
    region_score = _region_match_score(step, candidate)
    base_score = (
        (source_reliability_score * 0.25)
        + (candidate.confidence * 0.25)
        + (target_score * 0.25)
        + (source_support_score * 0.15)
        + (visibility_score * 0.1)
    )
    score = base_score
    if step.region is not None:
        # Region is a task-authored disambiguation hint, so it carries enough
        # weight to separate repeated labels without bypassing confidence gates.
        score = (base_score * 0.75) + (region_score * 0.25)
    return RankedCandidate(
        candidate=candidate,
        rank=0,
        score=score,
        source_priority=SOURCE_PRIORITY[candidate.source],
        target_match_score=target_score,
        region_match_score=region_score,
        source_reliability_score=source_reliability_score,
        source_support_score=source_support_score,
        confidence_score=candidate.confidence,
        visibility_score=visibility_score,
    )


def _candidate_matches_region(
    step: TaskStep,
    ranked_candidate: RankedCandidate,
) -> bool:
    return step.region is None or ranked_candidate.region_match_score > 0


def _region_match_score(step: TaskStep, candidate: ElementCandidate) -> float:
    if step.region is None:
        return 1.0
    region = Bounds(
        x=step.region.x,
        y=step.region.y,
        width=step.region.width,
        height=step.region.height,
    )
    if _bounds_center_inside(candidate.bounds, region):
        return 1.0
    candidate_area = candidate.bounds.width * candidate.bounds.height
    if candidate_area <= 0:
        return 0.0
    intersection_area = _intersection_area(candidate.bounds, region)
    return intersection_area / candidate_area


def _source_reliability_score(candidate: ElementCandidate) -> float:
    return max(
        SOURCE_RELIABILITY_SCORE[source]
        for source in _candidate_sources(candidate)
    )


def _source_support_score(candidate: ElementCandidate) -> float:
    return min(
        1.0,
        sum(
            SOURCE_SUPPORT_WEIGHT[source]
            for source in set(_candidate_sources(candidate))
        ),
    )


def _candidate_sources(candidate: ElementCandidate) -> tuple[CandidateSource, ...]:
    sources: list[CandidateSource] = []
    raw_sources = candidate.metadata.get("merged_sources")
    if isinstance(raw_sources, tuple | list):
        for source in raw_sources:
            if isinstance(source, str) and source in SOURCE_PRIORITY:
                sources.append(source)
    if candidate.source not in sources:
        sources.append(candidate.source)
    return tuple(sources)


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
    intersection = _intersection_area(first, second)
    if intersection == 0:
        return 0.0

    first_area = first.width * first.height
    second_area = second.width * second.height
    return intersection / (first_area + second_area - intersection)


def _intersection_area(first: Bounds, second: Bounds) -> int:
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
    return intersection_width * intersection_height


def _bounds_center_inside(bounds: Bounds, region: Bounds) -> bool:
    center_x = bounds.x + (bounds.width / 2)
    center_y = bounds.y + (bounds.height / 2)
    return (
        region.x <= center_x <= region.x + region.width
        and region.y <= center_y <= region.y + region.height
    )


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


def _dry_run_label(step: TaskStep) -> str | None:
    if step.target:
        return step.target
    if step.verify and step.verify.text:
        return step.verify.text
    if step.image:
        return step.image.name
    if step.verify and step.verify.image:
        return step.verify.image.name
    return None
