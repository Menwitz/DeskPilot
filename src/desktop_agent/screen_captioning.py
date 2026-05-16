"""Review-only screenshot caption prompt reports."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from desktop_agent.local_model_prompts import (
    LocalModelPrompt,
    build_screen_summary_prompt,
)


@dataclass(frozen=True)
class ScreenCaptionReviewReport:
    """Review-only prompt report for local screenshot captioning."""

    status: str
    screen_summary: Mapping[str, object]
    prompt: LocalModelPrompt
    review_only: bool = True
    authoring_only: bool = True
    direct_action_allowed: bool = False

    def metadata(self) -> dict[str, object]:
        return {
            "status": self.status,
            "review_only": self.review_only,
            "authoring_only": self.authoring_only,
            "direct_action_allowed": self.direct_action_allowed,
            "screen_summary": dict(self.screen_summary),
            "prompt": self.prompt.metadata(),
        }


def screen_caption_review_from_inspection(
    inspection: Mapping[str, object],
    *,
    inspection_report_path: Path | None = None,
) -> ScreenCaptionReviewReport:
    """Create a review-only screen caption prompt from inspect-screen output."""
    screen_summary = _screen_summary_from_inspection(inspection)
    artifact_references = _caption_artifact_references(
        inspection,
        inspection_report_path,
    )
    prompt = build_screen_summary_prompt(
        screen_summary=screen_summary,
        artifact_references=artifact_references,
    )
    return ScreenCaptionReviewReport(
        status="prompt_ready",
        screen_summary=screen_summary,
        prompt=prompt,
    )


def write_screen_caption_review_report(
    report: ScreenCaptionReviewReport,
    output_path: Path,
) -> Path:
    """Write local caption prompt metadata for review and routine authoring."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report.metadata(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def _screen_summary_from_inspection(
    inspection: Mapping[str, object],
) -> dict[str, object]:
    return {
        "screenshot_path": _optional_string(inspection.get("screenshot_path")),
        "size": _sequence_or_empty(inspection.get("size")),
        "warnings": _sequence_or_empty(inspection.get("warnings")),
        "active_window_title": _active_window_title(inspection),
        "ocr_text": _ocr_text(inspection),
        "candidate_labels": _candidate_labels(inspection),
    }


def _caption_artifact_references(
    inspection: Mapping[str, object],
    inspection_report_path: Path | None,
) -> tuple[str, ...]:
    references: list[str] = []
    if inspection_report_path is not None:
        references.append(str(inspection_report_path))
    screenshot_path = _optional_string(inspection.get("screenshot_path"))
    if screenshot_path is not None:
        references.append(screenshot_path)
    return tuple(references)


def _active_window_title(inspection: Mapping[str, object]) -> str | None:
    uia = inspection.get("uia")
    if not isinstance(uia, Mapping):
        return None
    tree = uia.get("tree")
    if not isinstance(tree, Mapping):
        return None
    active_window = tree.get("active_window")
    if not isinstance(active_window, Mapping):
        return None
    return _optional_string(active_window.get("title"))


def _ocr_text(inspection: Mapping[str, object]) -> tuple[str, ...]:
    ocr = inspection.get("ocr")
    if not isinstance(ocr, Mapping):
        return ()
    blocks = ocr.get("blocks")
    if not isinstance(blocks, Sequence) or isinstance(blocks, (str, bytes)):
        return ()
    texts: list[str] = []
    for block in blocks:
        if isinstance(block, Mapping):
            text = _optional_string(block.get("text"))
            if text is not None:
                texts.append(text)
    return tuple(texts)


def _candidate_labels(inspection: Mapping[str, object]) -> tuple[str, ...]:
    candidates = inspection.get("candidates")
    if not isinstance(candidates, Sequence) or isinstance(candidates, (str, bytes)):
        return ()
    labels: list[str] = []
    for candidate in candidates:
        if isinstance(candidate, Mapping):
            label = _optional_string(candidate.get("label"))
            if label is not None and label not in labels:
                labels.append(label)
    return tuple(labels)


def _optional_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _sequence_or_empty(value: object) -> tuple[object, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(value)
