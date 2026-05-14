from pathlib import Path

from desktop_agent.actuation import DryRunActuator
from desktop_agent.config import RuntimeConfig, StaticConfigLoader
from desktop_agent.perception import (
    CompositePerceptionEngine,
    ConfidenceTargetSelector,
    ElementCandidate,
    PerceptionEngine,
)
from desktop_agent.planner import ExecutionEngine
from desktop_agent.safety import LocalSafetyPolicy
from desktop_agent.screen import Bounds, ScreenObservation, StaticScreenObserver
from desktop_agent.task_dsl import (
    BasicTaskValidator,
    StaticTaskLoader,
    TaskDefinition,
    TaskStep,
)
from desktop_agent.tracing import MemoryTraceSink


class FixturePerceptionEngine(PerceptionEngine):
    def detect(
        self,
        step: TaskStep,
        observation: ScreenObservation,
        config: RuntimeConfig,
    ) -> tuple[ElementCandidate, ...]:
        _ = step, observation, config
        return (
            ElementCandidate(
                id="candidate-1",
                source="uia",
                label="Submit",
                bounds=Bounds(x=10, y=20, width=100, height=30),
                confidence=0.95,
            ),
        )


def test_execution_engine_runs_pipeline_and_reports_success() -> None:
    task = TaskDefinition(
        name="fixture",
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=30,
        steps=(TaskStep(id="click-submit", action="click_text", target="Submit"),),
    )
    trace_sink = MemoryTraceSink()
    engine = ExecutionEngine(
        config_loader=StaticConfigLoader(RuntimeConfig(confidence_threshold=0.8)),
        task_loader=StaticTaskLoader(task),
        task_validator=BasicTaskValidator(),
        trace_sink=trace_sink,
        safety_policy=LocalSafetyPolicy(),
        screen_observer=StaticScreenObserver(
            ScreenObservation(active_window_title="DeskPilot Fixture"),
        ),
        perception_engine=CompositePerceptionEngine((FixturePerceptionEngine(),)),
        target_selector=ConfidenceTargetSelector(),
        actuator=DryRunActuator(),
    )

    report = engine.run(Path("task.yaml"))

    assert report.status == "passed"
    assert report.task_name == "fixture"
    assert [step.step_id for step in report.steps] == ["click-submit"]
    assert report.steps[0].candidate_id == "candidate-1"
    assert "detect_candidates" in {event.phase for event in report.events}


def test_execution_engine_reports_validation_failures() -> None:
    task = TaskDefinition(
        name="invalid",
        allowed_windows=(),
        timeout_seconds=30,
        steps=(TaskStep(id="click-submit", action="click_text"),),
    )
    engine = ExecutionEngine(
        config_loader=StaticConfigLoader(),
        task_loader=StaticTaskLoader(task),
        task_validator=BasicTaskValidator(),
        trace_sink=MemoryTraceSink(),
        safety_policy=LocalSafetyPolicy(),
        screen_observer=StaticScreenObserver(),
        perception_engine=CompositePerceptionEngine((FixturePerceptionEngine(),)),
        target_selector=ConfidenceTargetSelector(),
        actuator=DryRunActuator(),
    )

    report = engine.run(Path("task.yaml"))

    assert report.status == "failed"
    assert report.abort_reason == "allowed_windows is required"
