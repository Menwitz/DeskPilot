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

Ranking metadata includes a score breakdown for monitoring and reports:

- `fusion_score`: final ranking score used for ordering.
- `source_reliability_score`: highest reliability score from the candidate's
  supporting sources.
- `source_support_score`: weighted support from merged UIA, OCR, image, and
  unknown-source evidence.
- `confidence_score`: the source confidence value.
- `target_match_score`: text or label match against the task target.
- `region_match_score`: whether the candidate is inside the task's declared
  region, or how much of the candidate overlaps it.
- `visibility_score`: whether the candidate is visible and enabled.

## Deduplication

Overlapping candidates are deduplicated when their intersection-over-union is
high enough to represent the same target. The retained candidate includes
metadata describing merged candidate IDs and sources.
Merged sources feed the `source_support_score`, so a target corroborated by UIA,
OCR, and image-template detection receives stronger grounding metadata than a
single-source candidate with similar confidence.

## Ambiguity

If two top candidates from the same source priority have nearly identical scores
and the task did not provide a `region`, target selection returns no candidate.
The planner records the ranking list in `detect_candidates` trace metadata so
the task author can add a region or more specific selector.

When normal selection fails while candidates are available across multiple
families, the planner treats it as a possible `layout_change`. It then isolates
UIA, OCR, image, and unknown-source candidates in a fixed order and lets the
selector choose inside one family. The recovery event records
`selector_family_attempts`, `alternate_selector_family`, and the selected
candidate ID, so reports show whether a layout shift was recovered without
loosening confidence checks.

When a task provides a `region`, candidates outside the region are filtered from
target selection. Candidates whose center falls inside the region receive a full
region score; partial overlaps receive proportional credit. This lets repeated
labels and repeated image-template icon matches resolve to the intended part of
the screen without disabling confidence checks.

## UI State Snapshots

The planner records `ui_state_snapshot` after each target-selection pass. The
snapshot summarizes visible controls, the selected candidate, confidence and
fusion scores, and blocked candidates with reasons such as disabled, not
visible, below confidence threshold, outside the task region, target mismatch,
or ambiguity gate.
