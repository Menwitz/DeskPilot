import json
from pathlib import Path

import pytest

from desktop_agent.computer_vision import (
    OpenCvTemplateMatcher,
    OpenCvTemplatePerceptionEngine,
)
from desktop_agent.config import RuntimeConfig
from desktop_agent.screen import ScreenObservation
from desktop_agent.task_dsl import TaskRegion, TaskStep

pytest.importorskip("cv2")

SCREENSHOT = Path("tests/fixtures/cv-screen.pgm")
TEMPLATE = Path("tests/fixtures/cv-template.pgm")


def test_opencv_template_matching_returns_image_candidate(tmp_path: Path) -> None:
    engine = OpenCvTemplatePerceptionEngine(OpenCvTemplateMatcher())
    step = TaskStep(id="find-icon", action="click_image", image=TEMPLATE)

    candidates = engine.detect(
        step,
        ScreenObservation(screenshot_path=SCREENSHOT),
        RuntimeConfig(trace_root=tmp_path, confidence_threshold=0.99),
    )

    report = json.loads((tmp_path / "cv" / "find-icon.json").read_text())
    assert len(candidates) == 1
    assert candidates[0].source == "image"
    assert candidates[0].bounds.x == 2
    assert candidates[0].bounds.y == 2
    assert candidates[0].confidence >= 0.99
    assert (tmp_path / "overlays" / "find-icon.png").exists()
    assert report["scale_tolerant"] is False


def test_opencv_template_matching_respects_region(tmp_path: Path) -> None:
    engine = OpenCvTemplatePerceptionEngine(OpenCvTemplateMatcher())
    step = TaskStep(
        id="miss-icon",
        action="click_image",
        image=TEMPLATE,
        region=TaskRegion(x=0, y=0, width=3, height=3),
    )

    candidates = engine.detect(
        step,
        ScreenObservation(screenshot_path=SCREENSHOT),
        RuntimeConfig(trace_root=tmp_path, confidence_threshold=0.99),
    )

    assert candidates == ()
