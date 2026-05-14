from pathlib import Path

from desktop_agent.actuation import ActionResult, Actuator, DryRunActuator
from desktop_agent.config import ExecutionProfile, RuntimeConfig, StaticConfigLoader
from desktop_agent.perception import (
    CompositePerceptionEngine,
    ConfidenceTargetSelector,
    ElementCandidate,
    PerceptionEngine,
)
from desktop_agent.planner import ExecutionEngine
from desktop_agent.safety import LocalSafetyPolicy
from desktop_agent.screen import (
    Bounds,
    ScreenObservation,
    ScreenObserver,
    StaticScreenObserver,
)
from desktop_agent.task_dsl import (
    BasicTaskValidator,
    StaticTaskLoader,
    TaskDefinition,
    TaskRegion,
    TaskStep,
    VerificationDefinition,
)
from desktop_agent.tracing import MemoryTraceSink


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds

    def advance(self, seconds: float) -> None:
        self.now += seconds


class SequencePerceptionEngine(PerceptionEngine):
    def __init__(self, responses: tuple[tuple[ElementCandidate, ...], ...]) -> None:
        self._responses = responses
        self.calls = 0

    def detect(
        self,
        step: TaskStep,
        observation: ScreenObservation,
        config: RuntimeConfig,
    ) -> tuple[ElementCandidate, ...]:
        _ = step, observation, config
        index = min(self.calls, len(self._responses) - 1)
        self.calls += 1
        return self._responses[index]


class SequenceScreenObserver:
    def __init__(self, observations: tuple[ScreenObservation, ...]) -> None:
        self._observations = observations
        self.calls = 0

    def observe(self, config: RuntimeConfig) -> ScreenObservation:
        _ = config
        index = min(self.calls, len(self._observations) - 1)
        self.calls += 1
        return self._observations[index]


class SequenceActuator:
    def __init__(self, results: tuple[ActionResult, ...]) -> None:
        self._results = results
        self.calls = 0

    def execute(
        self,
        step: TaskStep,
        target: ElementCandidate | None,
        observation: ScreenObservation,
        config: RuntimeConfig,
    ) -> ActionResult:
        _ = step, target, observation, config
        index = min(self.calls, len(self._results) - 1)
        self.calls += 1
        return self._results[index]


class AdvancingActuator:
    def __init__(self, clock: FakeClock, *, success: bool = True) -> None:
        self._clock = clock
        self._success = success
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
        self._clock.advance(2.0)
        return ActionResult(self._success, "advanced")


def test_execution_engine_enforces_per_step_timeout() -> None:
    clock = FakeClock()
    task = TaskDefinition(
        name="step-timeout",
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=30,
        steps=(
            TaskStep(
                id="click-submit",
                action="click_text",
                target="Submit",
                timeout_seconds=1,
            ),
        ),
    )
    engine = _engine(
        task,
        perception=SequencePerceptionEngine((_candidate_tuple("Submit"),)),
        actuator=AdvancingActuator(clock),
        clock=clock,
    )

    report = engine.run(Path("task.yaml"))

    assert report.status == "failed"
    assert report.steps[0].message == "step exceeded timeout"


def test_execution_engine_rejects_impossible_step_timing_budget() -> None:
    clock = FakeClock()
    actuator = AdvancingActuator(clock)
    perception = SequencePerceptionEngine((_candidate_tuple("Submit"),))
    trace_sink = MemoryTraceSink()
    task = TaskDefinition(
        name="step-budget",
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=30,
        steps=(
            TaskStep(
                id="click-submit",
                action="click_text",
                target="Submit",
                retry=1,
                timeout_seconds=0.4,
            ),
        ),
    )
    engine = _engine(
        task,
        config=RuntimeConfig(
            confidence_threshold=0.8,
            execution_profile=ExecutionProfile(
                enabled=True,
                action_delay_seconds=(0.1, 0.25),
                retry_delay_seconds=(0.2, 0.25),
            ),
        ),
        perception=perception,
        actuator=actuator,
        clock=clock,
        trace_sink=trace_sink,
    )

    report = engine.run(Path("task.yaml"))

    budget_event = next(
        event for event in trace_sink.events if event.phase == "step_timeout_budget"
    )
    assert report.status == "failed"
    assert report.steps[0].message == (
        "step timeout budget is smaller than planned waits"
    )
    assert actuator.calls == 0
    assert perception.calls == 0
    assert budget_event.metadata["planned_wait_seconds"] == 0.75
    assert budget_event.metadata["fits_timeout"] is False


