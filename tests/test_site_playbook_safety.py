from pathlib import Path

import pytest

from desktop_agent.actuation import DryRunActuator
from desktop_agent.config import RuntimeConfig, StaticConfigLoader
from desktop_agent.perception import (
    CompositePerceptionEngine,
    ConfidenceTargetSelector,
    DryRunPerceptionEngine,
    ElementCandidate,
    PerceptionEngine,
)
from desktop_agent.planner import ExecutionEngine
from desktop_agent.safety import LocalSafetyPolicy, StaticEmergencyStopMonitor
from desktop_agent.screen import Bounds, ScreenObservation, StaticScreenObserver
from desktop_agent.site_playbooks import SiteTaskCompiler, load_site_playbook
from desktop_agent.task_dsl import (
    BasicTaskValidator,
    StaticTaskLoader,
    TaskDefinition,
    TaskStep,
)
from desktop_agent.tracing import MemoryTraceSink


@pytest.mark.parametrize(
    "category",
    ["login", "publish", "message", "delete", "account_settings"],
)
def test_sensitive_site_steps_are_blocked_without_confirmation(
    tmp_path: Path,
    category: str,
) -> None:
    task = _compiled_sensitive_task(tmp_path, category, "candidate_count:>1")
    step = task.steps[-1]

    decision = LocalSafetyPolicy().check_before_action(
        task,
        step,
        RuntimeConfig(),
        ScreenObservation(active_window_title="Sensitive"),
    )

    assert decision.allowed is False
    assert "requires explicit confirmation" in decision.reason


def test_captcha_state_aborts_with_no_bypass_message(tmp_path: Path) -> None:
    task = _compiled_sensitive_task(tmp_path, "publish", "visible_text:challenge")

    report = _engine(
        task,
        perception_engine=BlockedTextPerceptionEngine("challenge"),
    ).run(Path("site-sensitive-publish.yaml"))

    assert report.status == "failed"
    assert "blocked state detected" in (report.abort_reason or "")
    assert "CAPTCHA challenges are not automated" in (report.abort_reason or "")


def test_active_window_mismatch_aborts_before_site_action(tmp_path: Path) -> None:
    task = _compiled_readonly_task(tmp_path)

    report = _engine(
        task,
        observation=ScreenObservation(active_window_title="Other Window"),
    ).run(Path("site-readonly.yaml"))

    assert report.status == "failed"
    assert report.steps[0].metadata["failure_category"] == "safety_stop"
    assert "allowed_windows" in (report.abort_reason or "")


def test_emergency_stop_behavior_remains_unchanged_for_site_tasks(
    tmp_path: Path,
) -> None:
    task = _compiled_readonly_task(tmp_path)

    report = _engine(task, emergency_stop=True).run(Path("site-readonly.yaml"))

    assert report.status == "emergency_stopped"
    assert report.abort_reason == "emergency stop requested"


def _engine(
    task: TaskDefinition,
    *,
    observation: ScreenObservation | None = None,
    emergency_stop: bool = False,
    perception_engine: PerceptionEngine | None = None,
) -> ExecutionEngine:
    return ExecutionEngine(
        config_loader=StaticConfigLoader(RuntimeConfig()),
        task_loader=StaticTaskLoader(task),
        task_validator=BasicTaskValidator(),
        trace_sink=MemoryTraceSink(),
        safety_policy=LocalSafetyPolicy(),
        screen_observer=StaticScreenObserver(observation or ScreenObservation()),
        perception_engine=CompositePerceptionEngine(
            (perception_engine or DryRunPerceptionEngine(),),
        ),
        target_selector=ConfidenceTargetSelector(),
        actuator=DryRunActuator(),
        emergency_stop_monitor=StaticEmergencyStopMonitor(triggered=emergency_stop),
    )


class BlockedTextPerceptionEngine:
    def __init__(self, text: str) -> None:
        self._text = text

    def detect(
        self,
        step: TaskStep,
        observation: ScreenObservation,
        config: RuntimeConfig,
    ) -> tuple[ElementCandidate, ...]:
        _ = step, observation, config
        return (
            ElementCandidate(
                id="blocked-state-text",
                source="ocr",
                label=self._text,
                bounds=Bounds(x=0, y=0, width=10, height=10),
                confidence=1.0,
            ),
        )


def _compiled_sensitive_task(
    tmp_path: Path,
    category: str,
    detector: str,
) -> TaskDefinition:
    playbook_path = tmp_path / "sensitive-site.yaml"
    playbook_path.write_text(_sensitive_playbook(category, detector), encoding="utf-8")
    playbook = load_site_playbook(playbook_path)
    return SiteTaskCompiler().compile(playbook, "sensitive-action")


def _compiled_readonly_task(tmp_path: Path) -> TaskDefinition:
    playbook_path = tmp_path / "readonly-site.yaml"
    playbook_path.write_text(_readonly_playbook(), encoding="utf-8")
    playbook = load_site_playbook(playbook_path)
    return SiteTaskCompiler().compile(playbook, "open-search")


def _sensitive_playbook(category: str, detector: str) -> str:
    return f"""site_id: sensitive-site
version: "1"
domains:
  - host: sensitive.example
allowed_window_titles:
  - Sensitive
landmarks:
  - id: action
    action: click_text
    target: Continue
flows:
  - id: sensitive-action
    timeout_seconds: 30
    steps:
      - id: sensitive-action
        action: click_text
        landmark: action
        timeout_seconds: 0.1
        requires_confirmation: true
        sensitive_category: {category}
        checkpoint:
          type: visible_text
          text: Continue
blocked_states:
  - id: captcha
    detector: "{detector}"
    reason: CAPTCHA challenges are not automated.
"""


def _readonly_playbook() -> str:
    return """site_id: readonly-site
version: "1"
domains:
  - host: readonly.example
allowed_window_titles:
  - Readonly
landmarks:
  - id: search
    action: click_text
    target: Search
flows:
  - id: open-search
    timeout_seconds: 30
    steps:
      - id: open-search
        action: click_text
        landmark: search
blocked_states:
  - id: ambiguous-target
    detector: "candidate_count:>1"
    reason: Choose a narrower target before continuing.
"""
