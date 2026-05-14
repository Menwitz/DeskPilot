"""Deterministic task execution pipeline."""

from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Protocol

from desktop_agent.actuation import ActionResult, Actuator
from desktop_agent.config import ConfigLoader, RuntimeConfig
from desktop_agent.entropy import (
    entropy_capacity_metadata,
    validate_entropy_budget_constraints,
)
from desktop_agent.perception import (
    ElementCandidate,
    PerceptionEngine,
    TargetSelector,
    candidate_ranking_metadata,
)
from desktop_agent.safety import (
    EmergencyStopMonitor,
    NoopEmergencyStopMonitor,
    SafetyPolicy,
)
from desktop_agent.screen import ScreenObservation, ScreenObserver
from desktop_agent.task_dsl import (
    TaskDefinition,
    TaskLoader,
    TaskStep,
    TaskValidator,
    step_category,
)
from desktop_agent.timing import (
    ExecutionTimingController,
    build_action_timing_context,
    estimate_step_timing_budget,
)
from desktop_agent.tracing import (
    RunReport,
    RunStatus,
    StepReport,
    TraceEvent,
    TraceSink,
)

TARGETED_ACTIONS: frozenset[str] = frozenset(
    {
        "click_text",
        "click_image",
        "click_uia",
        "scroll_until",
        "wait_for",
        "assert_visible",
        "drag",
    },
)
POLL_INTERVAL_SECONDS = 0.1


@dataclass(frozen=True)
class VerificationResult:
    """Result of a post-action verification check."""

    passed: bool
    message: str


@dataclass(frozen=True)
class StepExecutionOutcome:
    """Internal result that can redirect the planner to another step."""

    report: StepReport
    next_step_id: str | None = None
    abort_reason: str | None = None
    stop_status: RunStatus | None = None


class Clock(Protocol):
    """Time boundary used by tests to avoid real timeout delays."""

    def monotonic(self) -> float: ...

    def sleep(self, seconds: float) -> None: ...


class MonotonicClock(Clock):
    """Production clock backed by Python's monotonic timer."""

    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


class StepVerifier(Protocol):
    """Interface for step verification adapters."""

    def verify(
        self,
        step: TaskStep,
        observation: ScreenObservation,
        target: ElementCandidate | None,
        action_result: ActionResult,
        config: RuntimeConfig,
        candidates: tuple[ElementCandidate, ...] = (),
    ) -> VerificationResult: ...


