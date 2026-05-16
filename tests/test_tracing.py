import json
from pathlib import Path

from desktop_agent.actuation import DryRunActuator
from desktop_agent.config import ExecutionProfile, RuntimeConfig, StaticConfigLoader
from desktop_agent.perception import (
    CompositePerceptionEngine,
    ConfidenceTargetSelector,
    ElementCandidate,
    PerceptionEngine,
)
from desktop_agent.planner import ExecutionEngine
from desktop_agent.safety import LocalSafetyPolicy
from desktop_agent.screen import Bounds, ScreenObservation
from desktop_agent.task_dsl import (
    BasicTaskValidator,
    StaticTaskLoader,
    TaskDefinition,
    TaskStep,
    VerificationDefinition,
)
from desktop_agent.tracing import (
    TRACE_SCHEMA_V2,
    FileTraceSink,
    StepReport,
    TraceEvent,
)


class TraceScreenObserver:
    def __init__(self) -> None:
        self.calls = 0

    def observe(self, config: RuntimeConfig) -> ScreenObservation:
        self.calls += 1
        screenshot_path = config.trace_root / "screenshots" / f"screen-{self.calls}.png"
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        screenshot_path.write_bytes(b"fixture")
        return ScreenObservation(
            screenshot_path=screenshot_path,
            size=(640, 480),
            active_window_title="DeskPilot Fixture",
        )


class TargetEchoPerceptionEngine(PerceptionEngine):
    def detect(
        self,
        step: TaskStep,
        observation: ScreenObservation,
        config: RuntimeConfig,
    ) -> tuple[ElementCandidate, ...]:
        _ = observation, config
        label = step.target or "Submit"
        return (
            ElementCandidate(
                id=f"candidate-{label}",
                source="uia",
                label=label,
                bounds=Bounds(x=10, y=20, width=100, height=30),
                confidence=0.95,
            ),
        )


def test_file_trace_sink_writes_run_artifacts(tmp_path: Path) -> None:
    task = TaskDefinition(
        name="trace fixture",
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=30,
        steps=(
            TaskStep(
                id="click-submit",
                action="click_text",
                target="Submit",
                category="submission",
                entropy_budget=1.0,
                verify=VerificationDefinition(type="visible_text", text="Success"),
            ),
        ),
        entropy_budget=2.0,
    )
    trace_sink = FileTraceSink()
    engine = ExecutionEngine(
        config_loader=StaticConfigLoader(
            RuntimeConfig(
                trace_root=tmp_path / "traces",
                confidence_threshold=0.8,
                policy_preset="strict_qa",
                require_operator_approval=True,
                confirmed_steps=("click-submit",),
                execution_profile=ExecutionProfile(
                    enabled=True,
                    keyboard_interval_seconds=(0.01, 0.03),
                    scroll_interval_seconds=(0.02, 0.04),
                ),
            ),
        ),
        task_loader=StaticTaskLoader(task),
        task_validator=BasicTaskValidator(),
        trace_sink=trace_sink,
        safety_policy=LocalSafetyPolicy(),
        screen_observer=TraceScreenObserver(),
        perception_engine=CompositePerceptionEngine((TargetEchoPerceptionEngine(),)),
        target_selector=ConfidenceTargetSelector(),
        actuator=DryRunActuator(),
    )

    report = engine.run(Path("task.yaml"))

    assert report.status == "passed"
    assert report.trace_dir is not None
    assert report.trace_dir.exists()
    assert (report.trace_dir / "config.json").exists()
    assert (report.trace_dir / "trace-schema.json").exists()
    assert (report.trace_dir / "task.json").exists()
    assert (report.trace_dir / "action-log.jsonl").exists()
    assert (report.trace_dir / "safety-audit.json").exists()
    assert (report.trace_dir / "safety-audit.md").exists()
    assert (report.trace_dir / "final-report.json").exists()
    assert (report.trace_dir / "final-report.md").exists()
    assert (report.trace_dir / "screenshots" / "screen-1.png").exists()
    assert (report.trace_dir / "screenshots" / "screen-2.png").exists()

    final_report = json.loads((report.trace_dir / "final-report.json").read_text())
    config_payload = json.loads((report.trace_dir / "config.json").read_text())
    schema_payload = json.loads((report.trace_dir / "trace-schema.json").read_text())
    task_payload = json.loads((report.trace_dir / "task.json").read_text())
    audit_payload = json.loads((report.trace_dir / "safety-audit.json").read_text())
    action_log = (report.trace_dir / "action-log.jsonl").read_text().splitlines()
    assert final_report["status"] == "passed"
    assert final_report["trace_schema_version"] == TRACE_SCHEMA_V2.version
    assert final_report["trace_schema"]["sections"]["observation"]
    assert schema_payload["version"] == TRACE_SCHEMA_V2.version
    assert set(schema_payload["sections"]) == {
        "observation",
        "target_reasoning",
        "input",
        "verification",
        "state_delta",
    }
    assert final_report["abort_reason"] is None
    assert final_report["steps"][0]["candidate_id"] == "candidate-Submit"
    assert final_report["steps"][0]["metadata"]["step_category"] == "submission"
    assert final_report["steps"][0]["metadata"]["step_entropy_budget"] == 1.0
    assert config_payload["policy_preset"] == "strict_qa"
    assert config_payload["require_operator_approval"] is True
    assert config_payload["execution_profile"]["persona"] == "normal"
    assert audit_payload["policy_preset"] == "strict_qa"
    assert audit_payload["sensitive_steps"][0]["step_id"] == "click-submit"
    assert config_payload["execution_profile"]["keyboard_interval_seconds"] == [
        0.01,
        0.03,
    ]
    assert config_payload["execution_profile"]["scroll_interval_seconds"] == [
        0.02,
        0.04,
    ]
    assert task_payload["entropy_budget"] == 2.0
    assert task_payload["steps"][0]["category"] == "submission"
    assert task_payload["steps"][0]["entropy_budget"] == 1.0
    assert task_payload["steps"][0]["resolved_category"] == "submission"
    assert any("candidate_rankings" in line for line in action_log)
    assert all('"trace_schema_version": "2"' in line for line in action_log)
    assert any('"policy_preset": "strict_qa"' in line for line in action_log)
    assert any('"step_category": "submission"' in line for line in action_log)
    assert any("entropy_budget" in line for line in action_log)
    assert any("step_timeout_budget" in line for line in action_log)
    assert any("observe_after_action" in line for line in action_log)


