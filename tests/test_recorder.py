import json
from pathlib import Path

from pytest import CaptureFixture, MonkeyPatch

from desktop_agent.actuation import DryRunActuator
from desktop_agent.cli import main
from desktop_agent.config import RuntimeConfig, StaticConfigLoader
from desktop_agent.ocr import OcrTextBlock
from desktop_agent.perception import (
    CompositePerceptionEngine,
    ConfidenceTargetSelector,
    ElementCandidate,
    PerceptionEngine,
)
from desktop_agent.planner import ExecutionEngine
from desktop_agent.platforms.windows.uia import UiaElementSnapshot
from desktop_agent.recorder import (
    RecorderCandidateContext,
    RecorderController,
    RecorderEvent,
    RecorderReviewMetadata,
    RecorderSession,
    capture_image_snippet_for_point,
    capture_ocr_context_for_point,
    capture_uia_context_for_point,
    generate_task_from_recorder_session,
)
from desktop_agent.safety import LocalSafetyPolicy
from desktop_agent.screen import Bounds, ScreenObservation, StaticScreenObserver
from desktop_agent.task_dsl import (
    BasicTaskValidator,
    StaticTaskLoader,
    TaskStep,
    YamlTaskLoader,
)
from desktop_agent.tracing import FileTraceSink


class FakeUiaPointAdapter:
    def __init__(self, snapshot: UiaElementSnapshot) -> None:
        self.snapshot = snapshot
        self.point: tuple[int, int] | None = None

    def element_at_point(self, point: tuple[int, int]) -> UiaElementSnapshot:
        self.point = point
        return self.snapshot


class RecorderStreamPerceptionEngine(PerceptionEngine):
    def detect(
        self,
        step: TaskStep,
        observation: ScreenObservation,
        config: RuntimeConfig,
    ) -> tuple[ElementCandidate, ...]:
        _ = observation, config
        label = step.target or step.text or "recorded target"
        return (
            ElementCandidate(
                id=f"recorded-{label.lower().replace(' ', '-')}",
                source="uia",
                label=label,
                bounds=Bounds(x=20, y=40, width=120, height=24),
                confidence=0.96,
            ),
        )


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


def test_recorder_review_metadata_flows_to_generated_task(tmp_path: Path) -> None:
    state_path = tmp_path / "recording.json"
    controller = RecorderController(state_path)
    review = RecorderReviewMetadata(
        routine_name="Daily inbox triage",
        description="Review unread support messages",
        inputs=("support inbox",),
        outputs=("triaged messages", "draft replies"),
        tags=("email", "support"),
        risk_class="medium",
        expected_duration_seconds=420.0,
    )
    controller.start(name="Morning inbox", review=review)
    controller.record_event(
        RecorderEvent.create(
            "selected_point",
            active_window="DeskPilot Fixture",
            candidate_context=(
                RecorderCandidateContext(
                    source="ocr",
                    label="Inbox",
                    bounds={"x": 20, "y": 40, "width": 120, "height": 24},
                ),
            ),
        ),
    )
    session = controller.stop()

    task = generate_task_from_recorder_session(session)
    payload = json.loads(state_path.read_text(encoding="utf-8"))

    BasicTaskValidator().validate(task, RuntimeConfig())
    assert payload["review"]["routine_name"] == "Daily inbox triage"
    assert payload["review"]["outputs"] == ["triaged messages", "draft replies"]
    assert task.name == "Daily inbox triage"
    assert task.metadata["routine_description"] == "Review unread support messages"
    assert task.metadata["routine_inputs"] == ["support inbox"]
    assert task.metadata["routine_outputs"] == ["triaged messages", "draft replies"]
    assert task.metadata["routine_tags"] == ["email", "support"]
    assert task.metadata["routine_risk_class"] == "medium"
    assert task.metadata["routine_expected_duration_seconds"] == 420.0


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


