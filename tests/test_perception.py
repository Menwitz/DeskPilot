from desktop_agent.config import RuntimeConfig
from desktop_agent.perception import (
    CandidateFusion,
    CandidateSource,
    ConfidenceTargetSelector,
    DryRunPerceptionEngine,
    ElementCandidate,
    candidate_ranking_metadata,
    deduplicate_candidates,
    rank_candidates,
)
from desktop_agent.screen import Bounds, ScreenObservation
from desktop_agent.task_dsl import TaskRegion, TaskStep


def candidate(
    candidate_id: str,
    source: CandidateSource,
    confidence: float,
    *,
    x: int = 0,
    label: str = "Submit",
) -> ElementCandidate:
    return ElementCandidate(
        id=candidate_id,
        source=source,
        label=label,
        bounds=Bounds(x=x, y=0, width=100, height=30),
        confidence=confidence,
    )


def test_deduplicate_candidates_merges_overlapping_candidates() -> None:
    deduplicated = deduplicate_candidates(
        TaskStep(id="click-submit", action="click_text", target="Submit"),
        (
            candidate("ocr-1", "ocr", 0.96),
            candidate("uia-1", "uia", 0.93),
        ),
    )

    assert len(deduplicated) == 1
    assert deduplicated[0].id == "uia-1"
    assert deduplicated[0].metadata["merged_candidate_ids"] == ("uia-1", "ocr-1")


def test_candidate_fusion_ranks_and_annotates_candidates() -> None:
    fused = CandidateFusion().fuse(
        TaskStep(id="click-submit", action="click_text", target="Submit"),
        (
            candidate("ocr-1", "ocr", 0.96),
            candidate("uia-1", "uia", 0.93),
            candidate("image-1", "image", 0.99, x=200, label="Submit icon"),
        ),
        RuntimeConfig(confidence_threshold=0.8),
    )

    assert [item.id for item in fused] == ["uia-1", "image-1"]
    assert fused[0].metadata["rank"] == 1
    assert fused[0].metadata["source_priority"] == 3
    assert "fusion_score" in fused[0].metadata
    assert "source_support_score" in fused[0].metadata
    assert fused[1].metadata["rank"] == 2


def test_candidate_fusion_scores_cross_source_support() -> None:
    fused = CandidateFusion().fuse(
        TaskStep(id="click-submit", action="click_text", target="Submit"),
        (
            candidate("uia-1", "uia", 0.90),
            candidate("ocr-1", "ocr", 0.88),
            candidate("image-1", "image", 0.86),
            candidate("ocr-2", "ocr", 0.97, x=240),
        ),
        RuntimeConfig(confidence_threshold=0.8),
    )

    supported = fused[0]
    unsupported = fused[1]
    assert supported.id == "uia-1"
    assert supported.metadata["merged_sources"] == ("uia", "ocr", "image")
    assert supported.metadata["source_reliability_score"] == 1.0
    assert supported.metadata["source_support_score"] == 0.95
    supported_score = supported.metadata["fusion_score"]
    unsupported_score = unsupported.metadata["fusion_score"]
    assert isinstance(supported_score, float)
    assert isinstance(unsupported_score, float)
    assert supported_score > unsupported_score


def test_rank_candidates_uses_target_match_quality() -> None:
    ranked = rank_candidates(
        TaskStep(id="click-submit", action="click_text", target="Submit"),
        (
            candidate("exact", "ocr", 0.90, label="Submit"),
            candidate("weak", "ocr", 0.99, label="Settings"),
        ),
        RuntimeConfig(confidence_threshold=0.8),
    )

    assert ranked[0].candidate.id == "exact"
    assert ranked[0].target_match_score == 1.0


def test_confidence_selector_rejects_ambiguous_same_priority_candidates() -> None:
    selected = ConfidenceTargetSelector().select(
        TaskStep(id="click-submit", action="click_text", target="Submit"),
        (
            candidate("candidate-1", "uia", 0.95),
            candidate("candidate-2", "uia", 0.94, x=200),
        ),
        RuntimeConfig(confidence_threshold=0.8),
    )

    assert selected is None


def test_confidence_selector_prefers_higher_priority_source_when_unambiguous() -> None:
    selected = ConfidenceTargetSelector().select(
        TaskStep(id="click-submit", action="click_text", target="Submit"),
        (
            candidate("candidate-1", "ocr", 0.95),
            candidate("candidate-2", "uia", 0.94),
        ),
        RuntimeConfig(confidence_threshold=0.8),
    )

    assert selected is not None
    assert selected.id == "candidate-2"


def test_confidence_selector_allows_ambiguous_candidates_with_region() -> None:
    selected = ConfidenceTargetSelector().select(
        TaskStep(
            id="click-submit",
            action="click_text",
            target="Submit",
            region=TaskRegion(x=0, y=0, width=320, height=240),
        ),
        (
            candidate("candidate-1", "uia", 0.95),
            candidate("candidate-2", "uia", 0.94, x=200),
        ),
        RuntimeConfig(confidence_threshold=0.8),
    )

    assert selected is not None
    assert selected.id == "candidate-1"


def test_candidate_ranking_metadata_is_trace_ready() -> None:
    metadata = candidate_ranking_metadata(
        TaskStep(id="click-submit", action="click_text", target="Submit"),
        (candidate("candidate-1", "uia", 0.95),),
        RuntimeConfig(confidence_threshold=0.8),
    )

    rankings = metadata["candidate_rankings"]
    assert isinstance(rankings, list)
    assert rankings[0]["id"] == "candidate-1"
    assert rankings[0]["rank"] == 1
    assert "fusion_score" in rankings[0]
    assert "source_support_score" in rankings[0]


def test_dry_run_perception_emits_synthetic_planning_candidate() -> None:
    candidates = DryRunPerceptionEngine().detect(
        TaskStep(id="scroll-submit", action="scroll_until", target="Submit"),
        ScreenObservation(),
        config=RuntimeConfig(),
    )

    assert len(candidates) == 1
    assert candidates[0].id == "dry-run-scroll-submit"
    assert candidates[0].label == "Submit"
    assert candidates[0].metadata["dry_run"] is True