def test_execution_engine_selects_safe_action_variant() -> None:
    task = TaskDefinition(
        name="action-variant",
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=30,
        steps=(
            TaskStep(
                id="click-submit",
                action="click_text",
                target="Submit",
                safe_action_variants=("click_uia",),
            ),
        ),
    )
    trace_sink = MemoryTraceSink()
    engine = _engine(
        task,
        config=RuntimeConfig(
            confidence_threshold=0.8,
            execution_profile=ExecutionProfile(
                enabled=True,
                action_variant_distribution="uniform",
                random_seed=2,
            ),
        ),
        trace_sink=trace_sink,
    )

    report = engine.run(Path("task.yaml"))

    variant_event = next(
        event for event in trace_sink.events if event.phase == "action_variant"
    )
    assert report.status == "passed"
    assert report.steps[0].action == "click_uia"
    assert variant_event.metadata["selected_action"] == "click_uia"
    assert variant_event.metadata["random_seed"] == 2
    samples = variant_event.metadata["sample_records"]
    assert isinstance(samples, list)
    assert len(samples) == 1
    assert variant_event.metadata["available_action_variants"] == [
        "click_text",
        "click_uia",
    ]


def test_execution_engine_rejects_entropy_budget_before_observation() -> None:
    perception = SequencePerceptionEngine((_candidate_tuple("Submit"),))
    task = TaskDefinition(
        name="entropy-over-budget",
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=30,
        entropy_budget=5.0,
        steps=(
            TaskStep(
                id="click-submit",
                action="click_text",
                target="Submit",
                retry=0,
            ),
        ),
    )
    engine = _engine(task, perception=perception)

    report = engine.run(Path("task.yaml"))

    assert report.status == "failed"
    assert report.abort_reason == "entropy_budget exceeds task runtime capacity"
    assert perception.calls == 0


def test_execution_engine_enforces_task_level_timeout() -> None:
    clock = FakeClock()
    task = TaskDefinition(
        name="task-timeout",
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=1,
        steps=(
            TaskStep(id="first", action="click_text", target="Submit"),
            TaskStep(id="second", action="click_text", target="Submit"),
        ),
    )
    engine = _engine(
        task,
        perception=SequencePerceptionEngine((_candidate_tuple("Submit"),)),
        actuator=AdvancingActuator(clock),
        clock=clock,
    )

    report = engine.run(Path("task.yaml"))

    assert report.status == "aborted"
    assert report.abort_reason == "task exceeded timeout"
    assert [step.step_id for step in report.steps] == ["first"]


def test_execution_engine_wait_for_polls_until_candidate_is_visible() -> None:
    task = TaskDefinition(
        name="wait-for",
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=30,
        steps=(TaskStep(id="wait", action="wait_for", target="Ready"),),
    )
    trace_sink = MemoryTraceSink()
    engine = _engine(
        task,
        perception=SequencePerceptionEngine(((), _candidate_tuple("Ready"))),
        trace_sink=trace_sink,
    )

    report = engine.run(Path("task.yaml"))

    assert report.status == "passed"
    assert report.steps[0].attempts == 2
    assert "recover" in {event.phase for event in report.events}


def test_execution_engine_retries_stale_ui_selection_before_action() -> None:
    task = TaskDefinition(
        name="stale-ui",
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=30,
        steps=(
            TaskStep(id="click-submit", action="click_text", target="Submit", retry=1),
        ),
    )
    trace_sink = MemoryTraceSink()
    actuator = SequenceActuator((ActionResult(True, "clicked"),))
    engine = _engine(
        task,
        perception=SequencePerceptionEngine(((), _candidate_tuple("Submit"))),
        actuator=actuator,
        trace_sink=trace_sink,
        screen_observer=SequenceScreenObserver(
            (
                ScreenObservation(
                    active_window_title="DeskPilot Fixture",
                    warnings=("stale snapshot",),
                ),
                ScreenObservation(active_window_title="DeskPilot Fixture"),
            ),
        ),
    )

    report = engine.run(Path("task.yaml"))

    recover = next(event for event in report.events if event.phase == "recover")
    assert report.status == "passed"
    assert report.steps[0].attempts == 2
    assert actuator.calls == 1
    assert recover.metadata["recovery_reason"] == "stale_observation"
    assert recover.metadata["recovery_chosen_action"] == "reobserve_screen"


def test_execution_engine_retries_delayed_disabled_control() -> None:
    task = TaskDefinition(
        name="delayed-control",
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=30,
        steps=(
            TaskStep(id="click-submit", action="click_text", target="Submit", retry=1),
        ),
    )
    trace_sink = MemoryTraceSink()
    actuator = SequenceActuator((ActionResult(True, "clicked"),))
    engine = _engine(
        task,
        perception=SequencePerceptionEngine(
            (
                _candidate_tuple("Submit", enabled=False),
                _candidate_tuple("Submit"),
            ),
        ),
        actuator=actuator,
        trace_sink=trace_sink,
    )

    report = engine.run(Path("task.yaml"))

    recover = next(event for event in report.events if event.phase == "recover")
    assert report.status == "passed"
    assert report.steps[0].attempts == 2
    assert actuator.calls == 1
    assert recover.metadata["recovery_reason"] == "disabled_control"
    assert recover.metadata["recovery_backoff_strategy"] == "bounded_exponential"