def test_recorder_infers_verification_from_post_action_state_delta() -> None:
    session = _session_with_events(
        (
            RecorderEvent.create(
                "selected_point",
                active_window="DeskPilot Fixture",
                candidate_context=(
                    RecorderCandidateContext(
                        source="ocr",
                        label="Submit",
                        bounds={"x": 20, "y": 40, "width": 120, "height": 24},
                    ),
                ),
            ),
            RecorderEvent.create(
                "observation",
                active_window="DeskPilot Fixture",
                metadata={
                    "state_delta": {
                        "visible_text_added": ["Success"],
                        "target_appeared": True,
                    },
                },
            ),
        ),
    )

    task = generate_task_from_recorder_session(session)

    BasicTaskValidator().validate(task, RuntimeConfig())
    assert len(task.steps) == 1
    assert task.steps[0].action == "click_text"
    assert task.steps[0].verify is not None
    assert task.steps[0].verify.type == "visible_text"
    assert task.steps[0].verify.text == "Success"


def test_fake_recorder_event_streams_generate_valid_tasks() -> None:
    cases = (
        (_fake_browser_event_stream(), ["click_text", "type_text", "press_key"]),
        (_fake_native_event_stream(), ["click_uia", "scroll", "click_image"]),
    )

    for events, expected_actions in cases:
        task = generate_task_from_recorder_session(
            _session_with_events(
                events,
                review=RecorderReviewMetadata(
                    routine_name="Generated fake stream routine",
                    risk_class="low",
                ),
            ),
        )

        BasicTaskValidator().validate(task, RuntimeConfig())
        assert [step.action for step in task.steps] == expected_actions
        assert task.metadata["routine_risk_class"] == "low"


def test_fake_recorder_event_stream_report_includes_review_metadata(
    tmp_path: Path,
) -> None:
    task = generate_task_from_recorder_session(
        _session_with_events(
            _fake_browser_event_stream(),
            review=RecorderReviewMetadata(
                routine_name="Browser search routine",
                description="Search the browser fixture and confirm results",
                inputs=("search query",),
                outputs=("results page",),
                tags=("browser", "search"),
                risk_class="low",
                expected_duration_seconds=30.0,
            ),
        ),
    )
    trace_sink = FileTraceSink()
    engine = ExecutionEngine(
        config_loader=StaticConfigLoader(
            RuntimeConfig(
                trace_root=tmp_path / "traces",
                confidence_threshold=0.8,
            ),
        ),
        task_loader=StaticTaskLoader(task),
        task_validator=BasicTaskValidator(),
        trace_sink=trace_sink,
        safety_policy=LocalSafetyPolicy(),
        screen_observer=StaticScreenObserver(
            ScreenObservation(
                size=(800, 600),
                active_window_title="Browser Fixture",
            ),
        ),
        perception_engine=CompositePerceptionEngine(
            (RecorderStreamPerceptionEngine(),),
        ),
        target_selector=ConfidenceTargetSelector(),
        actuator=DryRunActuator(),
    )

    report = engine.run(Path("recorded-browser.yaml"))

    assert report.status == "passed"
    assert report.trace_dir is not None
    final_report = json.loads((report.trace_dir / "final-report.json").read_text())
    task_payload = json.loads((report.trace_dir / "task.json").read_text())
    assert final_report["metadata"]["routine_name"] == "Browser search routine"
    assert final_report["metadata"]["routine_tags"] == ["browser", "search"]
    assert task_payload["metadata"]["routine_outputs"] == ["results page"]
    assert task_payload["steps"][2]["verify"] == {
        "type": "visible_text",
        "text": "Results ready",
        "image": None,
    }


