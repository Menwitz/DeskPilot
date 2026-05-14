"""Bounded timing decisions for optional human-like execution profiles."""

from __future__ import annotations

import math
from dataclasses import dataclass

from desktop_agent.config import ExecutionProfile
from desktop_agent.perception import ElementCandidate
from desktop_agent.sampling import SampleRecord, SeededSampler
from desktop_agent.screen import Bounds, ScreenObservation
from desktop_agent.task_dsl import TaskStep, step_category

ACTION_COMPLEXITY_BY_TYPE: dict[str, float] = {
    "branch_if_visible": 0.2,
    "assert_visible": 0.2,
    "wait_for": 0.2,
    "press_key": 0.3,
    "type_text": 0.45,
    "click_uia": 0.5,
    "click_text": 0.6,
    "click_image": 0.65,
    "scroll": 0.7,
    "scroll_until": 0.75,
    "drag": 0.9,
}
DEFAULT_ACTION_COMPLEXITY = 0.5
RANDOM_TIMING_WEIGHT = 0.5
TARGET_TIMING_WEIGHT = 0.35
KLM_TIMING_WEIGHT = 0.15

KLM_OPERATOR_SECONDS: dict[str, float] = {
    "mental": 1.35,
    "system_wait": 0.7,
    "keying": 0.2,
    "pointing": 1.1,
    "homing": 0.4,
}
PERSONA_TIMING_BIAS: dict[str, float] = {
    "fast": -0.18,
    "normal": 0.0,
    "careful": 0.18,
}

POINTER_ACTIONS: frozenset[str] = frozenset(
    {
        "click_text",
        "click_image",
        "click_uia",
        "drag",
        "scroll",
        "scroll_until",
    },
)
KEYBOARD_ACTIONS: frozenset[str] = frozenset({"press_key", "type_text"})
ACTION_TIMED_ACTIONS: frozenset[str] = POINTER_ACTIONS | KEYBOARD_ACTIONS | frozenset(
    {"assert_visible"},
)
MENTAL_OPERATOR_COUNT_BY_CATEGORY: dict[str, int] = {
    "navigation": 1,
    "recognition": 1,
    "data_entry": 1,
    "verification": 1,
    "submission": 2,
}
BACKOFF_STRATEGIES: frozenset[str] = frozenset(
    {"bounded_linear", "bounded_exponential"}
)


@dataclass(frozen=True)
class KLMOperator:
    """Traceable Keystroke-Level-Model style operator used for timing analysis."""

    name: str
    count: int
    seconds_per_unit: float

    @property
    def total_seconds(self) -> float:
        return self.count * self.seconds_per_unit

    def metadata(self) -> dict[str, object]:
        return {
            "name": self.name,
            "count": self.count,
            "seconds_per_unit": self.seconds_per_unit,
            "total_seconds": self.total_seconds,
        }


@dataclass(frozen=True)
class ActionTimingContext:
    """Target and action features used to bias action timing safely."""

    action_type: str
    step_category: str
    target_id: str | None = None
    distance_pixels: float | None = None
    normalized_distance: float | None = None
    target_width_pixels: int | None = None
    target_height_pixels: int | None = None
    normalized_target_size: float | None = None
    action_complexity: float = DEFAULT_ACTION_COMPLEXITY
    target_complexity: float = DEFAULT_ACTION_COMPLEXITY
    input_mode: str | None = None
    keypress_count: int = 0

    def metadata(self) -> dict[str, object]:
        metadata: dict[str, object] = {
            "action_type": self.action_type,
            "step_category": self.step_category,
            "action_complexity": self.action_complexity,
            "target_complexity": self.target_complexity,
            "keypress_count": self.keypress_count,
        }
        if self.input_mode is not None:
            metadata["input_mode"] = self.input_mode
        if self.target_id is not None:
            metadata["target_id"] = self.target_id
        if self.distance_pixels is not None:
            metadata["distance_pixels"] = self.distance_pixels
        if self.normalized_distance is not None:
            metadata["normalized_distance"] = self.normalized_distance
        if self.target_width_pixels is not None:
            metadata["target_width_pixels"] = self.target_width_pixels
        if self.target_height_pixels is not None:
            metadata["target_height_pixels"] = self.target_height_pixels
        if self.normalized_target_size is not None:
            metadata["normalized_target_size"] = self.normalized_target_size
        return metadata


