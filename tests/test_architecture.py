from pathlib import Path

from desktop_agent.actuation import ActionResult, DryRunActuator
from desktop_agent.config import ExecutionProfile, RuntimeConfig, StaticConfigLoader
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


class FailingOnceActuator:
    def __init__(self) -> None:
        self.calls = 0

    def execute(
        self,
        step: TaskStep,
        target: ElementCandidate | None,
        observation: ScreenObservation,
        config: RuntimeConfig,
    ) -> ActionResult:
        _ = step, target, observation, config
        self.calls += 1
        if self.calls == 1:
            return ActionResult(success=False, message="transient failure")
        return ActionResult(success=True, message="recovered")


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


class AmbiguousPerceptionEngine(PerceptionEngine):
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
            ElementCandidate(
                id="candidate-2",
                source="uia",
                label="Submit",
                bounds=Bounds(x=220, y=20, width=100, height=30),
                confidence=0.94,
            ),
        )


def test_execution_engine_runs_pipeline_and_reports_success() -> None:
    task = TaskDefinition(
        name="fixture",
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=30,
        steps=(
            TaskStep(
                id="click-submit",
                action="click_text",
                target="Submit",
                category="submission",
            ),
        ),
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
    assert report.steps[0].metadata["step_category"] == "submission"
    assert "detect_candidates" in {event.phase for event in report.events}
    selection = next(event for event in report.events if event.phase == "select_target")
    detection = next(
        event for event in report.events if event.phase == "detect_candidates"
    )
    rankings = detection.metadata["candidate_rankings"]
    assert selection.metadata["step_category"] == "submission"
    assert detection.metadata["step_category"] == "submission"
    assert selection.metadata["candidate_confidence"] == 0.95
    assert isinstance(rankings, list)
    first_ranking = rankings[0]
    assert isinstance(first_ranking, dict)
    assert first_ranking["id"] == "candidate-1"
    assert first_ranking["rank"] == 1


def test_execution_engine_repeated_runs_preserve_deterministic_completion() -> None:
    task = TaskDefinition(
        name="repeatable-fixture",
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=30,
        steps=(TaskStep(id="click-submit", action="click_text", target="Submit"),),
    )

    reports = []
    for _ in range(3):
        engine = ExecutionEngine(
            config_loader=StaticConfigLoader(RuntimeConfig(confidence_threshold=0.8)),
            task_loader=StaticTaskLoader(task),
            task_validator=BasicTaskValidator(),
            trace_sink=MemoryTraceSink(),
            safety_policy=LocalSafetyPolicy(),
            screen_observer=StaticScreenObserver(
                ScreenObservation(active_window_title="DeskPilot Fixture"),
            ),
            perception_engine=CompositePerceptionEngine((FixturePerceptionEngine(),)),
            target_selector=ConfidenceTargetSelector(),
            actuator=DryRunActuator(),
        )
        reports.append(engine.run(Path("task.yaml")))

    assert [report.status for report in reports] == ["passed", "passed", "passed"]
    assert [report.steps[0].candidate_id for report in reports] == [
        "candidate-1",
        "candidate-1",
        "candidate-1",
    ]


def test_execution_engine_fails_when_confidence_gate_blocks_target() -> None:
    task = TaskDefinition(
        name="ambiguous-fixture",
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=30,
        steps=(TaskStep(id="click-submit", action="click_text", target="Submit"),),
    )
    engine = ExecutionEngine(
        config_loader=StaticConfigLoader(RuntimeConfig(confidence_threshold=0.8)),
        task_loader=StaticTaskLoader(task),
        task_validator=BasicTaskValidator(),
        trace_sink=MemoryTraceSink(),
        safety_policy=LocalSafetyPolicy(),
        screen_observer=StaticScreenObserver(
            ScreenObservation(active_window_title="DeskPilot Fixture"),
        ),
        perception_engine=CompositePerceptionEngine((AmbiguousPerceptionEngine(),)),
        target_selector=ConfidenceTargetSelector(),
        actuator=DryRunActuator(),
    )

    report = engine.run(Path("task.yaml"))

    selection = next(event for event in report.events if event.phase == "select_target")
    assert report.status == "failed"
    assert report.steps[0].message == (
        "target selection blocked by confidence or ambiguity gate"
    )
    assert selection.metadata["selection_blocked"] == "confidence_or_ambiguity_gate"


def test_execution_engine_reports_validation_failures() -> None:
    task = TaskDefinition(
        name="invalid",
        allowed_windows=(),
        timeout_seconds=30,
        steps=(TaskStep(id="click-submit", action="click_text", target="Submit"),),
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


def test_execution_engine_rejects_disallowed_active_window_before_action() -> None:
    task = TaskDefinition(
        name="window-fixture",
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=30,
        steps=(TaskStep(id="click-submit", action="click_text", target="Submit"),),
    )
    engine = ExecutionEngine(
        config_loader=StaticConfigLoader(RuntimeConfig(confidence_threshold=0.8)),
        task_loader=StaticTaskLoader(task),
        task_validator=BasicTaskValidator(),
        trace_sink=MemoryTraceSink(),
        safety_policy=LocalSafetyPolicy(),
        screen_observer=StaticScreenObserver(
            ScreenObservation(active_window_title="Unexpected Window"),
        ),
        perception_engine=CompositePerceptionEngine((FixturePerceptionEngine(),)),
        target_selector=ConfidenceTargetSelector(),
        actuator=DryRunActuator(),
    )

    report = engine.run(Path("task.yaml"))

    assert report.status == "failed"
    assert (
        report.steps[0].message == "active window is outside the task allowed_windows"
    )


def test_execution_engine_requires_confirmation_for_sensitive_step() -> None:
    task = TaskDefinition(
        name="confirmation-fixture",
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=30,
        steps=(
            TaskStep(
                id="submit-payment",
                action="click_text",
                target="Submit",
                requires_confirmation=True,
            ),
        ),
    )
    engine = ExecutionEngine(
        config_loader=StaticConfigLoader(RuntimeConfig(confidence_threshold=0.8)),
        task_loader=StaticTaskLoader(task),
        task_validator=BasicTaskValidator(),
        trace_sink=MemoryTraceSink(),
        safety_policy=LocalSafetyPolicy(),
        screen_observer=StaticScreenObserver(
            ScreenObservation(active_window_title="DeskPilot Fixture"),
        ),
        perception_engine=CompositePerceptionEngine((FixturePerceptionEngine(),)),
        target_selector=ConfidenceTargetSelector(),
        actuator=DryRunActuator(),
    )

    report = engine.run(Path("task.yaml"))

    assert report.status == "failed"
    assert report.steps[0].message == (
        "step submit-payment requires explicit confirmation"
    )


def test_execution_engine_runs_confirmed_sensitive_step() -> None:
    task = TaskDefinition(
        name="confirmation-fixture",
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=30,
        steps=(
            TaskStep(
                id="submit-payment",
                action="click_text",
                target="Submit",
                requires_confirmation=True,
            ),
        ),
    )
    engine = ExecutionEngine(
        config_loader=StaticConfigLoader(
            RuntimeConfig(
                confidence_threshold=0.8,
                confirmed_steps=("submit-payment",),
            ),
        ),
        task_loader=StaticTaskLoader(task),
        task_validator=BasicTaskValidator(),
        trace_sink=MemoryTraceSink(),
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


def test_execution_engine_traces_timing_and_recovery_metadata() -> None:
    task = TaskDefinition(
        name="timing-fixture",
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=30,
        steps=(
            TaskStep(
                id="click-submit",
                action="click_text",
                target="Submit",
                retry=1,
            ),
        ),
    )
    trace_sink = MemoryTraceSink()
    engine = ExecutionEngine(
        config_loader=StaticConfigLoader(
            RuntimeConfig(
                confidence_threshold=0.8,
                execution_profile=ExecutionProfile(
                    enabled=True,
                    action_delay_seconds=(0.1, 0.2),
                    retry_delay_seconds=(0.3, 0.4),
                    hesitation_probability=1.0,
                    movement_smoothness=0.5,
                    persona="careful",
                    random_seed=11,
                ),
            )
        ),
        task_loader=StaticTaskLoader(task),
        task_validator=BasicTaskValidator(),
        trace_sink=trace_sink,
        safety_policy=LocalSafetyPolicy(),
        screen_observer=StaticScreenObserver(
            ScreenObservation(
                active_window_title="DeskPilot Fixture",
                size=(800, 600),
            ),
        ),
        perception_engine=CompositePerceptionEngine((FixturePerceptionEngine(),)),
        target_selector=ConfidenceTargetSelector(),
        actuator=FailingOnceActuator(),
    )

    report = engine.run(Path("task.yaml"))

    timing_events = [
        event for event in report.events if event.phase == "execution_timing"
    ]
    recover_event = next(event for event in report.events if event.phase == "recover")
    assert report.status == "passed"
    assert report.steps[0].attempts == 2
    assert len(timing_events) == 3
    action_delay = timing_events[0].metadata["delay_seconds"]
    retry_delay = recover_event.metadata["retry_delay_seconds"]
    assert isinstance(action_delay, float)
    assert isinstance(retry_delay, float)
    assert 0.1 <= action_delay <= 0.2
    assert 0.3 <= retry_delay <= 0.4
    assert timing_events[0].metadata["timing_model"] == "target_aware"
    assert timing_events[0].metadata["execution_persona"] == "careful"
    assert timing_events[0].metadata["persona_timing_bias"] == 0.18
    assert timing_events[0].metadata["random_seed"] == 11
    samples = timing_events[0].metadata["sample_records"]
    assert isinstance(samples, list)
    assert samples
    assert timing_events[0].metadata["action_type"] == "click_text"
    assert timing_events[0].metadata["target_id"] == "candidate-1"
    operator_counts = timing_events[0].metadata["klm_operator_counts"]
    assert isinstance(operator_counts, dict)
    assert operator_counts["mental"] == 1
    assert operator_counts["pointing"] == 1
    assert "distance_pixels" in timing_events[0].metadata
    assert timing_events[0].metadata["target_width_pixels"] == 100
    assert timing_events[1].metadata["timing_model"] == "profile_bounds"
    retry_operator_counts = timing_events[1].metadata["klm_operator_counts"]
    assert isinstance(retry_operator_counts, dict)
    assert retry_operator_counts["system_wait"] == 1
    assert recover_event.metadata["retry_reason"] == "transient failure"