def test_cli_record_export_task_writes_valid_browser_fixture_yaml(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    state_path = tmp_path / "recorder-state.json"
    output_path = tmp_path / "browser-routine.yaml"
    controller = RecorderController(state_path)
    controller.start(
        name="Browser fixture",
        review=RecorderReviewMetadata(
            routine_name="Browser search routine",
            description="Search the browser fixture and confirm results",
            inputs=("search query",),
            outputs=("results page",),
            tags=("browser", "search"),
            risk_class="low",
            expected_duration_seconds=30.0,
        ),
    )
    for event in _fake_browser_event_stream():
        controller.record_event(event)
    controller.stop()

    status = main(
        [
            "record",
            "export-task",
            "--state",
            str(state_path),
            "--output",
            str(output_path),
        ],
    )

    output = capsys.readouterr().out
    task = YamlTaskLoader().load(output_path)
    BasicTaskValidator().validate(task, RuntimeConfig())
    assert status == 0
    assert "recording task exported:" in output
    assert task.name == "Browser search routine"
    assert task.allowed_windows == ("Browser Fixture",)
    assert [step.action for step in task.steps] == [
        "click_text",
        "type_text",
        "press_key",
    ]
    assert task.steps[2].verify is not None
    assert task.steps[2].verify.text == "Results ready"
    assert task.metadata["routine_tags"] == ["browser", "search"]


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
            "--confirm-save",
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


def test_cli_record_review_updates_metadata(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    state_path = tmp_path / "recorder-state.json"
    assert main(
        [
            "record",
            "start",
            "--state",
            str(state_path),
            "--name",
            "Morning inbox",
        ],
    ) == 0

    assert main(
        [
            "record",
            "review",
            "--state",
            str(state_path),
            "--routine-name",
            "Daily inbox triage",
            "--description",
            "Review unread support messages",
            "--input",
            "support inbox",
            "--output",
            "triaged messages",
            "--tag",
            "email",
            "--risk-class",
            "medium",
            "--expected-duration-seconds",
            "420",
        ],
    ) == 0

    output = capsys.readouterr().out
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert "recording review updated:" in output
    assert "routine: Daily inbox triage" in output
    assert payload["review"] == {
        "routine_name": "Daily inbox triage",
        "description": "Review unread support messages",
        "inputs": ["support inbox"],
        "outputs": ["triaged messages"],
        "tags": ["email"],
        "risk_class": "medium",
        "expected_duration_seconds": 420.0,
    }


def test_cli_record_save_requires_operator_confirmation(
    tmp_path: Path,
    capsys: CaptureFixture[str],
    monkeypatch: MonkeyPatch,
) -> None:
    state_path = tmp_path / "recorder-state.json"
    output_path = tmp_path / "recording.json"
    assert main(["record", "start", "--state", str(state_path)]) == 0
    monkeypatch.setattr("builtins.input", lambda _prompt: "no")

    status = main(
        [
            "record",
            "save",
            "--state",
            str(state_path),
            "--output",
            str(output_path),
        ],
    )

    output = capsys.readouterr().out
    assert status == 1
    assert "recording save not confirmed" in output
    assert not output_path.exists()


def _fake_browser_event_stream() -> tuple[RecorderEvent, ...]:
    return (
        RecorderEvent.create(
            "selected_point",
            active_window="Browser Fixture",
            candidate_context=(
                RecorderCandidateContext(
                    source="ocr",
                    label="Search",
                    bounds={"x": 20, "y": 40, "width": 120, "height": 24},
                ),
            ),
        ),
        RecorderEvent.create(
            "input_event",
            active_window="Browser Fixture",
            input_event={"kind": "type_text", "text": "DeskPilot"},
        ),
        RecorderEvent.create(
            "input_event",
            active_window="Browser Fixture",
            input_event={"kind": "press_key", "key": "enter"},
        ),
        RecorderEvent.create(
            "observation",
            active_window="Browser Fixture",
            metadata={
                "state_delta": {
                    "visible_text_added": ["Results ready"],
                    "target_appeared": True,
                },
            },
        ),
    )


def _fake_native_event_stream() -> tuple[RecorderEvent, ...]:
    return (
        RecorderEvent.create(
            "selected_point",
            active_window="Native Fixture",
            candidate_context=(
                RecorderCandidateContext(
                    source="uia",
                    label="Open",
                    control_type="Button",
                    bounds={"x": 10, "y": 10, "width": 80, "height": 24},
                ),
            ),
        ),
        RecorderEvent.create(
            "input_event",
            active_window="Native Fixture",
            input_event={"kind": "scroll", "clicks": -3},
        ),
        RecorderEvent.create(
            "selected_point",
            active_window="Native Fixture",
            candidate_context=(
                RecorderCandidateContext(
                    source="image",
                    label="native-action.pgm",
                    bounds={"x": 40, "y": 80, "width": 32, "height": 32},
                    metadata={"snippet_path": "snippets/native-action.pgm"},
                ),
            ),
        ),
    )


def _session_with_events(
    events: tuple[RecorderEvent, ...],
    *,
    review: RecorderReviewMetadata | None = None,
) -> RecorderSession:
    return RecorderSession(
        session_id="session-1",
        name="Generated routine",
        status="stopped",
        created_at="2026-05-16T00:00:00+00:00",
        updated_at="2026-05-16T00:00:00+00:00",
        review=review or RecorderReviewMetadata(routine_name="Generated routine"),
        events=events,
    )