@dataclass(frozen=True)
class RetryBackoffContext:
    """Retry index and strategy used to keep retry waits within safe bounds."""

    retry_index: int
    retry_budget: int
    strategy: str

    def normalized(self) -> RetryBackoffContext:
        retry_budget = max(self.retry_budget, 1)
        retry_index = min(max(self.retry_index, 1), retry_budget)
        strategy = (
            self.strategy
            if self.strategy in BACKOFF_STRATEGIES
            else "bounded_linear"
        )
        return RetryBackoffContext(
            retry_index=retry_index,
            retry_budget=retry_budget,
            strategy=strategy,
        )

    def metadata(self, fraction: float) -> dict[str, object]:
        return {
            "retry_backoff_strategy": self.strategy,
            "retry_index": self.retry_index,
            "retry_budget": self.retry_budget,
            "retry_backoff_fraction": fraction,
            "retry_limit_respected": self.retry_index <= self.retry_budget,
        }


@dataclass(frozen=True)
class TimingDecision:
    """A traceable delay decision made before an action or retry."""

    phase: str
    delay_seconds: float
    lower_bound_seconds: float
    upper_bound_seconds: float
    hesitation_applied: bool
    movement_smoothness: float
    reason: str
    execution_persona: str = "normal"
    action_context: ActionTimingContext | None = None
    retry_backoff_context: RetryBackoffContext | None = None
    retry_backoff_fraction: float | None = None
    klm_operators: tuple[KLMOperator, ...] = ()
    random_seed: int | None = None
    sample_records: tuple[SampleRecord, ...] = ()

    def metadata(self) -> dict[str, object]:
        metadata: dict[str, object] = {
            "timing_phase": self.phase,
            "timing_model": "target_aware"
            if self.action_context is not None
            else "profile_bounds",
            "delay_seconds": self.delay_seconds,
            "lower_bound_seconds": self.lower_bound_seconds,
            "upper_bound_seconds": self.upper_bound_seconds,
            "hesitation_applied": self.hesitation_applied,
            "movement_smoothness": self.movement_smoothness,
            "execution_persona": self.execution_persona,
            "persona_timing_bias": _persona_timing_bias(self.execution_persona),
            "random_seed": self.random_seed,
            "sample_records": [
                record.metadata() for record in self.sample_records
            ],
        }
        if self.action_context is not None:
            metadata.update(self.action_context.metadata())
        if (
            self.retry_backoff_context is not None
            and self.retry_backoff_fraction is not None
        ):
            metadata.update(
                self.retry_backoff_context.metadata(self.retry_backoff_fraction),
            )
        if self.klm_operators:
            metadata["klm_operators"] = [
                operator.metadata() for operator in self.klm_operators
            ]
            metadata["klm_operator_counts"] = _klm_operator_counts(
                self.klm_operators,
            )
            metadata["klm_total_seconds"] = _klm_total_seconds(self.klm_operators)
        return metadata


@dataclass(frozen=True)
class StepTimingBudget:
    """Worst-case planned timing overhead for a step's configured timeout."""

    timeout_seconds: float
    attempt_count: int
    action_timing_slots: int
    retry_timing_slots: int
    planned_action_wait_seconds: float
    planned_retry_wait_seconds: float
    planned_wait_seconds: float

    @property
    def remaining_timeout_seconds(self) -> float:
        return self.timeout_seconds - self.planned_wait_seconds

    @property
    def fits_timeout(self) -> bool:
        return self.remaining_timeout_seconds >= 0

    def metadata(self) -> dict[str, object]:
        return {
            "timeout_seconds": self.timeout_seconds,
            "attempt_count": self.attempt_count,
            "action_timing_slots": self.action_timing_slots,
            "retry_timing_slots": self.retry_timing_slots,
            "planned_action_wait_seconds": self.planned_action_wait_seconds,
            "planned_retry_wait_seconds": self.planned_retry_wait_seconds,
            "planned_wait_seconds": self.planned_wait_seconds,
            "remaining_timeout_seconds": self.remaining_timeout_seconds,
            "fits_timeout": self.fits_timeout,
        }


@dataclass(frozen=True)
class ActionVariantDecision:
    """Deterministic choice among task-author-approved equivalent actions."""

    selected_action: str
    available_actions: tuple[str, ...]
    distribution: str
    randomized: bool
    random_seed: int | None = None
    sample_records: tuple[SampleRecord, ...] = ()

    def metadata(self) -> dict[str, object]:
        return {
            "selected_action": self.selected_action,
            "available_action_variants": list(self.available_actions),
            "action_variant_distribution": self.distribution,
            "action_variant_randomized": self.randomized,
            "random_seed": self.random_seed,
            "sample_records": [
                record.metadata() for record in self.sample_records
            ],
        }


