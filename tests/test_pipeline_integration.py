from pathlib import Path

from desktop_agent.actuation import ActuationProfile, DesktopActuator, FakeInputBackend
from desktop_agent.config import RuntimeConfig, StaticConfigLoader
from desktop_agent.perception import (
    CompositePerceptionEngine,
    ConfidenceTargetSelector,
    ElementCandidate,
    PerceptionEngine,
)
from desktop_agent.planner import ExecutionEngine
from desktop_agent.safety import LocalSafetyPolicy
from desktop_agent.screen import Bounds, MonitorInfo, ScreenObservation
from desktop_agent.task_dsl import (
    BasicTaskValidator,
    StaticTaskLoader,
    TaskDefinition,
    TaskStep,
    VerificationDefinition,
)
from desktop_agent.tracing import MemoryTraceSink


class SequenceScreenObserver:
    def __init__(self, observations: tuple[ScreenObservation, ...]) -> None:
        self._observations = observations
        self.calls = 0

    def observe(self, config: RuntimeConfig) -> ScreenObservation:
        _ = config
        index = min(self.calls, len(self._observations) - 1)
        self.calls += 1
        return self._observations[index]


class StepAwarePerceptionEngine(PerceptionEngine):
    def detect(
        self,
        step: TaskStep,
        observation: ScreenObservation,
        config: RuntimeConfig,
    ) -> tuple[ElementCandidate, ...]:
        _ = observation, config
        if step.id.endswith("-verify"):
            return (_candidate("success", "Success"),)
        return (_candidate("submit", "Submit"),)


def test_planner_pipeline_uses_fake_screen_and_fake_input_without_real_mouse() -> None:
    backend = FakeInputBackend(
        start_position=(0, 0),
        active_window_title="DeskPilot Fixture",
    )
    task = TaskDefinition(
        name="fake-pipeline",
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=30,
        steps=(
            TaskStep(
                id="click-submit",
                action="click_text",
                target="Submit",
                verify=VerificationDefinition(type="visible_text", text="Success"),
            ),
        ),
    )
    trace_sink = MemoryTraceSink()
    screen_observer = SequenceScreenObserver(
        (
            _observation("before.png"),
            _observation("after.png"),
        ),
    )
    engine = _engine(
        task,
        screen_observer=screen_observer,
        actuator=DesktopActuator(backend, _instant_profile()),
        trace_sink=trace_sink,
    )

    report = engine.run(Path("task.yaml"))

    assert report.status == "passed"
    assert report.steps[0].candidate_id == "candidate-submit"
    assert screen_observer.calls == 2
    assert [event.kind for event in backend.events[-2:]] == [
        "mouse_down",
        "mouse_up",
    ]
    assert backend.events[-1].point == (150, 250)
    phases = {event.phase for event in report.events}
    assert {"observe_screen", "execute_action", "verify_candidates"} <= phases


def test_invalid_task_failure_is_reported_before_fake_input_is_used() -> None:
    backend = FakeInputBackend(active_window_title="DeskPilot Fixture")
    task = TaskDefinition(
        name="invalid",
        allowed_windows=(),
        timeout_seconds=30,
        steps=(TaskStep(id="click-submit", action="click_text", target="Submit"),),
    )
    engine = _engine(
        task,
        screen_observer=SequenceScreenObserver((_observation("unused.png"),)),
        actuator=DesktopActuator(backend, _instant_profile()),
    )

    report = engine.run(Path("task.yaml"))

    assert report.status == "failed"
    assert report.abort_reason == "allowed_windows is required"
    assert backend.events == []