def test_execution_engine_reports_duplicated_labels_as_ambiguity_gate() -> None:
    task = TaskDefinition(
        name="duplicated-labels",
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=30,
        steps=(
            TaskStep(id="click-submit", action="click_text", target="Submit", retry=1),
        ),
    )
    trace_sink = MemoryTraceSink()
    actuator = SequenceActuator((ActionResult(True, "should not execute"),))
    engine = _engine(
        task,
        perception=SequencePerceptionEngine(
            (
                (
                    _candidate("candidate-1", "Submit"),
                    _candidate("candidate-2", "Submit", x=220, confidence=0.94),
                ),
            ),
        ),
        actuator=actuator,
        trace_sink=trace_sink,
    )

    report = engine.run(Path("task.yaml"))

    selection = next(event for event in report.events if event.phase == "select_target")
    snapshot = next(
        event for event in report.events if event.phase == "ui_state_snapshot"
    )
    assert report.status == "failed"
    assert report.steps[0].message == (
        "target selection blocked by confidence or ambiguity gate"
    )
    assert report.steps[0].metadata["failure_category"] == "selection_ambiguity"
    assert selection.metadata["selection_blocked"] == "confidence_or_ambiguity_gate"
    blocked_candidates = snapshot.metadata["blocked_candidates"]
    assert isinstance(blocked_candidates, list)
    assert blocked_candidates[0]["blocked_reason"] == "confidence_or_ambiguity_gate"
    assert actuator.calls == 0


def test_execution_engine_reports_failure_category_metadata() -> None:
    perception_report = _engine(
        _single_click_task("perception", retry=0),
        perception=SequencePerceptionEngine(((),)),
    ).run(Path("task.yaml"))

    safety_report = _engine(
        _single_click_task("safety", retry=0),
        perception=SequencePerceptionEngine((_candidate_tuple("Submit"),)),
        screen_observer=SequenceScreenObserver(
            (ScreenObservation(active_window_title="Unexpected Window"),),
        ),
    ).run(Path("task.yaml"))

    verification_report = _engine(
        TaskDefinition(
            name="verification",
            allowed_windows=("DeskPilot Fixture",),
            timeout_seconds=30,
            steps=(
                TaskStep(
                    id="click-submit",
                    action="click_text",
                    target="Submit",
                    retry=0,
                    verify=VerificationDefinition(
                        type="visible_text",
                        text="Success",
                    ),
                ),
            ),
        ),
        perception=SequencePerceptionEngine((_candidate_tuple("Submit"), ())),
    ).run(Path("task.yaml"))

    actuation_report = _engine(
        _single_click_task("actuation", retry=0),
        perception=SequencePerceptionEngine((_candidate_tuple("Submit"),)),
        actuator=SequenceActuator((ActionResult(False, "click failed"),)),
    ).run(Path("task.yaml"))

    assert perception_report.steps[0].metadata["failure_category"] == (
        "perception_failure"
    )
    assert safety_report.steps[0].metadata["failure_category"] == "safety_stop"
    assert verification_report.steps[0].metadata["failure_category"] == (
        "verification_failure"
    )
    assert actuation_report.steps[0].metadata["failure_category"] == (
        "actuation_failure"
    )


def test_execution_engine_recovers_when_verification_target_disappears() -> None:
    task = TaskDefinition(
        name="disappearing-target",
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=30,
        steps=(
            TaskStep(
                id="click-submit",
                action="click_text",
                target="Submit",
                retry=1,
                verify=VerificationDefinition(type="visible_text", text="Success"),
            ),
        ),
    )
    trace_sink = MemoryTraceSink()
    actuator = SequenceActuator(
        (
            ActionResult(True, "clicked"),
            ActionResult(True, "clicked"),
        )
    )
    engine = _engine(
        task,
        perception=SequencePerceptionEngine(
            (
                _candidate_tuple("Submit"),
                (),
                (),
                _candidate_tuple("Submit"),
                _candidate_tuple("Success"),
            ),
        ),
        actuator=actuator,
        trace_sink=trace_sink,
    )

    report = engine.run(Path("task.yaml"))

    recover = next(event for event in report.events if event.phase == "recover")
    assert report.status == "passed"
    assert report.steps[0].attempts == 2
    assert actuator.calls == 2
    assert "recover_candidates" in {event.phase for event in report.events}
    assert recover.metadata["recovery_reason"] == "missed_target"
    assert recover.metadata["recovery_chosen_action"] == "wait_and_reobserve"


