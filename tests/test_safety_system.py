from pathlib import Path

import pytest

from desktop_agent.actuation import DryRunActuator
from desktop_agent.config import RuntimeConfig, StaticConfigLoader
from desktop_agent.perception import (
    CompositePerceptionEngine,
    ConfidenceTargetSelector,
    ElementCandidate,
    PerceptionEngine,
)
from desktop_agent.planner import ExecutionEngine
from desktop_agent.safety import (
    LocalSafetyPolicy,
    StaticEmergencyStopMonitor,
    _hotkey_virtual_keys,
)
from desktop_agent.screen import Bounds, ScreenObservation, StaticScreenObserver
from desktop_agent.task_dsl import (
    BasicTaskValidator,
    StaticTaskLoader,
    TaskDefinition,
    TaskStep,
    VerificationDefinition,
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


def test_execution_engine_stops_when_emergency_monitor_is_triggered() -> None:
    task = TaskDefinition(
        name="emergency",
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=30,
        steps=(TaskStep(id="click-submit", action="click_text", target="Submit"),),
    )
    engine = _engine(
        task,
        emergency_stop_monitor=StaticEmergencyStopMonitor(triggered=True),
    )

    report = engine.run(Path("task.yaml"))

    assert report.status == "emergency_stopped"
    assert report.abort_reason == "emergency stop requested"
    assert report.steps == ()


def test_safety_policy_blocks_unconfirmed_sensitive_steps() -> None:
    task = TaskDefinition(
        name="confirmation",
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
    engine = _engine(task)

    report = engine.run(Path("task.yaml"))

    assert report.status == "failed"
    assert report.steps[0].message == (
        "step submit-payment requires explicit confirmation"
    )


def test_safety_policy_allows_confirmed_sensitive_steps() -> None:
    task = TaskDefinition(
        name="confirmation",
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
    engine = _engine(
        task,
        config=RuntimeConfig(
            confidence_threshold=0.8,
            confirmed_steps=("submit-payment",),
        ),
    )

    report = engine.run(Path("task.yaml"))

    assert report.status == "passed"


def test_strict_qa_policy_requires_confirmation_for_submission_steps() -> None:
    task = TaskDefinition(
        name="strict qa",
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=30,
        steps=(
            TaskStep(
                id="submit-payment",
                action="click_text",
                target="Submit",
                category="submission",
                checkpoint=VerificationDefinition(
                    type="visible_text",
                    text="Submit",
                ),
            ),
        ),
    )
    engine = _engine(
        task,
        config=RuntimeConfig(confidence_threshold=0.8, policy_preset="strict_qa"),
    )

    report = engine.run(Path("task.yaml"))

    assert report.status == "failed"
    assert report.steps[0].message == (
        "step submit-payment requires confirmation under strict_qa policy"
    )


def test_operator_approval_gate_blocks_unapproved_submission_steps() -> None:
    task = TaskDefinition(
        name="operator approval",
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=30,
        steps=(
            TaskStep(
                id="submit-payment",
                action="click_text",
                target="Submit",
                category="submission",
                checkpoint=VerificationDefinition(
                    type="visible_text",
                    text="Submit",
                ),
            ),
        ),
    )
    engine = _engine(
        task,
        config=RuntimeConfig(
            confidence_threshold=0.8,
            require_operator_approval=True,
        ),
    )

    report = engine.run(Path("task.yaml"))

    assert report.status == "failed"
    assert report.steps[0].message == "step submit-payment requires operator approval"


def test_operator_approval_gate_allows_approved_submission_steps() -> None:
    task = TaskDefinition(
        name="operator approval",
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=30,
        steps=(
            TaskStep(
                id="submit-payment",
                action="click_text",
                target="Submit",
                category="submission",
                checkpoint=VerificationDefinition(
                    type="visible_text",
                    text="Submit",
                ),
            ),
        ),
    )
    engine = _engine(
        task,
        config=RuntimeConfig(
            confidence_threshold=0.8,
            require_operator_approval=True,
            confirmed_steps=("submit-payment",),
        ),
    )

    report = engine.run(Path("task.yaml"))

    assert report.status == "passed"


def test_external_mutation_requires_checkpoint_after_approval() -> None:
    task = TaskDefinition(
        name="operator approval",
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=30,
        steps=(
            TaskStep(
                id="submit-payment",
                action="click_text",
                target="Submit",
                requires_confirmation=True,
                metadata={"site_sensitive_category": "publish"},
            ),
        ),
    )
    engine = _engine(
        task,
        config=RuntimeConfig(
            confidence_threshold=0.8,
            require_operator_approval=True,
            confirmed_steps=("submit-payment",),
        ),
    )

    report = engine.run(Path("task.yaml"))

    assert report.status == "failed"
    assert report.steps[0].message == (
        "step submit-payment requires checkpoint before external mutation"
    )


def test_strict_qa_policy_allows_confirmed_submission_steps() -> None:
    task = TaskDefinition(
        name="strict qa",
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=30,
        steps=(
            TaskStep(
                id="submit-payment",
                action="click_text",
                target="Submit",
                category="submission",
                checkpoint=VerificationDefinition(
                    type="visible_text",
                    text="Submit",
                ),
            ),
        ),
    )
    engine = _engine(
        task,
        config=RuntimeConfig(
            confidence_threshold=0.8,
            policy_preset="strict_qa",
            confirmed_steps=("submit-payment",),
        ),
    )

    report = engine.run(Path("task.yaml"))

    assert report.status == "passed"


def test_exploratory_policy_blocks_submission_steps() -> None:
    task = TaskDefinition(
        name="exploratory",
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=30,
        steps=(
            TaskStep(
                id="submit-payment",
                action="click_text",
                target="Submit",
                category="submission",
                checkpoint=VerificationDefinition(
                    type="visible_text",
                    text="Submit",
                ),
            ),
        ),
    )
    engine = _engine(
        task,
        config=RuntimeConfig(
            confidence_threshold=0.8,
            policy_preset="exploratory_testing",
            confirmed_steps=("submit-payment",),
        ),
    )

    report = engine.run(Path("task.yaml"))

    assert report.status == "failed"
    assert report.steps[0].message == (
        "step submit-payment is blocked by exploratory_testing policy"
    )


def test_hotkey_parser_rejects_unsupported_keys() -> None:
    with pytest.raises(ValueError, match="unsupported emergency stop key"):
        _hotkey_virtual_keys("ctrl+nope")


def _engine(
    task: TaskDefinition,
    *,
    config: RuntimeConfig | None = None,
    emergency_stop_monitor: StaticEmergencyStopMonitor | None = None,
) -> ExecutionEngine:
    return ExecutionEngine(
        config_loader=StaticConfigLoader(
            config or RuntimeConfig(confidence_threshold=0.8)
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
        emergency_stop_monitor=emergency_stop_monitor
        or StaticEmergencyStopMonitor(triggered=False),
    )