def test_task_compilation_failure_stops_before_fake_screen_or_input() -> None:
    backend = FakeInputBackend(active_window_title="DeskPilot Fixture")
    screen_observer = SequenceScreenObserver((_observation("unused.png"),))
    task = TaskDefinition(
        name="invalid compiled graph",
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=30,
        steps=(
            TaskStep(
                id="click-submit",
                action="click_text",
                target="Submit",
                depends_on=("missing-step",),
            ),
        ),
    )
    trace_sink = MemoryTraceSink()
    engine = _engine(
        task,
        screen_observer=screen_observer,
        actuator=DesktopActuator(backend, _instant_profile()),
        trace_sink=trace_sink,
    )

    report = engine.run(Path("task.yaml"))

    phases = {event.phase for event in report.events}
    assert report.status == "failed"
    assert report.abort_reason == "step click-submit dependency target does not exist"
    assert "validate_task" in phases
    assert "observe_screen" not in phases
    assert "execute_action" not in phases
    assert screen_observer.calls == 0
    assert backend.events == []


def test_pipeline_records_keyboard_cadence_in_execute_action_monitoring() -> None:
    backend = FakeInputBackend(active_window_title="DeskPilot Fixture")
    task = TaskDefinition(
        name="typing pipeline",
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=30,
        steps=(
            TaskStep(
                id="type-code",
                action="type_text",
                text="abc",
            ),
        ),
    )
    trace_sink = MemoryTraceSink()
    engine = _engine(
        task,
        screen_observer=SequenceScreenObserver((_observation("typing.png"),)),
        actuator=DesktopActuator(
            backend,
            ActuationProfile(
                movement_duration_seconds=(0.0, 0.0),
                timing_variation_seconds=(0.0, 0.0),
                keyboard_interval_seconds=(0.01, 0.01),
                movement_steps=1,
            ),
        ),
        trace_sink=trace_sink,
    )

    report = engine.run(Path("task.yaml"))

    typed_text = "".join(
        event.text or "" for event in backend.events if event.kind == "type_text"
    )
    execute_action = next(
        event for event in report.events if event.phase == "execute_action"
    )
    phases = {event.phase for event in report.events}
    assert report.status == "passed"
    assert typed_text == "abc"
    assert {"detect_candidates", "execute_action"} <= phases
    assert execute_action.metadata["keyboard_cadence_applied"] is True
    assert execute_action.metadata["keyboard_interval_count"] == 2


def _engine(
    task: TaskDefinition,
    *,
    screen_observer: SequenceScreenObserver,
    actuator: DesktopActuator,
    trace_sink: MemoryTraceSink | None = None,
) -> ExecutionEngine:
    return ExecutionEngine(
        config_loader=StaticConfigLoader(RuntimeConfig(confidence_threshold=0.8)),
        task_loader=StaticTaskLoader(task),
        task_validator=BasicTaskValidator(),
        trace_sink=trace_sink or MemoryTraceSink(),
        safety_policy=LocalSafetyPolicy(),
        screen_observer=screen_observer,
        perception_engine=CompositePerceptionEngine((StepAwarePerceptionEngine(),)),
        target_selector=ConfidenceTargetSelector(),
        actuator=actuator,
    )


def _candidate(candidate_id: str, label: str) -> ElementCandidate:
    return ElementCandidate(
        id=f"candidate-{candidate_id}",
        source="uia",
        label=label,
        bounds=Bounds(x=10, y=20, width=30, height=10),
        confidence=0.95,
    )


def _observation(screenshot_name: str) -> ScreenObservation:
    return ScreenObservation(
        screenshot_path=Path("traces") / screenshot_name,
        size=(800, 600),
        active_window_title="DeskPilot Fixture",
        monitor=MonitorInfo(
            left=100,
            top=200,
            width=800,
            height=600,
            scale_x=2.0,
            scale_y=2.0,
            is_primary=True,
        ),
    )


def _instant_profile() -> ActuationProfile:
    return ActuationProfile(
        movement_duration_seconds=(0.0, 0.0),
        timing_variation_seconds=(0.0, 0.0),
        movement_steps=1,
        movement_smoothness=0.0,
        random_seed=1,
    )
