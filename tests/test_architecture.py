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
    RecoveryRule,
    StaticTaskLoader,
    TaskDefinition,
    TaskStep,
    YamlTaskLoader,
)
from desktop_agent.tracing import MemoryTraceSink


def test_proof_commands_stay_on_real_os_input_boundary() -> None:
    mouse_demo_code = Path("src/desktop_agent/mouse_demo.py").read_text(
        encoding="utf-8"
    )
    proof_code = "\n".join(
        [
            mouse_demo_code,
            Path("src/desktop_agent/cli.py").read_text(encoding="utf-8"),
        ]
    ).lower()
    proof_docs = "\n".join(
        [
            Path("docs/mouse-demo.md").read_text(encoding="utf-8"),
            Path("docs/linkedin-demo.md").read_text(encoding="utf-8"),
            Path("docs/browser-fixture-proof.md").read_text(encoding="utf-8"),
            Path("docs/native-fixture-proof.md").read_text(encoding="utf-8"),
            Path("docs/mixed-fixture-proof.md").read_text(encoding="utf-8"),
            Path("docs/recovery-fixture-proof.md").read_text(encoding="utf-8"),
            Path("docs/windows-proof-evidence-checklist.md").read_text(
                encoding="utf-8"
            ),
        ]
    )

    for forbidden in ("playwright", "selenium", "webdriver", "devtools"):
        assert forbidden not in proof_code
    assert "WindowsInputBackend" in mouse_demo_code
    assert "RealInputController" in mouse_demo_code
    for phrase in (
        "synthetic cursor",
        "does not use Playwright",
        "does not use app APIs",
        "no browser API",
        "no app API",
    ):
        assert phrase in proof_docs


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


class CapturingActuator:
    def __init__(self) -> None:
        self.allowed_windows: tuple[str, ...] | None = None

    def execute(
        self,
        step: TaskStep,
        target: ElementCandidate | None,
        observation: ScreenObservation,
        config: RuntimeConfig,
    ) -> ActionResult:
        _ = step, target, observation
        self.allowed_windows = config.allowed_windows
        return ActionResult(success=True, message="captured")


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
    compile_event = next(
        event for event in report.events if event.phase == "compile_task"
    )
    selection = next(event for event in report.events if event.phase == "select_target")
    snapshot = next(
        event for event in report.events if event.phase == "ui_state_snapshot"
    )
    detection = next(
        event for event in report.events if event.phase == "detect_candidates"
    )
    rankings = detection.metadata["candidate_rankings"]
    assert compile_event.metadata["step_order"] == ["click-submit"]
    assert selection.metadata["step_category"] == "submission"
    assert detection.metadata["step_category"] == "submission"
    assert selection.metadata["candidate_confidence"] == 0.95
    selected_candidate = snapshot.metadata["selected_candidate"]
    assert isinstance(selected_candidate, dict)
    assert selected_candidate["id"] == "candidate-1"
    visible_controls = snapshot.metadata["visible_controls"]
    assert isinstance(visible_controls, list)
    assert visible_controls[0]["confidence"] == 0.95
    assert isinstance(rankings, list)
    first_ranking = rankings[0]
    assert isinstance(first_ranking, dict)
    assert first_ranking["id"] == "candidate-1"
    assert first_ranking["rank"] == 1


def test_existing_yaml_task_runs_through_current_planner_contract(
    tmp_path: Path,
) -> None:
    task_path = tmp_path / "legacy-task.yaml"
    task_path.write_text(
        """name: legacy yaml fixture
allowed_windows:
  - DeskPilot Fixture
timeout_seconds: 30
steps:
  - id: click-submit
    action: click_text
    target: Submit
""",
        encoding="utf-8",
    )
    engine = ExecutionEngine(
        config_loader=StaticConfigLoader(RuntimeConfig(confidence_threshold=0.8)),
        task_loader=YamlTaskLoader(),
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

    report = engine.run(task_path)

    phases = {event.phase for event in report.events}
    compile_event = next(
        event for event in report.events if event.phase == "compile_task"
    )
    assert report.status == "passed"
    assert report.task_name == "legacy yaml fixture"
    assert report.steps[0].action == "click_text"
    assert {
        "load_task",
        "compile_task",
        "observe_screen",
        "detect_candidates",
        "action_safety",
        "desktop_io_plan",
        "execute_action",
    } <= phases
    assert compile_event.metadata["compiled_execution_model"] == "desktop_io_v1"
    assert compile_event.metadata["desktop_io_step_count"] == 1


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
        report.steps[0].message
        == "active window is outside the effective allowed_windows"
    )