def test_file_trace_sink_includes_recovery_decision_metadata_in_reports(
    tmp_path: Path,
) -> None:
    task = TaskDefinition(
        name="recovery report fixture",
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=30,
        steps=(TaskStep(id="click-submit", action="click_text", target="Submit"),),
    )
    trace_sink = FileTraceSink()
    trace_sink.prepare_run(
        task,
        RuntimeConfig(trace_root=tmp_path / "traces"),
    )
    trace_sink.record_event(
        TraceEvent(
            phase="recover",
            message="retrying step",
            metadata={
                "recovery_policy": "wait_for_transient_loading",
                "recovery_reason": "transient_loading",
                "recovery_chosen_action": "wait_for_loading",
                "recovery_path_summary": (
                    "classify transient_loading -> wait_for_loading -> "
                    "observe_screen attempt 2 -> retry attempt 2"
                ),
                "retry_limit_respected": True,
            },
        )
    )

    report = trace_sink.write_final_report("failed")

    assert report.trace_dir is not None
    final_report = (report.trace_dir / "final-report.md").read_text(encoding="utf-8")
    final_report_json = json.loads(
        (report.trace_dir / "final-report.json").read_text(encoding="utf-8")
    )
    recover_event = final_report_json["events"][0]
    assert "classify transient_loading" in final_report
    assert recover_event["metadata"]["recovery_policy"] == (
        "wait_for_transient_loading"
    )
    assert recover_event["metadata"]["recovery_reason"] == "transient_loading"
    assert recover_event["metadata"]["recovery_chosen_action"] == "wait_for_loading"
    assert recover_event["metadata"]["retry_limit_respected"] is True


def test_file_trace_sink_includes_failure_category_in_markdown(
    tmp_path: Path,
) -> None:
    task = TaskDefinition(
        name="failure category fixture",
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=30,
        steps=(TaskStep(id="click-submit", action="click_text", target="Submit"),),
    )
    trace_sink = FileTraceSink()
    trace_sink.prepare_run(
        task,
        RuntimeConfig(trace_root=tmp_path / "traces"),
    )
    trace_sink.record_step(
        StepReport(
            step_id="click-submit",
            action="click_text",
            status="failed",
            attempts=1,
            message="click failed",
            metadata={"failure_category": "actuation_failure"},
        )
    )

    report = trace_sink.write_final_report("failed")

    assert report.trace_dir is not None
    final_report = (report.trace_dir / "final-report.md").read_text(encoding="utf-8")
    assert "[actuation_failure]" in final_report


def test_file_trace_sink_renders_decision_details_in_markdown(
    tmp_path: Path,
) -> None:
    task = TaskDefinition(
        name="decision rendering fixture",
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=30,
        steps=(TaskStep(id="click-submit", action="click_text", target="Submit"),),
    )
    trace_sink = FileTraceSink()
    trace_sink.prepare_run(
        task,
        RuntimeConfig(trace_root=tmp_path / "traces"),
    )
    trace_sink.record_step(
        StepReport(
            step_id="click-submit",
            action="click_text",
            status="failed",
            attempts=1,
            message="active window rejected",
            metadata={"failure_category": "safety_stop"},
        )
    )
    trace_sink.record_event(
        TraceEvent(
            phase="execution_timing",
            message="action timing decided",
            metadata={"delay_seconds": 0.2},
        )
    )
    trace_sink.record_event(
        TraceEvent(
            phase="select_target",
            message="no target selected",
            metadata={"selection_blocked": "confidence_or_ambiguity_gate"},
        )
    )
    trace_sink.record_event(
        TraceEvent(
            phase="recover",
            message="retrying step",
            metadata={"recovery_path_summary": "classify missed_target -> retry"},
        )
    )
    trace_sink.record_event(
        TraceEvent(
            phase="execute_action",
            message="typed text",
            metadata={
                "keyboard_cadence_applied": True,
                "keyboard_interval_count": 2,
            },
        )
    )
    trace_sink.record_event(
        TraceEvent(
            phase="execute_action",
            message="scrolled",
            metadata={
                "scroll_cadence_applied": True,
                "scroll_step_count": 3,
            },
        )
    )
    trace_sink.record_event(
        TraceEvent(
            phase="execute_action",
            message="emergency stop requested before desktop input",
            metadata={
                "input_blocked": True,
                "actuation_guard": "emergency_stop",
            },
        )
    )

    report = trace_sink.write_final_report("failed")

    assert report.trace_dir is not None
    final_report = (report.trace_dir / "final-report.md").read_text(encoding="utf-8")
    assert "[safety_stop]" in final_report
    assert "delay 0.200s" in final_report
    assert "keyboard cadence 2 interval(s)" in final_report
    assert "scroll cadence 3 step(s)" in final_report
    assert "input blocked by emergency_stop" in final_report
    assert "confidence_or_ambiguity_gate" in final_report
    assert "classify missed_target -> retry" in final_report
