"""Local recorder session controls for demonstrated routine capture."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast
from uuid import uuid4

RECORDER_SESSION_FORMAT = "deskpilot_recorder_session_v1"
RecorderStatus = Literal["recording", "paused", "stopped", "saved"]
RecorderEventType = Literal["observation", "input_event", "selected_point"]


class RecorderError(RuntimeError):
    """Raised when recorder session controls are used out of order."""


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
