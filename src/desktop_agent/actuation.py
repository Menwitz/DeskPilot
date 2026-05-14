"""Action execution adapters for local desktop input."""

from __future__ import annotations

import ctypes
import math
import sys
import time
from ctypes import wintypes
from dataclasses import dataclass, field, replace
from typing import Any, Literal, Protocol

from desktop_agent.config import RuntimeConfig
from desktop_agent.perception import ElementCandidate
from desktop_agent.sampling import SampleRecord, SeededSampler
from desktop_agent.screen import (
    Bounds,
    ScreenObservation,
    screenshot_bounds_to_physical,
    screenshot_point_to_physical,
)
from desktop_agent.task_dsl import TaskRegion, TaskStep

MouseButton = Literal["left", "right", "middle"]

_CLICK_ACTIONS = {"click_text", "click_image", "click_uia"}
_PASSIVE_ACTIONS = {"wait_for", "assert_visible", "branch_if_visible"}
_REGION_GUARDED_ACTIONS = _CLICK_ACTIONS | {"scroll", "scroll_until"}
_DEFAULT_SCROLL_CLICKS = -3


@dataclass(frozen=True)
class ActionResult:
    """Outcome returned by an input adapter after a step action is attempted."""

    success: bool
    message: str
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ActuationProfile:
    """Bounded movement and timing settings for desktop input."""

    movement_duration_seconds: tuple[float, float] = (0.05, 0.20)
    timing_variation_seconds: tuple[float, float] = (0.0, 0.03)
    keyboard_interval_seconds: tuple[float, float] = (0.0, 0.0)
    scroll_interval_seconds: tuple[float, float] = (0.0, 0.0)
    movement_steps: int = 12
    movement_smoothness: float = 0.65
    overshoot_probability: float = 0.0
    overshoot_pixels: tuple[float, float] = (0.0, 0.0)
    settle_duration_seconds: tuple[float, float] = (0.0, 0.0)
    random_seed: int | None = None

    def __post_init__(self) -> None:
        _validate_seconds_pair(
            self.movement_duration_seconds,
            "movement_duration_seconds",
        )
        _validate_seconds_pair(
            self.timing_variation_seconds,
            "timing_variation_seconds",
        )
        _validate_seconds_pair(
            self.keyboard_interval_seconds,
            "keyboard_interval_seconds",
        )
        _validate_seconds_pair(
            self.scroll_interval_seconds,
            "scroll_interval_seconds",
        )
        _validate_seconds_pair(
            self.overshoot_pixels,
            "overshoot_pixels",
        )
        _validate_seconds_pair(
            self.settle_duration_seconds,
            "settle_duration_seconds",
        )
        if self.movement_steps <= 0:
            raise ValueError("movement_steps must be greater than zero")
        if self.movement_smoothness < 0 or self.movement_smoothness > 1:
            raise ValueError("movement_smoothness must be between 0 and 1")
        if self.overshoot_probability < 0 or self.overshoot_probability > 1:
            raise ValueError("overshoot_probability must be between 0 and 1")


@dataclass(frozen=True)
class PointerTimingContext:
    """Physical pointer movement geometry used by pointer timing models."""

    start: tuple[int, int]
    end: tuple[int, int]
    target_width_pixels: float | None = None
    target_height_pixels: float | None = None

    @property
    def distance_pixels(self) -> float:
        return math.hypot(self.end[0] - self.start[0], self.end[1] - self.start[1])

    @property
    def effective_target_width_pixels(self) -> float:
        if (
            self.target_width_pixels is None
            or self.target_height_pixels is None
            or self.target_width_pixels <= 0
            or self.target_height_pixels <= 0
        ):
            return 1.0
        return min(self.target_width_pixels, self.target_height_pixels)


@dataclass(frozen=True)
class PointerTimingEstimate:
    """Traceable pointer timing estimate emitted by a movement model."""

    model: str
    duration_seconds: float
    distance_pixels: float
    effective_target_width_pixels: float
    index_of_difficulty: float

    def metadata(self) -> dict[str, object]:
        return {
            "pointer_timing_model": self.model,
            "pointer_model_duration_seconds": self.duration_seconds,
            "pointer_distance_pixels": self.distance_pixels,
            "pointer_effective_target_width_pixels": (
                self.effective_target_width_pixels
            ),
            "pointer_index_of_difficulty": self.index_of_difficulty,
        }


class PointerTimingModel(Protocol):
    """Interface for local pointer timing duration estimates."""

    def estimate(self, context: PointerTimingContext) -> PointerTimingEstimate: ...


