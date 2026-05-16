"""Windows-only global input demo using the real OS cursor."""

from __future__ import annotations

import ctypes
import json
import math
import platform
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape as html_escape
from pathlib import Path
from typing import Any

from desktop_agent import __version__
from desktop_agent.actuation import (
    ActuationProfile,
    InputBackend,
    MouseButton,
    MovementPlan,
    SmoothMovementPlanner,
    WindowsInputBackend,
)
from desktop_agent.config import RuntimeConfig
from desktop_agent.sampling import SeededSampler
from desktop_agent.screen import (
    MssScreenObserver,
    ScreenObservation,
    ScreenObserver,
    ScreenUnavailableError,
)


class MouseDemoError(RuntimeError):
    """Raised when the local input demo cannot run safely."""


@dataclass(frozen=True)
class CursorFrame:
    """One planned pointer frame plus the real cursor readback after SendInput."""

    action: str
    index: int
    planned: tuple[int, int]
    actual: tuple[int, int]
    timestamp_seconds: float
    drift_pixels: float

    def metadata(self) -> dict[str, object]:
        return {
            "action": self.action,
            "frame_index": self.index,
            "planned": list(self.planned),
            "actual": list(self.actual),
            "timestamp_seconds": self.timestamp_seconds,
            "drift_pixels": self.drift_pixels,
        }


@dataclass(frozen=True)
class InputDemoEvent:
    """Low-level mouse or keyboard event recorded by the demo trace."""

    event: str
    timestamp_seconds: float
    point: tuple[int, int] | None = None
    button: MouseButton | None = None
    key: str | None = None
    text: str | None = None
    clicks: int | None = None
    interval_seconds: float | None = None

    def metadata(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "event": self.event,
            "timestamp_seconds": self.timestamp_seconds,
        }
        if self.point is not None:
            payload["point"] = list(self.point)
        if self.button is not None:
            payload["button"] = self.button
        if self.key is not None:
            payload["key"] = self.key
        if self.text is not None:
            payload["text"] = self.text
        if self.clicks is not None:
            payload["clicks"] = self.clicks
        if self.interval_seconds is not None:
            payload["interval_seconds"] = self.interval_seconds
        return payload


@dataclass(frozen=True)
class MovementTrace:
    """Movement plan and real cursor samples captured while executing it."""

    plan: MovementPlan
    frames: tuple[CursorFrame, ...]


@dataclass(frozen=True)
class PostActionEvidence:
    """Screen and focus evidence captured immediately after a demo step."""

    status: str
    active_window_title: str | None = None
    screenshot_path: Path | None = None
    screenshot_size: tuple[int, int] | None = None
    cursor_position: tuple[int, int] | None = None
    warnings: tuple[str, ...] = ()
    metadata: dict[str, object] | None = None
    reason: str | None = None

    def metadata_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "status": self.status,
            "active_window_title": self.active_window_title,
            "screenshot_path": str(self.screenshot_path)
            if self.screenshot_path
            else None,
            "screenshot_size": list(self.screenshot_size)
            if self.screenshot_size
            else None,
            "cursor_position": list(self.cursor_position)
            if self.cursor_position
            else None,
            "warnings": list(self.warnings),
            "metadata": self.metadata or {},
            "reason": self.reason,
        }
        return payload


@dataclass(frozen=True)
class MouseDemoStep:
    """One global input action recorded by the demo."""

    step_id: str
    action: str
    metadata: dict[str, object]


@dataclass(frozen=True)
class MouseDemoReport:
    """Result returned by the global input demo command."""

    status: str
    trace_dir: Path
    report_path: Path
    steps: tuple[MouseDemoStep, ...]
    reason: str | None = None
    proof_manifest_path: Path | None = None


@dataclass(frozen=True)
class InputDemoPoints:
    """Global desktop coordinates used by the low-level input demo."""

    screen_bounds: tuple[int, int, int, int]
    waypoints: tuple[tuple[int, int], ...]
    drag_start: tuple[int, int]
    drag_end: tuple[int, int]


type MouseDemoPoints = InputDemoPoints


class PostActionEvidenceRecorder:
    """Captures screenshot, focus, and cursor evidence after each real action."""

    def __init__(
        self,
        *,
        backend: InputBackend,
        trace_dir: Path,
        observer: ScreenObserver | None = None,
    ) -> None:
        self._backend = backend
        self._observer = observer or MssScreenObserver()
        self._config = RuntimeConfig(trace_root=trace_dir, save_screenshots=True)

    def attach(self, step: MouseDemoStep) -> MouseDemoStep:
        evidence = self.capture(step.step_id)
        metadata = dict(step.metadata)
        metadata["post_action_evidence"] = evidence.metadata_payload()
        return MouseDemoStep(step.step_id, step.action, metadata)

    def capture(self, step_id: str) -> PostActionEvidence:
        try:
            observation = self._observer.observe(self._config)
            return _post_action_evidence_from_observation(
                observation,
                cursor_position=self._read_cursor_position(),
                fallback_active_window_title=self._read_active_window_title(),
            )
        except (OSError, ScreenUnavailableError, RuntimeError) as exc:
            return PostActionEvidence(
                status="failed",
                active_window_title=self._read_active_window_title(),
                cursor_position=self._read_cursor_position(),
                reason=f"{step_id}: {exc}",
            )

    def _read_active_window_title(self) -> str | None:
        try:
            return self._backend.active_window_title()
        except (OSError, RuntimeError):
            return None

    def _read_cursor_position(self) -> tuple[int, int] | None:
        try:
            return self._backend.current_position()
        except (OSError, RuntimeError):
            return None


