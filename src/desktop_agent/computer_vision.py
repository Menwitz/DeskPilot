"""OpenCV-backed image-template perception."""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any, Protocol

from desktop_agent.config import RuntimeConfig
from desktop_agent.perception import ElementCandidate, PerceptionEngine
from desktop_agent.screen import Bounds, ScreenObservation
from desktop_agent.task_dsl import TaskRegion, TaskStep


class ComputerVisionUnavailableError(RuntimeError):
    """Raised when the local computer-vision backend cannot run."""


@dataclass(frozen=True)
class TemplateMatch:
    """Template match normalized into screenshot coordinates."""

    template_path: Path
    bounds: Bounds
    confidence: float
    grayscale: bool


class TemplateMatcher(Protocol):
    """Interface for image-template matching backends."""

    def match(
        self,
        screenshot_path: Path,
        template_path: Path,
        region: TaskRegion | None,
    ) -> tuple[TemplateMatch, ...]: ...

    def save_overlay(
        self,
        screenshot_path: Path,
        matches: tuple[TemplateMatch, ...],
        output_path: Path,
    ) -> None: ...


class OpenCvTemplateMatcher(TemplateMatcher):
    """Local OpenCV template matcher with grayscale matching enabled."""

    def __init__(self, *, grayscale: bool = True) -> None:
        self._grayscale = grayscale

    def match(
        self,
        screenshot_path: Path,
        template_path: Path,
        region: TaskRegion | None,
    ) -> tuple[TemplateMatch, ...]:
        cv2 = _cv2_module()
        screenshot = _read_image(cv2, screenshot_path, self._grayscale)
        template = _read_image(cv2, template_path, self._grayscale)
        search_image, offset = _restrict_to_region(screenshot, region)

        if (
            search_image.shape[0] < template.shape[0]
            or search_image.shape[1] < template.shape[1]
        ):
            return ()

        result = cv2.matchTemplate(search_image, template, cv2.TM_CCOEFF_NORMED)
        _, confidence, _, location = cv2.minMaxLoc(result)
        if confidence < 0:
            return ()

        return (
            TemplateMatch(
                template_path=template_path,
                bounds=Bounds(
                    x=int(location[0] + offset[0]),
                    y=int(location[1] + offset[1]),
                    width=int(template.shape[1]),
                    height=int(template.shape[0]),
                ),
                confidence=float(confidence),
                grayscale=self._grayscale,
            ),
        )

    def save_overlay(
        self,
        screenshot_path: Path,
        matches: tuple[TemplateMatch, ...],
        output_path: Path,
    ) -> None:
        cv2 = _cv2_module()
        image = _read_image(cv2, screenshot_path, grayscale=False)
        for match in matches:
            top_left = (match.bounds.x, match.bounds.y)
            bottom_right = (
                match.bounds.x + match.bounds.width,
                match.bounds.y + match.bounds.height,
            )
            cv2.rectangle(image, top_left, bottom_right, (0, 255, 0), 1)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(output_path), image)


class OpenCvTemplatePerceptionEngine(PerceptionEngine):
    """Converts OpenCV template matches into shared image candidates."""

    def __init__(self, matcher: TemplateMatcher | None = None) -> None:
        self._matcher = matcher or OpenCvTemplateMatcher()

    def detect(
        self,
        step: TaskStep,
        observation: ScreenObservation,
        config: RuntimeConfig,
    ) -> tuple[ElementCandidate, ...]:
        template_path = _step_template_path(step)
        if observation.screenshot_path is None or template_path is None:
            return ()

        try:
            matches = self._matcher.match(
                observation.screenshot_path,
                template_path,
                step.region,
            )
        except ComputerVisionUnavailableError:
            return ()

        candidates = _matches_to_candidates(step, matches, config)
        if config.save_screenshots:
            overlay_path = _overlay_path(config.trace_root, step.id)
            self._matcher.save_overlay(
                observation.screenshot_path,
                matches,
                overlay_path,
            )
            _write_detection_report(
                step,
                matches,
                candidates,
                overlay_path,
                config.trace_root,
            )
        return candidates


def _matches_to_candidates(
    step: TaskStep,
    matches: tuple[TemplateMatch, ...],
    config: RuntimeConfig,
) -> tuple[ElementCandidate, ...]:
    candidates: list[ElementCandidate] = []
    for index, match in enumerate(matches):
        if match.confidence < config.confidence_threshold:
            continue
        candidates.append(
            ElementCandidate(
                id=f"image-{step.id}-{index}",
                source="image",
                label=match.template_path.name,
                bounds=match.bounds,
                confidence=match.confidence,
                metadata={
                    "template_path": str(match.template_path),
                    "grayscale": match.grayscale,
                },
            ),
        )
    return tuple(candidates)


def _step_template_path(step: TaskStep) -> Path | None:
    if step.image is not None:
        return step.image
    if step.verify and step.verify.image is not None:
        return step.verify.image
    return None


def _restrict_to_region(
    image: Any,
    region: TaskRegion | None,
) -> tuple[Any, tuple[int, int]]:
    if region is None:
        return image, (0, 0)
    y_end = region.y + region.height
    x_end = region.x + region.width
    return image[region.y : y_end, region.x : x_end], (region.x, region.y)


def _read_image(cv2: Any, path: Path, grayscale: bool) -> Any:
    mode = cv2.IMREAD_GRAYSCALE if grayscale else cv2.IMREAD_COLOR
    image = cv2.imread(str(path), mode)
    if image is None:
        raise ComputerVisionUnavailableError(f"image could not be read: {path}")
    return image


def _cv2_module() -> Any:
    try:
        return import_module("cv2")
    except Exception as exc:
        raise ComputerVisionUnavailableError("OpenCV backend is unavailable") from exc


def _overlay_path(trace_root: Path, step_id: str) -> Path:
    return trace_root / "overlays" / f"{step_id}.png"


def _write_detection_report(
    step: TaskStep,
    matches: tuple[TemplateMatch, ...],
    candidates: tuple[ElementCandidate, ...],
    overlay_path: Path,
    trace_root: Path,
) -> Path:
    output_path = trace_root / "cv" / f"{step.id}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "step_id": step.id,
        "overlay_path": str(overlay_path),
        "matches": [_match_to_dict(match) for match in matches],
        "candidates": [_candidate_to_dict(candidate) for candidate in candidates],
        "scale_tolerant": False,
    }
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return output_path


def _match_to_dict(match: TemplateMatch) -> dict[str, object]:
    return {
        "template_path": str(match.template_path),
        "bounds": _bounds_to_dict(match.bounds),
        "confidence": match.confidence,
        "grayscale": match.grayscale,
    }


def _candidate_to_dict(candidate: ElementCandidate) -> dict[str, object]:
    return {
        "id": candidate.id,
        "label": candidate.label,
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
