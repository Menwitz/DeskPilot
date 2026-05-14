from pathlib import Path
from typing import cast

import pytest

from desktop_agent.actuation import ActionResult
from desktop_agent.config import (
    ConfigError,
    ExecutionProfile,
    RuntimeConfig,
    StaticConfigLoader,
)
from desktop_agent.perception import (
    CompositePerceptionEngine,
    ConfidenceTargetSelector,
    ElementCandidate,
    PerceptionEngine,
)
from desktop_agent.planner import ExecutionEngine
from desktop_agent.safety import LocalSafetyPolicy, SafetyDecision, SafetyPolicy
from desktop_agent.screen import Bounds, ScreenObservation, StaticScreenObserver
from desktop_agent.task_dsl import (
    BasicTaskValidator,
    StaticTaskLoader,
    TaskDefinition,
    TaskStep,
)
from desktop_agent.timing import ExecutionTimingController
from desktop_agent.tracing import MemoryTraceSink, RunReport, TraceEvent


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


class CountingSafetyPolicy:
    def __init__(self) -> None:
        self.precondition_calls = 0
        self.before_action_calls = 0

    def check_preconditions(
        self,
        task: TaskDefinition,
        config: RuntimeConfig,
    ) -> SafetyDecision:
        self.precondition_calls += 1
        return LocalSafetyPolicy().check_preconditions(task, config)

    def check_before_action(
        self,
        task: TaskDefinition,
        step: TaskStep,
        config: RuntimeConfig,
        observation: ScreenObservation | None = None,
    ) -> SafetyDecision:
        self.before_action_calls += 1
        return LocalSafetyPolicy().check_before_action(
            task,
            step,
            config,
            observation,
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


def test_regression_unsafe_profile_values_stop_before_actuation() -> None:
    actuator = CountingActuator()

    # Invalid timing bounds are rejected while loading config, before actuation exists.
    with pytest.raises(ConfigError, match=r"execution_profile\.action_delay_seconds"):
        run_fixture(
            actuator=actuator,
            observation=ScreenObservation(active_window_title="DeskPilot Fixture"),
            perception_engine=SingleCandidatePerceptionEngine(),
            config=RuntimeConfig(
                confidence_threshold=0.8,
                execution_profile=ExecutionProfile(
                    enabled=True,
                    action_delay_seconds=(0.3, 0.1),
                ),
            ),
        )

    assert actuator.calls == 0


def test_regression_operator_approval_stops_sensitive_step_before_observation() -> None:
    actuator = CountingActuator()
    task = fixture_task(
        TaskStep(
            id="submit-payment",
            action="click_text",
            target="Submit",
            category="submission",
        ),
    )
    report = run_fixture(
        task=task,
        actuator=actuator,
        observation=ScreenObservation(active_window_title="DeskPilot Fixture"),
        perception_engine=SingleCandidatePerceptionEngine(),
        config=RuntimeConfig(
            confidence_threshold=0.8,
            require_operator_approval=True,
            execution_profile=enabled_profile(),
        ),
    )

    assert report.status == "failed"
    assert report.steps[0].message == "step submit-payment requires operator approval"
    assert report.steps[0].metadata["failure_category"] == "safety_stop"
    assert actuator.calls == 0
    assert "observe_screen" not in event_phases(report)
    assert "execution_timing" not in event_phases(report)
    assert "execute_action" not in event_phases(report)


def test_acceptance_required_stop_conditions_prevent_actuation() -> None:
    disallowed_window_actuator = CountingActuator()
    disallowed_window = run_fixture(
        actuator=disallowed_window_actuator,
        observation=ScreenObservation(active_window_title="Unexpected Window"),
        perception_engine=SingleCandidatePerceptionEngine(),
        config=RuntimeConfig(
            confidence_threshold=0.8,
            execution_profile=enabled_profile(),
        ),
    )
    ambiguous_target_actuator = CountingActuator()
    ambiguous_target = run_fixture(
        actuator=ambiguous_target_actuator,
        observation=ScreenObservation(active_window_title="DeskPilot Fixture"),
        perception_engine=AmbiguousCandidatePerceptionEngine(),
        config=RuntimeConfig(
            confidence_threshold=0.8,
            execution_profile=enabled_profile(),
        ),
    )
    unconfirmed_sensitive_actuator = CountingActuator()
    unconfirmed_sensitive = run_fixture(
        task=fixture_task(
            TaskStep(
                id="submit-payment",
                action="click_text",
                target="Submit",
                requires_confirmation=True,
            ),
        ),
        actuator=unconfirmed_sensitive_actuator,
        observation=ScreenObservation(active_window_title="DeskPilot Fixture"),
        perception_engine=SingleCandidatePerceptionEngine(),
        config=RuntimeConfig(
            confidence_threshold=0.8,
            execution_profile=enabled_profile(),
        ),
    )
    unsafe_profile_actuator = CountingActuator()

    with pytest.raises(ConfigError, match=r"execution_profile\.action_delay_seconds"):
        run_fixture(
            actuator=unsafe_profile_actuator,
            observation=ScreenObservation(active_window_title="DeskPilot Fixture"),
            perception_engine=SingleCandidatePerceptionEngine(),
            config=RuntimeConfig(
                confidence_threshold=0.8,
                execution_profile=ExecutionProfile(
                    enabled=True,
                    action_delay_seconds=(0.3, 0.1),
                ),
            ),
        )

    stopped_reports = (
        (disallowed_window, disallowed_window_actuator),
        (ambiguous_target, ambiguous_target_actuator),
        (unconfirmed_sensitive, unconfirmed_sensitive_actuator),
    )
    assert unsafe_profile_actuator.calls == 0
    for report, actuator in stopped_reports:
        assert report.status == "failed"
        assert actuator.calls == 0
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


def test_acceptance_randomness_records_are_bounded_traceable_and_seeded() -> None:
    first_actuator = CountingActuator()
    second_actuator = CountingActuator()
    task = fixture_task(
        TaskStep(
            id="click-submit",
            action="click_text",
            target="Submit",
            safe_action_variants=("click_uia",),
        ),
    )
    config = RuntimeConfig(
        confidence_threshold=0.8,
        execution_profile=enabled_profile(),
    )

    first = run_fixture(
        task=task,
        actuator=first_actuator,
        observation=ScreenObservation(active_window_title="DeskPilot Fixture"),
        perception_engine=SingleCandidatePerceptionEngine(),
        config=config,
    )
    second = run_fixture(
        task=task,
        actuator=second_actuator,
        observation=ScreenObservation(active_window_title="DeskPilot Fixture"),
        perception_engine=SingleCandidatePerceptionEngine(),
        config=config,
    )

    first_events = events_with_sample_records(first)
    assert first.status == second.status == "passed"
    assert first_events
    assert sample_record_batches(first) == sample_record_batches(second)
    assert all(event.metadata["random_seed"] == 7 for event in first_events)
    assert any(event.phase == "action_variant" for event in first_events)
    assert any(event.phase == "execution_timing" for event in first_events)
    for event in first_events:
        records = event.metadata["sample_records"]
        assert isinstance(records, list)
        for record in records:
            assert_sample_record_is_bounded(record)


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


def test_regression_fast_path_reduces_wait_after_safety_check() -> None:
    actuator = CountingActuator()
    safety_policy = CountingSafetyPolicy()

    report = run_fixture(
        actuator=actuator,
        observation=ScreenObservation(active_window_title="DeskPilot Fixture"),
        perception_engine=SingleCandidatePerceptionEngine(),
        config=RuntimeConfig(
            confidence_threshold=0.8,
            execution_profile=ExecutionProfile(
                enabled=True,
                action_delay_seconds=(0.1, 0.9),
                retry_delay_seconds=(0.3, 0.4),
                hesitation_probability=0.0,
                random_seed=7,
            ),
        ),
        safety_policy=safety_policy,
    )

    timing_event = next(
        event for event in report.events if event.phase == "execution_timing"
    )
    original_delay = timing_event.metadata["original_delay_seconds"]
    reduced_delay = timing_event.metadata["delay_seconds"]
    assert isinstance(original_delay, float)
    assert isinstance(reduced_delay, float)
    assert report.status == "passed"
    assert actuator.calls == 1
    assert safety_policy.precondition_calls == 1
    assert safety_policy.before_action_calls == 1
    assert timing_event.metadata["execution_path"] == "fast"
    assert reduced_delay == 0.1
    assert original_delay > reduced_delay


def run_fixture(
    *,
    actuator: CountingActuator,
    observation: ScreenObservation,
    perception_engine: PerceptionEngine,
    config: RuntimeConfig,
    task: TaskDefinition | None = None,
    safety_policy: SafetyPolicy | None = None,
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
        safety_policy=safety_policy or LocalSafetyPolicy(),
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


def events_with_sample_records(report: RunReport) -> tuple[TraceEvent, ...]:
    return tuple(
        event
        for event in report.events
        if isinstance(event.metadata.get("sample_records"), list)
        and event.metadata["sample_records"]
    )


def sample_record_batches(report: RunReport) -> tuple[object, ...]:
    return tuple(
        event.metadata["sample_records"] for event in events_with_sample_records(report)
    )


def assert_sample_record_is_bounded(record: object) -> None:
    assert isinstance(record, dict)
    value = record["sample_value"]
    lower_bound = record["sample_lower_bound"]
    upper_bound = record["sample_upper_bound"]
    assert isinstance(value, float)
    assert isinstance(lower_bound, float)
    assert isinstance(upper_bound, float)
    assert lower_bound <= value <= upper_bound


def selected_candidate_id(report: RunReport) -> str:
    event = next(event for event in report.events if event.phase == "select_target")
    return cast(str, event.metadata["candidate_id"])


def event_phases(report: RunReport) -> set[str]:
    return {event.phase for event in report.events}
