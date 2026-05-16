import json
from pathlib import Path

from pytest import CaptureFixture

from desktop_agent.cli import main
from desktop_agent.config import RuntimeConfig
from desktop_agent.ocr import OcrTextBlock
from desktop_agent.platforms.windows.uia import UiaElementSnapshot
from desktop_agent.recorder import (
    RecorderCandidateContext,
    RecorderController,
    RecorderEvent,
    RecorderSession,
    capture_image_snippet_for_point,
    capture_ocr_context_for_point,
    capture_uia_context_for_point,
    generate_task_from_recorder_session,
)
from desktop_agent.screen import Bounds
from desktop_agent.task_dsl import BasicTaskValidator


class FakeUiaPointAdapter:
    def __init__(self, snapshot: UiaElementSnapshot) -> None:
        self.snapshot = snapshot
        self.point: tuple[int, int] | None = None

    def element_at_point(self, point: tuple[int, int]) -> UiaElementSnapshot:
        self.point = point
        return self.snapshot


def test_recorder_controller_runs_control_state_machine(tmp_path: Path) -> None:
    state_path = tmp_path / "recording.json"
    output_path = tmp_path / "saved-recording.json"
    controller = RecorderController(state_path)

    started = controller.start(name="Morning inbox")
    paused = controller.pause()
    stopped = controller.stop()
    saved = controller.save(output_path)
    discarded = controller.discard()

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert started.status == "recording"
    assert paused.status == "paused"
    assert stopped.status == "stopped"
    assert saved.status == "saved"
    assert discarded.session_id == started.session_id
    assert payload["format"] == "deskpilot_recorder_session_v1"
    assert payload["name"] == "Morning inbox"
    assert payload["status"] == "saved"
    assert payload["event_count"] == 0
    assert not state_path.exists()


def test_recorder_event_model_round_trips_desktop_context(tmp_path: Path) -> None:
    state_path = tmp_path / "recording.json"
    controller = RecorderController(state_path)
    controller.start(name="Click submit")
    event = RecorderEvent.create(
        "selected_point",
        active_window="DeskPilot Fixture",
        screenshot_path="screenshots/before.png",
        selected_point=(120, 240),
        input_event={"kind": "mouse_down", "button": "left"},
        candidate_context=(
            RecorderCandidateContext(
                source="uia",
                label="Submit",
                control_type="Button",
                bounds={"x": 100, "y": 220, "width": 80, "height": 30},
                confidence=0.98,
            ),
        ),
        metadata={"note": "operator clicked primary button"},
    )

    updated = controller.record_event(event)
    loaded = controller.load()
    payload = json.loads(state_path.read_text(encoding="utf-8"))

    assert updated.events == (event,)
    assert loaded.events == (event,)
    assert payload["event_count"] == 1
    assert payload["events"][0]["event_type"] == "selected_point"
    assert payload["events"][0]["active_window"] == "DeskPilot Fixture"
    assert payload["events"][0]["selected_point"] == [120, 240]
    assert payload["events"][0]["candidate_context"][0]["control_type"] == "Button"
    assert payload["events"][0]["input_event"]["kind"] == "mouse_down"


def test_recorder_captures_uia_context_around_clicked_point() -> None:
    adapter = FakeUiaPointAdapter(
        UiaElementSnapshot(
            name="Submit",
            control_type="Button",
            bounds=Bounds(x=100, y=220, width=80, height=30),
            enabled=True,
            visible=True,
        ),
    )

    context = capture_uia_context_for_point((120, 240), adapter)

    assert adapter.point == (120, 240)
    assert context == (
        RecorderCandidateContext(
            source="uia",
            label="Submit",
            control_type="Button",
            bounds={"x": 100, "y": 220, "width": 80, "height": 30},
            confidence=0.95,
            metadata={"enabled": True, "visible": True},
        ),
    )


def test_recorder_captures_ocr_text_blocks_around_clicked_point() -> None:
    blocks = (
        OcrTextBlock(
            text="Submit",
            bounds=Bounds(x=100, y=220, width=80, height=30),
            confidence=0.92,
        ),
        OcrTextBlock(
            text="Cancel",
            bounds=Bounds(x=240, y=220, width=80, height=30),
            confidence=0.88,
        ),
        OcrTextBlock(
            text="Footer",
            bounds=Bounds(x=500, y=700, width=120, height=30),
            confidence=0.99,
        ),
    )

    context = capture_ocr_context_for_point((120, 240), blocks)

    assert context == (
        RecorderCandidateContext(
            source="ocr",
            label="Submit",
            bounds={"x": 100, "y": 220, "width": 80, "height": 30},
            confidence=0.92,
            metadata={"contains_point": True, "distance_pixels": 20.616},
        ),
    )


