"""Local recorder session controls for demonstrated routine capture."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path
from typing import Literal, Protocol, cast
from uuid import uuid4

from desktop_agent.task_dsl import TaskDefinition, TaskStep

RECORDER_SESSION_FORMAT = "deskpilot_recorder_session_v1"
RecorderStatus = Literal["recording", "paused", "stopped", "saved"]
RecorderEventType = Literal["observation", "input_event", "selected_point"]


class RecorderError(RuntimeError):
    """Raised when recorder session controls are used out of order."""


class RecorderGenerationError(RecorderError):
    """Raised when recorder events cannot be converted into task steps."""


class UiaPointCaptureAdapter(Protocol):
    """UIA hit-test seam used by the recorder without hard-coding pywinauto."""

    def element_at_point(self, point: tuple[int, int]) -> object: ...


class OcrTextBlockLike(Protocol):
    """OCR text-block shape consumed by recorder click context capture."""

    @property
    def text(self) -> str: ...

    @property
    def bounds(self) -> object: ...

    @property
    def confidence(self) -> float: ...


@dataclass(frozen=True)
class RecorderCandidateContext:
    """Stable candidate details observed near a recorded interaction."""

    source: str
    label: str | None = None
    control_type: str | None = None
    bounds: dict[str, int] | None = None
    confidence: float | None = None
    metadata: dict[str, object] = field(default_factory=dict)

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "source": self.source,
            "metadata": dict(self.metadata),
        }
        if self.label is not None:
            payload["label"] = self.label
        if self.control_type is not None:
            payload["control_type"] = self.control_type
        if self.bounds is not None:
            payload["bounds"] = dict(self.bounds)
        if self.confidence is not None:
            payload["confidence"] = self.confidence
        return payload

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, object],
    ) -> RecorderCandidateContext:
        bounds = payload.get("bounds")
        if bounds is not None and not isinstance(bounds, dict):
            raise RecorderError("recorder candidate bounds must be an object")
        confidence = payload.get("confidence")
        if confidence is not None and not isinstance(confidence, int | float):
            raise RecorderError("recorder candidate confidence must be numeric")
        return cls(
            source=_required_string(payload, "source"),
            label=_optional_string(payload, "label"),
            control_type=_optional_string(payload, "control_type"),
            bounds=_int_dict(bounds) if isinstance(bounds, dict) else None,
            confidence=float(confidence) if confidence is not None else None,
            metadata=_object_dict(payload.get("metadata", {})),
        )


@dataclass(frozen=True)
class RecorderEvent:
    """Single timestamped recorder fact captured from desktop activity."""

    event_id: str
    event_type: RecorderEventType
    timestamp: str
    active_window: str | None = None
    screenshot_path: str | None = None
    selected_point: tuple[int, int] | None = None
    input_event: dict[str, object] | None = None
    candidate_context: tuple[RecorderCandidateContext, ...] = field(
        default_factory=tuple,
    )
    metadata: dict[str, object] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        event_type: RecorderEventType,
        *,
        active_window: str | None = None,
        screenshot_path: str | None = None,
        selected_point: tuple[int, int] | None = None,
        input_event: dict[str, object] | None = None,
        candidate_context: tuple[RecorderCandidateContext, ...] = (),
        metadata: dict[str, object] | None = None,
    ) -> RecorderEvent:
        return cls(
            event_id=uuid4().hex,
            event_type=event_type,
            timestamp=_timestamp(),
            active_window=active_window,
            screenshot_path=screenshot_path,
            selected_point=selected_point,
            input_event=dict(input_event) if input_event is not None else None,
            candidate_context=candidate_context,
            metadata=dict(metadata or {}),
        )

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "candidate_context": [
                candidate.to_payload() for candidate in self.candidate_context
            ],
            "metadata": dict(self.metadata),
        }
        if self.active_window is not None:
            payload["active_window"] = self.active_window
        if self.screenshot_path is not None:
            payload["screenshot_path"] = self.screenshot_path
        if self.selected_point is not None:
            payload["selected_point"] = list(self.selected_point)
        if self.input_event is not None:
            payload["input_event"] = dict(self.input_event)
        return payload

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> RecorderEvent:
        event_type_value = payload.get("event_type")
        if event_type_value not in {"observation", "input_event", "selected_point"}:
            raise RecorderError("recorder event type is unsupported")
        event_type = cast(RecorderEventType, event_type_value)
        candidate_context = payload.get("candidate_context", [])
        if not isinstance(candidate_context, list):
            raise RecorderError("recorder candidate_context must be a list")
        return cls(
            event_id=_required_string(payload, "event_id"),
            event_type=event_type,
            timestamp=_required_string(payload, "timestamp"),
            active_window=_optional_string(payload, "active_window"),
            screenshot_path=_optional_string(payload, "screenshot_path"),
            selected_point=_optional_point(payload.get("selected_point")),
            input_event=_optional_object_dict(payload.get("input_event")),
            candidate_context=tuple(
                RecorderCandidateContext.from_payload(_object_dict(candidate))
                for candidate in candidate_context
            ),
            metadata=_object_dict(payload.get("metadata", {})),
        )


@dataclass(frozen=True)
class RecorderSession:
    """Serializable recorder control state saved between CLI invocations."""

    session_id: str
    name: str
    status: RecorderStatus
    created_at: str
    updated_at: str
    events: tuple[RecorderEvent, ...] = field(default_factory=tuple)

    def to_payload(self) -> dict[str, object]:
        return {
            "format": RECORDER_SESSION_FORMAT,
            "session_id": self.session_id,
            "name": self.name,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "events": [event.to_payload() for event in self.events],
            "event_count": len(self.events),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> RecorderSession:
        if payload.get("format") != RECORDER_SESSION_FORMAT:
            raise RecorderError("recorder session format is unsupported")
        status_value = payload.get("status")
        if status_value not in {"recording", "paused", "stopped", "saved"}:
            raise RecorderError("recorder session status is unsupported")
        status = cast(RecorderStatus, status_value)
        events = payload.get("events", ())
        if not isinstance(events, list):
            raise RecorderError("recorder session events must be a list")
        return cls(
            session_id=_required_string(payload, "session_id"),
            name=_required_string(payload, "name"),
            status=status,
            created_at=_required_string(payload, "created_at"),
            updated_at=_required_string(payload, "updated_at"),
            events=tuple(
                RecorderEvent.from_payload(_object_dict(event)) for event in events
            ),
        )


class RecorderController:
    """State-machine wrapper for local recorder start/pause/stop/save/discard."""

    def __init__(self, state_path: Path) -> None:
        self.state_path = state_path

    def start(self, *, name: str, overwrite: bool = False) -> RecorderSession:
        if self.state_path.exists() and not overwrite:
            raise RecorderError(
                f"recorder session already exists: {self.state_path}",
            )
        now = _timestamp()
        session = RecorderSession(
            session_id=uuid4().hex,
            name=name,
            status="recording",
            created_at=now,
            updated_at=now,
        )
        self._write(session)
        return session

    def pause(self) -> RecorderSession:
        session = self.load()
        if session.status != "recording":
            raise RecorderError("only a recording session can be paused")
        return self._replace_status(session, "paused")

    def stop(self) -> RecorderSession:
        session = self.load()
        if session.status not in {"recording", "paused"}:
            raise RecorderError("only recording or paused sessions can be stopped")
        return self._replace_status(session, "stopped")

    def save(self, output_path: Path) -> RecorderSession:
        session = self.load()
        if session.status not in {"recording", "paused", "stopped"}:
            raise RecorderError("only active recorder sessions can be saved")
        saved = self._replace_status(session, "saved")
        _write_payload(output_path, saved.to_payload())
        return saved

    def record_event(self, event: RecorderEvent) -> RecorderSession:
        session = self.load()
        if session.status != "recording":
            raise RecorderError("only recording sessions can receive events")
        updated = RecorderSession(
            session_id=session.session_id,
            name=session.name,
            status=session.status,
            created_at=session.created_at,
            updated_at=_timestamp(),
            events=(*session.events, event),
        )
        self._write(updated)
        return updated

    def discard(self) -> RecorderSession:
        session = self.load()
        self.state_path.unlink()
        return session

    def load(self) -> RecorderSession:
        if not self.state_path.exists():
            raise RecorderError(f"recorder session not found: {self.state_path}")
        payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise RecorderError("recorder session file must contain an object")
        return RecorderSession.from_payload(payload)

    def _replace_status(
        self,
        session: RecorderSession,
        status: RecorderStatus,
    ) -> RecorderSession:
        updated = RecorderSession(
            session_id=session.session_id,
            name=session.name,
            status=status,
            created_at=session.created_at,
            updated_at=_timestamp(),
            events=session.events,
        )
        self._write(updated)
        return updated

    def _write(self, session: RecorderSession) -> None:
        _write_payload(self.state_path, session.to_payload())


def capture_uia_context_for_point(
    point: tuple[int, int],
    adapter: UiaPointCaptureAdapter | None = None,
) -> tuple[RecorderCandidateContext, ...]:
    if adapter is None:
        from desktop_agent.platforms.windows.uia import WindowsUiaAdapter

        adapter = WindowsUiaAdapter()
    try:
        snapshot = adapter.element_at_point(point)
    except Exception:
        return ()
    name = str(getattr(snapshot, "name", ""))
    control_type = str(getattr(snapshot, "control_type", "unknown"))
    enabled = bool(getattr(snapshot, "enabled", True))
    visible = bool(getattr(snapshot, "visible", True))
    return (
        RecorderCandidateContext(
            source="uia",
            label=name or control_type,
            control_type=control_type,
            bounds=_bounds_payload(getattr(snapshot, "bounds", None)),
            confidence=0.95 if enabled and visible else 0.5,
            metadata={"enabled": enabled, "visible": visible},
        ),
    )


def capture_ocr_context_for_point(
    point: tuple[int, int],
    text_blocks: tuple[OcrTextBlockLike, ...],
    *,
    max_distance_pixels: float = 96.0,
    limit: int = 5,
) -> tuple[RecorderCandidateContext, ...]:
    scored_blocks: list[tuple[bool, float, OcrTextBlockLike]] = []
    for block in text_blocks:
        bounds_payload = _bounds_payload(block.bounds)
        if bounds_payload is None:
            continue
        contains_point = _point_inside_bounds_payload(point, bounds_payload)
        distance = _distance_to_bounds_center(point, bounds_payload)
        if contains_point or distance <= max_distance_pixels:
            scored_blocks.append((contains_point, distance, block))

    contexts: list[RecorderCandidateContext] = []
    for contains_point, distance, block in sorted(
        scored_blocks,
        key=lambda item: (not item[0], item[1]),
    )[:limit]:
        contexts.append(
            RecorderCandidateContext(
                source="ocr",
                label=block.text,
                bounds=_bounds_payload(block.bounds),
                confidence=block.confidence,
                metadata={
                    "contains_point": contains_point,
                    "distance_pixels": round(distance, 3),
                },
            ),
        )
    return tuple(contexts)


def capture_image_snippet_for_point(
    point: tuple[int, int],
    screenshot_path: Path,
    output_path: Path,
    existing_context: tuple[RecorderCandidateContext, ...],
    *,
    size: tuple[int, int] = (96, 96),
) -> RecorderCandidateContext | None:
    if _has_stable_uia_or_ocr_context(existing_context):
        return None
    cv2 = import_module("cv2")
    image = cv2.imread(str(screenshot_path), cv2.IMREAD_UNCHANGED)
    if image is None:
        raise RecorderError(f"screenshot could not be read: {screenshot_path}")
    height, width = int(image.shape[0]), int(image.shape[1])
    bounds = _snippet_bounds(point, size, width=width, height=height)
    crop = image[
        bounds["y"] : bounds["y"] + bounds["height"],
        bounds["x"] : bounds["x"] + bounds["width"],
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not bool(cv2.imwrite(str(output_path), crop)):
        raise RecorderError(f"image snippet could not be written: {output_path}")
    return RecorderCandidateContext(
        source="image",
        label=output_path.name,
        bounds=bounds,
        confidence=0.5,
        metadata={
            "snippet_path": str(output_path),
            "source_screenshot_path": str(screenshot_path),
            "fallback_reason": "no_stable_uia_or_ocr_target",
        },
    )


def generate_task_from_recorder_session(session: RecorderSession) -> TaskDefinition:
    steps: list[TaskStep] = []
    for index, event in enumerate(session.events, start=1):
        step = _step_from_recorder_event(index, event)
        if step is not None:
            steps.append(step)
    if not steps:
        raise RecorderGenerationError("recorder session has no task-generating events")
    return TaskDefinition(
        name=session.name,
        allowed_windows=_allowed_windows_from_events(session.events),
        timeout_seconds=300,
        steps=tuple(steps),
        metadata={
            "recorder_session_id": session.session_id,
            "recorder_event_count": len(session.events),
        },
    )


def _write_payload(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _timestamp() -> str:
    return datetime.now(tz=UTC).isoformat(timespec="seconds")


def _required_string(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise RecorderError(f"recorder session {key} is required")
    return value


def _optional_string(payload: dict[str, object], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise RecorderError(f"recorder session {key} must be a string")
    return value


def _optional_point(value: object) -> tuple[int, int] | None:
    if value is None:
        return None
    if (
        not isinstance(value, list)
        or len(value) != 2
        or not all(isinstance(item, int) for item in value)
    ):
        raise RecorderError("recorder selected_point must be [x, y]")
    return (value[0], value[1])


def _optional_object_dict(value: object) -> dict[str, object] | None:
    if value is None:
        return None
    return _object_dict(value)


def _object_dict(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise RecorderError("recorder payload field must contain an object")
    return dict(value)


def _int_dict(value: dict[object, object]) -> dict[str, int]:
    result: dict[str, int] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not isinstance(item, int):
            raise RecorderError("recorder bounds must contain integer fields")
        result[key] = item
    return result


def _bounds_payload(bounds: object) -> dict[str, int] | None:
    if bounds is None:
        return None
    values = {
        "x": getattr(bounds, "x", None),
        "y": getattr(bounds, "y", None),
        "width": getattr(bounds, "width", None),
        "height": getattr(bounds, "height", None),
    }
    if not all(isinstance(value, int) for value in values.values()):
        return None
    return cast(dict[str, int], values)


def _point_inside_bounds_payload(
    point: tuple[int, int],
    bounds: dict[str, int],
) -> bool:
    return (
        bounds["x"] <= point[0] <= bounds["x"] + bounds["width"]
        and bounds["y"] <= point[1] <= bounds["y"] + bounds["height"]
    )


def _distance_to_bounds_center(
    point: tuple[int, int],
    bounds: dict[str, int],
) -> float:
    center_x = bounds["x"] + (bounds["width"] / 2)
    center_y = bounds["y"] + (bounds["height"] / 2)
    return math.hypot(point[0] - center_x, point[1] - center_y)


def _has_stable_uia_or_ocr_context(
    contexts: tuple[RecorderCandidateContext, ...],
) -> bool:
    return any(
        context.source in {"uia", "ocr"} and bool(context.label) and context.bounds
        for context in contexts
    )


def _snippet_bounds(
    point: tuple[int, int],
    size: tuple[int, int],
    *,
    width: int,
    height: int,
) -> dict[str, int]:
    snippet_width = max(1, min(size[0], width))
    snippet_height = max(1, min(size[1], height))
    left = min(max(point[0] - (snippet_width // 2), 0), width - snippet_width)
    top = min(max(point[1] - (snippet_height // 2), 0), height - snippet_height)
    return {
        "x": left,
        "y": top,
        "width": snippet_width,
        "height": snippet_height,
    }


def _step_from_recorder_event(index: int, event: RecorderEvent) -> TaskStep | None:
    if event.event_type == "selected_point":
        return _click_step_from_event(index, event)
    if event.event_type == "input_event" and event.input_event is not None:
        return _input_step_from_event(index, event)
    if event.event_type == "observation":
        return _observation_step_from_event(index, event)
    return None


def _click_step_from_event(index: int, event: RecorderEvent) -> TaskStep | None:
    context = _preferred_click_context(event.candidate_context)
    if context is None:
        return None
    step_id = _step_id(index, f"click-{context.source}")
    if context.source == "uia":
        return TaskStep(
            id=step_id,
            action="click_uia",
            target=context.label or context.control_type,
        )
    if context.source == "ocr":
        return TaskStep(id=step_id, action="click_text", target=context.label)
    if context.source == "image":
        snippet_path = context.metadata.get("snippet_path")
        if not isinstance(snippet_path, str):
            raise RecorderGenerationError("image recorder context needs snippet_path")
        return TaskStep(
            id=step_id,
            action="click_image",
            image=Path(snippet_path),
            target=context.label,
        )
    return None


def _input_step_from_event(index: int, event: RecorderEvent) -> TaskStep | None:
    payload = event.input_event or {}
    kind = payload.get("kind")
    if kind == "type_text":
        return TaskStep(
            id=_step_id(index, "type-text"),
            action="type_text",
            text=_payload_string(payload, "text"),
        )
    if kind in {"press_key", "hotkey"}:
        return TaskStep(
            id=_step_id(index, "press-key"),
            action="press_key",
            text=_payload_string(payload, "key"),
        )
    if kind == "scroll":
        clicks = payload.get("clicks", -3)
        return TaskStep(
            id=_step_id(index, "scroll"),
            action="scroll",
            text=str(clicks),
        )
    if kind == "wait_for":
        return TaskStep(
            id=_step_id(index, "wait-for"),
            action="wait_for",
            target=_payload_string(payload, "target"),
        )
    if kind == "assert_visible":
        return TaskStep(
            id=_step_id(index, "assert-visible"),
            action="assert_visible",
            target=_payload_string(payload, "target"),
        )
    return None


def _observation_step_from_event(index: int, event: RecorderEvent) -> TaskStep | None:
    suggested_action = event.metadata.get("suggested_action")
    target = event.metadata.get("target")
    if suggested_action == "wait_for" and isinstance(target, str):
        return TaskStep(
            id=_step_id(index, "wait-for"),
            action="wait_for",
            target=target,
        )
    if suggested_action == "assert_visible" and isinstance(target, str):
        return TaskStep(
            id=_step_id(index, "assert-visible"),
            action="assert_visible",
            target=target,
        )
    return None


def _preferred_click_context(
    contexts: tuple[RecorderCandidateContext, ...],
) -> RecorderCandidateContext | None:
    for source in ("uia", "ocr", "image"):
        for context in contexts:
            if context.source == source and (context.label or context.control_type):
                return context
    return None


def _allowed_windows_from_events(events: tuple[RecorderEvent, ...]) -> tuple[str, ...]:
    windows = tuple(
        dict.fromkeys(
            event.active_window
            for event in events
            if isinstance(event.active_window, str) and event.active_window
        ),
    )
    return windows or ("Recorded Window",)


def _payload_string(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise RecorderGenerationError(f"recorder input event {key} is required")
    return value


def _step_id(index: int, suffix: str) -> str:
    return f"recorded-{index:03d}-{suffix}"
