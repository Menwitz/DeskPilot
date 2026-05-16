import json
from pathlib import Path

from desktop_agent.config import RuntimeConfig
from desktop_agent.ocr import (
    OcrPerceptionEngine,
    OcrProvider,
    OcrTextBlock,
    match_ocr_text,
)
from desktop_agent.redaction import RedactionPolicy
from desktop_agent.screen import Bounds, ScreenObservation
from desktop_agent.task_dsl import TaskStep

FIXTURE_SCREENSHOT = Path("tests/fixtures/ocr-basic.ppm")


class FixtureOcrProvider(OcrProvider):
    def extract_text(self, screenshot_path: Path) -> tuple[OcrTextBlock, ...]:
        assert screenshot_path == FIXTURE_SCREENSHOT
        return (
            OcrTextBlock(
                text="Submit",
                bounds=Bounds(x=10, y=20, width=80, height=24),
                confidence=0.96,
            ),
            OcrTextBlock(
                text="Cancel",
                bounds=Bounds(x=100, y=20, width=80, height=24),
                confidence=0.42,
            ),
        )


def test_ocr_engine_normalizes_text_candidates_and_saves_output(
    tmp_path: Path,
) -> None:
    engine = OcrPerceptionEngine(FixtureOcrProvider())
    step = TaskStep(id="submit", action="click_text", target="submit")

    candidates = engine.detect(
        step,
        ScreenObservation(screenshot_path=FIXTURE_SCREENSHOT),
        RuntimeConfig(trace_root=tmp_path, confidence_threshold=0.8),
    )

    output = json.loads((tmp_path / "ocr" / "submit.json").read_text())
    assert len(candidates) == 1
    assert candidates[0].source == "ocr"
    assert candidates[0].label == "Submit"
    assert candidates[0].confidence == 0.96
    assert output["blocks"][0]["text"] == "Submit"
    assert output["candidates"][0]["id"] == "ocr-submit-0"


def test_ocr_engine_masks_saved_text_when_configured(tmp_path: Path) -> None:
    engine = OcrPerceptionEngine(FixtureOcrProvider())
    step = TaskStep(id="submit", action="click_text", target="submit")

    engine.detect(
        step,
        ScreenObservation(screenshot_path=FIXTURE_SCREENSHOT),
        RuntimeConfig(
            trace_root=tmp_path,
            confidence_threshold=0.8,
            redaction_policy=RedactionPolicy(ocr_text="mask"),
        ),
    )

    output = json.loads((tmp_path / "ocr" / "submit.json").read_text())
    assert output["ocr_text_redaction"] == "mask"
    assert output["blocks"][0]["text"] == "******"
    assert output["blocks"][0]["text_length"] == 6
    assert output["candidates"][0]["label"] == "******"


def test_ocr_engine_suppresses_saved_text_when_configured(tmp_path: Path) -> None:
    engine = OcrPerceptionEngine(FixtureOcrProvider())
    step = TaskStep(id="submit", action="click_text", target="submit")

    candidates = engine.detect(
        step,
        ScreenObservation(screenshot_path=FIXTURE_SCREENSHOT),
        RuntimeConfig(
            trace_root=tmp_path,
            confidence_threshold=0.8,
            redaction_policy=RedactionPolicy(ocr_text="suppress"),
        ),
    )

    assert len(candidates) == 1
    assert not (tmp_path / "ocr").exists()


def test_ocr_engine_filters_below_confidence_threshold(tmp_path: Path) -> None:
    engine = OcrPerceptionEngine(FixtureOcrProvider())
    step = TaskStep(id="cancel", action="click_text", target="Cancel")

    candidates = engine.detect(
        step,
        ScreenObservation(screenshot_path=FIXTURE_SCREENSHOT),
        RuntimeConfig(trace_root=tmp_path, confidence_threshold=0.8),
    )

    assert candidates == ()


def test_ocr_engine_returns_empty_without_screenshot(tmp_path: Path) -> None:
    engine = OcrPerceptionEngine(FixtureOcrProvider())

    candidates = engine.detect(
        TaskStep(id="submit", action="click_text", target="Submit"),
        ScreenObservation(),
        RuntimeConfig(trace_root=tmp_path),
    )

    assert candidates == ()


def test_ocr_text_matching_supports_case_exact_contains_and_fuzzy() -> None:
    assert match_ocr_text("submit", "Submit", "exact") == 1.0
    assert match_ocr_text("mit", "Submit", "contains") == 1.0
    assert match_ocr_text("Submit", "Subnit", "fuzzy") > 0.8
