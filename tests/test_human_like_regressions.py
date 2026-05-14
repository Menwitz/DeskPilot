from pathlib import Path
from typing import cast

from desktop_agent.actuation import ActionResult
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
from desktop_agent.timing import ExecutionTimingController
from desktop_agent.tracing import MemoryTraceSink, RunReport


class CountingActuator:
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
        return ActionResult(success=True, message="executed")


class SingleCandidatePerceptionEngine(PerceptionEngine):
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


class AmbiguousCandidatePerceptionEngine(PerceptionEngine):
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


def test_regression_safety_stop_happens_before_timing_and_actuation() -> None:
    actuator = CountingActuator()
    report = run_fixture(
        actuator=actuator,
        observation=ScreenObservation(active_window_title="Unexpected Window"),
        perception_engine=SingleCandidatePerceptionEngine(),
        config=RuntimeConfig(
            confidence_threshold=0.8,
            execution_profile=enabled_profile(),
        ),
    )

    assert report.status == "failed"
    assert (
        report.steps[0].message == "active window is outside the task allowed_windows"
    )
    assert actuator.calls == 0
    assert "execution_timing" not in event_phases(report)
    assert "execute_action" not in event_phases(report)


def test_regression_ambiguity_gate_happens_before_timing_and_actuation() -> None:
    actuator = CountingActuator()
    report = run_fixture(
        actuator=actuator,
        observation=ScreenObservation(active_window_title="DeskPilot Fixture"),
        perception_engine=AmbiguousCandidatePerceptionEngine(),
        config=RuntimeConfig(
            confidence_threshold=0.8,
            execution_profile=enabled_profile(),
        ),
    )

    selection = next(event for event in report.events if event.phase == "select_target")
    assert report.status == "failed"
    assert report.steps[0].message == (
        "target selection blocked by confidence or ambiguity gate"
    )
    assert selection.metadata["selection_blocked"] == "confidence_or_ambiguity_gate"
    assert actuator.calls == 0
    assert "execution_timing" not in event_phases(report)
    assert "execute_action" not in event_phases(report)


def test_regression_unconfirmed_step_happens_before_timing_and_actuation() -> None:
    actuator = CountingActuator()
    task = fixture_task(
        TaskStep(
            id="submit-payment",
            action="click_text",
            target="Submit",
            requires_confirmation=True,
        ),
    )
    report = run_fixture(
        task=task,
        actuator=actuator,
        observation=ScreenObservation(active_window_title="DeskPilot Fixture"),
        perception_engine=SingleCandidatePerceptionEngine(),
        config=RuntimeConfig(
            confidence_threshold=0.8,
            execution_profile=enabled_profile(),
        ),
    )

    assert report.status == "failed"
    assert report.steps[0].message == (
        "step submit-payment requires explicit confirmation"
    )
    assert actuator.calls == 0
    assert "execution_timing" not in event_phases(report)
    assert "execute_action" not in event_phases(report)


def test_regression_seeded_timing_decisions_are_reproducible() -> None:
    profile = ExecutionProfile(
        enabled=True,
        action_delay_seconds=(0.1, 0.4),
        retry_delay_seconds=(0.5, 1.0),
        hesitation_probability=0.5,
        movement_smoothness=0.6,
        random_seed=42,
    )

    assert timing_sequence(profile) == timing_sequence(profile)


def test_regression_seeded_runs_reproduce_trace_random_samples() -> None:
    first_actuator = CountingActuator()
    second_actuator = CountingActuator()
    config = RuntimeConfig(
        confidence_threshold=0.8,
        execution_profile=enabled_profile(),
    )

    first = run_fixture(
        actuator=first_actuator,
        observation=ScreenObservation(active_window_title="DeskPilot Fixture"),
        perception_engine=SingleCandidatePerceptionEngine(),
        config=config,
    )
    second = run_fixture(
        actuator=second_actuator,
        observation=ScreenObservation(active_window_title="DeskPilot Fixture"),
        perception_engine=SingleCandidatePerceptionEngine(),
        config=config,
    )

    assert first.status == second.status == "passed"
    assert first.steps[0].candidate_id == second.steps[0].candidate_id
    assert first_actuator.calls == second_actuator.calls == 1
    assert timing_delay(first) == timing_delay(second)
    assert timing_sample_records(first) == timing_sample_records(second)


def test_regression_unseeded_runs_remain_inside_timing_and_safety_bounds() -> None:
    reports: list[RunReport] = []
    actuators: list[CountingActuator] = []
    for _ in range(5):
        actuator = CountingActuator()
        actuators.append(actuator)
        reports.append(
            run_fixture(
                actuator=actuator,
                observation=ScreenObservation(active_window_title="DeskPilot Fixture"),
                perception_engine=SingleCandidatePerceptionEngine(),
                config=RuntimeConfig(
                    confidence_threshold=0.8,
                    execution_profile=ExecutionProfile(
                        enabled=True,
                        action_delay_seconds=(0.1, 0.2),
                        retry_delay_seconds=(0.3, 0.4),
                        hesitation_probability=0.5,
                    ),
                ),
            ),
        )

    assert all(report.status == "passed" for report in reports)
    assert all(report.steps[0].candidate_id == "candidate-1" for report in reports)
    assert all(actuator.calls == 1 for actuator in actuators)
    assert all(0.1 <= timing_delay(report) <= 0.2 for report in reports)
    assert all("execute_action" in event_phases(report) for report in reports)


