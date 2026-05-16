import json
from pathlib import Path

from desktop_agent.screen_captioning import (
    screen_caption_review_from_inspection,
    write_screen_caption_review_report,
)


def test_screen_caption_review_report_is_review_only(tmp_path: Path) -> None:
    inspection = {
        "screenshot_path": str(tmp_path / "screen.png"),
        "size": [640, 480],
        "warnings": [],
        "ocr": {"blocks": [{"text": "Submit"}]},
        "uia": {"tree": {"active_window": {"title": "DeskPilot Fixture"}}},
        "candidates": [{"label": "Submit"}, {"label": "Cancel"}],
    }

    report = screen_caption_review_from_inspection(
        inspection,
        inspection_report_path=tmp_path / "inspect-screen.json",
    )
    metadata = report.metadata()

    assert metadata["status"] == "prompt_ready"
    assert metadata["review_only"] is True
    assert metadata["authoring_only"] is True
    assert metadata["direct_action_allowed"] is False
    assert metadata["screen_summary"] == {
        "screenshot_path": str(tmp_path / "screen.png"),
        "size": (640, 480),
        "warnings": (),
        "active_window_title": "DeskPilot Fixture",
        "ocr_text": ("Submit",),
        "candidate_labels": ("Submit", "Cancel"),
    }
    prompt = metadata["prompt"]
    assert isinstance(prompt, dict)
    assert prompt["prompt_class"] == "screen_summary"
    assert prompt["input_artifact_references"] == [
        str(tmp_path / "inspect-screen.json"),
        str(tmp_path / "screen.png"),
    ]


def test_screen_caption_review_report_writes_json(tmp_path: Path) -> None:
    report = screen_caption_review_from_inspection(
        {"screenshot_path": None, "candidates": []},
    )
    output_path = tmp_path / "caption-review.json"

    write_screen_caption_review_report(report, output_path)

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["status"] == "prompt_ready"
    assert payload["direct_action_allowed"] is False
