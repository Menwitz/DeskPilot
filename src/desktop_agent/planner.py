"""Deterministic task execution pipeline."""

from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Literal, Protocol

from desktop_agent.action_safety import action_safety_metadata
from desktop_agent.actuation import ActionResult, Actuator
from desktop_agent.config import ConfigLoader, RuntimeConfig
from desktop_agent.desktop_io import desktop_io_operations_for_action
from desktop_agent.entropy import (
    entropy_capacity_metadata,
    validate_entropy_budget_constraints,
)
from desktop_agent.execution_paths import choose_execution_path
from desktop_agent.perception import (
    ElementCandidate,
    PerceptionEngine,
    RankedCandidate,
    TargetSelector,
    candidate_ranking_metadata,
    rank_candidates,
    ui_state_snapshot_metadata,
)
from desktop_agent.recovery import (
    RECOVERY_POLICIES,
    RecoveryPolicy,
    constrain_recovery_policy,
    recovery_policy_for_action_result,
    recovery_policy_for_selection,
)
from desktop_agent.safety import (
    EmergencyStopMonitor,
    NoopEmergencyStopMonitor,
    SafetyPolicy,
)
from desktop_agent.screen import (
    Bounds,
    ScreenObservation,
    ScreenObserver,
    screenshot_bounds_to_physical,
    screenshot_point_to_physical,
)
from desktop_agent.task_compiler import TaskCompiler
from desktop_agent.task_dsl import (
    TaskDefinition,
    TaskLoader,
    TaskStep,
    TaskValidator,
    VerificationDefinition,
    step_category,
)
from desktop_agent.task_state import TaskStateTracker
from desktop_agent.timing import (
    ExecutionTimingController,
    TimingDecision,
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
from desktop_agent.window_allowlist import effective_allowed_windows

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
VerificationOutcome = Literal["passed", "failed", "inconclusive"]
RECOVERABLE_SELECTION_REASONS: frozenset[str] = frozenset(
    {
        "stale_observation",
        "missed_target",
        "disabled_control",
        "occluded_control",
        "transient_loading",
    },
)


@dataclass(frozen=True)
class VerificationResult:
    """Result of a post-action verification check."""

    passed: bool
    message: str
    outcome: VerificationOutcome | None = None

    @property
    def resolved_outcome(self) -> VerificationOutcome:
        if self.outcome is not None:
            return self.outcome
        return "passed" if self.passed else "failed"


@dataclass(frozen=True)
class StepExecutionOutcome:
    """Internal result that can redirect the planner to another step."""

    report: StepReport
    next_step_id: str | None = None
    abort_reason: str | None = None
    stop_status: RunStatus | None = None


@dataclass(frozen=True)
class TimingDelayResult:
    """Observed consumption of a bounded planner timing delay."""

    elapsed_seconds: float
    emergency_stopped: bool = False
    emergency_stop_boundary: str | None = None


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
            blocked_reason = step.metadata.get("site_blocked_state_reason")
            if visible_matches and isinstance(blocked_reason, str):
                return VerificationResult(
                    False,
                    f"blocked state detected: {blocked_reason}",
                )
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
    task_compiler: TaskCompiler = field(default_factory=TaskCompiler)

    def run(self, task_path: Path, config_path: Path | None = None) -> RunReport:
        config = self.config_loader.load(config_path)
        task = self.task_loader.load(task_path)
        config = replace(
            config,
            allowed_windows=effective_allowed_windows(
                task.allowed_windows,
                config.allowed_windows,
            ),
        )
        config = self.trace_sink.prepare_run(task, config)

        try:
            self._record(
                "load_config",
                "configuration loaded",
                {"policy_preset": config.policy_preset},
            )
            self._record(
                "load_task",
                "task loaded",
                {
                    "task": task.name,
                    "task_entropy_budget": task.entropy_budget,
                    **task.metadata,
                },
            )
            self.task_validator.validate(task, config)
            self._record("validate_task", "task validated")
            compiled_task = self.task_compiler.compile(task)
            self._record(
                "compile_task",
                "task compiled",
                compiled_task.metadata(),
            )
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
            task_state = TaskStateTracker()

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
                state_check = task_state.check_before_step(step)
                self._record(
                    "task_state",
                    state_check.message,
                    _step_metadata(step, **state_check.metadata()),
                )
                if not state_check.passed:
                    self.trace_sink.record_step(
                        self._step_failed(
                            step,
                            0,
                            state_check.message,
                            None,
                            failure_category="task_state",
                        )
                    )
                    return self.trace_sink.write_final_report(
                        "failed",
                        state_check.message,
                    )
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
                state_update = task_state.mark_step_completed(step)
                self._record(
                    "task_state",
                    "task state updated",
                    _step_metadata(step, **state_update.metadata()),
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
                    failure_category="timeout",
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

        self._record(
            "action_safety",
            "action safety metadata resolved",
            _step_metadata(
                step,
                **action_safety_metadata(step, allowed_windows=config.allowed_windows),
            ),
        )

        if config.require_operator_approval:
            early_safety = self.safety_policy.check_before_action(task, step, config)
            if not early_safety.allowed:
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
                        0,
                        early_safety.reason,
                        None,
                        failure_category="safety_stop",
                    ),
                )

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
        last_failure_category = "execution_failure"
        last_failure_evidence: dict[str, object] | None = None
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
                        failure_category="timeout",
                    ),
                )
            observation = self.screen_observer.observe(config)
            observation_metadata = self._pre_action_observation_metadata(
                step,
                observation,
                attempt,
            )
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
                        failure_category="timeout",
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
            selection_recovery_policy: RecoveryPolicy | None = None
            selection_metadata: dict[str, object] = _step_metadata(
                step,
                candidate_id=last_candidate_id,
                candidate_confidence=target.confidence if target else None,
                candidate_source=target.source if target else None,
                candidate_count=len(candidates),
                step_action=step.action,
            )
            if target is None:
                selection_recovery_policy = recovery_policy_for_selection(
                    observation,
                    candidates,
                    target,
                )
                selection_metadata.update(selection_recovery_policy.metadata())
                if candidates and not _selection_retryable(
                    selection_recovery_policy,
                    candidates,
                ):
                    selection_metadata["selection_blocked"] = (
                        "confidence_or_ambiguity_gate"
                    )
            selection_blocked = selection_metadata.get("selection_blocked")
            selection_metadata.update(
                _target_reasoning_metadata(
                    step,
                    observation,
                    candidates,
                    target,
                    config,
                    selection_blocked
                    if isinstance(selection_blocked, str)
                    else None,
                )
            )
            self._record(
                "select_target",
                "target selected" if target else "no target selected",
                selection_metadata,
            )
            self._record(
                "ui_state_snapshot",
                "ui state summarized",
                _step_metadata(
                    step,
                    **ui_state_snapshot_metadata(
                        step,
                        candidates,
                        target,
                        config,
                        selection_blocked=selection_blocked
                        if isinstance(selection_blocked, str)
                        else None,
                    ),
                ),
            )
            if target is None and step.action in TARGETED_ACTIONS:
                if (
                    selection_recovery_policy is not None
                    and attempt < total_attempts
                    and _selection_retryable(selection_recovery_policy, candidates)
                ):
                    retry_reason = _selection_retry_reason(
                        selection_recovery_policy,
                        candidates,
                    )
                    retry_timing = timing_controller.before_retry(
                        retry_index=attempt,
                        retry_budget=retry_budget,
                        backoff_strategy=selection_recovery_policy.backoff_strategy,
                    )
                    recover_metadata = _recovery_metadata(
                        step,
                        selection_recovery_policy,
                        failed_attempt=attempt,
                        next_attempt=attempt + 1,
                        retry_reason=retry_reason,
                        retry_delay_seconds=retry_timing.delay_seconds,
                    )
                    recover_metadata.update(_retry_backoff_metadata(retry_timing))
                    self._record(
                        "recover",
                        "retrying target selection",
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
                    delay_result = self._consume_timing_delay(
                        retry_timing,
                        config,
                        emergency_stop_boundary="retry_wait",
                    )
                    if delay_result.emergency_stopped:
                        return self._emergency_stop_outcome(
                            step,
                            attempt,
                            last_candidate_id,
                        )
                    continue
                diagnostic_bundle = self._target_selection_diagnostics(
                    step,
                    observation,
                    candidates,
                    target,
                    config,
                    selection_recovery_policy,
                )
                self._record(
                    "target_diagnostics",
                    "target selection diagnostic bundle captured",
                    _step_metadata(step, **diagnostic_bundle),
                )
                return StepExecutionOutcome(
                    self._step_failed(
                        step,
                        attempt,
                        _selection_retry_reason(
                            selection_recovery_policy,
                            candidates,
                        ),
                        None,
                        failure_category=_selection_failure_category(
                            selection_recovery_policy,
                            candidates,
                        ),
                        diagnostic_bundle=diagnostic_bundle,
                    ),
                )

            safety = self.safety_policy.check_before_action(
                task,
                step,
                config,
                observation,
            )
            if step.requires_confirmation:
                confirmed = step.id in config.confirmed_steps
                self._record(
                    "confirmation",
                    "sensitive step confirmed"
                    if confirmed
                    else "sensitive step blocked",
                    _step_metadata(
                        step,
                        sensitive_step_confirmed=confirmed,
                        sensitive_step_confirmation_state="confirmed"
                        if confirmed
                        else "blocked",
                    ),
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
                        failure_category="safety_stop",
                    ),
                )

            if self.emergency_stop_monitor.is_triggered(config):
                return self._emergency_stop_outcome(step, attempt, last_candidate_id)
            execution_path = choose_execution_path(
                step,
                candidates,
                target,
                config,
                attempt,
            )
            self._record(
                "execution_path",
                "execution path selected",
                _step_metadata(step, **execution_path.metadata()),
            )
            self._record(
                "desktop_io_plan",
                "semantic action compiled to desktop I/O",
                _step_metadata(step, **_desktop_io_plan_metadata(step)),
            )
            if step.action == "manual_handoff":
                self._record(
                    "manual_handoff",
                    "operator handoff requested",
                    _step_metadata(step, **_manual_handoff_metadata(step)),
                )
            if step.checkpoint is not None:
                checkpoint = self._run_verification_checkpoint(
                    step,
                    config,
                    attempt,
                )
                if not checkpoint.passed:
                    return StepExecutionOutcome(
                        self._step_failed(
                            step,
                            attempt,
                            f"verification checkpoint failed: {checkpoint.message}",
                            last_candidate_id,
                            failure_category="verification_checkpoint",
                        ),
                    )
            action_timing = timing_controller.before_action(
                build_action_timing_context(step, target, observation),
            )
            original_delay_seconds = action_timing.delay_seconds
            if execution_path.fast:
                action_timing = replace(
                    action_timing,
                    delay_seconds=action_timing.lower_bound_seconds,
                    reason="fast-path action timing decided",
                )
            elif execution_path.careful:
                action_timing = replace(
                    action_timing,
                    delay_seconds=action_timing.upper_bound_seconds,
                    reason="careful-path action timing decided",
                )
            if config.execution_profile.enabled:
                metadata = action_timing.metadata()
                metadata["step_id"] = step.id
                metadata["step_category"] = step_category(step)
                metadata["attempt"] = attempt
                metadata.update(execution_path.metadata())
                if execution_path.fast:
                    metadata["original_delay_seconds"] = original_delay_seconds
                    metadata["delay_reduction_seconds"] = max(
                        original_delay_seconds - action_timing.delay_seconds,
                        0.0,
                    )
                elif execution_path.careful:
                    metadata["original_delay_seconds"] = original_delay_seconds
                    metadata["delay_extension_seconds"] = max(
                        action_timing.delay_seconds - original_delay_seconds,
                        0.0,
                    )
                self._record("execution_timing", action_timing.reason, metadata)
            input_wait = self._consume_input_wait(
                step,
                action_timing,
                attempt,
                config,
            )
            if input_wait.emergency_stopped:
                return self._emergency_stop_outcome(step, attempt, last_candidate_id)
            if self._deadline_expired(step_deadline):
                return StepExecutionOutcome(
                    self._step_failed(
                        step,
                        attempt,
                        "step exceeded timeout",
                        last_candidate_id,
                        failure_category="timeout",
                    ),
                )

            action_count += 1
            if action_count > config.max_steps:
                return StepExecutionOutcome(
                    self._step_failed(
                        step,
                        attempt,
                        "task exceeded max action count",
                        last_candidate_id,
                        failure_category="execution_limit",
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
                        failure_category="timeout",
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
                        failure_category="timeout",
                    ),
                )
            action_metadata = _step_metadata(
                step,
                success=action_result.success,
                **_desktop_io_plan_metadata(step),
            )
            action_metadata.update(action_result.metadata)
            self._record(
                "execute_action",
                action_result.message,
                action_metadata,
            )

            verification_observation, verification_candidates = (
                self._verification_observation(step, config, attempt)
            )
            verification = self.verifier.verify(
                step,
                verification_observation,
                target,
                action_result,
                config,
                verification_candidates,
            )
            state_delta_metadata = _state_delta_metadata(
                step,
                observation,
                verification_observation,
                candidates,
                verification_candidates,
                action_result,
            )
            self._record(
                "verify_result",
                verification.message,
                _step_metadata(
                    step,
                    passed=verification.passed,
                    verification_outcome=verification.resolved_outcome,
                ),
            )
            self._record(
                "state_delta",
                "visual state delta summarized",
                _step_metadata(
                    step,
                    **state_delta_metadata,
                ),
            )
            if step.action in {"click_text", "click_image", "click_uia"}:
                last_failure_evidence = _click_failure_evidence_metadata(
                    step,
                    observation,
                    candidates,
                    config,
                    action_result,
                    state_delta_metadata,
                )
            elif step.action == "type_text":
                last_failure_evidence = _type_failure_evidence_metadata(
                    observation,
                    action_result,
                    state_delta_metadata,
                )
            elif step.action == "scroll":
                last_failure_evidence = _scroll_failure_evidence_metadata(
                    action_result,
                    state_delta_metadata,
                )

            if verification.resolved_outcome == "inconclusive":
                last_message = verification.message
                last_failure_category = "verification_inconclusive"
                if attempt < total_attempts:
                    retry_timing = timing_controller.before_retry(
                        retry_index=attempt,
                        retry_budget=retry_budget,
                        backoff_strategy=RECOVERY_POLICIES[
                            "verification_inconclusive"
                        ].backoff_strategy,
                    )
                    recover_metadata = _recovery_metadata(
                        step,
                        RECOVERY_POLICIES["verification_inconclusive"],
                        failed_attempt=attempt,
                        failure_observation_phase="observe_after_action",
                        next_attempt=attempt + 1,
                        retry_reason=last_message,
                        retry_delay_seconds=retry_timing.delay_seconds,
                        verification_outcome=verification.resolved_outcome,
                    )
                    recover_metadata.update(_retry_backoff_metadata(retry_timing))
                    self._record(
                        "recover",
                        "retrying inconclusive verification",
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
                    delay_result = self._consume_timing_delay(
                        retry_timing,
                        config,
                        emergency_stop_boundary="retry_wait",
                    )
                    if delay_result.emergency_stopped:
                        return self._emergency_stop_outcome(
                            step,
                            attempt,
                            last_candidate_id,
                        )
                    continue
                self._record(
                    "manual_handoff",
                    "verification inconclusive; manual handoff required",
                    _step_metadata(
                        step,
                        attempt=attempt,
                        verification_outcome=verification.resolved_outcome,
                        manual_handoff_required=True,
                    ),
                )
                return StepExecutionOutcome(
                    self._step_failed(
                        step,
                        attempt,
                        f"manual handoff required: {verification.message}",
                        last_candidate_id,
                        failure_category="manual_handoff",
                    ),
                )

            if action_result.success and verification.passed:
                return StepExecutionOutcome(
                    self._step_passed(
                        step,
                        attempt,
                        verification.message,
                        last_candidate_id,
                        action_count,
                        success_evidence=_success_evidence_metadata(
                            verification_observation,
                            action_result,
                            state_delta_metadata,
                            verification,
                        ),
                    ),
                )

            last_message = verification.message
            last_failure_category = _action_failure_category(action_result)
            if attempt < total_attempts:
                recovery_observation, recovery_candidates = self._recovery_observation(
                    step,
                    config,
                    failed_attempt=attempt,
                    next_attempt=attempt + 1,
                )
                recovery_policy = recovery_policy_for_action_result(
                    recovery_observation,
                    recovery_candidates,
                    action_result,
                    verification.passed,
                )
                retry_timing = timing_controller.before_retry(
                    retry_index=attempt,
                    retry_budget=retry_budget,
                    backoff_strategy=recovery_policy.backoff_strategy,
                )
                recover_metadata = _recovery_metadata(
                    step,
                    recovery_policy,
                    failed_attempt=attempt,
                    failure_observation_phase="reobserve_after_failure",
                    recovery_candidate_count=len(recovery_candidates),
                    next_attempt=attempt + 1,
                    retry_reason=last_message,
                    retry_delay_seconds=retry_timing.delay_seconds,
                )
                recover_metadata.update(_retry_backoff_metadata(retry_timing))
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
                delay_result = self._consume_timing_delay(
                    retry_timing,
                    config,
                    emergency_stop_boundary="retry_wait",
                )
                if delay_result.emergency_stopped:
                    return self._emergency_stop_outcome(
                        step,
                        attempt,
                        last_candidate_id,
                    )

        return StepExecutionOutcome(
            self._step_failed(
                step,
                total_attempts,
                last_message,
                last_candidate_id,
                failure_category=last_failure_category,
                failure_evidence=last_failure_evidence,
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
                _step_metadata(
                    step,
                    passed=verification.passed,
                    verification_outcome=verification.resolved_outcome,
                ),
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
                _recovery_metadata(
                    step,
                    recovery_policy_for_selection(observation, candidates, target),
                    failed_attempt=attempts,
                    next_attempt=attempts + 1,
                    retry_reason=last_message,
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
                step,
                attempts,
                f"wait_for timed out: {last_message}",
                None,
                failure_category="perception_failure",
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
                        failure_category="timeout",
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
                    self._step_failed(
                        step,
                        attempt,
                        safety.reason,
                        None,
                        failure_category="safety_stop",
                    ),
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
                        failure_category="execution_limit",
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
            input_wait = self._consume_input_wait(
                step,
                action_timing,
                attempt,
                config,
            )
            if input_wait.emergency_stopped:
                return self._emergency_stop_outcome(step, attempt, None)
            if self._deadline_expired(step_deadline):
                return StepExecutionOutcome(
                    self._step_failed(
                        step,
                        attempt,
                        "scroll_until exceeded timeout",
                        None,
                        failure_category="timeout",
                    ),
                )

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
                _recovery_metadata(
                    step,
                    RecoveryPolicy(
                        name="scroll_search_region",
                        reason="missed_target",
                        actions=(
                            "scroll_search_region",
                            "wait_and_reobserve",
                            "abort_with_trace",
                        ),
                    ),
                    failed_attempt=attempt,
                    next_attempt=attempt + 1,
                ),
            )

        return StepExecutionOutcome(
            self._step_failed(
                step,
                max_scrolls + 1,
                last_message,
                None,
                failure_category="actuation_failure"
                if last_message != "scroll_until target was not visible"
                else "perception_failure",
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
            _step_metadata(
                step,
                passed=verification.passed,
                verification_outcome=verification.resolved_outcome,
            ),
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
                self._step_failed(
                    step,
                    1,
                    "task exceeded timeout",
                    None,
                    failure_category="timeout",
                ),
            )
        if step.on_failure is None:
            return StepExecutionOutcome(
                self._step_failed(
                    step,
                    1,
                    "branch condition not visible",
                    None,
                    failure_category="perception_failure",
                ),
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
        attempt: int,
    ) -> tuple[ScreenObservation, tuple[ElementCandidate, ...]]:
        observation = self.screen_observer.observe(config)
        observation_metadata = self._post_action_observation_metadata(
            step,
            observation,
            attempt,
        )
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

    def _run_verification_checkpoint(
        self,
        step: TaskStep,
        config: RuntimeConfig,
        attempt: int,
    ) -> VerificationResult:
        observation = self.screen_observer.observe(config)
        observation_metadata = _observation_metadata(step.id, observation, attempt)
        observation_metadata["step_category"] = step_category(step)
        self._record(
            "observe_checkpoint",
            "screen observed for verification checkpoint",
            observation_metadata,
        )
        checkpoint_step = _checkpoint_step(step)
        candidates = self.perception_engine.detect(checkpoint_step, observation, config)
        metadata = _step_metadata(
            checkpoint_step,
            candidate_count=len(candidates),
            checkpoint_for_step_id=step.id,
        )
        metadata.update(candidate_ranking_metadata(checkpoint_step, candidates, config))
        self._record("checkpoint_candidates", "candidate search completed", metadata)
        target = self.target_selector.select(checkpoint_step, candidates, config)
        checkpoint = self.verifier.verify(
            checkpoint_step,
            observation,
            target,
            ActionResult(True, "checkpoint checked"),
            config,
            candidates,
        )
        self._record(
            "verification_checkpoint",
            checkpoint.message,
            _step_metadata(
                step,
                checkpoint_type=step.checkpoint.type if step.checkpoint else None,
                checkpoint_target_id=target.id if target else None,
                irreversible_action=_irreversible_action(step),
                passed=checkpoint.passed,
            ),
        )
        return checkpoint

    def _recovery_observation(
        self,
        step: TaskStep,
        config: RuntimeConfig,
        *,
        failed_attempt: int,
        next_attempt: int,
    ) -> tuple[ScreenObservation, tuple[ElementCandidate, ...]]:
        observation = self.screen_observer.observe(config)
        observation_metadata = self._post_action_observation_metadata(
            step,
            observation,
            failed_attempt,
            failure_observation=True,
        )
        observation_metadata["step_category"] = step_category(step)
        observation_metadata["failed_attempt"] = failed_attempt
        observation_metadata["next_attempt"] = next_attempt
        self._record(
            "reobserve_after_failure",
            "screen re-observed after failed attempt",
            observation_metadata,
        )
        recovery_step = _verification_step(step) if step.verify is not None else step
        candidates = self.perception_engine.detect(recovery_step, observation, config)
        metadata = _step_metadata(
            recovery_step,
            candidate_count=len(candidates),
            failed_attempt=failed_attempt,
            next_attempt=next_attempt,
            recovery_for_step_id=step.id,
        )
        metadata.update(candidate_ranking_metadata(recovery_step, candidates, config))
        # Recovery re-observation is read-only, but it still runs through the
        # perception stack so traces show what deep search saw before retrying.
        self._record(
            "recover_candidates",
            "candidate search completed after failed attempt",
            metadata,
        )
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
        observation_metadata = self._pre_action_observation_metadata(
            step,
            observation,
            attempt,
        )
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

    def _consume_input_wait(
        self,
        step: TaskStep,
        decision: TimingDecision,
        attempt: int,
        config: RuntimeConfig,
    ) -> TimingDelayResult:
        result = self._consume_timing_delay(
            decision,
            config,
            emergency_stop_boundary="action_wait",
        )
        if decision.phase == "action" and decision.delay_seconds > 0:
            self._record(
                "input_wait",
                "timing delay consumed before desktop input",
                _step_metadata(
                    step,
                    attempt=attempt,
                    requested_delay_seconds=decision.delay_seconds,
                    elapsed_wait_seconds=result.elapsed_seconds,
                    before_desktop_input=True,
                ),
            )
        return result

    def _consume_timing_delay(
        self,
        decision: TimingDecision,
        config: RuntimeConfig | None = None,
        *,
        emergency_stop_boundary: str = "timing_wait",
    ) -> TimingDelayResult:
        if decision.delay_seconds <= 0:
            return TimingDelayResult(0.0)
        started = self.clock.monotonic()
        remaining = decision.delay_seconds
        while remaining > 0:
            if (
                config is not None
                and self.emergency_stop_monitor.is_triggered(config)
            ):
                return self._timing_delay_emergency_stop(
                    decision,
                    started,
                    emergency_stop_boundary,
                )
            sleep_seconds = min(POLL_INTERVAL_SECONDS, remaining)
            self.clock.sleep(sleep_seconds)
            remaining = max(0.0, remaining - sleep_seconds)
        if config is not None and self.emergency_stop_monitor.is_triggered(config):
            return self._timing_delay_emergency_stop(
                decision,
                started,
                emergency_stop_boundary,
            )
        return TimingDelayResult(max(0.0, self.clock.monotonic() - started))

    def _timing_delay_emergency_stop(
        self,
        decision: TimingDecision,
        started: float,
        boundary: str,
    ) -> TimingDelayResult:
        elapsed = max(0.0, self.clock.monotonic() - started)
        self._record(
            "emergency_stop",
            "emergency stop requested during timing wait",
            {
                "timing_phase": decision.phase,
                "timing_reason": decision.reason,
                "requested_delay_seconds": decision.delay_seconds,
                "elapsed_wait_seconds": elapsed,
                "emergency_stop_boundary": boundary,
            },
        )
        return TimingDelayResult(
            elapsed_seconds=elapsed,
            emergency_stopped=True,
            emergency_stop_boundary=boundary,
        )

    def _target_selection_diagnostics(
        self,
        step: TaskStep,
        observation: ScreenObservation,
        candidates: tuple[ElementCandidate, ...],
        target: ElementCandidate | None,
        config: RuntimeConfig,
        recovery_policy: RecoveryPolicy | None,
    ) -> dict[str, object]:
        ranking_metadata = candidate_ranking_metadata(step, candidates, config)
        snapshot_metadata = ui_state_snapshot_metadata(step, candidates, target, config)
        return {
            "diagnostic_type": "target_selection_failure",
            "step_id": step.id,
            "action": step.action,
            "target": step.target,
            "recovery_reason": recovery_policy.reason if recovery_policy else None,
            "screenshot_path": str(observation.screenshot_path)
            if observation.screenshot_path
            else None,
            "screen_size": list(observation.size),
            "active_window_title": observation.active_window_title,
            "active_window_process": _metadata_dict(
                observation,
                "active_window_process",
            ),
            "focused_element": _metadata_dict(observation, "focused_element"),
            "monitor": _monitor_metadata(observation),
            "dpi_scale": _dpi_metadata(observation),
            "candidate_count": len(candidates),
            "candidates_by_source": _candidates_by_source(candidates),
            "chosen_target": snapshot_metadata.get("selected_candidate"),
            "selected_candidate": snapshot_metadata.get("selected_candidate"),
            "blocked_candidates": snapshot_metadata.get("blocked_candidates", []),
            "candidate_rankings": ranking_metadata.get("candidate_rankings", []),
            "cursor_readback": self._cursor_readback_metadata(),
        }

    def _cursor_readback_metadata(self) -> dict[str, object]:
        current_position = getattr(self.actuator, "current_position", None)
        if not callable(current_position):
            return {"status": "unavailable", "reason": "actuator has no cursor reader"}
        try:
            point = current_position()
        except Exception as exc:
            return {
                "status": "failed",
                "reason": str(exc),
                "error_type": type(exc).__name__,
            }
        return {"status": "passed", "position": list(point)}

    def _pre_action_observation_metadata(
        self,
        step: TaskStep,
        observation: ScreenObservation,
        attempt: int,
    ) -> dict[str, object]:
        metadata = _observation_metadata(step.id, observation, attempt)
        cursor_readback = self._cursor_readback_metadata()
        metadata["trace_schema_section"] = "observation"
        metadata["observation_role"] = "pre_action"
        metadata["pre_action_evidence"] = _observation_evidence(
            observation,
            cursor_readback,
        )
        return metadata

    def _post_action_observation_metadata(
        self,
        step: TaskStep,
        observation: ScreenObservation,
        attempt: int,
        *,
        failure_observation: bool = False,
    ) -> dict[str, object]:
        metadata = _observation_metadata(step.id, observation, attempt)
        cursor_readback = self._cursor_readback_metadata()
        metadata["trace_schema_section"] = "verification"
        metadata["observation_role"] = "post_action"
        metadata["post_action_evidence"] = _observation_evidence(
            observation,
            cursor_readback,
        )
        if failure_observation:
            metadata["failure_observation"] = True
        return metadata

    def _step_passed(
        self,
        step: TaskStep,
        attempts: int,
        message: str,
        candidate_id: str | None,
        action_count: int | None,
        *,
        success_evidence: dict[str, object] | None = None,
    ) -> StepReport:
        metadata = _step_report_metadata(step)
        if action_count is not None:
            metadata["action_count"] = action_count
        if success_evidence is not None:
            metadata["success_evidence"] = success_evidence
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
        *,
        failure_category: str = "execution_failure",
        diagnostic_bundle: dict[str, object] | None = None,
        failure_evidence: dict[str, object] | None = None,
    ) -> StepReport:
        failure_metadata = _step_metadata(
            step,
            candidate_id=candidate_id,
            failure_category=failure_category,
        )
        if diagnostic_bundle is not None:
            failure_metadata["diagnostic_bundle"] = diagnostic_bundle
        if failure_evidence is not None:
            failure_metadata["failure_evidence"] = failure_evidence
        self._record(
            "failure",
            message,
            failure_metadata,
        )
        report_metadata = _step_report_metadata(step)
        report_metadata["failure_category"] = failure_category
        if diagnostic_bundle is not None:
            report_metadata["diagnostic_bundle"] = diagnostic_bundle
        if failure_evidence is not None:
            report_metadata["failure_evidence"] = failure_evidence
        return StepReport(
            step_id=step.id,
            action=step.action,
            status="failed",
            attempts=max(attempts, 1),
            message=message,
            candidate_id=candidate_id,
            metadata=report_metadata,
        )

    def _emergency_stop_outcome(
        self,
        step: TaskStep,
        attempts: int,
        candidate_id: str | None,
    ) -> StepExecutionOutcome:
        reason = "emergency stop requested"
        return StepExecutionOutcome(
            self._step_failed(
                step,
                attempts,
                reason,
                candidate_id,
                failure_category="safety_stop",
            ),
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


def _action_failure_category(action_result: ActionResult) -> str:
    if action_result.success:
        return "verification_failure"
    if _actuation_guard_blocked(action_result):
        return "safety_stop"
    return "actuation_failure"


def _actuation_guard_blocked(action_result: ActionResult) -> bool:
    return action_result.metadata.get("input_blocked") is True and isinstance(
        action_result.metadata.get("actuation_guard"), str
    )


def _checkpoint_step(step: TaskStep) -> TaskStep:
    if step.checkpoint is None:
        return step
    target = step.target
    if step.checkpoint.type in {
        "visible_text",
        "not_visible_text",
        "uia_element_exists",
    }:
        target = step.checkpoint.text
    return TaskStep(
        id=f"{step.id}-checkpoint",
        action="assert_visible",
        target=target,
        image=step.checkpoint.image,
        region=step.region,
        verify=step.checkpoint,
        category="verification",
    )


def _irreversible_action(step: TaskStep) -> bool:
    return step.requires_confirmation or step_category(step) == "submission"


def _step_metadata(step: TaskStep, **metadata: object) -> dict[str, object]:
    step_metadata: dict[str, object] = {
        "step_id": step.id,
        "step_category": step_category(step),
        **step.metadata,
        **action_safety_metadata(step),
        **metadata,
    }
    if step.entropy_budget is not None:
        step_metadata["step_entropy_budget"] = step.entropy_budget
    return step_metadata


def _recovery_metadata(
    step: TaskStep,
    policy: RecoveryPolicy,
    **metadata: object,
) -> dict[str, object]:
    recovery_metadata = _step_metadata(step, **metadata)
    constrained = constrain_recovery_policy(step, policy)
    recovery_metadata.update(constrained.metadata())
    recovery_metadata.update(
        _recovery_path_metadata(
            reason=constrained.policy.reason,
            chosen_action=constrained.chosen_action,
            failed_attempt=metadata.get("failed_attempt"),
            next_attempt=metadata.get("next_attempt"),
            failure_observation_phase=metadata.get("failure_observation_phase"),
        )
    )
    return recovery_metadata


def _selection_retryable(
    policy: RecoveryPolicy,
    candidates: tuple[ElementCandidate, ...],
) -> bool:
    if policy.reason not in RECOVERABLE_SELECTION_REASONS:
        return False
    return not (policy.reason == "missed_target" and candidates)


def _selection_retry_reason(
    policy: RecoveryPolicy | None,
    candidates: tuple[ElementCandidate, ...],
) -> str:
    if policy is None:
        return "target selection failed"
    if policy.reason == "missed_target" and candidates:
        return "target selection blocked by confidence or ambiguity gate"
    return f"target selection failed: {policy.reason}"


def _selection_failure_category(
    policy: RecoveryPolicy | None,
    candidates: tuple[ElementCandidate, ...],
) -> str:
    if policy is not None and policy.reason == "missed_target" and candidates:
        return "selection_ambiguity"
    return "perception_failure"


def _recovery_path_metadata(
    *,
    reason: str,
    chosen_action: str,
    failed_attempt: object,
    next_attempt: object,
    failure_observation_phase: object,
) -> dict[str, object]:
    path: list[dict[str, object]] = [
        {
            "stage": "classify_failure",
            "reason": reason,
            "attempt": failed_attempt,
        }
    ]
    if isinstance(failure_observation_phase, str):
        path.append(
            {
                "stage": "fresh_failure_observation",
                "phase": failure_observation_phase,
                "attempt": failed_attempt,
            }
        )
    path.append({"stage": "recovery_action", "action": chosen_action})
    reobserve_before_retry = (
        chosen_action != "abort_with_trace" and next_attempt is not None
    )
    if reobserve_before_retry:
        path.extend(
            [
                {
                    "stage": "fresh_retry_observation",
                    "phase": "observe_screen",
                    "attempt": next_attempt,
                },
                {"stage": "retry_attempt", "attempt": next_attempt},
            ]
        )
    return {
        "recovery_path": path,
        "recovery_path_summary": _recovery_path_summary(path),
        "reobserve_before_retry": reobserve_before_retry,
    }


def _recovery_path_summary(path: list[dict[str, object]]) -> str:
    parts: list[str] = []
    for item in path:
        stage = item["stage"]
        if stage == "classify_failure":
            parts.append(f"classify {item['reason']}")
        elif stage == "fresh_failure_observation":
            parts.append(f"{item['phase']} attempt {item['attempt']}")
        elif stage == "recovery_action":
            parts.append(str(item["action"]))
        elif stage == "fresh_retry_observation":
            parts.append(f"{item['phase']} attempt {item['attempt']}")
        elif stage == "retry_attempt":
            parts.append(f"retry attempt {item['attempt']}")
    return " -> ".join(parts)


def _retry_backoff_metadata(decision: TimingDecision) -> dict[str, object]:
    decision_metadata = decision.metadata()
    backoff_keys = {
        "retry_backoff_strategy",
        "retry_index",
        "retry_budget",
        "retry_backoff_fraction",
        "retry_limit_respected",
    }
    return {
        key: decision_metadata[key] for key in backoff_keys if key in decision_metadata
    }


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
    metadata: dict[str, object] = {
        "step_category": step_category(step),
        **step.metadata,
        **action_safety_metadata(step),
    }
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
        "active_window_process": _metadata_dict(
            observation,
            "active_window_process",
        ),
        "focused_element": _metadata_dict(observation, "focused_element"),
        "monitor": _monitor_metadata(observation),
        "dpi_scale": _dpi_metadata(observation),
        "warnings": list(observation.warnings),
    }


def _observation_evidence(
    observation: ScreenObservation,
    cursor_readback: dict[str, object],
) -> dict[str, object]:
    cursor_position = cursor_readback.get("position")
    return {
        "screenshot_path": str(observation.screenshot_path)
        if observation.screenshot_path
        else None,
        "screen_size": list(observation.size),
        "active_window_title": observation.active_window_title,
        "active_window_process": _metadata_dict(
            observation,
            "active_window_process",
        ),
        "focused_element": _metadata_dict(observation, "focused_element"),
        "cursor_position": cursor_position
        if isinstance(cursor_position, list)
        else None,
        "cursor_readback": cursor_readback,
        "monitor": _monitor_metadata(observation),
        "dpi_scale": _dpi_metadata(observation),
        "warnings": list(observation.warnings),
    }


def _target_reasoning_metadata(
    step: TaskStep,
    observation: ScreenObservation,
    candidates: tuple[ElementCandidate, ...],
    selected: ElementCandidate | None,
    config: RuntimeConfig,
    selection_blocked: str | None,
) -> dict[str, object]:
    ranked = rank_candidates(step, candidates, config)
    selected_id = selected.id if selected is not None else None
    snapshot_metadata = ui_state_snapshot_metadata(
        step,
        candidates,
        selected,
        config,
        selection_blocked=selection_blocked,
    )
    blocked_candidates = snapshot_metadata.get("blocked_candidates")
    if not isinstance(blocked_candidates, list):
        blocked_candidates = []
    rejected_reasons = {
        str(candidate["id"]): str(candidate["blocked_reason"])
        for candidate in blocked_candidates
        if isinstance(candidate, dict)
        and isinstance(candidate.get("id"), str)
        and isinstance(candidate.get("blocked_reason"), str)
    }
    selected_snapshot = _reasoning_snapshot_for_id(ranked, selected_id, observation)
    return {
        "trace_schema_section": "target_reasoning",
        "selected_candidate": selected_snapshot,
        "selected_candidate_id": selected_id,
        "rejected_candidates": [
            _candidate_reasoning_snapshot(
                ranked_candidate,
                observation,
                rejection_reason=rejected_reasons.get(ranked_candidate.candidate.id),
            )
            for ranked_candidate in ranked
            if ranked_candidate.candidate.id != selected_id
        ],
        "rejection_reasons": rejected_reasons,
        "confidence_values": {
            ranked_candidate.candidate.id: ranked_candidate.candidate.confidence
            for ranked_candidate in ranked
        },
        "coordinate_conversion": selected_snapshot.get("coordinate_conversion")
        if selected_snapshot is not None
        else None,
    }


def _state_delta_metadata(
    step: TaskStep,
    before_observation: ScreenObservation,
    after_observation: ScreenObservation,
    before_candidates: tuple[ElementCandidate, ...],
    after_candidates: tuple[ElementCandidate, ...],
    action_result: ActionResult,
) -> dict[str, object]:
    before_text = _visible_candidate_labels(before_candidates)
    after_text = _visible_candidate_labels(after_candidates)
    target_text = _state_delta_target_text(step)
    target_visible_before = _label_visible(target_text, before_candidates)
    target_visible_after = _label_visible(target_text, after_candidates)
    return {
        "trace_schema_section": "state_delta",
        "before_screenshot_path": str(before_observation.screenshot_path)
        if before_observation.screenshot_path
        else None,
        "after_screenshot_path": str(after_observation.screenshot_path)
        if after_observation.screenshot_path
        else None,
        "before_active_window_title": before_observation.active_window_title,
        "after_active_window_title": after_observation.active_window_title,
        "active_window_changed": before_observation.active_window_title
        != after_observation.active_window_title,
        "before_focused_element": _metadata_dict(
            before_observation,
            "focused_element",
        ),
        "after_focused_element": _metadata_dict(
            after_observation,
            "focused_element",
        ),
        "focused_element_changed": _metadata_dict(
            before_observation,
            "focused_element",
        )
        != _metadata_dict(after_observation, "focused_element"),
        "focus_changed": _focus_signature(before_observation)
        != _focus_signature(after_observation),
        "visible_text_before": before_text,
        "visible_text_after": after_text,
        "visible_text_added": sorted(set(after_text) - set(before_text)),
        "visible_text_removed": sorted(set(before_text) - set(after_text)),
        "visible_text_changed": set(before_text) != set(after_text),
        "target_text": target_text,
        "target_visible_before": target_visible_before,
        "target_visible_after": target_visible_after,
        "target_appeared": target_visible_before is False
        and target_visible_after is True,
        "target_disappeared": target_visible_before is True
        and target_visible_after is False,
        **_scroll_delta_metadata(step, action_result),
    }


def _click_failure_evidence_metadata(
    step: TaskStep,
    observation: ScreenObservation,
    candidates: tuple[ElementCandidate, ...],
    config: RuntimeConfig,
    action_result: ActionResult,
    state_delta: dict[str, object],
) -> dict[str, object]:
    return {
        "failure_evidence_type": "failed_click",
        "action_message": action_result.message,
        "action_success": action_result.success,
        "before_screenshot_path": str(observation.screenshot_path)
        if observation.screenshot_path
        else None,
        "before_active_window_title": observation.active_window_title,
        "visible_before": [
            _candidate_reasoning_snapshot(ranked_candidate, observation)
            for ranked_candidate in rank_candidates(step, candidates, config)
            if ranked_candidate.candidate.visible
        ],
        "state_delta": state_delta,
    }


def _type_failure_evidence_metadata(
    observation: ScreenObservation,
    action_result: ActionResult,
    state_delta: dict[str, object],
) -> dict[str, object]:
    return {
        "failure_evidence_type": "failed_type",
        "action_message": action_result.message,
        "action_success": action_result.success,
        "before_screenshot_path": str(observation.screenshot_path)
        if observation.screenshot_path
        else None,
        "before_active_window_title": observation.active_window_title,
        "before_focused_element": _metadata_dict(observation, "focused_element"),
        "before_active_window_process": _metadata_dict(
            observation,
            "active_window_process",
        ),
        "state_delta": state_delta,
    }


def _scroll_failure_evidence_metadata(
    action_result: ActionResult,
    state_delta: dict[str, object],
) -> dict[str, object]:
    return {
        "failure_evidence_type": "failed_scroll",
        "action_message": action_result.message,
        "action_success": action_result.success,
        "scroll_moved": state_delta.get("scroll_moved"),
        "scroll_clicks": state_delta.get("scroll_clicks"),
        "scroll_step_count": state_delta.get("scroll_step_count"),
        "scroll_step_clicks": state_delta.get("scroll_step_clicks"),
        "state_delta": state_delta,
    }


def _desktop_io_plan_metadata(step: TaskStep) -> dict[str, object]:
    operations = _desktop_io_operations(step.action)
    return {
        "semantic_action": step.action,
        "desktop_io_operations": operations,
        "desktop_io_operation_count": len(operations),
    }


def _desktop_io_operations(action: str) -> list[str]:
    return list(desktop_io_operations_for_action(action))


def _manual_handoff_metadata(step: TaskStep) -> dict[str, object]:
    return {
        "manual_handoff_required": True,
        "handoff_prompt": step.handoff_prompt or step.text,
        "expected_operator_work": step.expected_operator_work,
        "resume_verification": _verification_metadata(step.verify),
    }


def _verification_metadata(
    verification: VerificationDefinition | None,
) -> dict[str, object] | None:
    if verification is None:
        return None
    return {
        "type": verification.type,
        "text": verification.text,
        "image": str(verification.image) if verification.image else None,
    }


def _success_evidence_metadata(
    observation: ScreenObservation,
    action_result: ActionResult,
    state_delta: dict[str, object],
    verification: VerificationResult,
) -> dict[str, object]:
    return {
        "success_evidence_type": "passed_action",
        "action_message": action_result.message,
        "verification_message": verification.message,
        "verification_outcome": verification.resolved_outcome,
        "post_action_evidence": _observation_evidence(
            observation,
            {"status": "not_captured_in_step_summary"},
        ),
        "state_delta": state_delta,
    }


def _visible_candidate_labels(
    candidates: tuple[ElementCandidate, ...],
) -> list[str]:
    return sorted(
        {
            candidate.label
            for candidate in candidates
            if candidate.visible and candidate.label
        }
    )


def _label_visible(
    label: str | None,
    candidates: tuple[ElementCandidate, ...],
) -> bool | None:
    if label is None:
        return None
    normalized_label = _normalize_text(label)
    return any(
        candidate.visible and normalized_label in _normalize_text(candidate.label)
        for candidate in candidates
    )


def _state_delta_target_text(step: TaskStep) -> str | None:
    if step.verify is not None and step.verify.text:
        return step.verify.text
    return step.target


def _focus_signature(observation: ScreenObservation) -> tuple[object, object]:
    return (
        observation.active_window_title,
        _metadata_dict(observation, "focused_element"),
    )


def _scroll_delta_metadata(
    step: TaskStep,
    action_result: ActionResult,
) -> dict[str, object]:
    scroll_moved = (
        action_result.success
        and action_result.metadata.get("input_action") == "scroll"
    )
    scroll_action = step.action if step.action in {"scroll", "scroll_until"} else None
    metadata: dict[str, object] = {
        "scroll_moved": scroll_moved,
        "scroll_action": scroll_action,
    }
    for key in (
        "scroll_clicks",
        "scroll_requested_clicks",
        "scroll_step_count",
        "scroll_step_clicks",
    ):
        if key in action_result.metadata:
            metadata[key] = action_result.metadata[key]
    return metadata


def _reasoning_snapshot_for_id(
    ranked: tuple[RankedCandidate, ...],
    candidate_id: str | None,
    observation: ScreenObservation,
) -> dict[str, object] | None:
    if candidate_id is None:
        return None
    for ranked_candidate in ranked:
        if ranked_candidate.candidate.id == candidate_id:
            return _candidate_reasoning_snapshot(ranked_candidate, observation)
    return None


def _candidate_reasoning_snapshot(
    ranked: RankedCandidate,
    observation: ScreenObservation,
    *,
    rejection_reason: str | None = None,
) -> dict[str, object]:
    candidate = ranked.candidate
    snapshot: dict[str, object] = {
        "id": candidate.id,
        "source": candidate.source,
        "label": candidate.label,
        "confidence": candidate.confidence,
        "enabled": candidate.enabled,
        "visible": candidate.visible,
        "rank": ranked.rank,
        "fusion_score": ranked.score,
        "target_match_score": ranked.target_match_score,
        "region_match_score": ranked.region_match_score,
        "bounds": _bounds_metadata(candidate.bounds),
        "coordinate_conversion": _coordinate_conversion_metadata(
            candidate,
            observation,
        ),
    }
    if rejection_reason is not None:
        snapshot["rejection_reason"] = rejection_reason
    return snapshot


def _coordinate_conversion_metadata(
    candidate: ElementCandidate,
    observation: ScreenObservation,
) -> dict[str, object]:
    screenshot_center = candidate.bounds.center
    metadata: dict[str, object] = {
        "screenshot_bounds": _bounds_metadata(candidate.bounds),
        "screenshot_center": list(screenshot_center),
        "monitor": _monitor_metadata(observation),
        "dpi_scale": _dpi_metadata(observation),
    }
    if observation.monitor is None:
        metadata["conversion_status"] = "unavailable"
        metadata["physical_bounds"] = None
        metadata["physical_center"] = None
        return metadata
    physical_bounds = screenshot_bounds_to_physical(
        candidate.bounds,
        observation.monitor,
    )
    physical_center = screenshot_point_to_physical(
        screenshot_center,
        observation.monitor,
    )
    metadata["conversion_status"] = "converted"
    metadata["physical_bounds"] = _bounds_metadata(physical_bounds)
    metadata["physical_center"] = list(physical_center)
    return metadata


def _bounds_metadata(bounds: Bounds) -> dict[str, object]:
    return {
        "x": bounds.x,
        "y": bounds.y,
        "width": bounds.width,
        "height": bounds.height,
        "center": list(bounds.center),
    }


def _metadata_dict(
    observation: ScreenObservation,
    key: str,
) -> dict[str, object] | None:
    value = observation.metadata.get(key)
    if isinstance(value, dict):
        return {str(item_key): item_value for item_key, item_value in value.items()}
    return None


def _monitor_metadata(observation: ScreenObservation) -> dict[str, object] | None:
    if observation.monitor is None:
        return None
    return {
        "left": observation.monitor.left,
        "top": observation.monitor.top,
        "width": observation.monitor.width,
        "height": observation.monitor.height,
        "scale_x": observation.monitor.scale_x,
        "scale_y": observation.monitor.scale_y,
        "is_primary": observation.monitor.is_primary,
    }


def _dpi_metadata(observation: ScreenObservation) -> dict[str, object] | None:
    if observation.monitor is None:
        return None
    return {
        "scale_x": observation.monitor.scale_x,
        "scale_y": observation.monitor.scale_y,
    }


def _candidates_by_source(
    candidates: tuple[ElementCandidate, ...],
) -> dict[str, list[dict[str, object]]]:
    grouped: dict[str, list[dict[str, object]]] = {
        "uia": [],
        "ocr": [],
        "image": [],
        "unknown": [],
    }
    for candidate in candidates:
        grouped.setdefault(candidate.source, []).append(
            _candidate_diagnostic(candidate)
        )
    return grouped


def _candidate_diagnostic(candidate: ElementCandidate) -> dict[str, object]:
    return {
        "id": candidate.id,
        "source": candidate.source,
        "label": candidate.label,
        "confidence": candidate.confidence,
        "visible": candidate.visible,
        "enabled": candidate.enabled,
        "bounds": {
            "x": candidate.bounds.x,
            "y": candidate.bounds.y,
            "width": candidate.bounds.width,
            "height": candidate.bounds.height,
            "center": list(candidate.bounds.center),
        },
        "metadata": candidate.metadata,
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