class PassingStepVerifier(StepVerifier):
    """Verifier for configured visibility, image, focus, and window checks."""

    def verify(
        self,
        step: TaskStep,
        observation: ScreenObservation,
        target: ElementCandidate | None,
        action_result: ActionResult,
        config: RuntimeConfig,
        candidates: tuple[ElementCandidate, ...] = (),
    ) -> VerificationResult:
        _ = config
        if not action_result.success:
            return VerificationResult(False, action_result.message)

        if step.verify is None:
            if step.action in {"wait_for", "assert_visible", "branch_if_visible"}:
                return _verify_candidate_presence(step, candidates)
            return VerificationResult(True, action_result.message)

        verify = step.verify
        if verify.type == "visible_text":
            return _verify_visible_text(verify.text, candidates)
        if verify.type == "not_visible_text":
            visible_matches = _matching_candidates(verify.text, candidates)
            return VerificationResult(
                not visible_matches,
                "text is not visible" if not visible_matches else "text is visible",
            )
        if verify.type == "visible_image":
            image_visible = any(candidate.source == "image" for candidate in candidates)
            return VerificationResult(
                image_visible,
                "image is visible" if image_visible else "image is not visible",
            )
        if verify.type == "focused":
            focused = _candidate_is_focused(target) or any(
                _candidate_is_focused(candidate) for candidate in candidates
            )
            return VerificationResult(
                focused,
                "target is focused" if focused else "target is not focused",
            )
        if verify.type == "window_title_contains":
            title = observation.active_window_title or ""
            expected = verify.text or ""
            passed = expected.casefold() in title.casefold()
            return VerificationResult(
                passed,
                "window title matched" if passed else "window title did not match",
            )
        if verify.type == "uia_element_exists":
            exists = any(
                candidate.source == "uia"
                for candidate in _matching_candidates(
                    verify.text or step.target,
                    candidates,
                )
            )
            return VerificationResult(
                exists,
                "uia element exists" if exists else "uia element does not exist",
            )
        return VerificationResult(False, f"unsupported verification: {verify.type}")


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
    clock: Clock = field(default_factory=MonotonicClock)
    emergency_stop_monitor: EmergencyStopMonitor = field(
        default_factory=NoopEmergencyStopMonitor,
    )

    def run(self, task_path: Path, config_path: Path | None = None) -> RunReport:
        config = self.config_loader.load(config_path)
        task = self.task_loader.load(task_path)
        config = self.trace_sink.prepare_run(task, config)

        try:
            self._record("load_config", "configuration loaded")
            self._record(
                "load_task",
                "task loaded",
                {
                    "task": task.name,
                    "task_entropy_budget": task.entropy_budget,
                },
            )
            self.task_validator.validate(task, config)
            self._record("validate_task", "task validated")
            validate_entropy_budget_constraints(task, config)
            self._record(
                "entropy_budget",
                "entropy budget defined",
                {
                    **_task_entropy_metadata(task),
                    **entropy_capacity_metadata(task, config),
                },
            )
            self._record("prepare_trace", "trace sink prepared")
            timing_controller = ExecutionTimingController(config.execution_profile)

            precondition = self.safety_policy.check_preconditions(task, config)
            if not precondition.allowed:
                self._record("safety", precondition.reason)
                return self.trace_sink.write_final_report(
                    "aborted",
                    precondition.reason,
                )
            self._record("safety", "preconditions passed")

            task_deadline = self.clock.monotonic() + min(
                task.timeout_seconds,
                config.max_runtime_seconds,
            )
            step_by_id = {step.id: index for index, step in enumerate(task.steps)}
            step_index = 0
            executed_steps = 0
            action_count = 0

            while step_index < len(task.steps):
                if self.emergency_stop_monitor.is_triggered(config):
                    reason = "emergency stop requested"
                    self._record("emergency_stop", reason)
                    return self.trace_sink.write_final_report(
                        "emergency_stopped",
                        reason,
                    )
                if self._deadline_expired(task_deadline):
                    reason = "task exceeded timeout"
                    self._record("abort", reason, {"deadline": task_deadline})
                    return self.trace_sink.write_final_report("aborted", reason)

                executed_steps += 1
                if executed_steps > config.max_steps:
                    reason = "task exceeded max_steps"
                    self._record("abort", reason, {"max_steps": config.max_steps})
                    return self.trace_sink.write_final_report("aborted", reason)

                step = task.steps[step_index]
                outcome = self._execute_step(
                    task,
                    step,
                    config,
                    timing_controller,
                    task_deadline,
                    action_count,
                )
                step_report = outcome.report
                metadata_action_count = step_report.metadata.get("action_count")
                if isinstance(metadata_action_count, int):
                    action_count = metadata_action_count
                self.trace_sink.record_step(step_report)
                if outcome.abort_reason is not None:
                    self._record(
                        "emergency_stop"
                        if outcome.stop_status == "emergency_stopped"
                        else "abort",
                        outcome.abort_reason,
                        _step_metadata(step),
                    )
                    return self.trace_sink.write_final_report(
                        outcome.stop_status or "aborted",
                        outcome.abort_reason,
                    )
                if step_report.status != "passed":
                    return self.trace_sink.write_final_report(
                        "failed",
                        step_report.message,
                    )
                if outcome.next_step_id is not None:
                    if outcome.next_step_id not in step_by_id:
                        reason = f"branch target not found: {outcome.next_step_id}"
                        self._record("failure", reason, _step_metadata(step))
                        return self.trace_sink.write_final_report("failed", reason)
                    self._record(
                        "branch",
                        "jumping to branch target",
                        _step_metadata(step, next_step_id=outcome.next_step_id),
                    )
                    step_index = step_by_id[outcome.next_step_id]
                    continue
                step_index += 1

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
        timing_controller: ExecutionTimingController,
        task_deadline: float,
        action_count: int,
    ) -> StepExecutionOutcome:
        budget = estimate_step_timing_budget(
            step,
            config.execution_profile,
            default_timeout_seconds=config.default_timeout_seconds,
            max_retries_per_step=config.max_retries_per_step,
        )
        self._record(
            "step_timeout_budget",
            "step timing budget planned",
            _step_metadata(step, **budget.metadata()),
        )
        if not budget.fits_timeout:
            return StepExecutionOutcome(
                self._step_failed(
                    step,
                    0,
                    "step timeout budget is smaller than planned waits",
                    None,
                ),
            )

        variant_decision = timing_controller.select_action_variant(step)
        if step.safe_action_variants:
            self._record(
                "action_variant",
                "safe action variant selected",
                _step_metadata(step, **variant_decision.metadata()),
            )
        if variant_decision.selected_action != step.action:
            step = replace(step, action=variant_decision.selected_action)

        if step.action == "wait_for":
            return self._execute_wait_for(step, config, task_deadline)
        if step.action == "scroll_until":
            return self._execute_scroll_until(
                task,
                step,
                config,
                timing_controller,
                task_deadline,
                action_count,
            )
        if step.action == "branch_if_visible":
            return self._execute_branch_if_visible(step, config, task_deadline)

        retry_budget = step.retry
        if retry_budget is None:
            retry_budget = config.max_retries_per_step

        # Retry counts are budgets, so a retry value of 2 means 3 total attempts.
        total_attempts = retry_budget + 1
        last_message = "step was not attempted"
        last_candidate_id: str | None = None
        step_deadline = self._step_deadline(step, config, task_deadline)

        for attempt in range(1, total_attempts + 1):
            if self.emergency_stop_monitor.is_triggered(config):
                return self._emergency_stop_outcome(step, attempt, last_candidate_id)
            if self._deadline_expired(step_deadline):
                return StepExecutionOutcome(
                    self._step_failed(
                        step,
                        attempt - 1,
                        "step exceeded timeout",
                        last_candidate_id,
                    ),
                )
            observation = self.screen_observer.observe(config)
            observation_metadata = _observation_metadata(step.id, observation, attempt)
            observation_metadata["step_category"] = step_category(step)
            self._record(
                "observe_screen",
                "screen observed",
                observation_metadata,
            )

            candidates = self.perception_engine.detect(step, observation, config)
            if self._deadline_expired(step_deadline):
                return StepExecutionOutcome(
                    self._step_failed(
                        step,
                        attempt,
                        "step exceeded timeout",
                        last_candidate_id,
                    ),
                )
            detection_metadata = _step_metadata(
                step,
                candidate_count=len(candidates),
            )
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
            selection_metadata: dict[str, object] = _step_metadata(
                step,
                candidate_id=last_candidate_id,
                candidate_confidence=target.confidence if target else None,
                candidate_source=target.source if target else None,
                candidate_count=len(candidates),
            )
            if target is None and candidates:
                selection_metadata["selection_blocked"] = "confidence_or_ambiguity_gate"
            self._record(
                "select_target",
                "target selected" if target else "no target selected",
                selection_metadata,
            )
            if target is None and candidates and step.action in TARGETED_ACTIONS:
                return StepExecutionOutcome(
                    self._step_failed(
                        step,
                        attempt,
                        "target selection blocked by confidence or ambiguity gate",
                        None,
                    ),
                )

            safety = self.safety_policy.check_before_action(
                task,
                step,
                config,
                observation,
            )
            if not safety.allowed:
                self._record(
                    "recover",
                    "aborting with trace after safety rejection",
                    _step_metadata(
                        step,
                        recovery_actions=[
                            "refocus_allowed_window",
                            "abort_with_trace",
                        ],
                    ),
                )
                return StepExecutionOutcome(
                    self._step_failed(
                        step,
                        attempt,
                        safety.reason,
                        last_candidate_id,
                    ),
                )

            if self.emergency_stop_monitor.is_triggered(config):
                return self._emergency_stop_outcome(step, attempt, last_candidate_id)
            action_timing = timing_controller.before_action(
                build_action_timing_context(step, target, observation),
            )
            if config.execution_profile.enabled:
                metadata = action_timing.metadata()
                metadata["step_id"] = step.id
                metadata["step_category"] = step_category(step)
                metadata["attempt"] = attempt
                self._record("execution_timing", action_timing.reason, metadata)

            action_count += 1
            if action_count > config.max_steps:
                return StepExecutionOutcome(
                    self._step_failed(
                        step,
                        attempt,
                        "task exceeded max action count",
                        last_candidate_id,
                    ),
                )
            action_result = self.actuator.execute(step, target, observation, config)
            if self._deadline_expired(task_deadline):
                return StepExecutionOutcome(
                    self._step_failed(
                        step,
                        attempt,
                        "task exceeded timeout",
                        last_candidate_id,
                    ),
                    abort_reason="task exceeded timeout",
                )
            if self._deadline_expired(step_deadline):
                return StepExecutionOutcome(
                    self._step_failed(
                        step,
                        attempt,
                        "step exceeded timeout",
                        last_candidate_id,
                    ),
                )
            action_metadata = _step_metadata(step, success=action_result.success)
            action_metadata.update(action_result.metadata)
            self._record(
                "execute_action",
                action_result.message,
                action_metadata,
            )

            verification_observation, verification_candidates = (
                self._verification_observation(step, config)
            )
            verification = self.verifier.verify(
                step,
                verification_observation,
                target,
                action_result,
                config,
                verification_candidates,
            )
            self._record(
                "verify_result",
                verification.message,
                _step_metadata(step, passed=verification.passed),
            )

            if action_result.success and verification.passed:
                return StepExecutionOutcome(
                    self._step_passed(
                        step,
                        attempt,
                        verification.message,
                        last_candidate_id,
                        action_count,
                    ),
                )

            last_message = verification.message
            if attempt < total_attempts:
                retry_timing = timing_controller.before_retry()
                recover_metadata = _step_metadata(
                    step,
                    next_attempt=attempt + 1,
                    retry_reason=last_message,
                    retry_delay_seconds=retry_timing.delay_seconds,
                    recovery_actions=[
                        "wait_and_reobserve",
                        "retry_alternate_candidate",
                        "abort_with_trace",
                    ],
                )
                self._record(
                    "recover",
                    "retrying step",
                    recover_metadata,
                )
                if config.execution_profile.enabled:
                    timing_metadata = retry_timing.metadata()
                    timing_metadata["step_id"] = step.id
                    timing_metadata["step_category"] = step_category(step)
                    timing_metadata["next_attempt"] = attempt + 1
                    self._record(
                        "execution_timing",
                        retry_timing.reason,
                        timing_metadata,
                    )

        return StepExecutionOutcome(
            self._step_failed(
                step,
                total_attempts,
                last_message,
                last_candidate_id,
            ),
        )

    def _execute_wait_for(
        self,
        step: TaskStep,
        config: RuntimeConfig,
        task_deadline: float,
    ) -> StepExecutionOutcome:
        step_deadline = self._step_deadline(step, config, task_deadline)
        attempts = 0
        last_message = "wait_for condition was not visible"
        while not self._deadline_expired(step_deadline):
            attempts += 1
            if self.emergency_stop_monitor.is_triggered(config):
                return self._emergency_stop_outcome(step, attempts, None)
            observation, candidates = self._detect_for_step(step, config, attempts)
            target = self.target_selector.select(step, candidates, config)
            verification = self.verifier.verify(
                step,
                observation,
                target,
                ActionResult(True, "waited"),
                config,
                candidates,
            )
            self._record(
                "verify_result",
                verification.message,
                _step_metadata(step, passed=verification.passed),
            )
            if verification.passed:
                return StepExecutionOutcome(
                    self._step_passed(
                        step,
                        attempts,
                        verification.message,
                        target.id if target else None,
                        None,
                    ),
                )
            last_message = verification.message
            self._record(
                "recover",
                "waiting and re-observing",
                _step_metadata(
                    step,
                    next_attempt=attempts + 1,
                    recovery_actions=["wait_and_reobserve", "abort_with_trace"],
                ),
            )
            self.clock.sleep(
                min(
                    POLL_INTERVAL_SECONDS,
                    max(0.0, step_deadline - self.clock.monotonic()),
                ),
            )

        return StepExecutionOutcome(
            self._step_failed(
                step, attempts, f"wait_for timed out: {last_message}", None
            ),
        )

    def _execute_scroll_until(
        self,
        task: TaskDefinition,
        step: TaskStep,
        config: RuntimeConfig,
        timing_controller: ExecutionTimingController,
        task_deadline: float,
        action_count: int,
    ) -> StepExecutionOutcome:
        retry_budget = step.retry
        if retry_budget is None:
            retry_budget = config.max_retries_per_step
        max_scrolls = retry_budget + 1
        step_deadline = self._step_deadline(step, config, task_deadline)
        last_message = "scroll_until target was not visible"

        for attempt in range(1, max_scrolls + 2):
            if self.emergency_stop_monitor.is_triggered(config):
                return self._emergency_stop_outcome(step, attempt, None)
            if self._deadline_expired(step_deadline):
                return StepExecutionOutcome(
                    self._step_failed(
                        step,
                        attempt - 1,
                        "scroll_until exceeded timeout",
                        None,
                    ),
                )
            observation, candidates = self._detect_for_step(step, config, attempt)
            target = self.target_selector.select(step, candidates, config)
            if target is not None:
                return StepExecutionOutcome(
                    self._step_passed(
                        step,
                        attempt,
                        "scroll_until target is visible",
                        target.id,
                        action_count,
                    ),
                )
            if attempt > max_scrolls:
                break

            safety = self.safety_policy.check_before_action(
                task,
                step,
                config,
                observation,
            )
            if not safety.allowed:
                return StepExecutionOutcome(
                    self._step_failed(step, attempt, safety.reason, None),
                )

            if self.emergency_stop_monitor.is_triggered(config):
                return self._emergency_stop_outcome(step, attempt, None)
            action_count += 1
            if action_count > config.max_steps:
                return StepExecutionOutcome(
                    self._step_failed(
                        step,
                        attempt,
                        "task exceeded max action count",
                        None,
                    ),
                )

            action_timing = timing_controller.before_action(
                build_action_timing_context(step, None, observation),
            )
            if config.execution_profile.enabled:
                metadata = action_timing.metadata()
                metadata["step_id"] = step.id
                metadata["step_category"] = step_category(step)
                metadata["attempt"] = attempt
                self._record("execution_timing", action_timing.reason, metadata)

            action_result = self.actuator.execute(step, None, observation, config)
            self._record(
                "execute_action",
                action_result.message,
                {
                    **_step_metadata(step, success=action_result.success),
                    **action_result.metadata,
                },
            )
            if not action_result.success:
                last_message = action_result.message
                break
            self._record(
                "recover",
                "scrolling search region and re-observing",
                _step_metadata(
                    step,
                    next_attempt=attempt + 1,
                    recovery_actions=[
                        "scroll_search_region",
                        "wait_and_reobserve",
                        "abort_with_trace",
                    ],
                ),
            )

        return StepExecutionOutcome(
            self._step_failed(
                step,
                max_scrolls + 1,
                last_message,
                None,
            ),
        )

    def _execute_branch_if_visible(
        self,
        step: TaskStep,
        config: RuntimeConfig,
        task_deadline: float,
    ) -> StepExecutionOutcome:
        observation, candidates = self._detect_for_step(step, config, 1)
        if self.emergency_stop_monitor.is_triggered(config):
            return self._emergency_stop_outcome(step, 1, None)
        target = self.target_selector.select(step, candidates, config)
        verification = self.verifier.verify(
            step,
            observation,
            target,
            ActionResult(True, "branch checked"),
            config,
            candidates,
        )
        self._record(
            "verify_result",
            verification.message,
            _step_metadata(step, passed=verification.passed),
        )
        if verification.passed:
            return StepExecutionOutcome(
                self._step_passed(
                    step,
                    1,
                    "branch condition visible; continuing",
                    target.id if target else None,
                    None,
                ),
            )
        if self._deadline_expired(task_deadline):
            return StepExecutionOutcome(
                self._step_failed(step, 1, "task exceeded timeout", None),
            )
        if step.on_failure is None:
            return StepExecutionOutcome(
                self._step_failed(step, 1, "branch condition not visible", None),
            )
        return StepExecutionOutcome(
            self._step_passed(
                step,
                1,
                f"branching to {step.on_failure}",
                None,
                None,
            ),
            next_step_id=step.on_failure,
        )

    def _verification_observation(
        self,
        step: TaskStep,
        config: RuntimeConfig,
    ) -> tuple[ScreenObservation, tuple[ElementCandidate, ...]]:
        observation = self.screen_observer.observe(config)
        observation_metadata = _observation_metadata(step.id, observation, attempt=1)
        observation_metadata["step_category"] = step_category(step)
        self._record(
            "observe_after_action",
            "screen observed after action",
            observation_metadata,
        )
        if step.verify is None:
            return observation, ()
        verify_step = _verification_step(step)
        candidates = self.perception_engine.detect(verify_step, observation, config)
        metadata = _step_metadata(verify_step, candidate_count=len(candidates))
        metadata.update(candidate_ranking_metadata(verify_step, candidates, config))
        self._record("verify_candidates", "candidate search completed", metadata)
        return observation, candidates

    def _detect_for_step(
        self,
        step: TaskStep,
        config: RuntimeConfig,
        attempt: int,
        *,
        phase: str = "detect_candidates",
    ) -> tuple[ScreenObservation, tuple[ElementCandidate, ...]]:
        observation = self.screen_observer.observe(config)
        observation_metadata = _observation_metadata(step.id, observation, attempt)
        observation_metadata["step_category"] = step_category(step)
        self._record(
            "observe_screen",
            "screen observed",
            observation_metadata,
        )
        candidates = self.perception_engine.detect(step, observation, config)
        metadata = _step_metadata(step, candidate_count=len(candidates))
        metadata.update(candidate_ranking_metadata(step, candidates, config))
        self._record(phase, "candidate search completed", metadata)
        return observation, candidates

    def _step_deadline(
        self,
        step: TaskStep,
        config: RuntimeConfig,
        task_deadline: float,
    ) -> float:
        timeout = step.timeout_seconds or config.default_timeout_seconds
        return min(self.clock.monotonic() + timeout, task_deadline)

    def _deadline_expired(self, deadline: float) -> bool:
        return self.clock.monotonic() >= deadline

    def _step_passed(
        self,
        step: TaskStep,
        attempts: int,
        message: str,
        candidate_id: str | None,
        action_count: int | None,
    ) -> StepReport:
        metadata = _step_report_metadata(step)
        if action_count is not None:
            metadata["action_count"] = action_count
        return StepReport(
            step_id=step.id,
            action=step.action,
            status="passed",
            attempts=attempts,
            message=message,
            candidate_id=candidate_id,
            metadata=metadata,
        )

    def _step_failed(
        self,
        step: TaskStep,
        attempts: int,
        message: str,
        candidate_id: str | None,
    ) -> StepReport:
        self._record(
            "failure",
            message,
            _step_metadata(step, candidate_id=candidate_id),
        )
        return StepReport(
            step_id=step.id,
            action=step.action,
            status="failed",
            attempts=max(attempts, 1),
            message=message,
            candidate_id=candidate_id,
            metadata=_step_report_metadata(step),
        )

    def _emergency_stop_outcome(
        self,
        step: TaskStep,
        attempts: int,
        candidate_id: str | None,
    ) -> StepExecutionOutcome:
        reason = "emergency stop requested"
        return StepExecutionOutcome(
            self._step_failed(step, attempts, reason, candidate_id),
            abort_reason=reason,
            stop_status="emergency_stopped",
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


def _verification_step(step: TaskStep) -> TaskStep:
    if step.verify is None:
        return step
    target = step.target
    if step.verify.type in {
        "visible_text",
        "not_visible_text",
        "uia_element_exists",
    }:
        target = step.verify.text
    return TaskStep(
        id=f"{step.id}-verify",
        action="assert_visible",
        target=target,
        image=step.verify.image,
        region=step.region,
        category="verification",
    )


def _step_metadata(step: TaskStep, **metadata: object) -> dict[str, object]:
    step_metadata: dict[str, object] = {
        "step_id": step.id,
        "step_category": step_category(step),
        **metadata,
    }
    if step.entropy_budget is not None:
        step_metadata["step_entropy_budget"] = step.entropy_budget
    return step_metadata


def _task_entropy_metadata(task: TaskDefinition) -> dict[str, object]:
    return {
        "task_entropy_budget": task.entropy_budget,
        "step_entropy_budgets": {
            step.id: step.entropy_budget
            for step in task.steps
            if step.entropy_budget is not None
        },
    }


def _step_report_metadata(step: TaskStep) -> dict[str, object]:
    metadata: dict[str, object] = {"step_category": step_category(step)}
    if step.entropy_budget is not None:
        metadata["step_entropy_budget"] = step.entropy_budget
    return metadata


def _observation_metadata(
    step_id: str,
    observation: ScreenObservation,
    attempt: int,
) -> dict[str, object]:
    return {
        "step_id": step_id,
        "attempt": attempt,
        "screenshot_path": str(observation.screenshot_path)
        if observation.screenshot_path
        else None,
        "size": list(observation.size),
        "active_window_title": observation.active_window_title,
        "warnings": list(observation.warnings),
    }


def _verify_candidate_presence(
    step: TaskStep,
    candidates: tuple[ElementCandidate, ...],
) -> VerificationResult:
    matches = _matching_candidates(step.target, candidates)
    return VerificationResult(
        bool(matches),
        "target is visible" if matches else "target is not visible",
    )


def _verify_visible_text(
    text: str | None,
    candidates: tuple[ElementCandidate, ...],
) -> VerificationResult:
    matches = _matching_candidates(text, candidates)
    return VerificationResult(
        bool(matches),
        "text is visible" if matches else "text is not visible",
    )


def _matching_candidates(
    text: str | None,
    candidates: tuple[ElementCandidate, ...],
) -> tuple[ElementCandidate, ...]:
    if text is None:
        return candidates
    normalized = _normalize_text(text)
    return tuple(
        candidate
        for candidate in candidates
        if normalized in _normalize_text(candidate.label)
    )


def _candidate_is_focused(candidate: ElementCandidate | None) -> bool:
    if candidate is None:
        return False
    return candidate.metadata.get("focused") is True


def _normalize_text(value: str) -> str:
    return " ".join(value.casefold().split())