def test_regression_klm_metadata_is_trace_only_after_safety_gates() -> None:
    actuator = CountingActuator()
    report = run_fixture(
        actuator=actuator,
        observation=ScreenObservation(active_window_title="DeskPilot Fixture"),
        perception_engine=SingleCandidatePerceptionEngine(),
        config=RuntimeConfig(
            confidence_threshold=0.8,
            execution_profile=enabled_profile(),
        ),
    )

    timing_event = next(
        event for event in report.events if event.phase == "execution_timing"
    )
    operator_counts = timing_event.metadata["klm_operator_counts"]
    assert isinstance(operator_counts, dict)
    assert report.status == "passed"
    assert actuator.calls == 1
    assert operator_counts["mental"] == 1
    assert operator_counts["pointing"] == 1
    assert "execute_action" in event_phases(report)


def test_regression_persona_changes_timing_only_not_outcome_or_target() -> None:
    fast_actuator = CountingActuator()
    careful_actuator = CountingActuator()

    fast_report = run_fixture(
        actuator=fast_actuator,
        observation=ScreenObservation(active_window_title="DeskPilot Fixture"),
        perception_engine=SingleCandidatePerceptionEngine(),
        config=RuntimeConfig(
            confidence_threshold=0.8,
            execution_profile=persona_profile("fast"),
        ),
    )
    careful_report = run_fixture(
        actuator=careful_actuator,
        observation=ScreenObservation(active_window_title="DeskPilot Fixture"),
        perception_engine=SingleCandidatePerceptionEngine(),
        config=RuntimeConfig(
            confidence_threshold=0.8,
            execution_profile=persona_profile("careful"),
        ),
    )

    assert fast_report.status == careful_report.status == "passed"
    assert fast_report.steps[0].candidate_id == careful_report.steps[0].candidate_id
    assert selected_candidate_id(fast_report) == selected_candidate_id(careful_report)
    assert fast_actuator.calls == careful_actuator.calls == 1
    assert timing_delay(fast_report) < timing_delay(careful_report)
    assert timing_persona(fast_report) == "fast"
    assert timing_persona(careful_report) == "careful"


def run_fixture(
    *,
    actuator: CountingActuator,
    observation: ScreenObservation,
    perception_engine: PerceptionEngine,
    config: RuntimeConfig,
    task: TaskDefinition | None = None,
) -> RunReport:
    engine = ExecutionEngine(
        config_loader=StaticConfigLoader(config),
        task_loader=StaticTaskLoader(
            task
            or fixture_task(
                TaskStep(id="click-submit", action="click_text", target="Submit"),
            ),
        ),
        task_validator=BasicTaskValidator(),
        trace_sink=MemoryTraceSink(),
        safety_policy=LocalSafetyPolicy(),
        screen_observer=StaticScreenObserver(observation),
        perception_engine=CompositePerceptionEngine((perception_engine,)),
        target_selector=ConfidenceTargetSelector(),
        actuator=actuator,
    )
    return engine.run(Path("task.yaml"))


def fixture_task(step: TaskStep) -> TaskDefinition:
    return TaskDefinition(
        name="human-like-regression-fixture",
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=30,
        steps=(step,),
    )


def enabled_profile() -> ExecutionProfile:
    return ExecutionProfile(
        enabled=True,
        action_delay_seconds=(0.1, 0.2),
        retry_delay_seconds=(0.3, 0.4),
        hesitation_probability=0.5,
        movement_smoothness=0.5,
        random_seed=7,
    )


def persona_profile(persona: str) -> ExecutionProfile:
    return ExecutionProfile(
        persona=persona,
        enabled=True,
        action_delay_seconds=(0.1, 0.9),
        retry_delay_seconds=(0.3, 0.4),
        hesitation_probability=0.0,
        movement_smoothness=0.5,
        random_seed=7,
    )


def timing_sequence(profile: ExecutionProfile) -> tuple[tuple[float, bool], ...]:
    controller = ExecutionTimingController(profile)
    decisions = (
        controller.before_action(),
        controller.before_retry(),
        controller.before_action(),
        controller.before_retry(),
    )
    return tuple(
        (decision.delay_seconds, decision.hesitation_applied)
        for decision in decisions
    )


def timing_delay(report: RunReport) -> float:
    event = next(event for event in report.events if event.phase == "execution_timing")
    return cast(float, event.metadata["delay_seconds"])


def timing_persona(report: RunReport) -> str:
    event = next(event for event in report.events if event.phase == "execution_timing")
    return cast(str, event.metadata["execution_persona"])


def timing_sample_records(report: RunReport) -> object:
    event = next(event for event in report.events if event.phase == "execution_timing")
    return event.metadata["sample_records"]


def selected_candidate_id(report: RunReport) -> str:
    event = next(event for event in report.events if event.phase == "select_target")
    return cast(str, event.metadata["candidate_id"])


def event_phases(report: RunReport) -> set[str]:
    return {event.phase for event in report.events}