def test_execution_engine_scroll_until_scrolls_search_region() -> None:
    task = TaskDefinition(
        name="scroll-until",
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=30,
        steps=(
            TaskStep(
                id="scroll",
                action="scroll_until",
                target="Submit",
                region=TaskRegion(x=0, y=0, width=100, height=100),
            ),
        ),
    )
    engine = _engine(
        task,
        perception=SequencePerceptionEngine(((), _candidate_tuple("Submit"))),
    )

    report = engine.run(Path("task.yaml"))

    assert report.status == "passed"
    assert report.steps[0].message == "scroll_until target is visible"
    assert "execute_action" in {event.phase for event in report.events}


def test_execution_engine_branch_if_visible_jumps_to_failure_target() -> None:
    task = TaskDefinition(
        name="branch",
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=30,
        steps=(
            TaskStep(
                id="branch",
                action="branch_if_visible",
                target="Optional",
                on_failure="fallback",
            ),
            TaskStep(id="middle", action="press_key", text="enter"),
            TaskStep(id="fallback", action="press_key", text="esc"),
        ),
    )
    engine = _engine(task, perception=SequencePerceptionEngine(((),)))

    report = engine.run(Path("task.yaml"))

    assert report.status == "passed"
    assert [step.step_id for step in report.steps] == ["branch", "fallback"]


def test_execution_engine_aborts_when_action_count_exceeds_limit() -> None:
    clock = FakeClock()
    task = TaskDefinition(
        name="action-limit",
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=30,
        steps=(
            TaskStep(id="click-submit", action="click_text", target="Submit", retry=1),
        ),
    )
    engine = _engine(
        task,
        config=RuntimeConfig(max_steps=1, confidence_threshold=0.8),
        perception=SequencePerceptionEngine((_candidate_tuple("Submit"),)),
        actuator=AdvancingActuator(clock, success=False),
        clock=clock,
    )

    report = engine.run(Path("task.yaml"))

    assert report.status == "failed"
    assert report.steps[0].message == "task exceeded max action count"


def test_execution_engine_verifies_visible_text_after_action() -> None:
    task = TaskDefinition(
        name="verify",
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
    engine = _engine(
        task,
        perception=SequencePerceptionEngine(
            (_candidate_tuple("Submit"), _candidate_tuple("Success")),
        ),
    )

    report = engine.run(Path("task.yaml"))

    assert report.status == "passed"
    assert report.steps[0].message == "text is visible"


def _engine(
    task: TaskDefinition,
    *,
    config: RuntimeConfig | None = None,
    perception: PerceptionEngine | None = None,
    actuator: Actuator | None = None,
    clock: FakeClock | None = None,
    trace_sink: MemoryTraceSink | None = None,
    screen_observer: ScreenObserver | None = None,
) -> ExecutionEngine:
    return ExecutionEngine(
        config_loader=StaticConfigLoader(
            config or RuntimeConfig(confidence_threshold=0.8),
        ),
        task_loader=StaticTaskLoader(task),
        task_validator=BasicTaskValidator(),
        trace_sink=trace_sink or MemoryTraceSink(),
        safety_policy=LocalSafetyPolicy(),
        screen_observer=screen_observer
        or StaticScreenObserver(
            ScreenObservation(active_window_title="DeskPilot Fixture"),
        ),
        perception_engine=CompositePerceptionEngine(
            (perception or SequencePerceptionEngine((_candidate_tuple("Submit"),)),),
        ),
        target_selector=ConfidenceTargetSelector(),
        actuator=actuator or DryRunActuator(),
        clock=clock or FakeClock(),
    )


def _candidate_tuple(
    label: str,
    *,
    enabled: bool = True,
    visible: bool = True,
) -> tuple[ElementCandidate, ...]:
    return (_candidate(f"candidate-{label}", label, enabled=enabled, visible=visible),)


def _candidate(
    candidate_id: str,
    label: str,
    *,
    x: int = 10,
    confidence: float = 0.95,
    enabled: bool = True,
    visible: bool = True,
) -> ElementCandidate:
    return ElementCandidate(
        id=candidate_id,
        source="uia",
        label=label,
        bounds=Bounds(x=x, y=20, width=100, height=30),
        confidence=confidence,
        enabled=enabled,
        visible=visible,
    )


def _single_click_task(name: str, *, retry: int) -> TaskDefinition:
    return TaskDefinition(
        name=name,
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=30,
        steps=(
            TaskStep(
                id="click-submit",
                action="click_text",
                target="Submit",
                retry=retry,
            ),
        ),
    )