def test_recorder_captures_image_snippet_only_without_stable_text_context(
    tmp_path: Path,
) -> None:
    screenshot_path = Path("tests/fixtures/cv-screen.pgm")
    output_path = tmp_path / "snippet.pgm"
    stable_context = (
        RecorderCandidateContext(
            source="ocr",
            label="Submit",
            bounds={"x": 100, "y": 220, "width": 80, "height": 30},
        ),
    )

    skipped = capture_image_snippet_for_point(
        (20, 20),
        screenshot_path,
        tmp_path / "stable-skipped.pgm",
        stable_context,
    )
    captured = capture_image_snippet_for_point(
        (20, 20),
        screenshot_path,
        output_path,
        (),
        size=(12, 12),
    )

    assert skipped is None
    assert not (tmp_path / "stable-skipped.pgm").exists()
    assert output_path.exists()
    assert captured == RecorderCandidateContext(
        source="image",
        label="snippet.pgm",
        bounds={"x": 0, "y": 0, "width": 6, "height": 6},
        confidence=0.5,
        metadata={
            "snippet_path": str(output_path),
            "source_screenshot_path": str(screenshot_path),
            "fallback_reason": "no_stable_uia_or_ocr_target",
        },
    )


def test_recorder_generates_supported_task_steps_from_events() -> None:
    session = _session_with_events(
        (
            RecorderEvent.create(
                "selected_point",
                active_window="DeskPilot Fixture",
                candidate_context=(
                    RecorderCandidateContext(
                        source="uia",
                        label="Submit",
                        control_type="Button",
                        bounds={"x": 10, "y": 10, "width": 80, "height": 24},
                    ),
                ),
            ),
            RecorderEvent.create(
                "selected_point",
                active_window="DeskPilot Fixture",
                candidate_context=(
                    RecorderCandidateContext(
                        source="ocr",
                        label="Search",
                        bounds={"x": 20, "y": 40, "width": 120, "height": 24},
                    ),
                ),
            ),
            RecorderEvent.create(
                "selected_point",
                active_window="DeskPilot Fixture",
                candidate_context=(
                    RecorderCandidateContext(
                        source="image",
                        label="snippet.pgm",
                        bounds={"x": 40, "y": 80, "width": 32, "height": 32},
                        metadata={"snippet_path": "snippets/button.pgm"},
                    ),
                ),
            ),
            RecorderEvent.create(
                "input_event",
                input_event={"kind": "type_text", "text": "hello"},
            ),
            RecorderEvent.create(
                "input_event",
                input_event={"kind": "press_key", "key": "ctrl+s"},
            ),
            RecorderEvent.create(
                "input_event",
                input_event={"kind": "scroll", "clicks": -2},
            ),
            RecorderEvent.create(
                "input_event",
                input_event={"kind": "wait_for", "target": "Ready"},
            ),
            RecorderEvent.create(
                "observation",
                metadata={"suggested_action": "assert_visible", "target": "Done"},
            ),
        ),
    )

    task = generate_task_from_recorder_session(session)

    BasicTaskValidator().validate(task, RuntimeConfig())
    assert task.allowed_windows == ("DeskPilot Fixture",)
    assert [step.action for step in task.steps] == [
        "click_uia",
        "click_text",
        "click_image",
        "type_text",
        "press_key",
        "scroll",
        "wait_for",
        "assert_visible",
    ]
    assert task.steps[0].target == "Submit"
    assert task.steps[2].image == Path("snippets/button.pgm")
    assert task.steps[3].text == "hello"
    assert task.steps[5].text == "-2"
    assert task.steps[7].target == "Done"


def test_cli_record_exposes_start_pause_stop_save_discard_controls(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    state_path = tmp_path / "recorder-state.json"
    output_path = tmp_path / "recording.json"

    assert main(
        [
            "record",
            "start",
            "--state",
            str(state_path),
            "--name",
            "Browser fixture",
        ],
    ) == 0
    assert main(["record", "pause", "--state", str(state_path)]) == 0
    assert main(["record", "stop", "--state", str(state_path)]) == 0
    assert main(
        [
            "record",
            "save",
            "--state",
            str(state_path),
            "--output",
            str(output_path),
        ],
    ) == 0
    assert main(["record", "discard", "--state", str(state_path)]) == 0

    output = capsys.readouterr().out
    saved_payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert "recording started:" in output
    assert "recording paused:" in output
    assert "recording stopped:" in output
    assert "recording saved:" in output
    assert "recording discarded:" in output
    assert saved_payload["name"] == "Browser fixture"
    assert saved_payload["status"] == "saved"
    assert not state_path.exists()


def _session_with_events(events: tuple[RecorderEvent, ...]) -> RecorderSession:
    return RecorderSession(
        session_id="session-1",
        name="Generated routine",
        status="stopped",
        created_at="2026-05-16T00:00:00+00:00",
        updated_at="2026-05-16T00:00:00+00:00",
        events=events,
    )
