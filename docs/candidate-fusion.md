# Candidate Fusion

Candidate fusion merges UIA, OCR, and image-template detections before target
selection. The goal is deterministic target selection with enough trace detail
to debug why a candidate won or why selection was blocked.

## Shared Candidate Model

Every perception source emits `ElementCandidate` objects with:

- `id`
- `source`
- `label`
- `bounds`
- `confidence`
- `visible`
- `enabled`
- `metadata`

## Ranking

Candidates are ranked with source reliability, source confidence, target text
match quality, and visibility/enabled state. UIA is preferred over OCR and image
matching when scores are close because UIA usually reflects real controls rather
than pixels alone.

## Deduplication

Overlapping candidates are deduplicated when their intersection-over-union is
high enough to represent the same target. The retained candidate includes
metadata describing merged candidate IDs and sources.

## Ambiguity

If two top candidates from the same source priority have nearly identical scores
and the task did not provide a `region`, target selection returns no candidate.
The planner records the ranking list in `detect_candidates` trace metadata so
the task author can add a region or more specific selector.
