import json
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
from desktop_agent.screen import Bounds, ScreenObservation
from desktop_agent.task_dsl import (
    BasicTaskValidator,
    StaticTaskLoader,
    TaskDefinition,
    TaskStep,
    VerificationDefinition,
)
from desktop_agent.tracing import FileTraceSink


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
                verify=VerificationDefinition(type="visible_text", text="Success"),
            ),
        ),
    )
    trace_sink = FileTraceSink()
    engine = ExecutionEngine(
        config_loader=StaticConfigLoader(
            RuntimeConfig(trace_root=tmp_path / "traces", confidence_threshold=0.8),
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
    assert (report.trace_dir / "task.json").exists()
    assert (report.trace_dir / "action-log.jsonl").exists()
    assert (report.trace_dir / "final-report.json").exists()
    assert (report.trace_dir / "final-report.md").exists()
    assert (report.trace_dir / "screenshots" / "screen-1.png").exists()
    assert (report.trace_dir / "screenshots" / "screen-2.png").exists()

    final_report = json.loads((report.trace_dir / "final-report.json").read_text())
    config_payload = json.loads((report.trace_dir / "config.json").read_text())
    task_payload = json.loads((report.trace_dir / "task.json").read_text())
    action_log = (report.trace_dir / "action-log.jsonl").read_text().splitlines()
    assert final_report["status"] == "passed"
    assert final_report["abort_reason"] is None
    assert final_report["steps"][0]["candidate_id"] == "candidate-Submit"
    assert final_report["steps"][0]["metadata"]["step_category"] == "submission"
    assert config_payload["execution_profile"]["persona"] == "normal"
    assert task_payload["steps"][0]["category"] == "submission"
    assert task_payload["steps"][0]["resolved_category"] == "submission"
    assert any("candidate_rankings" in line for line in action_log)
    assert any('"step_category": "submission"' in line for line in action_log)
    assert any("step_timeout_budget" in line for line in action_log)
    assert any("observe_after_action" in line for line in action_log)