def test_execution_engine_passes_effective_allowed_windows_to_actuator() -> None:
    task = TaskDefinition(
        name="window-fixture",
        allowed_windows=("Task Window",),
        timeout_seconds=30,
        steps=(TaskStep(id="click-submit", action="click_text", target="Submit"),),
    )
    actuator = CapturingActuator()
    engine = ExecutionEngine(
        config_loader=StaticConfigLoader(
            RuntimeConfig(
                confidence_threshold=0.8,
                allowed_windows=("Runtime Window",),
            ),
        ),
        task_loader=StaticTaskLoader(task),
        task_validator=BasicTaskValidator(),
        trace_sink=MemoryTraceSink(),
        safety_policy=LocalSafetyPolicy(),
        screen_observer=StaticScreenObserver(
            ScreenObservation(active_window_title="Runtime Window - Browser"),
        ),
        perception_engine=CompositePerceptionEngine((FixturePerceptionEngine(),)),
        target_selector=ConfidenceTargetSelector(),
        actuator=actuator,
    )

    report = engine.run(Path("task.yaml"))

    assert report.status == "passed"
    assert actuator.allowed_windows == ("Task Window", "Runtime Window")


def test_execution_engine_passes_task_allowed_windows_without_runtime_config() -> None:
    task = TaskDefinition(
        name="window-fixture",
        allowed_windows=("Task Window",),
        timeout_seconds=30,
        steps=(TaskStep(id="click-submit", action="click_text", target="Submit"),),
    )
    actuator = CapturingActuator()
    engine = ExecutionEngine(
        config_loader=StaticConfigLoader(RuntimeConfig(confidence_threshold=0.8)),
        task_loader=StaticTaskLoader(task),
        task_validator=BasicTaskValidator(),
        trace_sink=MemoryTraceSink(),
        safety_policy=LocalSafetyPolicy(),
        screen_observer=StaticScreenObserver(
            ScreenObservation(active_window_title="Task Window - Browser"),
        ),
        perception_engine=CompositePerceptionEngine((FixturePerceptionEngine(),)),
        target_selector=ConfidenceTargetSelector(),
        actuator=actuator,
    )

    report = engine.run(Path("task.yaml"))

    assert report.status == "passed"
    assert actuator.allowed_windows == ("Task Window",)


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
                recovery=(
                    RecoveryRule(
                        reason="transient_loading",
                        actions=("wait_for_loading", "abort_with_trace"),
                    ),
                ),
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
    reobserve_event = next(
        event for event in report.events if event.phase == "reobserve_after_failure"
    )
    recover_candidates_event = next(
        event for event in report.events if event.phase == "recover_candidates"
    )
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
    assert timing_events[1].metadata["retry_backoff_strategy"] == (
        "bounded_exponential"
    )
    assert timing_events[1].metadata["retry_index"] == 1
    assert timing_events[1].metadata["retry_budget"] == 1
    assert reobserve_event.metadata["attempt"] == 1
    assert reobserve_event.metadata["next_attempt"] == 2
    assert recover_candidates_event.metadata["failed_attempt"] == 1
    assert recover_candidates_event.metadata["candidate_count"] == 1
    assert recover_candidates_event.metadata["recovery_for_step_id"] == "click-submit"
    assert recover_event.metadata["retry_reason"] == "transient failure"
    assert recover_event.metadata["failed_attempt"] == 1
    assert recover_event.metadata["failure_observation_phase"] == (
        "reobserve_after_failure"
    )
    assert recover_event.metadata["recovery_candidate_count"] == 1
    assert recover_event.metadata["recovery_reason"] == "transient_loading"
    assert recover_event.metadata["recovery_policy"] == "wait_for_transient_loading"
    assert recover_event.metadata["recovery_backoff_strategy"] == (
        "bounded_exponential"
    )
    assert recover_event.metadata["retry_backoff_strategy"] == "bounded_exponential"
    assert recover_event.metadata["retry_limit_respected"] is True
    assert recover_event.metadata["recovery_chosen_action"] == "wait_for_loading"
    assert recover_event.metadata["recovery_actions"] == [
        "wait_for_loading",
        "abort_with_trace",
    ]
    assert recover_event.metadata["recovery_actions_constrained"] is True
    assert recover_event.metadata["reobserve_before_retry"] is True
    assert recover_event.metadata["recovery_path"] == [
        {
            "stage": "classify_failure",
            "reason": "transient_loading",
            "attempt": 1,
        },
        {
            "stage": "fresh_failure_observation",
            "phase": "reobserve_after_failure",
            "attempt": 1,
        },
        {"stage": "recovery_action", "action": "wait_for_loading"},
        {
            "stage": "fresh_retry_observation",
            "phase": "observe_screen",
            "attempt": 2,
        },
        {"stage": "retry_attempt", "attempt": 2},
    ]
