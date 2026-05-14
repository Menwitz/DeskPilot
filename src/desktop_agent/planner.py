"""Deterministic task execution pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from desktop_agent.actuation import ActionResult, Actuator
from desktop_agent.config import ConfigLoader, RuntimeConfig
from desktop_agent.perception import (
    ElementCandidate,
    PerceptionEngine,
    TargetSelector,
    candidate_ranking_metadata,
)
from desktop_agent.safety import SafetyPolicy
from desktop_agent.screen import ScreenObservation, ScreenObserver
from desktop_agent.task_dsl import TaskDefinition, TaskLoader, TaskStep, TaskValidator
from desktop_agent.tracing import RunReport, StepReport, TraceEvent, TraceSink


@dataclass(frozen=True)
class VerificationResult:
    """Result of a post-action verification check."""

    passed: bool
    message: str


class StepVerifier(Protocol):
    """Interface for step verification adapters."""

    def verify(
        self,
        step: TaskStep,
        observation: ScreenObservation,
        target: ElementCandidate | None,
        action_result: ActionResult,
        config: RuntimeConfig,
    ) -> VerificationResult: ...


class PassingStepVerifier(StepVerifier):
    """Verifier used until task-specific verification types are implemented."""

    def verify(
        self,
        step: TaskStep,
        observation: ScreenObservation,
        target: ElementCandidate | None,
        action_result: ActionResult,
        config: RuntimeConfig,
    ) -> VerificationResult:
        _ = step, observation, target, config
        return VerificationResult(
            passed=action_result.success,
            message=action_result.message,
        )


@dataclass
class ExecutionEngine:
    """Coordinates config, task validation, perception, safety, and actuation."""

    config_loader: ConfigLoader
    task_loader: TaskLoader
    task_validator: TaskValidator
    trace_sink: TraceSink
    safety_policy: SafetyPolicy
    screen_observer: ScreenObserver
    perception_engine: PerceptionEngine
    target_selector: TargetSelector
    actuator: Actuator
    verifier: StepVerifier = field(default_factory=PassingStepVerifier)

    def run(self, task_path: Path, config_path: Path | None = None) -> RunReport:
        config = self.config_loader.load(config_path)
        task = self.task_loader.load(task_path)
        self.trace_sink.prepare_run(task, config)

        try:
            self._record("load_config", "configuration loaded")
            self._record("load_task", "task loaded", {"task": task.name})
            self.task_validator.validate(task, config)
            self._record("validate_task", "task validated")
            self._record("prepare_trace", "trace sink prepared")

            precondition = self.safety_policy.check_preconditions(task, config)
            if not precondition.allowed:
                self._record("safety", precondition.reason)
                return self.trace_sink.write_final_report(
                    "aborted",
                    precondition.reason,
                )
            self._record("safety", "preconditions passed")

            for step_index, step in enumerate(task.steps, start=1):
                if step_index > config.max_steps:
                    reason = "task exceeded max_steps"
                    self._record("abort", reason, {"max_steps": config.max_steps})
                    return self.trace_sink.write_final_report("aborted", reason)

                step_report = self._execute_step(task, step, config)
                self.trace_sink.record_step(step_report)
                if step_report.status != "passed":
                    return self.trace_sink.write_final_report(
                        "failed",
                        step_report.message,
                    )

            return self.trace_sink.write_final_report("passed")
        except Exception as exc:
            reason = str(exc)
            self._record("failure", reason, {"error_type": type(exc).__name__})
            return self.trace_sink.write_final_report("failed", reason)

    def _execute_step(
        self,
        task: TaskDefinition,
        step: TaskStep,
        config: RuntimeConfig,
    ) -> StepReport:
        retry_budget = step.retry
        if retry_budget is None:
            retry_budget = config.max_retries_per_step

        # Retry counts are budgets, so a retry value of 2 means 3 total attempts.
        total_attempts = retry_budget + 1
        last_message = "step was not attempted"
        last_candidate_id: str | None = None

        for attempt in range(1, total_attempts + 1):
            observation = self.screen_observer.observe(config)
            self._record(
                "observe_screen",
                "screen observed",
                {"step_id": step.id, "attempt": attempt},
            )

            candidates = self.perception_engine.detect(step, observation, config)
            detection_metadata = {
                "step_id": step.id,
                "candidate_count": len(candidates),
            }
            detection_metadata.update(
                candidate_ranking_metadata(step, candidates, config),
            )
            self._record(
                "detect_candidates",
                "candidate search completed",
                detection_metadata,
            )

            target = self.target_selector.select(step, candidates, config)
            last_candidate_id = target.id if target else None
            self._record(
                "select_target",
                "target selected" if target else "no target selected",
                {"step_id": step.id, "candidate_id": last_candidate_id},
            )

            safety = self.safety_policy.check_before_action(task, step, config)
            if not safety.allowed:
                return StepReport(
                    step_id=step.id,
                    action=step.action,
                    status="failed",
                    attempts=attempt,
                    message=safety.reason,
                    candidate_id=last_candidate_id,
                )

            action_result = self.actuator.execute(step, target, observation, config)
            action_metadata = {
                "step_id": step.id,
                "success": action_result.success,
            }
            action_metadata.update(action_result.metadata)
            self._record(
                "execute_action",
                action_result.message,
                action_metadata,
            )

            verification = self.verifier.verify(
                step,
                observation,
                target,
                action_result,
                config,
            )
            self._record(
                "verify_result",
                verification.message,
                {"step_id": step.id, "passed": verification.passed},
            )

            if action_result.success and verification.passed:
                return StepReport(
                    step_id=step.id,
                    action=step.action,
                    status="passed",
                    attempts=attempt,
                    message=verification.message,
                    candidate_id=last_candidate_id,
                )

            last_message = verification.message
            if attempt < total_attempts:
                self._record(
                    "recover",
                    "retrying step",
                    {"step_id": step.id, "next_attempt": attempt + 1},
                )

        return StepReport(
            step_id=step.id,
            action=step.action,
            status="failed",
            attempts=total_attempts,
            message=last_message,
            candidate_id=last_candidate_id,
        )

    def _record(
        self,
        phase: str,
        message: str,
        metadata: dict[str, object] | None = None,
    ) -> None:
        self.trace_sink.record_event(
            TraceEvent(phase=phase, message=message, metadata=metadata or {}),
        )
