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


class RecorderError(RuntimeError):
    """Raised when recorder session controls are used out of order."""


@dataclass(frozen=True)
class RecorderSession:
    """Serializable recorder control state saved between CLI invocations."""

    session_id: str
    name: str
    status: RecorderStatus
    created_at: str
    updated_at: str
    events: tuple[dict[str, object], ...] = field(default_factory=tuple)

    def to_payload(self) -> dict[str, object]:
        return {
            "format": RECORDER_SESSION_FORMAT,
            "session_id": self.session_id,
            "name": self.name,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "events": list(self.events),
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
            events=tuple(_event_payload(event) for event in events),
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


def _event_payload(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise RecorderError("recorder session events must contain objects")
    return dict(value)