class ExecutionTimingController:
    """Samples safe timing values without changing task intent or action order."""

    def __init__(self, profile: ExecutionProfile) -> None:
        self._profile = profile
        self._sampler = SeededSampler(profile.random_seed)
        self._last_input_mode: str | None = None

    def before_action(
        self,
        context: ActionTimingContext | None = None,
    ) -> TimingDecision:
        return self._sample("action", self._profile.action_delay_seconds, context)

    def before_retry(
        self,
        *,
        retry_index: int | None = None,
        retry_budget: int | None = None,
        backoff_strategy: str = "bounded_linear",
    ) -> TimingDecision:
        retry_backoff_context = None
        if retry_index is not None and retry_budget is not None:
            retry_backoff_context = RetryBackoffContext(
                retry_index=retry_index,
                retry_budget=retry_budget,
                strategy=backoff_strategy,
            ).normalized()
        return self._sample(
            "retry",
            self._profile.retry_delay_seconds,
            None,
            (KLMOperator("system_wait", 1, KLM_OPERATOR_SECONDS["system_wait"]),),
            retry_backoff_context=retry_backoff_context,
        )

    def select_action_variant(self, step: TaskStep) -> ActionVariantDecision:
        sample_start = self._sampler.sample_count
        available_actions = _available_action_variants(step)
        randomized = self._profile.enabled and len(available_actions) > 1
        selected_index = 0
        if randomized:
            selected_index = self._sampler.index(
                "action_variant",
                len(available_actions),
                self._profile.action_variant_distribution,
            )
        return ActionVariantDecision(
            selected_action=available_actions[selected_index],
            available_actions=available_actions,
            distribution=self._profile.action_variant_distribution,
            randomized=randomized,
            random_seed=self._sampler.seed,
            sample_records=self._sampler.records_since(sample_start),
        )

    def _sample(
        self,
        phase: str,
        bounds: tuple[float, float],
        context: ActionTimingContext | None,
        klm_operators: tuple[KLMOperator, ...] | None = None,
        retry_backoff_context: RetryBackoffContext | None = None,
    ) -> TimingDecision:
        sample_start = self._sampler.sample_count
        if klm_operators is None:
            klm_operators = self._klm_operators_for_action(context)
        lower, upper = bounds
        if not self._profile.enabled:
            return TimingDecision(
                phase=phase,
                delay_seconds=0.0,
                lower_bound_seconds=0.0,
                upper_bound_seconds=0.0,
                hesitation_applied=False,
                movement_smoothness=0.0,
                reason="execution profile disabled",
                execution_persona=self._profile.persona,
                action_context=context,
                retry_backoff_context=retry_backoff_context,
                retry_backoff_fraction=0.0
                if retry_backoff_context is not None
                else None,
                klm_operators=klm_operators,
                random_seed=self._sampler.seed,
                sample_records=self._sampler.records_since(sample_start),
            )

        hesitation_applied = phase == "action" and self._sampler.probability(
            "timing.hesitation",
            self._profile.hesitation_probability,
        )
        sample_lower = lower
        if hesitation_applied:
            # Hesitation is modeled by sampling the upper half of the same safe
            # range, so the decision never exceeds configured bounds.
            sample_lower = lower + ((upper - lower) / 2)

        random_fraction = self._sampler.fraction(
            f"timing.{phase}.fraction",
            self._distribution_for_phase(phase),
        )
        timing_fraction = random_fraction
        if phase == "action" and context is not None:
            timing_fraction = _clamp(
                (random_fraction * RANDOM_TIMING_WEIGHT)
                + (context.target_complexity * TARGET_TIMING_WEIGHT)
                + (_klm_complexity(klm_operators) * KLM_TIMING_WEIGHT)
            )
        timing_fraction = _clamp(
            timing_fraction + _persona_timing_bias(self._profile.persona),
        )
        retry_backoff_fraction = None
        if phase == "retry" and retry_backoff_context is not None:
            retry_backoff_fraction = _retry_backoff_fraction(
                timing_fraction,
                retry_backoff_context,
            )
            timing_fraction = retry_backoff_fraction

        return TimingDecision(
            phase=phase,
            delay_seconds=sample_lower + ((upper - sample_lower) * timing_fraction),
            lower_bound_seconds=lower,
            upper_bound_seconds=upper,
            hesitation_applied=hesitation_applied,
            movement_smoothness=self._profile.movement_smoothness,
            reason="target-aware action timing decided"
            if phase == "action" and context is not None
            else f"{phase} timing decided",
            execution_persona=self._profile.persona,
            action_context=context,
            retry_backoff_context=retry_backoff_context,
            retry_backoff_fraction=retry_backoff_fraction,
            klm_operators=klm_operators,
            random_seed=self._sampler.seed,
            sample_records=self._sampler.records_since(sample_start),
        )

    def _klm_operators_for_action(
        self,
        context: ActionTimingContext | None,
    ) -> tuple[KLMOperator, ...]:
        if context is None:
            return ()
        operators = _build_klm_operators(context, self._last_input_mode)
        if context.input_mode is not None:
            self._last_input_mode = context.input_mode
        return operators

    def _distribution_for_phase(self, phase: str) -> str:
        if phase == "retry":
            return self._profile.retry_delay_distribution
        return self._profile.action_delay_distribution