@dataclass(frozen=True)
class FittsLawPointerTimingModel:
    """Simple Fitts' Law-inspired model for bounded local pointer timing."""

    intercept_seconds: float = 0.05
    slope_seconds: float = 0.08
    minimum_target_width_pixels: float = 1.0

    def estimate(self, context: PointerTimingContext) -> PointerTimingEstimate:
        width = max(
            context.effective_target_width_pixels,
            self.minimum_target_width_pixels,
        )
        distance = context.distance_pixels
        index_of_difficulty = math.log2((distance / width) + 1)
        return PointerTimingEstimate(
            model="fitts_law",
            duration_seconds=self.intercept_seconds
            + (self.slope_seconds * index_of_difficulty),
            distance_pixels=distance,
            effective_target_width_pixels=width,
            index_of_difficulty=index_of_difficulty,
        )


@dataclass(frozen=True)
class MovementPlan:
    """Concrete physical mouse path emitted by the movement planner."""

    points: tuple[tuple[int, int], ...]
    duration_seconds: float
    timing_estimate: PointerTimingEstimate | None = None
    path_model: str = "minimum_jerk_quadratic_bezier"
    overshoot_applied: bool = False
    overshoot_point: tuple[int, int] | None = None
    settle_duration_seconds: float = 0.0
    random_seed: int | None = None
    sample_records: tuple[SampleRecord, ...] = ()

    @property
    def step_delay_seconds(self) -> float:
        if len(self.points) <= 1:
            return 0.0
        return self.movement_duration_seconds / len(self.points)

    @property
    def movement_duration_seconds(self) -> float:
        return max(0.0, self.duration_seconds - self.settle_duration_seconds)


@dataclass(frozen=True)
class KeyboardCadencePlan:
    """Text cadence emitted by the desktop actuator without changing text."""

    text: str
    interval_seconds: tuple[float, ...] = ()
    random_seed: int | None = None
    sample_records: tuple[SampleRecord, ...] = ()

    def metadata(self) -> dict[str, object]:
        return {
            "keyboard_cadence_applied": bool(self.interval_seconds),
            "keyboard_interval_count": len(self.interval_seconds),
            "keyboard_interval_seconds": list(self.interval_seconds),
            "random_seed": self.random_seed,
            "sample_records": [
                record.metadata() for record in self.sample_records
            ],
        }


@dataclass(frozen=True)
class ScrollCadencePlan:
    """Wheel cadence emitted by the desktop actuator without changing distance."""

    requested_clicks: int
    step_clicks: tuple[int, ...]
    interval_seconds: tuple[float, ...] = ()
    random_seed: int | None = None
    sample_records: tuple[SampleRecord, ...] = ()

    def metadata(self) -> dict[str, object]:
        return {
            "scroll_cadence_applied": bool(self.interval_seconds),
            "scroll_requested_clicks": self.requested_clicks,
            "scroll_step_count": len(self.step_clicks),
            "scroll_step_clicks": list(self.step_clicks),
            "scroll_interval_count": len(self.interval_seconds),
            "scroll_interval_seconds": list(self.interval_seconds),
            "random_seed": self.random_seed,
            "sample_records": [
                record.metadata() for record in self.sample_records
            ],
        }


@dataclass(frozen=True)
class InputEvent:
    """Recorded fake-backend event used by tests."""

    kind: str
    point: tuple[int, int] | None = None
    button: MouseButton | None = None
    text: str | None = None
    key: str | None = None
    clicks: int | None = None
    duration_seconds: float | None = None


class Actuator(Protocol):
    """Interface for platform-specific input adapters."""

    def execute(
        self,
        step: TaskStep,
        target: ElementCandidate | None,
        observation: ScreenObservation,
        config: RuntimeConfig,
    ) -> ActionResult: ...


class InputBackend(Protocol):
    """Low-level OS input boundary used by the high-level actuator."""

    def current_position(self) -> tuple[int, int]: ...

    def move_to(self, point: tuple[int, int]) -> None: ...

    def mouse_down(self, point: tuple[int, int], button: MouseButton) -> None: ...

    def mouse_up(self, point: tuple[int, int], button: MouseButton) -> None: ...

    def scroll(self, point: tuple[int, int], clicks: int) -> None: ...

    def type_text(self, text: str) -> None: ...

    def key_down(self, key: str) -> None: ...

    def key_up(self, key: str) -> None: ...

    def press_key(self, key: str) -> None: ...

    def active_window_title(self) -> str | None: ...

    def sleep(self, seconds: float) -> None: ...


class EmergencyStopChecker(Protocol):
    """Optional final emergency-stop guard checked by real input adapters."""

    def is_triggered(self, config: RuntimeConfig) -> bool: ...


class DryRunActuator(Actuator):
    """Adapter used by tests and dry-run flows where no input is sent."""

    def execute(
        self,
        step: TaskStep,
        target: ElementCandidate | None,
        observation: ScreenObservation,
        config: RuntimeConfig,
    ) -> ActionResult:
        _ = target, observation, config
        return ActionResult(success=True, message=f"planned {step.action}")


class UnavailableActuator(Actuator):
    """Adapter used where real desktop input is not available."""

    def execute(
        self,
        step: TaskStep,
        target: ElementCandidate | None,
        observation: ScreenObservation,
        config: RuntimeConfig,
    ) -> ActionResult:
        _ = step, target, observation, config
        return ActionResult(
            success=False,
            message="desktop actuation is unavailable on this platform; use dry-run",
        )