class RealInputController:
    """Reusable low-level controller for the real Windows cursor and keyboard."""

    def __init__(
        self,
        backend: InputBackend,
        profile: ActuationProfile,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._backend = backend
        self._profile = profile
        self._movement_planner = SmoothMovementPlanner(profile)
        self._keyboard_sampler = SeededSampler(profile.random_seed)
        self._scroll_sampler = SeededSampler(profile.random_seed)
        self._clock = clock
        self._started_at = clock()

    def move_to(
        self,
        step_id: str,
        point: tuple[int, int],
        *,
        target_size_pixels: tuple[float, float] = (96.0, 96.0),
    ) -> MouseDemoStep:
        """Move the real cursor through a planned path and record readback frames."""

        trace = self._run_movement(step_id, point, target_size_pixels)
        return MouseDemoStep(
            step_id,
            "move",
            {"point": list(point), **_movement_trace_metadata(trace)},
        )

    def click(
        self,
        step_id: str,
        point: tuple[int, int],
        *,
        button: MouseButton = "left",
        target_size_pixels: tuple[float, float] = (64.0, 64.0),
    ) -> MouseDemoStep:
        """Click a physical point with low-level down/up events."""

        trace = self._run_movement(step_id, point, target_size_pixels)
        events = [
            self._mouse_down(point, button),
        ]
        self.pause(0.08)
        events.append(self._mouse_up(point, button))
        return MouseDemoStep(
            step_id,
            "click",
            {
                "point": list(point),
                "button": button,
                "button_events": _events_metadata(events),
                **_movement_trace_metadata(trace),
            },
        )

    def drag(
        self,
        step_id: str,
        start: tuple[int, int],
        end: tuple[int, int],
        *,
        button: MouseButton = "left",
        start_target_size_pixels: tuple[float, float] = (72.0, 72.0),
        end_target_size_pixels: tuple[float, float] = (180.0, 120.0),
    ) -> MouseDemoStep:
        """Drag the real cursor from start to end and trace down/move/up order."""

        approach = self._run_movement(
            f"{step_id}.approach",
            start,
            start_target_size_pixels,
        )
        events = [self._mouse_down(start, button)]
        self.pause(0.10)
        drag_trace = self._run_movement(
            f"{step_id}.drag",
            end,
            end_target_size_pixels,
        )
        events.append(self._mouse_up(end, button))
        return MouseDemoStep(
            step_id,
            "drag",
            {
                "start": list(start),
                "end": list(end),
                "button": button,
                "button_events": _events_metadata(events),
                "approach_movement": _movement_trace_metadata(approach),
                **_movement_trace_metadata(drag_trace),
            },
        )

    def scroll(
        self,
        step_id: str,
        point: tuple[int, int],
        clicks: int,
        *,
        target_size_pixels: tuple[float, float] = (220.0, 140.0),
    ) -> MouseDemoStep:
        """Send wheel events from the real cursor location with cadence metadata."""

        trace = self._run_movement(step_id, point, target_size_pixels)
        direction = 1 if clicks > 0 else -1
        events: list[InputDemoEvent] = []
        intervals: list[float] = []
        sample_start = self._scroll_sampler.sample_count
        for index in range(abs(clicks)):
            self._backend.scroll(point, direction)
            events.append(
                InputDemoEvent(
                    event="wheel",
                    timestamp_seconds=self._elapsed(),
                    point=point,
                    clicks=direction,
                )
            )
            if index == abs(clicks) - 1:
                continue
            interval = self._sample_interval(
                self._scroll_sampler,
                "actuation.scroll_interval",
                self._profile.scroll_interval_seconds,
            )
            intervals.append(interval)
            self.pause(interval)
        return MouseDemoStep(
            step_id,
            "scroll",
            {
                "point": list(point),
                "requested_clicks": clicks,
                "scroll_events": _events_metadata(events),
                "scroll_interval_seconds": intervals,
                "sample_records": [
                    record.metadata()
                    for record in self._scroll_sampler.records_since(sample_start)
                ],
                **_movement_trace_metadata(trace),
            },
        )

    def type_text(self, step_id: str, text: str) -> MouseDemoStep:
        """Type exact text as per-character events so cadence can be audited."""

        events: list[InputDemoEvent] = []
        intervals: list[float] = []
        sample_start = self._keyboard_sampler.sample_count
        for index, character in enumerate(text):
            self._backend.type_text(character)
            events.append(
                InputDemoEvent(
                    event="type_text",
                    timestamp_seconds=self._elapsed(),
                    text=character,
                )
            )
            if index == len(text) - 1:
                continue
            interval = self._sample_interval(
                self._keyboard_sampler,
                "actuation.keyboard_interval",
                self._profile.keyboard_interval_seconds,
            )
            intervals.append(interval)
            self.pause(interval)
        return MouseDemoStep(
            step_id,
            "type_text",
            {
                "text": text,
                "text_length": len(text),
                "typed_events": _events_metadata(events),
                "typed_text_reconstructed": "".join(
                    event.text or "" for event in events
                ),
                "keyboard_interval_seconds": intervals,
                "sample_records": [
                    record.metadata()
                    for record in self._keyboard_sampler.records_since(sample_start)
                ],
            },
        )

    def press_chord(self, step_id: str, chord: str) -> MouseDemoStep:
        """Press a keyboard chord such as Win+D using real key down/up events."""

        keys = tuple(part.strip().lower() for part in chord.split("+") if part.strip())
        if not keys:
            raise MouseDemoError("keyboard chord must contain at least one key")

        events: list[InputDemoEvent] = []
        modifiers = keys[:-1]
        final_key = keys[-1]
        for key in modifiers:
            self._backend.key_down(key)
            events.append(
                InputDemoEvent(
                    event="key_down",
                    timestamp_seconds=self._elapsed(),
                    key=key,
                )
            )
            self.pause(0.04)
        self._backend.press_key(final_key)
        events.append(
            InputDemoEvent(
                event="press_key",
                timestamp_seconds=self._elapsed(),
                key=final_key,
            )
        )
        self.pause(0.04)
        for key in reversed(modifiers):
            self._backend.key_up(key)
            events.append(
                InputDemoEvent(
                    event="key_up",
                    timestamp_seconds=self._elapsed(),
                    key=key,
                )
            )
            self.pause(0.04)
        return MouseDemoStep(
            step_id,
            "press_chord",
            {"chord": chord, "key_events": _events_metadata(events)},
        )

    def current_position_step(self, step_id: str) -> MouseDemoStep:
        """Record the final OS cursor position without moving it."""

        point = self._backend.current_position()
        return MouseDemoStep(
            step_id,
            "cursor_readback",
            {
                "actual": list(point),
                "timestamp_seconds": self._elapsed(),
            },
        )

    def pause(self, seconds: float) -> None:
        if seconds > 0:
            self._backend.sleep(seconds)

    def _run_movement(
        self,
        action: str,
        point: tuple[int, int],
        target_size_pixels: tuple[float, float],
    ) -> MovementTrace:
        start = self._backend.current_position()
        plan = self._movement_planner.plan(start, point, target_size_pixels)
        frames: list[CursorFrame] = []
        for index, path_point in enumerate(plan.points, start=1):
            self._backend.move_to(path_point)
            actual = self._backend.current_position()
            frames.append(
                CursorFrame(
                    action=action,
                    index=index,
                    planned=path_point,
                    actual=actual,
                    timestamp_seconds=self._elapsed(),
                    drift_pixels=math.hypot(
                        actual[0] - path_point[0],
                        actual[1] - path_point[1],
                    ),
                )
            )
            self.pause(plan.step_delay_seconds)
        self.pause(plan.settle_duration_seconds)
        return MovementTrace(plan=plan, frames=tuple(frames))

    def _mouse_down(
        self,
        point: tuple[int, int],
        button: MouseButton,
    ) -> InputDemoEvent:
        self._backend.mouse_down(point, button)
        return InputDemoEvent(
            event="mouse_down",
            timestamp_seconds=self._elapsed(),
            point=self._backend.current_position(),
            button=button,
        )

    def _mouse_up(
        self,
        point: tuple[int, int],
        button: MouseButton,
    ) -> InputDemoEvent:
        self._backend.mouse_up(point, button)
        return InputDemoEvent(
            event="mouse_up",
            timestamp_seconds=self._elapsed(),
            point=self._backend.current_position(),
            button=button,
        )

    def _sample_interval(
        self,
        sampler: SeededSampler,
        label: str,
        bounds: tuple[float, float],
    ) -> float:
        lower, upper = bounds
        if lower == upper:
            return lower
        return sampler.uniform(label, bounds)

    def _elapsed(self) -> float:
        return max(0.0, self._clock() - self._started_at)


def run_input_demo(
    *,
    trace_root: Path = Path("traces"),
    random_seed: int = 20260515,
    movement_smoothness: float = 0.85,
    keyboard_text: str = "DeskPilot controlled input",
    countdown_seconds: float = 3.0,
) -> MouseDemoReport:
    """Move the main Windows cursor globally, drag on the desktop, and type."""

    if sys.platform != "win32":
        raise MouseDemoError("demo-input requires Windows desktop input")
    if not 0 <= movement_smoothness <= 1:
        raise MouseDemoError("movement_smoothness must be between 0 and 1")
    if countdown_seconds < 0:
        raise MouseDemoError("countdown_seconds must not be negative")

    _set_process_dpi_aware()
    trace_dir = _prepare_trace_dir(trace_root, "input-demo")
    profile = _demo_actuation_profile(random_seed, movement_smoothness)
    backend = WindowsInputBackend(move_mode="absolute")
    controller = RealInputController(backend, profile)
    evidence_recorder = PostActionEvidenceRecorder(
        backend=backend,
        trace_dir=trace_dir,
    )
    steps: list[MouseDemoStep] = []
    status = "passed"
    reason: str | None = None
    started_at = _timestamp()
    screen_bounds: tuple[int, int, int, int] | None = None

    try:
        _countdown(countdown_seconds)
        screen_bounds = _windows_virtual_screen_bounds()
        points = _input_demo_points(screen_bounds)
        steps.extend(
            _run_global_input_sequence(
                controller,
                points,
                keyboard_text,
                evidence_recorder,
            )
        )
    except Exception as exc:  # pragma: no cover - exercised manually on Windows.
        status = "failed"
        reason = str(exc)

    report_path = _write_report(
        trace_dir,
        tuple(steps),
        status,
        reason,
        report_name="input-demo-report.json",
    )
    proof_manifest_path = _write_proof_manifest(
        trace_dir,
        proof_name="input-demo",
        command=_input_demo_command(
            trace_root,
            random_seed,
            movement_smoothness,
            keyboard_text,
            countdown_seconds,
        ),
        status=status,
        reason=reason,
        started_at=started_at,
        completed_at=_timestamp(),
        report_path=report_path,
        steps=tuple(steps),
        monitor_bounds=screen_bounds,
    )
    return MouseDemoReport(
        status=status,
        reason=reason,
        trace_dir=trace_dir,
        report_path=report_path,
        steps=tuple(steps),
        proof_manifest_path=proof_manifest_path,
    )


def run_mouse_demo(
    *,
    trace_root: Path = Path("traces"),
    random_seed: int = 20260515,
    movement_smoothness: float = 0.85,
    keyboard_text: str = "DeskPilot controlled input",
    countdown_seconds: float = 3.0,
) -> MouseDemoReport:
    """Backward-compatible alias for the global input demo."""

    return run_input_demo(
        trace_root=trace_root,
        random_seed=random_seed,
        movement_smoothness=movement_smoothness,
        keyboard_text=keyboard_text,
        countdown_seconds=countdown_seconds,
    )


def run_linkedin_demo(
    *,
    trace_root: Path = Path("traces"),
    random_seed: int = 20260515,
    movement_smoothness: float = 0.85,
    countdown_seconds: float = 3.0,
    url: str = "https://www.linkedin.com/",
    find_text: str = "LinkedIn",
    page_load_seconds: float = 5.0,
) -> MouseDemoReport:
    """Open Edge, navigate to LinkedIn, then visibly interact with the page."""

    if sys.platform != "win32":
        raise MouseDemoError("demo-linkedin requires Windows desktop input")
    if not 0 <= movement_smoothness <= 1:
        raise MouseDemoError("movement_smoothness must be between 0 and 1")
    if countdown_seconds < 0:
        raise MouseDemoError("countdown_seconds must not be negative")
    if page_load_seconds < 0:
        raise MouseDemoError("page_load_seconds must not be negative")
    if not url:
        raise MouseDemoError("url must not be empty")
    if not find_text:
        raise MouseDemoError("find_text must not be empty")

    _set_process_dpi_aware()
    trace_dir = _prepare_trace_dir(trace_root, "linkedin-demo")
    profile = _demo_actuation_profile(random_seed, movement_smoothness)
    backend = WindowsInputBackend(move_mode="absolute")
    controller = RealInputController(backend, profile)
    evidence_recorder = PostActionEvidenceRecorder(
        backend=backend,
        trace_dir=trace_dir,
    )
    steps: list[MouseDemoStep] = []
    status = "passed"
    reason: str | None = None
    started_at = _timestamp()
    screen_bounds: tuple[int, int, int, int] | None = None

    try:
        _countdown(countdown_seconds)
        screen_bounds = _windows_virtual_screen_bounds()
        steps.extend(
            _run_linkedin_sequence(
                controller,
                screen_bounds,
                url=url,
                find_text=find_text,
                page_load_seconds=page_load_seconds,
                evidence_recorder=evidence_recorder,
            )
        )
    except Exception as exc:  # pragma: no cover - exercised manually on Windows.
        status = "failed"
        reason = str(exc)

    report_path = _write_report(
        trace_dir,
        tuple(steps),
        status,
        reason,
        report_name="linkedin-demo-report.json",
    )
    proof_manifest_path = _write_proof_manifest(
        trace_dir,
        proof_name="linkedin-demo",
        command=_linkedin_demo_command(
            trace_root,
            random_seed,
            movement_smoothness,
            countdown_seconds,
            url,
            find_text,
            page_load_seconds,
        ),
        status=status,
        reason=reason,
        started_at=started_at,
        completed_at=_timestamp(),
        report_path=report_path,
        steps=tuple(steps),
        monitor_bounds=screen_bounds,
    )
    return MouseDemoReport(
        status=status,
        reason=reason,
        trace_dir=trace_dir,
        report_path=report_path,
        steps=tuple(steps),
        proof_manifest_path=proof_manifest_path,
    )


def run_browser_fixture(
    *,
    trace_root: Path = Path("traces"),
    random_seed: int = 20260515,
    movement_smoothness: float = 0.85,
    countdown_seconds: float = 3.0,
    fixture_text: str = "DeskPilot browser fixture",
    result_text: str = "DeskPilot browser fixture submitted",
    page_load_seconds: float = 1.5,
) -> MouseDemoReport:
    """Open a generated local browser fixture and submit a form with real input."""

    if sys.platform != "win32":
        raise MouseDemoError("proof browser-fixture requires Windows desktop input")
    if not 0 <= movement_smoothness <= 1:
        raise MouseDemoError("movement_smoothness must be between 0 and 1")
    if countdown_seconds < 0:
        raise MouseDemoError("countdown_seconds must not be negative")
    if page_load_seconds < 0:
        raise MouseDemoError("page_load_seconds must not be negative")
    if not fixture_text:
        raise MouseDemoError("fixture_text must not be empty")
    if not result_text:
        raise MouseDemoError("result_text must not be empty")

    _set_process_dpi_aware()
    trace_dir = _prepare_trace_dir(trace_root, "browser-fixture")
    fixture_path = _write_browser_fixture_html(trace_dir, result_text)
    fixture_url = fixture_path.resolve().as_uri()
    profile = _demo_actuation_profile(random_seed, movement_smoothness)
    backend = WindowsInputBackend(move_mode="absolute")
    controller = RealInputController(backend, profile)
    evidence_recorder = PostActionEvidenceRecorder(
        backend=backend,
        trace_dir=trace_dir,
    )
    steps: list[MouseDemoStep] = []
    status = "passed"
    reason: str | None = None
    started_at = _timestamp()
    screen_bounds: tuple[int, int, int, int] | None = None

    try:
        _countdown(countdown_seconds)
        screen_bounds = _windows_virtual_screen_bounds()
        steps.extend(
            _run_browser_fixture_sequence(
                controller,
                screen_bounds,
                fixture_path=fixture_path,
                fixture_url=fixture_url,
                fixture_text=fixture_text,
                result_text=result_text,
                page_load_seconds=page_load_seconds,
                evidence_recorder=evidence_recorder,
            )
        )
    except Exception as exc:  # pragma: no cover - exercised manually on Windows.
        status = "failed"
        reason = str(exc)

    report_path = _write_report(
        trace_dir,
        tuple(steps),
        status,
        reason,
        report_name="browser-fixture-report.json",
    )
    proof_manifest_path = _write_proof_manifest(
        trace_dir,
        proof_name="browser-fixture",
        command=_browser_fixture_command(
            trace_root,
            random_seed,
            movement_smoothness,
            countdown_seconds,
            fixture_text,
            result_text,
            page_load_seconds,
        ),
        status=status,
        reason=reason,
        started_at=started_at,
        completed_at=_timestamp(),
        report_path=report_path,
        steps=tuple(steps),
        monitor_bounds=screen_bounds,
    )
    return MouseDemoReport(
        status=status,
        reason=reason,
        trace_dir=trace_dir,
        report_path=report_path,
        steps=tuple(steps),
        proof_manifest_path=proof_manifest_path,
    )


def run_native_fixture(
    *,
    trace_root: Path = Path("traces"),
    random_seed: int = 20260515,
    movement_smoothness: float = 0.85,
    countdown_seconds: float = 3.0,
    initial_text: str = "DeskPilot native fixture",
    replacement_text: str = "DeskPilot native fixture updated",
) -> MouseDemoReport:
    """Open Notepad and perform a bounded native-app text editing proof."""

    if sys.platform != "win32":
        raise MouseDemoError("proof native-fixture requires Windows desktop input")
    if not 0 <= movement_smoothness <= 1:
        raise MouseDemoError("movement_smoothness must be between 0 and 1")
    if countdown_seconds < 0:
        raise MouseDemoError("countdown_seconds must not be negative")
    if not initial_text:
        raise MouseDemoError("initial_text must not be empty")
    if not replacement_text:
        raise MouseDemoError("replacement_text must not be empty")

    _set_process_dpi_aware()
    trace_dir = _prepare_trace_dir(trace_root, "native-fixture")
    profile = _demo_actuation_profile(random_seed, movement_smoothness)
    backend = WindowsInputBackend(move_mode="absolute")
    controller = RealInputController(backend, profile)
    evidence_recorder = PostActionEvidenceRecorder(
        backend=backend,
        trace_dir=trace_dir,
    )
    steps: list[MouseDemoStep] = []
    status = "passed"
    reason: str | None = None
    started_at = _timestamp()
    screen_bounds: tuple[int, int, int, int] | None = None

    try:
        _countdown(countdown_seconds)
        screen_bounds = _windows_virtual_screen_bounds()
        steps.extend(
            _run_native_fixture_sequence(
                controller,
                initial_text=initial_text,
                replacement_text=replacement_text,
                evidence_recorder=evidence_recorder,
            )
        )
    except Exception as exc:  # pragma: no cover - exercised manually on Windows.
        status = "failed"
        reason = str(exc)

    report_path = _write_report(
        trace_dir,
        tuple(steps),
        status,
        reason,
        report_name="native-fixture-report.json",
    )
    proof_manifest_path = _write_proof_manifest(
        trace_dir,
        proof_name="native-fixture",
        command=_native_fixture_command(
            trace_root,
            random_seed,
            movement_smoothness,
            countdown_seconds,
            initial_text,
            replacement_text,
        ),
        status=status,
        reason=reason,
        started_at=started_at,
        completed_at=_timestamp(),
        report_path=report_path,
        steps=tuple(steps),
        monitor_bounds=screen_bounds,
    )
    return MouseDemoReport(
        status=status,
        reason=reason,
        trace_dir=trace_dir,
        report_path=report_path,
        steps=tuple(steps),
        proof_manifest_path=proof_manifest_path,
    )


def run_windows_smoke_checklist(
    *,
    trace_root: Path = Path("traces"),
    random_seed: int = 20260515,
    movement_smoothness: float = 0.85,
    countdown_seconds: float = 3.0,
    keyboard_text: str = "DeskPilot Windows smoke check",
    edge_url: str = "about:blank",
) -> MouseDemoReport:
    """Run a bounded Windows smoke checklist through real desktop input."""

    if sys.platform != "win32":
        raise MouseDemoError("windows-smoke-checklist requires Windows desktop input")
    if not 0 <= movement_smoothness <= 1:
        raise MouseDemoError("movement_smoothness must be between 0 and 1")
    if countdown_seconds < 0:
        raise MouseDemoError("countdown_seconds must not be negative")
    if not keyboard_text:
        raise MouseDemoError("keyboard_text must not be empty")
    if not edge_url:
        raise MouseDemoError("edge_url must not be empty")

    _set_process_dpi_aware()
    trace_dir = _prepare_trace_dir(trace_root, "windows-smoke-checklist")
    profile = _demo_actuation_profile(random_seed, movement_smoothness)
    backend = WindowsInputBackend(move_mode="absolute")
    controller = RealInputController(backend, profile)
    evidence_recorder = PostActionEvidenceRecorder(
        backend=backend,
        trace_dir=trace_dir,
    )
    steps: list[MouseDemoStep] = []
    status = "passed"
    reason: str | None = None
    started_at = _timestamp()
    screen_bounds: tuple[int, int, int, int] | None = None

    try:
        _countdown(countdown_seconds)
        screen_bounds = _windows_virtual_screen_bounds()
        steps.extend(
            _run_windows_smoke_sequence(
                controller,
                keyboard_text=keyboard_text,
                edge_url=edge_url,
                evidence_recorder=evidence_recorder,
            )
        )
    except Exception as exc:  # pragma: no cover - exercised manually on Windows.
        status = "failed"
        reason = str(exc)

    report_path = _write_report(
        trace_dir,
        tuple(steps),
        status,
        reason,
        report_name="windows-smoke-checklist-report.json",
    )
    _write_smoke_checklist_markdown(
        trace_dir,
        tuple(steps),
        status,
        report_path,
    )
    proof_manifest_path = _write_proof_manifest(
        trace_dir,
        proof_name="windows-smoke-checklist",
        command=_windows_smoke_command(
            trace_root,
            random_seed,
            movement_smoothness,
            countdown_seconds,
            keyboard_text,
            edge_url,
        ),
        status=status,
        reason=reason,
        started_at=started_at,
        completed_at=_timestamp(),
        report_path=report_path,
        steps=tuple(steps),
        monitor_bounds=screen_bounds,
    )
    return MouseDemoReport(
        status=status,
        reason=reason,
        trace_dir=trace_dir,
        report_path=report_path,
        steps=tuple(steps),
        proof_manifest_path=proof_manifest_path,
    )


def _demo_actuation_profile(
    random_seed: int,
    movement_smoothness: float,
) -> ActuationProfile:
    return ActuationProfile(
        movement_duration_seconds=(0.90, 1.80),
        timing_variation_seconds=(0.04, 0.12),
        keyboard_interval_seconds=(0.02, 0.07),
        scroll_interval_seconds=(0.08, 0.18),
        movement_steps=72,
        movement_smoothness=movement_smoothness,
        overshoot_probability=0.35,
        overshoot_pixels=(3.0, 8.0),
        settle_duration_seconds=(0.04, 0.12),
        random_seed=random_seed,
    )


def _run_global_input_sequence(
    controller: RealInputController,
    points: InputDemoPoints,
    keyboard_text: str,
    evidence_recorder: PostActionEvidenceRecorder | None = None,
) -> tuple[MouseDemoStep, ...]:
    steps: list[MouseDemoStep] = []

    # Win+D exposes the desktop so the drag-selection demonstration is harmless.
    _record_step(
        steps,
        controller.press_chord("reveal-desktop", "win+d"),
        evidence_recorder,
    )
    controller.pause(0.60)
    for index, point in enumerate(points.waypoints, start=1):
        _record_step(
            steps,
            controller.move_to(f"desktop-waypoint-{index}", point),
            evidence_recorder,
        )
    controller.pause(0.20)
    _record_step(
        steps,
        controller.drag(
            "desktop-drag-selection",
            points.drag_start,
            points.drag_end,
        ),
        evidence_recorder,
    )
    controller.pause(0.40)
    _record_step(steps, _launch_notepad(), evidence_recorder)
    controller.pause(1.00)
    _record_step(
        steps,
        controller.type_text("type-notepad-text", keyboard_text),
        evidence_recorder,
    )
    _record_step(
        steps,
        controller.current_position_step("final-cursor-readback"),
        evidence_recorder,
    )
    return tuple(steps)


def _run_linkedin_sequence(
    controller: RealInputController,
    screen_bounds: tuple[int, int, int, int],
    *,
    url: str,
    find_text: str,
    page_load_seconds: float,
    launch_edge: Callable[[str], MouseDemoStep] | None = None,
    evidence_recorder: PostActionEvidenceRecorder | None = None,
) -> tuple[MouseDemoStep, ...]:
    steps: list[MouseDemoStep] = []
    edge_launcher = launch_edge or _launch_edge

    _record_step(steps, edge_launcher("about:blank"), evidence_recorder)
    controller.pause(2.0)
    _record_step(
        steps,
        controller.press_chord("focus-edge-address-bar", "ctrl+l"),
        evidence_recorder,
    )
    _record_step(
        steps,
        controller.type_text("type-linkedin-url", url),
        evidence_recorder,
    )
    _record_step(
        steps,
        controller.press_chord("submit-linkedin-url", "enter"),
        evidence_recorder,
    )
    controller.pause(page_load_seconds)
    _record_step(
        steps,
        controller.scroll(
            "scroll-linkedin-page",
            _screen_point(screen_bounds, 0.50, 0.56),
            -3,
        ),
        evidence_recorder,
    )
    _record_step(
        steps,
        controller.press_chord("open-browser-find", "ctrl+f"),
        evidence_recorder,
    )
    _record_step(
        steps,
        controller.type_text("type-find-text", find_text),
        evidence_recorder,
    )
    _record_step(
        steps,
        controller.press_chord("confirm-find-text", "enter"),
        evidence_recorder,
    )
    _record_step(
        steps,
        controller.press_chord("close-browser-find", "esc"),
        evidence_recorder,
    )
    _record_step(
        steps,
        controller.current_position_step("final-cursor-readback"),
        evidence_recorder,
    )
    return tuple(steps)


def _run_browser_fixture_sequence(
    controller: RealInputController,
    screen_bounds: tuple[int, int, int, int],
    *,
    fixture_path: Path,
    fixture_url: str,
    fixture_text: str,
    result_text: str,
    page_load_seconds: float,
    launch_edge: Callable[[str], MouseDemoStep] | None = None,
    evidence_recorder: PostActionEvidenceRecorder | None = None,
) -> tuple[MouseDemoStep, ...]:
    steps: list[MouseDemoStep] = []
    edge_launcher = launch_edge or _launch_edge

    _record_step(
        steps,
        MouseDemoStep(
            "write-browser-fixture",
            "write_fixture",
            {
                "fixture_path": str(fixture_path),
                "fixture_url": fixture_url,
                "result_fixture_path": str(
                    fixture_path.with_name("browser-fixture-result.html")
                ),
                "expected_result_text": result_text,
            },
        ),
        evidence_recorder,
    )
    _record_step(steps, edge_launcher(fixture_url), evidence_recorder)
    controller.pause(page_load_seconds)
    _record_step(
        steps,
        controller.click(
            "focus-browser-fixture-input",
            _screen_point(screen_bounds, 0.50, 0.46),
            target_size_pixels=(360.0, 56.0),
        ),
        evidence_recorder,
    )
    _record_step(
        steps,
        controller.type_text("type-browser-fixture-text", fixture_text),
        evidence_recorder,
    )
    _record_step(
        steps,
        controller.press_chord("submit-browser-fixture-form", "enter"),
        evidence_recorder,
    )
    controller.pause(0.50)
    _record_step(
        steps,
        controller.press_chord("open-browser-find", "ctrl+f"),
        evidence_recorder,
    )
    _record_step(
        steps,
        controller.type_text("type-browser-fixture-result-search", result_text),
        evidence_recorder,
    )
    _record_step(
        steps,
        controller.press_chord("confirm-browser-fixture-result-search", "enter"),
        evidence_recorder,
    )
    _record_step(
        steps,
        controller.press_chord("close-browser-find", "esc"),
        evidence_recorder,
    )
    _record_step(
        steps,
        controller.current_position_step("final-cursor-readback"),
        evidence_recorder,
    )
    return tuple(steps)


def _run_native_fixture_sequence(
    controller: RealInputController,
    *,
    initial_text: str,
    replacement_text: str,
    evidence_recorder: PostActionEvidenceRecorder | None = None,
    launch_notepad: Callable[[], MouseDemoStep] | None = None,
) -> tuple[MouseDemoStep, ...]:
    steps: list[MouseDemoStep] = []
    notepad_launcher = launch_notepad or _launch_notepad

    _record_step(steps, notepad_launcher(), evidence_recorder)
    controller.pause(1.0)
    _record_step(
        steps,
        controller.type_text("type-native-fixture-initial-text", initial_text),
        evidence_recorder,
    )
    _record_step(
        steps,
        controller.press_chord("select-native-fixture-text", "ctrl+a"),
        evidence_recorder,
    )
    _record_step(
        steps,
        controller.type_text("replace-native-fixture-text", replacement_text),
        evidence_recorder,
    )
    _record_step(
        steps,
        controller.current_position_step("final-cursor-readback"),
        evidence_recorder,
    )
    return tuple(steps)


def _run_windows_smoke_sequence(
    controller: RealInputController,
    *,
    keyboard_text: str,
    edge_url: str,
    evidence_recorder: PostActionEvidenceRecorder | None = None,
    launch_notepad: Callable[[], MouseDemoStep] | None = None,
    launch_edge: Callable[[str], MouseDemoStep] | None = None,
) -> tuple[MouseDemoStep, ...]:
    steps: list[MouseDemoStep] = []
    notepad_launcher = launch_notepad or _launch_notepad
    edge_launcher = launch_edge or _launch_edge

    _record_step(
        steps,
        _smoke_step(
            controller.current_position_step("cursor-readback-check"),
            "cursor_readback",
            "real cursor position was read from the desktop input backend",
        ),
        evidence_recorder,
    )
    _record_step(
        steps,
        _smoke_step(
            notepad_launcher(),
            "notepad_launch",
            "Notepad process was launched for disposable keyboard input",
        ),
        evidence_recorder,
    )
    controller.pause(1.0)
    _record_step(
        steps,
        _smoke_step(
            controller.type_text("notepad-typing-check", keyboard_text),
            "notepad_typing",
            "configured text was sent through low-level keyboard input",
        ),
        evidence_recorder,
    )
    _record_step(
        steps,
        _smoke_step(
            edge_launcher(edge_url),
            "edge_launch",
            "Microsoft Edge process was launched for browser input validation",
        ),
        evidence_recorder,
    )
    controller.pause(1.0)
    _record_step(
        steps,
        _smoke_step(
            controller.current_position_step("final-cursor-readback"),
            "final_cursor_readback",
            "cursor remained readable after app launch and typing checks",
        ),
        evidence_recorder,
    )
    return tuple(steps)


def _write_browser_fixture_html(trace_dir: Path, result_text: str) -> Path:
    fixture_path = trace_dir / "browser-fixture.html"
    result_path = trace_dir / "browser-fixture-result.html"
    # The proof fixture is a local HTML file so the command avoids network
    # variance while still proving real Edge keyboard and pointer I/O.
    fixture_path.write_text(
        "\n".join(
            [
                "<!doctype html>",
                '<html lang="en">',
                "<head>",
                '  <meta charset="utf-8">',
                "  <title>DeskPilot Browser Fixture</title>",
                "  <style>",
                "    body {",
                "      margin: 0;",
                "      min-height: 100vh;",
                "      display: grid;",
                "      place-items: center;",
                "      font-family: Segoe UI, Arial, sans-serif;",
                "      background: #f5f7fb;",
                "      color: #172033;",
                "    }",
                "    main {",
                "      width: min(560px, calc(100vw - 96px));",
                "      padding: 32px;",
                "      border: 1px solid #cbd5e1;",
                "      border-radius: 8px;",
                "      background: #ffffff;",
                "    }",
                "    h1 { font-size: 24px; margin: 0 0 20px; }",
                "    label { display: block; font-weight: 600; margin-bottom: 8px; }",
                "    input {",
                "      box-sizing: border-box;",
                "      width: 100%;",
                "      min-height: 48px;",
                "      padding: 0 14px;",
                "      border: 1px solid #64748b;",
                "      border-radius: 6px;",
                "      font-size: 18px;",
                "    }",
                "    button {",
                "      margin-top: 16px;",
                "      min-height: 44px;",
                "      padding: 0 18px;",
                "      border: 0;",
                "      border-radius: 6px;",
                "      background: #2563eb;",
                "      color: white;",
                "      font-size: 16px;",
                "      font-weight: 600;",
                "    }",
                "    #result { margin-top: 18px; font-weight: 700; }",
                "  </style>",
                "</head>",
                "<body>",
                "  <main>",
                "    <h1>DeskPilot Browser Fixture</h1>",
                f'    <form action="{result_path.name}" method="get">',
                '      <label for="routine-input">Routine note</label>',
                '      <input id="routine-input" name="routine" autofocus>',
                "      <button type=\"submit\">Submit fixture</button>",
                "    </form>",
                "    <p>Submitting this form navigates to a local result page.</p>",
                "  </main>",
                "</body>",
                "</html>",
                "",
            ]
        ),
        encoding="utf-8",
    )
    result_path.write_text(
        "\n".join(
            [
                "<!doctype html>",
                '<html lang="en">',
                "<head>",
                '  <meta charset="utf-8">',
                "  <title>DeskPilot Browser Fixture Result</title>",
                "  <style>",
                "    body {",
                "      margin: 0;",
                "      min-height: 100vh;",
                "      display: grid;",
                "      place-items: center;",
                "      font-family: Segoe UI, Arial, sans-serif;",
                "      background: #f5f7fb;",
                "      color: #172033;",
                "    }",
                "    main {",
                "      width: min(560px, calc(100vw - 96px));",
                "      padding: 32px;",
                "      border: 1px solid #cbd5e1;",
                "      border-radius: 8px;",
                "      background: #ffffff;",
                "    }",
                "    h1 { font-size: 24px; margin: 0 0 20px; }",
                "    p { font-size: 18px; font-weight: 700; }",
                "  </style>",
                "</head>",
                "<body>",
                "  <main>",
                "    <h1>DeskPilot Browser Fixture Result</h1>",
                f"    <p>{html_escape(result_text)}</p>",
                "  </main>",
                "</body>",
                "</html>",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return fixture_path


def _launch_notepad() -> MouseDemoStep:
    process = subprocess.Popen(["notepad.exe"])
    return MouseDemoStep(
        "open-notepad",
        "launch_application",
        {
            "application": "notepad.exe",
            "pid": process.pid,
            "expected_target": "fresh Notepad editing surface",
        },
    )


def _launch_edge(initial_url: str) -> MouseDemoStep:
    edge_args = ("--new-window", initial_url)
    attempted: list[str] = []
    for executable in _edge_executable_candidates():
        attempted.append(executable)
        try:
            process = subprocess.Popen([executable, *edge_args])
        except FileNotFoundError:
            continue
        return MouseDemoStep(
            "open-edge",
            "launch_application",
            {
                "application": "msedge.exe",
                "executable": executable,
                "arguments": list(edge_args),
                "pid": process.pid,
                "expected_target": "fresh Edge browser window",
            },
        )
    raise MouseDemoError(
        "Microsoft Edge was not found; attempted " + ", ".join(attempted)
    )


def _edge_executable_candidates() -> tuple[str, ...]:
    return (
        "msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    )


def _record_step(
    steps: list[MouseDemoStep],
    step: MouseDemoStep,
    evidence_recorder: PostActionEvidenceRecorder | None,
) -> None:
    if evidence_recorder is None:
        steps.append(step)
        return
    steps.append(evidence_recorder.attach(step))


def _smoke_step(
    step: MouseDemoStep,
    check_id: str,
    expectation: str,
) -> MouseDemoStep:
    metadata = dict(step.metadata)
    metadata["smoke_check"] = {
        "check_id": check_id,
        "expectation": expectation,
    }
    return MouseDemoStep(step.step_id, step.action, metadata)


def _post_action_evidence_from_observation(
    observation: ScreenObservation,
    *,
    cursor_position: tuple[int, int] | None,
    fallback_active_window_title: str | None,
) -> PostActionEvidence:
    return PostActionEvidence(
        status="passed",
        active_window_title=observation.active_window_title
        or fallback_active_window_title,
        screenshot_path=observation.screenshot_path,
        screenshot_size=observation.size,
        cursor_position=cursor_position,
        warnings=observation.warnings,
        metadata=observation.metadata,
    )


def _movement_trace_metadata(trace: MovementTrace) -> dict[str, object]:
    plan = trace.plan
    metadata: dict[str, object] = {
        "movement_points": len(plan.points),
        "movement_duration_seconds": plan.duration_seconds,
        "movement_smoothness": plan.movement_smoothness,
        "pointer_path_model": plan.path_model,
        "overshoot_applied": plan.overshoot_applied,
        "overshoot_point": list(plan.overshoot_point) if plan.overshoot_point else None,
        "settle_duration_seconds": plan.settle_duration_seconds,
        "random_seed": plan.random_seed,
        "cursor_frame_count": len(trace.frames),
        "cursor_frames": [frame.metadata() for frame in trace.frames],
        "max_drift_pixels": max(
            (frame.drift_pixels for frame in trace.frames),
            default=0.0,
        ),
        "sample_records": [record.metadata() for record in plan.sample_records],
    }
    if plan.timing_estimate is not None:
        metadata.update(plan.timing_estimate.metadata())
    return metadata


def _events_metadata(events: list[InputDemoEvent]) -> list[dict[str, object]]:
    return [event.metadata() for event in events]


def _write_report(
    trace_dir: Path,
    steps: tuple[MouseDemoStep, ...],
    status: str,
    reason: str | None,
    *,
    report_name: str,
) -> Path:
    action_log_path = _write_demo_action_log(trace_dir, steps)
    report_path = trace_dir / report_name
    payload: dict[str, object] = {
        "status": status,
        "reason": reason,
        "generated_at": datetime.now(UTC).isoformat(),
        "trace_dir": str(trace_dir),
        "action_log_path": str(action_log_path),
        "proof_manifest_path": str(trace_dir / "proof-manifest.json"),
        "steps": [
            {
                "step_id": step.step_id,
                "action": step.action,
                "metadata": step.metadata,
            }
            for step in steps
        ],
    }
    report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return report_path


def _write_proof_manifest(
    trace_dir: Path,
    *,
    proof_name: str,
    command: tuple[str, ...],
    status: str,
    reason: str | None,
    started_at: str,
    completed_at: str,
    report_path: Path,
    steps: tuple[MouseDemoStep, ...],
    monitor_bounds: tuple[int, int, int, int] | None,
) -> Path:
    manifest_path = trace_dir / "proof-manifest.json"
    # The manifest is the stable index for human review: it ties the visible
    # proof command to local evidence without requiring a rerun of desktop input.
    payload: dict[str, object] = {
        "schema_version": 1,
        "proof_name": proof_name,
        "command": list(command),
        "status": status,
        "reason": reason,
        "started_at": started_at,
        "completed_at": completed_at,
        "executable_version": __version__,
        "python_version": platform.python_version(),
        "windows_version": platform.platform() if sys.platform == "win32" else None,
        "platform": sys.platform,
        "monitor_geometry": _monitor_geometry_metadata(monitor_bounds),
        "dpi_scale": list(_safe_windows_dpi_scale()),
        "artifacts": {
            "trace_dir": str(trace_dir),
            "report_path": str(report_path),
            "action_log_path": str(trace_dir / "action-log.jsonl"),
            "proof_manifest_path": str(manifest_path),
            "screenshots": _screenshot_artifacts(trace_dir),
            "video_path": None,
        },
        "step_count": len(steps),
        "steps": [
            {
                "step_id": step.step_id,
                "action": step.action,
                "has_post_action_evidence": "post_action_evidence" in step.metadata,
            }
            for step in steps
        ],
    }
    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return manifest_path


def _write_demo_action_log(
    trace_dir: Path,
    steps: tuple[MouseDemoStep, ...],
) -> Path:
    action_log_path = trace_dir / "action-log.jsonl"
    with action_log_path.open("w", encoding="utf-8") as file:
        for index, step in enumerate(steps, start=1):
            payload = {
                "index": index,
                "phase": "demo_step",
                "message": f"{step.step_id}: {step.action}",
                "metadata": {
                    "step_id": step.step_id,
                    "action": step.action,
                    "post_action_evidence": step.metadata.get("post_action_evidence"),
                },
            }
            file.write(json.dumps(payload, sort_keys=True) + "\n")
    return action_log_path


def _write_smoke_checklist_markdown(
    trace_dir: Path,
    steps: tuple[MouseDemoStep, ...],
    status: str,
    report_path: Path,
) -> Path:
    checklist_path = trace_dir / "windows-smoke-checklist.md"
    lines = [
        "# Windows Smoke Checklist",
        "",
        f"- [x] Status: `{status}`",
        f"- [x] Report written: `{report_path}`",
        f"- [x] Action log written: `{trace_dir / 'action-log.jsonl'}`",
    ]
    for step in steps:
        smoke_check = step.metadata.get("smoke_check")
        if isinstance(smoke_check, dict):
            check_id = smoke_check.get("check_id", step.step_id)
            expectation = smoke_check.get("expectation", step.action)
            evidence = step.metadata.get("post_action_evidence")
            evidence_status = (
                evidence.get("status") if isinstance(evidence, dict) else "not captured"
            )
            lines.append(
                f"- [x] `{check_id}`: {expectation} "
                f"(post-action evidence: `{evidence_status}`)"
            )
    checklist_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return checklist_path


def _prepare_trace_dir(trace_root: Path, suffix: str) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    trace_dir = trace_root / f"{timestamp}-{suffix}"
    trace_dir.mkdir(parents=True, exist_ok=False)
    return trace_dir


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()


def _monitor_geometry_metadata(
    bounds: tuple[int, int, int, int] | None,
) -> dict[str, int] | None:
    if bounds is None:
        return None
    left, top, width, height = bounds
    return {
        "left": left,
        "top": top,
        "width": width,
        "height": height,
    }


def _safe_windows_dpi_scale() -> tuple[float, float]:
    if sys.platform != "win32":
        return (1.0, 1.0)
    try:
        ctypes_module: Any = ctypes
        dpi = int(ctypes_module.windll.user32.GetDpiForSystem())
    except (AttributeError, OSError):
        return (1.0, 1.0)
    scale = dpi / 96
    return (scale, scale)


def _screenshot_artifacts(trace_dir: Path) -> list[str]:
    screenshot_dir = trace_dir / "screenshots"
    if not screenshot_dir.exists():
        return []
    return [
        str(path)
        for path in sorted(screenshot_dir.glob("*.png"))
        if path.is_file()
    ]


def _input_demo_command(
    trace_root: Path,
    random_seed: int,
    movement_smoothness: float,
    keyboard_text: str,
    countdown_seconds: float,
) -> tuple[str, ...]:
    return (
        "desktop-agent",
        "demo-input",
        "--trace-root",
        str(trace_root),
        "--random-seed",
        str(random_seed),
        "--movement-smoothness",
        str(movement_smoothness),
        "--keyboard-text",
        keyboard_text,
        "--countdown-seconds",
        str(countdown_seconds),
    )


def _linkedin_demo_command(
    trace_root: Path,
    random_seed: int,
    movement_smoothness: float,
    countdown_seconds: float,
    url: str,
    find_text: str,
    page_load_seconds: float,
) -> tuple[str, ...]:
    return (
        "desktop-agent",
        "demo-linkedin",
        "--trace-root",
        str(trace_root),
        "--random-seed",
        str(random_seed),
        "--movement-smoothness",
        str(movement_smoothness),
        "--countdown-seconds",
        str(countdown_seconds),
        "--url",
        url,
        "--find-text",
        find_text,
        "--page-load-seconds",
        str(page_load_seconds),
    )


def _browser_fixture_command(
    trace_root: Path,
    random_seed: int,
    movement_smoothness: float,
    countdown_seconds: float,
    fixture_text: str,
    result_text: str,
    page_load_seconds: float,
) -> tuple[str, ...]:
    return (
        "desktop-agent",
        "proof",
        "browser-fixture",
        "--trace-root",
        str(trace_root),
        "--random-seed",
        str(random_seed),
        "--movement-smoothness",
        str(movement_smoothness),
        "--countdown-seconds",
        str(countdown_seconds),
        "--fixture-text",
        fixture_text,
        "--result-text",
        result_text,
        "--page-load-seconds",
        str(page_load_seconds),
    )


def _native_fixture_command(
    trace_root: Path,
    random_seed: int,
    movement_smoothness: float,
    countdown_seconds: float,
    initial_text: str,
    replacement_text: str,
) -> tuple[str, ...]:
    return (
        "desktop-agent",
        "proof",
        "native-fixture",
        "--trace-root",
        str(trace_root),
        "--random-seed",
        str(random_seed),
        "--movement-smoothness",
        str(movement_smoothness),
        "--countdown-seconds",
        str(countdown_seconds),
        "--initial-text",
        initial_text,
        "--replacement-text",
        replacement_text,
    )


def _windows_smoke_command(
    trace_root: Path,
    random_seed: int,
    movement_smoothness: float,
    countdown_seconds: float,
    keyboard_text: str,
    edge_url: str,
) -> tuple[str, ...]:
    return (
        "desktop-agent",
        "windows-smoke-checklist",
        "--trace-root",
        str(trace_root),
        "--random-seed",
        str(random_seed),
        "--movement-smoothness",
        str(movement_smoothness),
        "--countdown-seconds",
        str(countdown_seconds),
        "--keyboard-text",
        keyboard_text,
        "--edge-url",
        edge_url,
    )


def _countdown(seconds: float) -> None:
    whole_seconds = int(seconds)
    for remaining in range(whole_seconds, 0, -1):
        print(f"starting global input demo in {remaining}...")
        time.sleep(1.0)
    fractional = seconds - whole_seconds
    if fractional > 0:
        time.sleep(fractional)


def _input_demo_points(screen_bounds: tuple[int, int, int, int]) -> InputDemoPoints:
    waypoints = (
        _screen_point(screen_bounds, 0.18, 0.18),
        _screen_point(screen_bounds, 0.82, 0.30),
        _screen_point(screen_bounds, 0.50, 0.78),
    )
    return InputDemoPoints(
        screen_bounds=screen_bounds,
        waypoints=waypoints,
        drag_start=_screen_point(screen_bounds, 0.26, 0.38),
        drag_end=_screen_point(screen_bounds, 0.52, 0.58),
    )


def _screen_point(
    screen_bounds: tuple[int, int, int, int],
    x_fraction: float,
    y_fraction: float,
) -> tuple[int, int]:
    left, top, width, height = screen_bounds
    if width <= 0 or height <= 0:
        raise MouseDemoError(f"invalid virtual screen bounds: {screen_bounds}")

    # Keep the demo away from screen edges so taskbars and VM chrome are avoided.
    margin_x = min(140, max(20, width // 8))
    margin_y = min(110, max(20, height // 8))
    usable_left = left + margin_x
    usable_top = top + margin_y
    usable_width = max(1, width - (margin_x * 2))
    usable_height = max(1, height - (margin_y * 2))
    x = usable_left + round(usable_width * x_fraction)
    y = usable_top + round(usable_height * y_fraction)
    return (x, y)


def _windows_virtual_screen_bounds() -> tuple[int, int, int, int]:
    ctypes_module: Any = ctypes
    user32: Any = ctypes_module.windll.user32
    left = int(user32.GetSystemMetrics(76))
    top = int(user32.GetSystemMetrics(77))
    width = int(user32.GetSystemMetrics(78))
    height = int(user32.GetSystemMetrics(79))
    if width <= 0 or height <= 0:
        width = int(user32.GetSystemMetrics(0))
        height = int(user32.GetSystemMetrics(1))
        left = 0
        top = 0
    return (left, top, width, height)


def _set_process_dpi_aware() -> None:
    try:
        ctypes_module: Any = ctypes
        user32: Any = ctypes_module.windll.user32
        user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        return