def build_action_timing_context(
    step: TaskStep,
    target: ElementCandidate | None,
    observation: ScreenObservation,
) -> ActionTimingContext:
    """Build target-aware timing context from the selected UI candidate."""

    bounds = target.bounds if target is not None else _region_bounds(step)
    distance_pixels, normalized_distance = _distance_features(bounds, observation)
    normalized_target_size = _normalized_target_size(bounds, observation)
    action_complexity = _action_complexity(step.action)
    target_complexity = _target_complexity(
        has_bounds=bounds is not None,
        normalized_distance=normalized_distance,
        normalized_target_size=normalized_target_size,
        action_complexity=action_complexity,
    )
    return ActionTimingContext(
        action_type=step.action,
        step_category=step_category(step),
        target_id=target.id if target else None,
        distance_pixels=distance_pixels,
        normalized_distance=normalized_distance,
        target_width_pixels=bounds.width if bounds else None,
        target_height_pixels=bounds.height if bounds else None,
        normalized_target_size=normalized_target_size,
        action_complexity=action_complexity,
        target_complexity=target_complexity,
        input_mode=_input_mode(step.action),
        keypress_count=_keypress_count(step),
    )


def estimate_step_timing_budget(
    step: TaskStep,
    profile: ExecutionProfile,
    *,
    default_timeout_seconds: float,
    max_retries_per_step: int,
) -> StepTimingBudget:
    """Estimate worst-case profile waits that must fit inside a step timeout."""

    retry_budget = step.retry if step.retry is not None else max_retries_per_step
    attempt_count = retry_budget + 1
    action_timing_slots = _action_timing_slots(step, attempt_count)
    retry_timing_slots = _retry_timing_slots(step, retry_budget)
    action_wait_seconds = 0.0
    retry_wait_seconds = 0.0
    if profile.enabled:
        action_wait_seconds = action_timing_slots * profile.action_delay_seconds[1]
        retry_wait_seconds = retry_timing_slots * profile.retry_delay_seconds[1]
    return StepTimingBudget(
        timeout_seconds=step.timeout_seconds or default_timeout_seconds,
        attempt_count=attempt_count,
        action_timing_slots=action_timing_slots,
        retry_timing_slots=retry_timing_slots,
        planned_action_wait_seconds=action_wait_seconds,
        planned_retry_wait_seconds=retry_wait_seconds,
        planned_wait_seconds=action_wait_seconds + retry_wait_seconds,
    )


def _action_timing_slots(step: TaskStep, attempt_count: int) -> int:
    if step.action == "scroll_until":
        return attempt_count
    if step.action in ACTION_TIMED_ACTIONS:
        return attempt_count
    return 0


def _retry_timing_slots(step: TaskStep, retry_budget: int) -> int:
    if step.action in {"branch_if_visible", "scroll_until", "wait_for"}:
        return 0
    return retry_budget


def _retry_backoff_fraction(
    sample_fraction: float,
    context: RetryBackoffContext,
) -> float:
    lower_fraction, upper_fraction = _backoff_segment(context)
    return _clamp(
        lower_fraction + ((upper_fraction - lower_fraction) * sample_fraction),
    )


def _backoff_segment(context: RetryBackoffContext) -> tuple[float, float]:
    retry_index = context.retry_index
    retry_budget = context.retry_budget
    if context.strategy == "bounded_exponential":
        weights = tuple(2**index for index in range(retry_budget))
        total = sum(weights)
        lower = sum(weights[: retry_index - 1]) / total
        upper = sum(weights[:retry_index]) / total
        return lower, upper
    width = 1 / retry_budget
    return (retry_index - 1) * width, retry_index * width


def _available_action_variants(step: TaskStep) -> tuple[str, ...]:
    variants = [step.action]
    for variant in step.safe_action_variants:
        if variant not in variants:
            variants.append(variant)
    return tuple(variants)