class SmoothMovementPlanner:
    """Builds small eased mouse paths between physical coordinates."""

    def __init__(
        self,
        profile: ActuationProfile | None = None,
        timing_model: PointerTimingModel | None = None,
    ) -> None:
        self._profile = profile or ActuationProfile()
        self._timing_model = timing_model or FittsLawPointerTimingModel()
        self._sampler = SeededSampler(self._profile.random_seed)

    def plan(
        self,
        start: tuple[int, int],
        end: tuple[int, int],
        target_size_pixels: tuple[float, float] | None = None,
    ) -> MovementPlan:
        sample_start = self._sampler.sample_count
        estimate = self._timing_model.estimate(
            PointerTimingContext(
                start=start,
                end=end,
                target_width_pixels=target_size_pixels[0]
                if target_size_pixels
                else None,
                target_height_pixels=target_size_pixels[1]
                if target_size_pixels
                else None,
            )
        )
        bounded_duration = _clamp_seconds(
            estimate.duration_seconds,
            self._profile.movement_duration_seconds,
        )
        estimate = replace(estimate, duration_seconds=bounded_duration)
        settle_duration = self._sample_seconds(
            "actuation.settle_duration",
            self._profile.settle_duration_seconds,
        )
        duration = (
            bounded_duration
            + self._sample_seconds(
                "actuation.timing_variation",
                self._profile.timing_variation_seconds,
            )
            + settle_duration
        )
        if start == end:
            return MovementPlan(
                points=(end,),
                duration_seconds=duration,
                timing_estimate=estimate,
                settle_duration_seconds=settle_duration,
                random_seed=self._sampler.seed,
                sample_records=self._sampler.records_since(sample_start),
            )

        overshoot_point = self._overshoot_point(start, end, target_size_pixels)
        points = self._path_points(start, overshoot_point or end)
        path_model = "minimum_jerk_quadratic_bezier"
        if overshoot_point is not None:
            correction_steps = max(2, self._profile.movement_steps // 3)
            points += self._path_points(overshoot_point, end, correction_steps)
            path_model = "minimum_jerk_quadratic_bezier_with_correction"
        return MovementPlan(
            points=points,
            duration_seconds=duration,
            timing_estimate=estimate,
            path_model=path_model,
            overshoot_applied=overshoot_point is not None,
            overshoot_point=overshoot_point,
            settle_duration_seconds=settle_duration,
            random_seed=self._sampler.seed,
            sample_records=self._sampler.records_since(sample_start),
        )

    def _sample_seconds(self, label: str, bounds: tuple[float, float]) -> float:
        lower, upper = bounds
        if lower == upper:
            return lower
        return self._sampler.uniform(label, bounds)

    def _control_point(
        self,
        start: tuple[int, int],
        end: tuple[int, int],
    ) -> tuple[float, float]:
        start_x, start_y = start
        end_x, end_y = end
        mid_x = (start_x + end_x) / 2
        mid_y = (start_y + end_y) / 2
        delta_x = end_x - start_x
        delta_y = end_y - start_y
        distance = math.hypot(delta_x, delta_y)
        if distance == 0:
            return (mid_x, mid_y)

        bend = distance * 0.18 * self._profile.movement_smoothness
        direction = (
            -1
            if self._sampler.probability("actuation.control_direction", 0.5)
            else 1
        )
        normal_x = -delta_y / distance
        normal_y = delta_x / distance
        return (
            mid_x + normal_x * bend * direction,
            mid_y + normal_y * bend * direction,
        )

    def _path_points(
        self,
        start: tuple[int, int],
        end: tuple[int, int],
        steps: int | None = None,
    ) -> tuple[tuple[int, int], ...]:
        step_count = steps or self._profile.movement_steps
        control = self._control_point(start, end)
        return tuple(
            _quadratic_bezier(
                start,
                control,
                end,
                _minimum_jerk(index / step_count),
            )
            for index in range(1, step_count + 1)
        )

    def _overshoot_point(
        self,
        start: tuple[int, int],
        end: tuple[int, int],
        target_size_pixels: tuple[float, float] | None,
    ) -> tuple[int, int] | None:
        if (
            target_size_pixels is None
            or self._profile.overshoot_probability <= 0
            or not self._sampler.probability(
                "actuation.overshoot",
                self._profile.overshoot_probability,
            )
        ):
            return None

        distance = math.hypot(end[0] - start[0], end[1] - start[1])
        if distance == 0:
            return None

        safe_limit = max(0.0, (min(target_size_pixels) / 2) - 1)
        overshoot_pixels = min(
            self._sample_seconds(
                "actuation.overshoot_pixels",
                self._profile.overshoot_pixels,
            ),
            safe_limit,
        )
        if overshoot_pixels <= 0:
            return None

        unit_x = (end[0] - start[0]) / distance
        unit_y = (end[1] - start[1]) / distance
        return (
            round(end[0] + (unit_x * overshoot_pixels)),
            round(end[1] + (unit_y * overshoot_pixels)),
        )


class DesktopActuator(Actuator):
    """Executes high-level task actions through a low-level input backend."""

    def __init__(
        self,
        backend: InputBackend,
        profile: ActuationProfile | None = None,
        emergency_stop_monitor: EmergencyStopChecker | None = None,
    ) -> None:
        self._profile = profile or ActuationProfile()
        self._backend = backend
        self._emergency_stop_monitor = emergency_stop_monitor
        self._movement_planner = SmoothMovementPlanner(self._profile)
        self._keyboard_sampler = SeededSampler(self._profile.random_seed)
        self._scroll_sampler = SeededSampler(self._profile.random_seed)

    def execute(
        self,
        step: TaskStep,
        target: ElementCandidate | None,
        observation: ScreenObservation,
        config: RuntimeConfig,
    ) -> ActionResult:
        blocked = self._blocked_by_active_window(config)
        if blocked is not None:
            return blocked
        blocked = self._blocked_by_allowed_region(step, target)
        if blocked is not None:
            return blocked
        blocked = self._blocked_by_emergency_stop(config)
        if blocked is not None:
            return blocked

        try:
            if step.action in _PASSIVE_ACTIONS:
                return ActionResult(True, f"observed {step.action}")
            if step.action in _CLICK_ACTIONS:
                return self._execute_click(step, target, observation)
            if step.action == "type_text":
                return self._execute_type_text(step)
            if step.action == "press_key":
                return self._execute_press_key(step)
            if step.action in {"scroll", "scroll_until"}:
                return self._execute_scroll(step, target, observation)
            if step.action == "drag":
                return self._execute_drag(step, target, observation)
        except ActuationError as exc:
            return ActionResult(False, str(exc))

        return ActionResult(False, f"unsupported actuation action: {step.action}")

    def move_mouse(
        self,
        point: tuple[int, int],
        target_size_pixels: tuple[float, float] | None = None,
    ) -> MovementPlan:
        start = self._backend.current_position()
        plan = self._movement_planner.plan(start, point, target_size_pixels)
        for path_point in plan.points:
            self._backend.move_to(path_point)
            if plan.step_delay_seconds > 0:
                self._backend.sleep(plan.step_delay_seconds)
        if plan.settle_duration_seconds > 0:
            self._backend.sleep(plan.settle_duration_seconds)
        return plan

    def click(
        self,
        point: tuple[int, int],
        button: MouseButton = "left",
        *,
        target_size_pixels: tuple[float, float] | None = None,
    ) -> MovementPlan:
        plan = self.move_mouse(point, target_size_pixels)
        self._backend.mouse_down(point, button)
        self._backend.mouse_up(point, button)
        return plan

    def double_click(
        self,
        point: tuple[int, int],
        button: MouseButton = "left",
        *,
        target_size_pixels: tuple[float, float] | None = None,
    ) -> MovementPlan:
        plan = self.click(point, button, target_size_pixels=target_size_pixels)
        self._backend.sleep(0.05)
        self._backend.mouse_down(point, button)
        self._backend.mouse_up(point, button)
        return plan

    def drag(
        self,
        start: tuple[int, int],
        end: tuple[int, int],
        button: MouseButton = "left",
        *,
        start_target_size_pixels: tuple[float, float] | None = None,
        end_target_size_pixels: tuple[float, float] | None = None,
    ) -> MovementPlan:
        plan = self.move_mouse(start, start_target_size_pixels)
        self._backend.mouse_down(start, button)
        drag_plan = self.move_mouse(end, end_target_size_pixels)
        self._backend.mouse_up(end, button)
        return MovementPlan(
            points=plan.points + drag_plan.points,
            duration_seconds=plan.duration_seconds + drag_plan.duration_seconds,
            path_model="combined_drag",
            overshoot_applied=plan.overshoot_applied or drag_plan.overshoot_applied,
            overshoot_point=drag_plan.overshoot_point or plan.overshoot_point,
            settle_duration_seconds=(
                plan.settle_duration_seconds + drag_plan.settle_duration_seconds
            ),
            random_seed=drag_plan.random_seed
            if drag_plan.random_seed is not None
            else plan.random_seed,
            sample_records=plan.sample_records + drag_plan.sample_records,
        )

    def scroll(
        self,
        point: tuple[int, int],
        clicks: int,
        target_size_pixels: tuple[float, float] | None = None,
    ) -> ScrollCadencePlan:
        self.move_mouse(point, target_size_pixels)
        interval_bounds = self._profile.scroll_interval_seconds
        if clicks == 0 or abs(clicks) <= 1 or interval_bounds == (0.0, 0.0):
            self._backend.scroll(point, clicks)
            return ScrollCadencePlan(
                requested_clicks=clicks,
                step_clicks=(clicks,),
                random_seed=self._scroll_sampler.seed,
            )

        sample_start = self._scroll_sampler.sample_count
        direction = 1 if clicks > 0 else -1
        step_clicks: list[int] = []
        intervals: list[float] = []
        for index in range(abs(clicks)):
            self._backend.scroll(point, direction)
            step_clicks.append(direction)
            if index == abs(clicks) - 1:
                continue
            interval = self._sample_scroll_interval()
            intervals.append(interval)
            self._backend.sleep(interval)
        return ScrollCadencePlan(
            requested_clicks=clicks,
            step_clicks=tuple(step_clicks),
            interval_seconds=tuple(intervals),
            random_seed=self._scroll_sampler.seed,
            sample_records=self._scroll_sampler.records_since(sample_start),
        )

    def type_text(self, text: str) -> KeyboardCadencePlan:
        interval_bounds = self._profile.keyboard_interval_seconds
        if len(text) <= 1 or interval_bounds == (0.0, 0.0):
            # Preserve the legacy single-call path unless a cadence profile is active.
            self._backend.type_text(text)
            return KeyboardCadencePlan(
                text=text,
                random_seed=self._keyboard_sampler.seed,
            )

        sample_start = self._keyboard_sampler.sample_count
        intervals: list[float] = []
        for index, character in enumerate(text):
            self._backend.type_text(character)
            if index == len(text) - 1:
                continue
            interval = self._sample_keyboard_interval()
            intervals.append(interval)
            self._backend.sleep(interval)
        return KeyboardCadencePlan(
            text=text,
            interval_seconds=tuple(intervals),
            random_seed=self._keyboard_sampler.seed,
            sample_records=self._keyboard_sampler.records_since(sample_start),
        )

    def _sample_keyboard_interval(self) -> float:
        lower, upper = self._profile.keyboard_interval_seconds
        if lower == upper:
            return lower
        return self._keyboard_sampler.uniform(
            "actuation.keyboard_interval",
            self._profile.keyboard_interval_seconds,
        )

    def _sample_scroll_interval(self) -> float:
        lower, upper = self._profile.scroll_interval_seconds
        if lower == upper:
            return lower
        return self._scroll_sampler.uniform(
            "actuation.scroll_interval",
            self._profile.scroll_interval_seconds,
        )

    def press_key_or_chord(self, value: str) -> None:
        parts = tuple(part.strip() for part in value.split("+") if part.strip())
        if not parts:
            raise ActuationError("key value must not be blank")
        if len(parts) == 1:
            self._backend.press_key(parts[0])
            return

        modifiers = parts[:-1]
        key = parts[-1]
        for modifier in modifiers:
            self._backend.key_down(modifier)
        try:
            self._backend.press_key(key)
        finally:
            for modifier in reversed(modifiers):
                self._backend.key_up(modifier)

    def _execute_click(
        self,
        step: TaskStep,
        target: ElementCandidate | None,
        observation: ScreenObservation,
    ) -> ActionResult:
        point = _target_point(target, observation)
        plan = self.click(
            point,
            target_size_pixels=_target_size_pixels(target, observation),
        )
        return ActionResult(
            True,
            f"clicked {step.action}",
            _input_metadata("click", point, plan, target),
        )

    def _execute_type_text(self, step: TaskStep) -> ActionResult:
        if step.text is None:
            raise ActuationError("type_text requires step.text")
        cadence = self.type_text(step.text)
        return ActionResult(
            True,
            "typed text",
            {
                "input_action": "type_text",
                "text_length": len(step.text),
                **cadence.metadata(),
            },
        )

    def _execute_press_key(self, step: TaskStep) -> ActionResult:
        if step.text is None:
            raise ActuationError("press_key requires step.text")
        self.press_key_or_chord(step.text)
        return ActionResult(
            True,
            "pressed key",
            {"input_action": "press_key", "key": step.text},
        )

    def _execute_scroll(
        self,
        step: TaskStep,
        target: ElementCandidate | None,
        observation: ScreenObservation,
    ) -> ActionResult:
        point = _target_or_region_point(target, step.region, observation)
        clicks = _scroll_clicks(step)
        target_size = _target_or_region_size_pixels(target, step.region, observation)
        cadence = self.scroll(point, clicks, target_size)
        return ActionResult(
            True,
            "scrolled",
            {
                "input_action": "scroll",
                "point": list(point),
                "scroll_clicks": clicks,
                **cadence.metadata(),
            },
        )

    def _execute_drag(
        self,
        step: TaskStep,
        target: ElementCandidate | None,
        observation: ScreenObservation,
    ) -> ActionResult:
        if step.region is None:
            raise ActuationError("drag requires a destination region")
        start = _target_point(target, observation)
        end = _region_center(step.region, observation)
        plan = self.drag(
            start,
            end,
            start_target_size_pixels=_target_size_pixels(target, observation),
            end_target_size_pixels=_region_size_pixels(step.region, observation),
        )
        return ActionResult(
            True,
            "dragged",
            {
                "input_action": "drag",
                "start": list(start),
                "end": list(end),
                "movement_points": len(plan.points),
                "movement_duration_seconds": plan.duration_seconds,
                "candidate_id": target.id if target else None,
            },
        )

    def _blocked_by_active_window(self, config: RuntimeConfig) -> ActionResult | None:
        if not config.allowed_windows:
            return None
        active_title = self._backend.active_window_title()
        if active_title in config.allowed_windows:
            return None
        return ActionResult(
            False,
            "active window is outside the configured allowed_windows",
            {
                "input_blocked": True,
                "actuation_guard": "active_window",
                "active_window_title": active_title,
                "allowed_windows": list(config.allowed_windows),
            },
        )

    def _blocked_by_allowed_region(
        self,
        step: TaskStep,
        target: ElementCandidate | None,
    ) -> ActionResult | None:
        if (
            step.region is None
            or target is None
            or step.action not in _REGION_GUARDED_ACTIONS
            or _bounds_center_inside_region(target.bounds, step.region)
        ):
            return None
        return ActionResult(
            False,
            "target is outside the configured step region",
            {
                "input_blocked": True,
                "actuation_guard": "allowed_region",
                "candidate_id": target.id,
                "candidate_center": list(target.bounds.center),
                "allowed_region": _region_metadata(step.region),
            },
        )

    def _blocked_by_emergency_stop(self, config: RuntimeConfig) -> ActionResult | None:
        if (
            self._emergency_stop_monitor is None
            or not self._emergency_stop_monitor.is_triggered(config)
        ):
            return None
        return ActionResult(
            False,
            "emergency stop requested before desktop input",
            {
                "input_blocked": True,
                "actuation_guard": "emergency_stop",
                "emergency_stop_triggered": True,
            },
        )


class FakeInputBackend(InputBackend):
    """Deterministic input backend for actuation tests."""

    def __init__(
        self,
        *,
        start_position: tuple[int, int] = (0, 0),
        active_window_title: str | None = None,
    ) -> None:
        self._position = start_position
        self._active_window_title = active_window_title
        self.events: list[InputEvent] = []

    def current_position(self) -> tuple[int, int]:
        return self._position

    def move_to(self, point: tuple[int, int]) -> None:
        self._position = point
        self.events.append(InputEvent(kind="move", point=point))

    def mouse_down(self, point: tuple[int, int], button: MouseButton) -> None:
        self.events.append(InputEvent(kind="mouse_down", point=point, button=button))

    def mouse_up(self, point: tuple[int, int], button: MouseButton) -> None:
        self.events.append(InputEvent(kind="mouse_up", point=point, button=button))

    def scroll(self, point: tuple[int, int], clicks: int) -> None:
        self.events.append(InputEvent(kind="scroll", point=point, clicks=clicks))

    def type_text(self, text: str) -> None:
        self.events.append(InputEvent(kind="type_text", text=text))

    def key_down(self, key: str) -> None:
        self.events.append(InputEvent(kind="key_down", key=key))

    def key_up(self, key: str) -> None:
        self.events.append(InputEvent(kind="key_up", key=key))

    def press_key(self, key: str) -> None:
        self.events.append(InputEvent(kind="press_key", key=key))

    def active_window_title(self) -> str | None:
        return self._active_window_title

    def sleep(self, seconds: float) -> None:
        if seconds > 0:
            self.events.append(InputEvent(kind="sleep", duration_seconds=seconds))


class WindowsInputBackend(InputBackend):
    """Windows input backend using the local user32 API."""

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise ActuationError("Windows input backend requires Windows")
        self._user32: Any = ctypes.windll.user32

    def current_position(self) -> tuple[int, int]:
        point = wintypes.POINT()
        if not self._user32.GetCursorPos(ctypes.byref(point)):
            raise ActuationError("unable to read cursor position")
        return (int(point.x), int(point.y))

    def move_to(self, point: tuple[int, int]) -> None:
        if not self._user32.SetCursorPos(int(point[0]), int(point[1])):
            raise ActuationError("unable to move mouse")

    def mouse_down(self, point: tuple[int, int], button: MouseButton) -> None:
        self.move_to(point)
        self._user32.mouse_event(_MOUSE_DOWN_FLAGS[button], 0, 0, 0, 0)

    def mouse_up(self, point: tuple[int, int], button: MouseButton) -> None:
        self.move_to(point)
        self._user32.mouse_event(_MOUSE_UP_FLAGS[button], 0, 0, 0, 0)

    def scroll(self, point: tuple[int, int], clicks: int) -> None:
        self.move_to(point)
        self._user32.mouse_event(_MOUSEEVENTF_WHEEL, 0, 0, clicks * 120, 0)

    def type_text(self, text: str) -> None:
        for character in text:
            self._press_character(character)

    def key_down(self, key: str) -> None:
        self._key_event(_virtual_key(key), key_down=True)

    def key_up(self, key: str) -> None:
        self._key_event(_virtual_key(key), key_down=False)

    def press_key(self, key: str) -> None:
        virtual_key = _virtual_key(key)
        self._key_event(virtual_key, key_down=True)
        self._key_event(virtual_key, key_down=False)

    def active_window_title(self) -> str | None:
        hwnd = int(self._user32.GetForegroundWindow())
        if hwnd == 0:
            return None
        length = int(self._user32.GetWindowTextLengthW(hwnd))
        buffer = ctypes.create_unicode_buffer(length + 1)
        copied = int(self._user32.GetWindowTextW(hwnd, buffer, length + 1))
        if copied <= 0:
            return ""
        return buffer.value

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    def _press_character(self, character: str) -> None:
        if character == "\n":
            self.press_key("enter")
            return
        key_scan = int(self._user32.VkKeyScanW(ord(character)))
        if key_scan == -1:
            raise ActuationError(f"unsupported text character: {character!r}")
        virtual_key = key_scan & 0xFF
        shift_state = (key_scan >> 8) & 0xFF
        pressed_modifiers = _shift_state_modifiers(shift_state)
        for modifier in pressed_modifiers:
            self._key_event(modifier, key_down=True)
        try:
            self._key_event(virtual_key, key_down=True)
            self._key_event(virtual_key, key_down=False)
        finally:
            for modifier in reversed(pressed_modifiers):
                self._key_event(modifier, key_down=False)

    def _key_event(self, virtual_key: int, *, key_down: bool) -> None:
        flags = 0 if key_down else _KEYEVENTF_KEYUP
        self._user32.keybd_event(virtual_key, 0, flags, 0)


class ActuationError(RuntimeError):
    """Raised when an action cannot be represented safely as local input."""


def create_platform_actuator(
    profile: ActuationProfile | None = None,
    emergency_stop_monitor: EmergencyStopChecker | None = None,
) -> Actuator:
    if sys.platform != "win32":
        return UnavailableActuator()
    return DesktopActuator(WindowsInputBackend(), profile, emergency_stop_monitor)


def actuation_profile_from_runtime_config(
    config: RuntimeConfig,
    base_profile: ActuationProfile | None = None,
) -> ActuationProfile:
    """Build the desktop actuation profile from enabled execution settings."""

    profile = base_profile or ActuationProfile()
    if not config.execution_profile.enabled:
        return profile
    return replace(
        profile,
        movement_smoothness=config.execution_profile.movement_smoothness,
        keyboard_interval_seconds=config.execution_profile.keyboard_interval_seconds,
        scroll_interval_seconds=config.execution_profile.scroll_interval_seconds,
    )


def _target_point(
    target: ElementCandidate | None,
    observation: ScreenObservation,
) -> tuple[int, int]:
    if target is None:
        raise ActuationError("targeted action requires a selected target")
    return _bounds_center(target.bounds, observation)


def _target_or_region_point(
    target: ElementCandidate | None,
    region: TaskRegion | None,
    observation: ScreenObservation,
) -> tuple[int, int]:
    if target is not None:
        return _bounds_center(target.bounds, observation)
    if region is not None:
        return _region_center(region, observation)
    raise ActuationError("scroll requires a target or region")


def _target_size_pixels(
    target: ElementCandidate | None,
    observation: ScreenObservation,
) -> tuple[float, float] | None:
    if target is None:
        return None
    return _bounds_size_pixels(target.bounds, observation)


def _target_or_region_size_pixels(
    target: ElementCandidate | None,
    region: TaskRegion | None,
    observation: ScreenObservation,
) -> tuple[float, float] | None:
    if target is not None:
        return _bounds_size_pixels(target.bounds, observation)
    if region is not None:
        return _region_size_pixels(region, observation)
    return None


def _region_size_pixels(
    region: TaskRegion,
    observation: ScreenObservation,
) -> tuple[float, float]:
    return _bounds_size_pixels(
        Bounds(region.x, region.y, region.width, region.height),
        observation,
    )


def _bounds_size_pixels(
    bounds: Bounds,
    observation: ScreenObservation,
) -> tuple[float, float]:
    if observation.monitor is None:
        return (float(bounds.width), float(bounds.height))
    physical = screenshot_bounds_to_physical(bounds, observation.monitor)
    return (float(physical.width), float(physical.height))


def _bounds_center(
    bounds: Bounds,
    observation: ScreenObservation,
) -> tuple[int, int]:
    center = bounds.center
    if observation.monitor is None:
        return center
    # Screen perception returns screenshot-space coordinates; OS input expects
    # physical desktop coordinates after monitor origin and DPI scaling.
    return screenshot_point_to_physical(center, observation.monitor)


def _region_center(
    region: TaskRegion,
    observation: ScreenObservation,
) -> tuple[int, int]:
    bounds = Bounds(region.x, region.y, region.width, region.height)
    return _bounds_center(bounds, observation)


def _bounds_center_inside_region(bounds: Bounds, region: TaskRegion) -> bool:
    center_x, center_y = bounds.center
    return (
        region.x <= center_x <= region.x + region.width
        and region.y <= center_y <= region.y + region.height
    )


def _region_metadata(region: TaskRegion) -> dict[str, int]:
    return {
        "x": region.x,
        "y": region.y,
        "width": region.width,
        "height": region.height,
    }


def _input_metadata(
    action: str,
    point: tuple[int, int],
    plan: MovementPlan,
    target: ElementCandidate | None,
) -> dict[str, object]:
    metadata: dict[str, object] = {
        "input_action": action,
        "point": list(point),
        "movement_points": len(plan.points),
        "movement_duration_seconds": plan.duration_seconds,
        "pointer_path_model": plan.path_model,
        "overshoot_applied": plan.overshoot_applied,
        "overshoot_point": list(plan.overshoot_point)
        if plan.overshoot_point
        else None,
        "settle_duration_seconds": plan.settle_duration_seconds,
        "random_seed": plan.random_seed,
        "sample_records": [record.metadata() for record in plan.sample_records],
        "candidate_id": target.id if target else None,
    }
    if plan.timing_estimate is not None:
        metadata.update(plan.timing_estimate.metadata())
    return metadata


def _scroll_clicks(step: TaskStep) -> int:
    if step.text is None:
        return _DEFAULT_SCROLL_CLICKS
    try:
        return int(step.text)
    except ValueError as exc:
        raise ActuationError("scroll text must be an integer wheel distance") from exc


def _quadratic_bezier(
    start: tuple[int, int],
    control: tuple[float, float],
    end: tuple[int, int],
    t: float,
) -> tuple[int, int]:
    inverse = 1 - t
    x = inverse * inverse * start[0] + 2 * inverse * t * control[0] + t * t * end[0]
    y = inverse * inverse * start[1] + 2 * inverse * t * control[1] + t * t * end[1]
    return (round(x), round(y))


def _minimum_jerk(t: float) -> float:
    return (10 * t**3) - (15 * t**4) + (6 * t**5)


def _clamp_seconds(value: float, bounds: tuple[float, float]) -> float:
    lower, upper = bounds
    return max(lower, min(upper, value))


def _validate_seconds_pair(value: tuple[float, float], field_name: str) -> None:
    lower, upper = value
    if lower < 0 or upper < 0:
        raise ValueError(f"{field_name} values must not be negative")
    if lower > upper:
        raise ValueError(f"{field_name} lower bound must not exceed upper bound")


def _virtual_key(key: str) -> int:
    normalized = key.strip().lower()
    if len(normalized) == 1 and normalized.isascii():
        return ord(normalized.upper())
    if normalized in _KEY_ALIASES:
        return _KEY_ALIASES[normalized]
    raise ActuationError(f"unsupported key: {key}")


def _shift_state_modifiers(shift_state: int) -> tuple[int, ...]:
    modifiers: list[int] = []
    if shift_state & 1:
        modifiers.append(_VK_SHIFT)
    if shift_state & 2:
        modifiers.append(_VK_CONTROL)
    if shift_state & 4:
        modifiers.append(_VK_MENU)
    return tuple(modifiers)


_MOUSEEVENTF_LEFTDOWN = 0x0002
_MOUSEEVENTF_LEFTUP = 0x0004
_MOUSEEVENTF_RIGHTDOWN = 0x0008
_MOUSEEVENTF_RIGHTUP = 0x0010
_MOUSEEVENTF_MIDDLEDOWN = 0x0020
_MOUSEEVENTF_MIDDLEUP = 0x0040
_MOUSEEVENTF_WHEEL = 0x0800

_MOUSE_DOWN_FLAGS: dict[MouseButton, int] = {
    "left": _MOUSEEVENTF_LEFTDOWN,
    "right": _MOUSEEVENTF_RIGHTDOWN,
    "middle": _MOUSEEVENTF_MIDDLEDOWN,
}
_MOUSE_UP_FLAGS: dict[MouseButton, int] = {
    "left": _MOUSEEVENTF_LEFTUP,
    "right": _MOUSEEVENTF_RIGHTUP,
    "middle": _MOUSEEVENTF_MIDDLEUP,
}

_KEYEVENTF_KEYUP = 0x0002
_VK_SHIFT = 0x10
_VK_CONTROL = 0x11
_VK_MENU = 0x12

_KEY_ALIASES = {
    "ctrl": _VK_CONTROL,
    "control": _VK_CONTROL,
    "shift": _VK_SHIFT,
    "alt": _VK_MENU,
    "enter": 0x0D,
    "return": 0x0D,
    "tab": 0x09,
    "esc": 0x1B,
    "escape": 0x1B,
    "backspace": 0x08,
    "delete": 0x2E,
    "space": 0x20,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pagedown": 0x22,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "win": 0x5B,
    **{f"f{index}": 0x6F + index for index in range(1, 13)},
}
