"""Offline OCR perception adapter and text matching helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from difflib import SequenceMatcher
from importlib import import_module
from pathlib import Path
from typing import Any, Literal, Protocol, cast

from desktop_agent.config import RuntimeConfig
from desktop_agent.perception import ElementCandidate, PerceptionEngine
from desktop_agent.redaction import (
    RedactionPolicy,
    mask_ocr_text,
    should_save_ocr_text,
)
from desktop_agent.screen import Bounds, ScreenObservation
from desktop_agent.task_dsl import TaskStep

OcrMatchMode = Literal["exact", "contains", "fuzzy"]


class OcrUnavailableError(RuntimeError):
    """Raised when the configured local OCR backend cannot run."""


@dataclass(frozen=True)
class OcrTextBlock:
    """OCR text normalized into screenshot coordinates and 0..1 confidence."""

    text: str
    bounds: Bounds
    confidence: float


class OcrProvider(Protocol):
    """Interface for local OCR backends."""

    def extract_text(self, screenshot_path: Path) -> tuple[OcrTextBlock, ...]: ...


class TesseractOcrProvider(OcrProvider):
    """Offline OCR provider backed by local Pillow and Tesseract installs."""

    def extract_text(self, screenshot_path: Path) -> tuple[OcrTextBlock, ...]:
        try:
            image_module = import_module("PIL.Image")
            pytesseract = import_module("pytesseract")
            image = image_module.open(screenshot_path)
            data = pytesseract.image_to_data(
                image,
                output_type=pytesseract.Output.DICT,
            )
        except Exception as exc:
            raise OcrUnavailableError("offline OCR backend is unavailable") from exc

        return tuple(_blocks_from_tesseract_data(cast(dict[str, list[Any]], data)))


class OcrPerceptionEngine(PerceptionEngine):
    """Converts local OCR text blocks into shared perception candidates."""

    def __init__(self, provider: OcrProvider | None = None) -> None:
        self._provider = provider or TesseractOcrProvider()

    def detect(
        self,
        step: TaskStep,
        observation: ScreenObservation,
        config: RuntimeConfig,
    ) -> tuple[ElementCandidate, ...]:
        if observation.screenshot_path is None:
            return ()

        try:
            text_blocks = self._provider.extract_text(observation.screenshot_path)
        except OcrUnavailableError:
            return ()

        candidates = ocr_blocks_to_candidates(step, text_blocks, config)
        if should_save_ocr_text(
            config.redaction_policy,
            save_enabled=config.save_ocr_text,
        ):
            save_ocr_text_output(
                step,
                text_blocks,
                candidates,
                config.trace_root,
                config.redaction_policy,
            )
        return candidates


def ocr_blocks_to_candidates(
    step: TaskStep,
    text_blocks: tuple[OcrTextBlock, ...],
    config: RuntimeConfig,
) -> tuple[ElementCandidate, ...]:
    candidates: list[ElementCandidate] = []
    for index, block in enumerate(text_blocks):
        if block.confidence < config.confidence_threshold:
            continue

        match_score = _target_match_score(step.target, block.text)
        if match_score <= 0:
            continue

        confidence = min(block.confidence, match_score)
        if confidence < config.confidence_threshold:
            continue

        candidates.append(
            ElementCandidate(
                id=f"ocr-{step.id}-{index}",
                source="ocr",
                label=block.text,
                bounds=block.bounds,
                confidence=confidence,
                metadata={
                    "ocr_confidence": block.confidence,
                    "text_match_score": match_score,
                },
            ),
        )
    return tuple(candidates)


def match_ocr_text(query: str, value: str, mode: OcrMatchMode) -> float:
    normalized_query = _normalize_text(query)
    normalized_value = _normalize_text(value)
    if not normalized_query or not normalized_value:
        return 0.0

    if mode == "exact":
        return 1.0 if normalized_query == normalized_value else 0.0
    if mode == "contains":
        return 1.0 if normalized_query in normalized_value else 0.0

    return SequenceMatcher(None, normalized_query, normalized_value).ratio()


def save_ocr_text_output(
    step: TaskStep,
    text_blocks: tuple[OcrTextBlock, ...],
    candidates: tuple[ElementCandidate, ...],
    trace_root: Path,
    redaction_policy: RedactionPolicy | None = None,
) -> Path:
    policy = redaction_policy or RedactionPolicy()
    output_dir = trace_root / "ocr"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{step.id}.json"
    payload = {
        "step_id": step.id,
        "ocr_text_redaction": policy.ocr_text,
        "blocks": [_block_to_dict(block, policy) for block in text_blocks],
        "candidates": [
            _candidate_to_dict(candidate, policy) for candidate in candidates
        ],
    }
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return output_path


def _target_match_score(target: str | None, value: str) -> float:
    if target is None:
        return 1.0
    return max(
        match_ocr_text(target, value, "exact"),
        match_ocr_text(target, value, "contains"),
        match_ocr_text(target, value, "fuzzy"),
    )


def _blocks_from_tesseract_data(data: dict[str, list[Any]]) -> list[OcrTextBlock]:
    blocks: list[OcrTextBlock] = []
    for index, text_value in enumerate(data.get("text", [])):
        text = str(text_value).strip()
        if not text:
            continue

        left = _int_at(data, "left", index)
        top = _int_at(data, "top", index)
        width = _int_at(data, "width", index)
        height = _int_at(data, "height", index)
        if left is None or top is None or width is None or height is None:
            continue

        confidence = _normalize_confidence(_value_at(data, "conf", index))
        bounds = Bounds(
            x=left,
            y=top,
            width=width,
            height=height,
        )
        if bounds.width <= 0 or bounds.height <= 0:
            continue
        blocks.append(OcrTextBlock(text=text, bounds=bounds, confidence=confidence))
    return blocks


def _int_at(data: dict[str, list[Any]], key: str, index: int) -> int | None:
    value = _value_at(data, key, index)
    if isinstance(value, bool) or not isinstance(value, str | int | float):
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _value_at(data: dict[str, list[Any]], key: str, index: int) -> object | None:
    values = data.get(key, [])
    if index >= len(values):
        return None
    return cast(object, values[index])


def _normalize_confidence(value: object) -> float:
    if not isinstance(value, str | int | float):
        return 0.0
    try:
        confidence = float(value)
    except ValueError:
        return 0.0
    if confidence < 0:
        return 0.0
    if confidence > 1:
        confidence = confidence / 100
    return min(confidence, 1.0)


def _normalize_text(value: str) -> str:
    return " ".join(value.casefold().split())


def _block_to_dict(
    block: OcrTextBlock,
    policy: RedactionPolicy,
) -> dict[str, object]:
    redacted_text = mask_ocr_text(block.text, policy)
    return {
        "text": redacted_text,
        "text_length": len(block.text),
        "bounds": _bounds_to_dict(block.bounds),
        "confidence": block.confidence,
    }


def _candidate_to_dict(
    candidate: ElementCandidate,
    policy: RedactionPolicy,
) -> dict[str, object]:
    redacted_label = mask_ocr_text(candidate.label, policy)
    return {
        "id": candidate.id,
        "label": redacted_label,
        "label_length": len(candidate.label),
        "bounds": _bounds_to_dict(candidate.bounds),
        "confidence": candidate.confidence,
        "metadata": candidate.metadata,
    }


def _bounds_to_dict(bounds: Bounds) -> dict[str, int]:
    return {
        "x": bounds.x,
        "y": bounds.y,
        "width": bounds.width,
        "height": bounds.height,
    }
