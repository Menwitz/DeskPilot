from pathlib import Path

from desktop_agent.actuation import ActionResult, Actuator, DryRunActuator
from desktop_agent.config import ExecutionProfile, RuntimeConfig, StaticConfigLoader
from desktop_agent.perception import (
    CompositePerceptionEngine,
    ConfidenceTargetSelector,
    ElementCandidate,
    PerceptionEngine,
)
from desktop_agent.planner import (
    ExecutionEngine,
    PassingStepVerifier,
    VerificationResult,
)
from desktop_agent.safety import LocalSafetyPolicy
from desktop_agent.screen import (
    Bounds,
    MonitorInfo,
    ScreenObservation,
    ScreenObserver,
    StaticScreenObserver,
)
from desktop_agent.task_dsl import (
    BasicTaskValidator,
    ExpectedStateTransition,
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

    def current_position(self) -> tuple[int, int]:
        return (333, 444)


class SequenceVerifier:
    def __init__(self, results: tuple[VerificationResult, ...]) -> None:
        self._results = results
        self.calls = 0

    def verify(
        self,
        step: TaskStep,
        observation: ScreenObservation,
        target: ElementCandidate | None,
        action_result: ActionResult,
        config: RuntimeConfig,
        candidates: tuple[ElementCandidate, ...] = (),
    ) -> VerificationResult:
        _ = step, observation, target, action_result, config, candidates
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


def test_execution_engine_consumes_profile_timing_delays() -> None:
    clock = FakeClock()
    trace_sink = MemoryTraceSink()
    task = TaskDefinition(
        name="timing-consumption",
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=30,
        steps=(
            TaskStep(id="click-submit", action="click_text", target="Submit", retry=1),
        ),
    )
    engine = _engine(
        task,
        config=RuntimeConfig(
            confidence_threshold=0.8,
            execution_profile=ExecutionProfile(
                enabled=True,
                action_delay_seconds=(0.2, 0.2),
                retry_delay_seconds=(0.3, 0.3),
                random_seed=1,
            ),
        ),
        perception=SequencePerceptionEngine(
            (
                _candidate_tuple("Submit"),
                _candidate_tuple("Submit"),
                _candidate_tuple("Submit"),
            ),
        ),
        actuator=SequenceActuator(
            (
                ActionResult(False, "click failed"),
                ActionResult(True, "clicked"),
            ),
        ),
        clock=clock,
        trace_sink=trace_sink,
    )

    report = engine.run(Path("task.yaml"))

    timing_events = [
        event for event in report.events if event.phase == "execution_timing"
    ]
    assert report.status == "passed"
    assert round(clock.now, 2) == 0.7
    assert [event.metadata["delay_seconds"] for event in timing_events] == [
        0.2,
        0.3,
        0.2,
    ]


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


def test_execution_engine_fast_path_uses_lower_bound_timing() -> None:
    clock = FakeClock()
    task = TaskDefinition(
        name="fast-path",
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=30,
        steps=(TaskStep(id="open-menu", action="click_text", target="Menu"),),
    )
    trace_sink = MemoryTraceSink()
    engine = _engine(
        task,
        config=RuntimeConfig(
            confidence_threshold=0.8,
            execution_profile=ExecutionProfile(
                enabled=True,
                action_delay_seconds=(0.2, 0.8),
                hesitation_probability=0.0,
                random_seed=3,
            ),
        ),
        perception=SequencePerceptionEngine(
            (_candidate_tuple("Menu", confidence=1.0),),
        ),
        clock=clock,
        trace_sink=trace_sink,
    )

    report = engine.run(Path("task.yaml"))

    path_event = next(
        event for event in report.events if event.phase == "execution_path"
    )
    timing_event = next(
        event for event in report.events if event.phase == "execution_timing"
    )
    assert report.status == "passed"
    assert path_event.metadata["execution_path"] == "fast"
    assert timing_event.metadata["execution_path"] == "fast"
    assert timing_event.metadata["delay_seconds"] == 0.2
    original_delay = timing_event.metadata["original_delay_seconds"]
    delay_reduction = timing_event.metadata["delay_reduction_seconds"]
    assert isinstance(original_delay, float)
    assert isinstance(delay_reduction, float)
    assert original_delay > 0.2
    assert delay_reduction > 0
    assert timing_event.metadata["safety_checks_required"] is True
    assert round(clock.now, 3) == 0.2


def test_execution_engine_careful_path_uses_upper_bound_timing() -> None:
    clock = FakeClock()
    task = TaskDefinition(
        name="careful-path",
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=30,
        steps=(TaskStep(id="click-review", action="click_text", target="Review"),),
    )
    engine = _engine(
        task,
        config=RuntimeConfig(
            confidence_threshold=0.8,
            execution_profile=ExecutionProfile(
                enabled=True,
                action_delay_seconds=(0.2, 0.8),
                hesitation_probability=0.0,
                random_seed=3,
            ),
        ),
        perception=SequencePerceptionEngine(
            (_candidate_tuple("Review", confidence=0.9),),
        ),
        clock=clock,
    )

    report = engine.run(Path("task.yaml"))

    path_event = next(
        event for event in report.events if event.phase == "execution_path"
    )
    timing_event = next(
        event for event in report.events if event.phase == "execution_timing"
    )
    original_delay = timing_event.metadata["original_delay_seconds"]
    delay_extension = timing_event.metadata["delay_extension_seconds"]
    assert report.status == "passed"
    assert path_event.metadata["execution_path"] == "careful"
    assert path_event.metadata["execution_path_reason"] == (
        "low_confidence_selected_target"
    )
    assert timing_event.metadata["execution_path"] == "careful"
    assert timing_event.metadata["delay_seconds"] == 0.8
    assert isinstance(original_delay, float)
    assert isinstance(delay_extension, float)
    assert original_delay < 0.8
    assert delay_extension > 0
    assert round(clock.now, 3) == 0.8


def test_execution_engine_records_elapsed_input_wait_before_action() -> None:
    clock = FakeClock()
    task = TaskDefinition(
        name="input-wait",
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=30,
        steps=(TaskStep(id="click-submit", action="click_text", target="Submit"),),
    )
    engine = _engine(
        task,
        config=RuntimeConfig(
            confidence_threshold=0.8,
            execution_profile=ExecutionProfile(
                enabled=True,
                action_delay_seconds=(0.2, 0.2),
            ),
        ),
        clock=clock,
    )

    report = engine.run(Path("task.yaml"))

    phases = [event.phase for event in report.events]
    wait_event = next(event for event in report.events if event.phase == "input_wait")
    assert report.status == "passed"
    assert wait_event.metadata["requested_delay_seconds"] == 0.2
    assert wait_event.metadata["elapsed_wait_seconds"] == 0.2
    assert wait_event.metadata["before_desktop_input"] is True
    assert phases.index("input_wait") < phases.index("execute_action")


def test_execution_engine_records_pre_action_observation_evidence(
    tmp_path: Path,
) -> None:
    task = TaskDefinition(
        name="pre-action-evidence",
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=30,
        steps=(TaskStep(id="click-submit", action="click_text", target="Submit"),),
    )
    observation = ScreenObservation(
        screenshot_path=tmp_path / "before.png",
        size=(800, 600),
        active_window_title="DeskPilot Fixture",
        monitor=MonitorInfo(
            left=10,
            top=20,
            width=800,
            height=600,
            scale_x=1.25,
            scale_y=1.5,
            is_primary=True,
        ),
        metadata={
            "active_window_process": {
                "process_id": 1234,
                "process_name": "notepad.exe",
            },
            "focused_element": {
                "name": "Routine",
                "class_name": "Edit",
            },
        },
    )
    trace_sink = MemoryTraceSink()
    engine = _engine(
        task,
        screen_observer=SequenceScreenObserver((observation,)),
        perception=SequencePerceptionEngine((_candidate_tuple("Submit"),)),
        actuator=SequenceActuator((ActionResult(True, "clicked"),)),
        trace_sink=trace_sink,
    )

    report = engine.run(Path("task.yaml"))

    phases = [event.phase for event in report.events]
    observe_event = next(
        event for event in report.events if event.phase == "observe_screen"
    )
    evidence = observe_event.metadata["pre_action_evidence"]
    assert isinstance(evidence, dict)
    assert report.status == "passed"
    assert observe_event.metadata["trace_schema_section"] == "observation"
    assert observe_event.metadata["observation_role"] == "pre_action"
    assert evidence["screenshot_path"] == str(tmp_path / "before.png")
    assert evidence["active_window_title"] == "DeskPilot Fixture"
    assert evidence["active_window_process"] == {
        "process_id": 1234,
        "process_name": "notepad.exe",
    }
    assert evidence["focused_element"] == {
        "name": "Routine",
        "class_name": "Edit",
    }
    assert evidence["cursor_position"] == [333, 444]
    assert evidence["cursor_readback"] == {"status": "passed", "position": [333, 444]}
    assert evidence["monitor"] == {
        "left": 10,
        "top": 20,
        "width": 800,
        "height": 600,
        "scale_x": 1.25,
        "scale_y": 1.5,
        "is_primary": True,
    }
    assert evidence["dpi_scale"] == {"scale_x": 1.25, "scale_y": 1.5}
    assert phases.index("observe_screen") < phases.index("detect_candidates")
    assert phases.index("observe_screen") < phases.index("execute_action")


def test_execution_engine_records_post_action_observation_evidence(
    tmp_path: Path,
) -> None:
    task = TaskDefinition(
        name="post-action-evidence",
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=30,
        steps=(TaskStep(id="click-submit", action="click_text", target="Submit"),),
    )
    pre_action = ScreenObservation(active_window_title="DeskPilot Fixture")
    post_action = ScreenObservation(
        screenshot_path=tmp_path / "after.png",
        size=(1024, 768),
        active_window_title="DeskPilot Fixture - Complete",
        monitor=MonitorInfo(
            left=0,
            top=0,
            width=1024,
            height=768,
            scale_x=1.0,
            scale_y=1.25,
            is_primary=True,
        ),
        warnings=("focus moved after click",),
        metadata={
            "active_window_process": {
                "process_id": 4321,
                "process_name": "msedge.exe",
            },
            "focused_element": {
                "name": "Done",
                "class_name": "Button",
            },
        },
    )
    engine = _engine(
        task,
        screen_observer=SequenceScreenObserver((pre_action, post_action)),
        perception=SequencePerceptionEngine((_candidate_tuple("Submit"),)),
        actuator=SequenceActuator((ActionResult(True, "clicked"),)),
    )

    report = engine.run(Path("task.yaml"))

    phases = [event.phase for event in report.events]
    observe_event = next(
        event for event in report.events if event.phase == "observe_after_action"
    )
    evidence = observe_event.metadata["post_action_evidence"]
    assert isinstance(evidence, dict)
    assert report.status == "passed"
    assert observe_event.metadata["trace_schema_section"] == "verification"
    assert observe_event.metadata["observation_role"] == "post_action"
    assert evidence["screenshot_path"] == str(tmp_path / "after.png")
    assert evidence["active_window_title"] == "DeskPilot Fixture - Complete"
    assert evidence["active_window_process"] == {
        "process_id": 4321,
        "process_name": "msedge.exe",
    }
    assert evidence["focused_element"] == {
        "name": "Done",
        "class_name": "Button",
    }
    assert evidence["cursor_position"] == [333, 444]
    assert evidence["warnings"] == ["focus moved after click"]
    assert evidence["dpi_scale"] == {"scale_x": 1.0, "scale_y": 1.25}
    assert phases.index("execute_action") < phases.index("observe_after_action")
    assert phases.index("observe_after_action") < phases.index("verify_result")


def test_execution_engine_records_target_reasoning_and_coordinate_conversion() -> None:
    task = TaskDefinition(
        name="target-reasoning",
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=30,
        steps=(TaskStep(id="click-submit", action="click_text", target="Submit"),),
    )
    observation = ScreenObservation(
        active_window_title="DeskPilot Fixture",
        monitor=MonitorInfo(
            left=100,
            top=200,
            width=1200,
            height=800,
            scale_x=2.0,
            scale_y=2.0,
            is_primary=True,
        ),
    )
    trace_sink = MemoryTraceSink()
    engine = _engine(
        task,
        screen_observer=SequenceScreenObserver((observation,)),
        perception=SequencePerceptionEngine(
            (
                (
                    _candidate("candidate-selected", "Submit", confidence=0.97),
                    _candidate(
                        "candidate-disabled",
                        "Submit",
                        x=220,
                        confidence=0.96,
                        enabled=False,
                    ),
                ),
            ),
        ),
        actuator=SequenceActuator((ActionResult(True, "clicked"),)),
        trace_sink=trace_sink,
    )

    report = engine.run(Path("task.yaml"))

    selection = next(event for event in report.events if event.phase == "select_target")
    selected = selection.metadata["selected_candidate"]
    rejected = selection.metadata["rejected_candidates"]
    conversion = selection.metadata["coordinate_conversion"]
    assert isinstance(selected, dict)
    assert isinstance(rejected, list)
    assert isinstance(conversion, dict)
    assert report.status == "passed"
    assert selection.metadata["trace_schema_section"] == "target_reasoning"
    assert selected["id"] == "candidate-selected"
    assert selected["confidence"] == 0.97
    assert selection.metadata["confidence_values"] == {
        "candidate-selected": 0.97,
        "candidate-disabled": 0.96,
    }
    assert rejected[0]["id"] == "candidate-disabled"
    assert rejected[0]["rejection_reason"] == "disabled"
    assert selection.metadata["rejection_reasons"] == {
        "candidate-disabled": "disabled",
    }
    assert conversion["screenshot_center"] == [60, 35]
    assert conversion["physical_center"] == [220, 270]
    assert conversion["physical_bounds"] == {
        "x": 120,
        "y": 240,
        "width": 200,
        "height": 60,
        "center": [220, 270],
    }
    assert conversion["conversion_status"] == "converted"


def test_execution_engine_records_state_delta_summary() -> None:
    task = TaskDefinition(
        name="state-delta",
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
    before = ScreenObservation(
        active_window_title="DeskPilot Fixture",
        metadata={"focused_element": {"name": "Submit", "class_name": "Button"}},
    )
    after = ScreenObservation(
        active_window_title="DeskPilot Fixture - Done",
        metadata={"focused_element": {"name": "Success", "class_name": "Text"}},
    )
    engine = _engine(
        task,
        screen_observer=SequenceScreenObserver((before, after)),
        perception=SequencePerceptionEngine(
            (_candidate_tuple("Submit"), _candidate_tuple("Success")),
        ),
        actuator=SequenceActuator((ActionResult(True, "clicked"),)),
    )

    report = engine.run(Path("task.yaml"))

    delta = next(event for event in report.events if event.phase == "state_delta")
    assert report.status == "passed"
    assert delta.metadata["trace_schema_section"] == "state_delta"
    assert delta.metadata["focus_changed"] is True
    assert delta.metadata["active_window_changed"] is True
    assert delta.metadata["focused_element_changed"] is True
    assert delta.metadata["visible_text_before"] == ["Submit"]
    assert delta.metadata["visible_text_after"] == ["Success"]
    assert delta.metadata["visible_text_added"] == ["Success"]
    assert delta.metadata["visible_text_removed"] == ["Submit"]
    assert delta.metadata["visible_text_changed"] is True
    assert delta.metadata["target_text"] == "Success"
    assert delta.metadata["target_appeared"] is True
    assert delta.metadata["target_disappeared"] is False


def test_execution_engine_records_scroll_state_delta() -> None:
    task = TaskDefinition(
        name="scroll-delta",
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=30,
        steps=(
            TaskStep(
                id="scroll-list",
                action="scroll",
                text="-3",
                region=TaskRegion(x=0, y=0, width=100, height=100),
            ),
        ),
    )
    engine = _engine(
        task,
        perception=SequencePerceptionEngine(((),)),
        actuator=SequenceActuator(
            (
                ActionResult(
                    True,
                    "scrolled",
                    metadata={
                        "input_action": "scroll",
                        "scroll_clicks": -3,
                        "scroll_step_count": 3,
                        "scroll_step_clicks": [-1, -1, -1],
                    },
                ),
            ),
        ),
    )

    report = engine.run(Path("task.yaml"))

    delta = next(event for event in report.events if event.phase == "state_delta")
    assert report.status == "passed"
    assert delta.metadata["scroll_moved"] is True
    assert delta.metadata["scroll_action"] == "scroll"
    assert delta.metadata["scroll_clicks"] == -3
    assert delta.metadata["scroll_step_count"] == 3
    assert delta.metadata["scroll_step_clicks"] == [-1, -1, -1]


def test_execution_engine_retries_inconclusive_verification() -> None:
    task = TaskDefinition(
        name="inconclusive-retry",
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
    verifier = SequenceVerifier(
        (
            VerificationResult(
                False,
                "verification evidence was inconclusive",
                outcome="inconclusive",
            ),
            VerificationResult(True, "verified"),
        ),
    )
    actuator = SequenceActuator(
        (
            ActionResult(True, "clicked"),
            ActionResult(True, "clicked"),
        ),
    )
    engine = _engine(
        task,
        perception=SequencePerceptionEngine(
            (
                _candidate_tuple("Submit"),
                (),
                _candidate_tuple("Submit"),
                _candidate_tuple("Success"),
            ),
        ),
        actuator=actuator,
        verifier=verifier,
    )

    report = engine.run(Path("task.yaml"))

    recover = next(event for event in report.events if event.phase == "recover")
    outcomes = [
        event.metadata["verification_outcome"]
        for event in report.events
        if event.phase == "verify_result"
    ]
    assert report.status == "passed"
    assert report.steps[0].attempts == 2
    assert verifier.calls == 2
    assert actuator.calls == 2
    assert outcomes == ["inconclusive", "passed"]
    assert recover.metadata["recovery_reason"] == "verification_inconclusive"
    assert recover.metadata["recovery_chosen_action"] == "wait_and_reobserve"


def test_execution_engine_routes_inconclusive_verification_to_handoff() -> None:
    task = TaskDefinition(
        name="inconclusive-handoff",
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=30,
        steps=(
            TaskStep(
                id="click-submit",
                action="click_text",
                target="Submit",
                retry=0,
                verify=VerificationDefinition(type="visible_text", text="Success"),
            ),
        ),
    )
    engine = _engine(
        task,
        perception=SequencePerceptionEngine((_candidate_tuple("Submit"), ())),
        actuator=SequenceActuator((ActionResult(True, "clicked"),)),
        verifier=SequenceVerifier(
            (
                VerificationResult(
                    False,
                    "verification evidence was inconclusive",
                    outcome="inconclusive",
                ),
            ),
        ),
    )

    report = engine.run(Path("task.yaml"))

    handoff = next(event for event in report.events if event.phase == "manual_handoff")
    assert report.status == "failed"
    assert report.steps[0].metadata["failure_category"] == "manual_handoff"
    assert report.steps[0].message == (
        "manual handoff required: verification evidence was inconclusive"
    )
    assert handoff.metadata["verification_outcome"] == "inconclusive"
    assert handoff.metadata["manual_handoff_required"] is True


def test_execution_engine_runs_checkpoint_before_irreversible_action() -> None:
    task = TaskDefinition(
        name="checkpoint-pass",
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=30,
        steps=(
            TaskStep(
                id="submit",
                action="click_text",
                target="Submit",
                category="submission",
                checkpoint=VerificationDefinition(
                    type="visible_text",
                    text="Ready",
                ),
            ),
        ),
    )
    engine = _engine(
        task,
        config=RuntimeConfig(
            confidence_threshold=0.8,
            execution_profile=ExecutionProfile(
                enabled=True,
                action_delay_seconds=(0.1, 0.1),
            ),
        ),
        perception=SequencePerceptionEngine(
            (_candidate_tuple("Submit"), _candidate_tuple("Ready")),
        ),
    )

    report = engine.run(Path("task.yaml"))

    phases = [event.phase for event in report.events]
    checkpoint = next(
        event for event in report.events if event.phase == "verification_checkpoint"
    )
    assert report.status == "passed"
    assert checkpoint.metadata["passed"] is True
    assert checkpoint.metadata["irreversible_action"] is True
    assert phases.index("verification_checkpoint") < phases.index("execution_timing")
    assert phases.index("verification_checkpoint") < phases.index("execute_action")


def test_execution_engine_stops_when_checkpoint_fails_before_action() -> None:
    actuator = SequenceActuator((ActionResult(True, "should not run"),))
    task = TaskDefinition(
        name="checkpoint-fail",
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=30,
        steps=(
            TaskStep(
                id="submit",
                action="click_text",
                target="Submit",
                category="submission",
                checkpoint=VerificationDefinition(
                    type="visible_text",
                    text="Ready",
                ),
            ),
        ),
    )
    engine = _engine(
        task,
        config=RuntimeConfig(
            confidence_threshold=0.8,
            execution_profile=ExecutionProfile(
                enabled=True,
                action_delay_seconds=(0.1, 0.1),
            ),
        ),
        perception=SequencePerceptionEngine((_candidate_tuple("Submit"), ())),
        actuator=actuator,
    )

    report = engine.run(Path("task.yaml"))

    phases = {event.phase for event in report.events}
    assert report.status == "failed"
    assert report.steps[0].metadata["failure_category"] == "verification_checkpoint"
    assert report.steps[0].message == (
        "verification checkpoint failed: text is not visible"
    )
    assert "execution_timing" not in phases
    assert "execute_action" not in phases
    assert actuator.calls == 0


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


def test_execution_engine_missed_target_includes_diagnostic_bundle(
    tmp_path: Path,
) -> None:
    observation = ScreenObservation(
        screenshot_path=tmp_path / "screen.png",
        size=(800, 600),
        active_window_title="LinkedIn - Edge",
    )
    candidates = (
        ElementCandidate(
            id="uia-settings",
            source="uia",
            label="Submit",
            bounds=Bounds(x=10, y=20, width=100, height=30),
            confidence=0.40,
        ),
        ElementCandidate(
            id="ocr-profile",
            source="ocr",
            label="Submit",
            bounds=Bounds(x=200, y=40, width=90, height=25),
            confidence=0.50,
        ),
    )
    trace_sink = MemoryTraceSink()
    report = _engine(
        _single_click_task("diagnostics", retry=0),
        perception=SequencePerceptionEngine((candidates,)),
        screen_observer=SequenceScreenObserver((observation,)),
        actuator=SequenceActuator((ActionResult(True, "unused"),)),
        trace_sink=trace_sink,
    ).run(Path("task.yaml"))

    diagnostic = report.steps[0].metadata["diagnostic_bundle"]
    assert isinstance(diagnostic, dict)
    assert report.status == "failed"
    assert report.steps[0].metadata["failure_category"] == "selection_ambiguity"
    assert diagnostic["diagnostic_type"] == "target_selection_failure"
    assert diagnostic["screenshot_path"] == str(tmp_path / "screen.png")
    assert diagnostic["active_window_title"] == "LinkedIn - Edge"
    assert diagnostic["cursor_readback"] == {
        "status": "passed",
        "position": [333, 444],
    }
    candidates_by_source = diagnostic["candidates_by_source"]
    assert isinstance(candidates_by_source, dict)
    assert candidates_by_source["uia"][0]["id"] == "uia-settings"
    assert candidates_by_source["ocr"][0]["id"] == "ocr-profile"
    assert any(event.phase == "target_diagnostics" for event in report.events)


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
    reobserve = next(
        event for event in report.events if event.phase == "reobserve_after_failure"
    )
    post_failure_evidence = reobserve.metadata["post_action_evidence"]
    assert report.status == "passed"
    assert report.steps[0].attempts == 2
    assert actuator.calls == 2
    assert "recover_candidates" in {event.phase for event in report.events}
    assert recover.metadata["recovery_reason"] == "missed_target"
    assert recover.metadata["recovery_chosen_action"] == "wait_and_reobserve"
    assert reobserve.metadata["failure_observation"] is True
    assert isinstance(post_failure_evidence, dict)
    assert post_failure_evidence["active_window_title"] == "DeskPilot Fixture"


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


def test_execution_engine_scroll_cadence_stops_at_intended_target() -> None:
    clock = FakeClock()
    actuator = SequenceActuator((ActionResult(True, "scrolled"),))
    task = TaskDefinition(
        name="scroll-cadence",
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=30,
        steps=(
            TaskStep(
                id="scroll",
                action="scroll_until",
                target="Submit",
                retry=3,
                region=TaskRegion(x=0, y=0, width=100, height=100),
            ),
        ),
    )
    engine = _engine(
        task,
        config=RuntimeConfig(
            confidence_threshold=0.8,
            execution_profile=ExecutionProfile(
                enabled=True,
                action_delay_seconds=(0.2, 0.2),
            ),
        ),
        perception=SequencePerceptionEngine(((), _candidate_tuple("Submit"))),
        actuator=actuator,
        clock=clock,
    )

    report = engine.run(Path("task.yaml"))

    assert report.status == "passed"
    assert report.steps[0].attempts == 2
    assert actuator.calls == 1
    assert round(clock.now, 2) == 0.2


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


def test_execution_engine_blocks_branch_target_with_missing_dependency() -> None:
    task = TaskDefinition(
        name="branch-state",
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=30,
        steps=(
            TaskStep(
                id="branch",
                action="branch_if_visible",
                target="Optional",
                on_failure="submit",
            ),
            TaskStep(
                id="prepare",
                action="press_key",
                text="enter",
                expected_state=ExpectedStateTransition(after="ready"),
            ),
            TaskStep(
                id="submit",
                action="click_text",
                target="Submit",
                depends_on=("prepare",),
                expected_state=ExpectedStateTransition(before="ready"),
            ),
        ),
    )
    engine = _engine(task, perception=SequencePerceptionEngine(((),)))

    report = engine.run(Path("task.yaml"))

    state_failure = next(event for event in report.events if event.phase == "failure")
    assert report.status == "failed"
    assert report.steps[-1].step_id == "submit"
    assert report.steps[-1].metadata["failure_category"] == "task_state"
    assert state_failure.metadata["failure_category"] == "task_state"


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
    verifier: SequenceVerifier | None = None,
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
        verifier=verifier if verifier is not None else PassingStepVerifier(),
        clock=clock or FakeClock(),
    )


def _candidate_tuple(
    label: str,
    *,
    confidence: float = 0.95,
    enabled: bool = True,
    visible: bool = True,
) -> tuple[ElementCandidate, ...]:
    return (
        _candidate(
            f"candidate-{label}",
            label,
            confidence=confidence,
            enabled=enabled,
            visible=visible,
        ),
    )


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