def _build_klm_operators(
    context: ActionTimingContext,
    previous_input_mode: str | None,
) -> tuple[KLMOperator, ...]:
    operators: list[KLMOperator] = []
    mental_count = MENTAL_OPERATOR_COUNT_BY_CATEGORY.get(context.step_category, 1)
    if mental_count > 0:
        operators.append(
            KLMOperator("mental", mental_count, KLM_OPERATOR_SECONDS["mental"]),
        )
    if context.input_mode == "keyboard" and context.keypress_count > 0:
        operators.append(
            KLMOperator(
                "keying",
                context.keypress_count,
                KLM_OPERATOR_SECONDS["keying"],
            ),
        )
    if context.input_mode == "pointer":
        operators.append(
            KLMOperator("pointing", 1, KLM_OPERATOR_SECONDS["pointing"]),
        )
    if (
        previous_input_mode is not None
        and context.input_mode in {"keyboard", "pointer"}
        and previous_input_mode in {"keyboard", "pointer"}
        and context.input_mode != previous_input_mode
    ):
        # Homing is only recorded after the controller has observed a prior
        # input mode, which keeps the first action from getting a fake switch.
        operators.append(
            KLMOperator("homing", 1, KLM_OPERATOR_SECONDS["homing"]),
        )
    return tuple(operators)


def _input_mode(action_type: str) -> str | None:
    if action_type in POINTER_ACTIONS:
        return "pointer"
    if action_type in KEYBOARD_ACTIONS:
        return "keyboard"
    return None


def _keypress_count(step: TaskStep) -> int:
    if step.action == "type_text":
        return len(step.text or "")
    if step.action == "press_key":
        return 1
    return 0


def _region_bounds(step: TaskStep) -> Bounds | None:
    if step.region is None:
        return None
    return Bounds(
        x=step.region.x,
        y=step.region.y,
        width=step.region.width,
        height=step.region.height,
    )


def _distance_features(
    bounds: Bounds | None,
    observation: ScreenObservation,
) -> tuple[float | None, float | None]:
    if bounds is None or observation.size[0] <= 0 or observation.size[1] <= 0:
        return None, None

    target_x, target_y = bounds.center
    screen_width, screen_height = observation.size
    screen_center_x = screen_width / 2
    screen_center_y = screen_height / 2
    distance_pixels = math.hypot(
        target_x - screen_center_x,
        target_y - screen_center_y,
    )
    screen_diagonal = math.hypot(screen_width, screen_height)
    if screen_diagonal <= 0:
        return distance_pixels, None
    return distance_pixels, _clamp(distance_pixels / screen_diagonal)


def _normalized_target_size(
    bounds: Bounds | None,
    observation: ScreenObservation,
) -> float | None:
    if bounds is None or observation.size[0] <= 0 or observation.size[1] <= 0:
        return None
    target_diagonal = math.hypot(bounds.width, bounds.height)
    screen_diagonal = math.hypot(observation.size[0], observation.size[1])
    if screen_diagonal <= 0:
        return None
    return _clamp(target_diagonal / screen_diagonal)


def _action_complexity(action_type: str) -> float:
    return ACTION_COMPLEXITY_BY_TYPE.get(action_type, DEFAULT_ACTION_COMPLEXITY)


def _target_complexity(
    *,
    has_bounds: bool,
    normalized_distance: float | None,
    normalized_target_size: float | None,
    action_complexity: float,
) -> float:
    if not has_bounds:
        return action_complexity

    # Farther targets and smaller targets bias timing toward the upper bound,
    # while the configured bounds still define the hard safety envelope.
    distance_component = normalized_distance if normalized_distance is not None else 0.5
    size_component = (
        1.0 - normalized_target_size
        if normalized_target_size is not None
        else 0.5
    )
    return _clamp(
        (distance_component * 0.45)
        + (size_component * 0.35)
        + (action_complexity * 0.20)
    )


def _klm_operator_counts(operators: tuple[KLMOperator, ...]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for operator in operators:
        counts[operator.name] = counts.get(operator.name, 0) + operator.count
    return counts


def _klm_total_seconds(operators: tuple[KLMOperator, ...]) -> float:
    return sum(operator.total_seconds for operator in operators)


def _klm_complexity(operators: tuple[KLMOperator, ...]) -> float:
    # The KLM estimate biases the sampled point within configured bounds; it
    # never expands the actual lower or upper delay limits.
    return _clamp(_klm_total_seconds(operators) / 6.0)


def _persona_timing_bias(persona: str) -> float:
    return PERSONA_TIMING_BIAS.get(persona, 0.0)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
