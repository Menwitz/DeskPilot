"""Trace schema migration helpers for legacy local artifacts."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import cast

from desktop_agent.tracing import TRACE_SCHEMA_V2

SUPPORTED_TRACE_SCHEMA_VERSIONS: frozenset[str] = frozenset({"1", "2"})


class TraceMigrationError(ValueError):
    """Raised when a trace artifact cannot be migrated safely."""


def migrate_trace_report_payload(payload: object) -> dict[str, object]:
    """Normalize a final-report payload to the current trace schema."""
    if not isinstance(payload, dict):
        raise TraceMigrationError("trace report must be a JSON object")
    report = cast(dict[str, object], deepcopy(payload))
    source_version = _source_version(report)
    _require_supported_version(source_version)

    report["trace_schema_version"] = TRACE_SCHEMA_V2.version
    report["trace_schema"] = TRACE_SCHEMA_V2.to_dict()
    report.setdefault("metadata", {})
    report["steps"] = _migrated_list_of_objects(report.get("steps"), "steps")
    report["events"] = [
        _migrate_event(event, index)
        for index, event in enumerate(
            _migrated_list_of_objects(report.get("events"), "events"),
            start=1,
        )
    ]
    report["trace_schema_migration"] = {
        "from_version": source_version,
        "to_version": TRACE_SCHEMA_V2.version,
        "applied": source_version != TRACE_SCHEMA_V2.version,
    }
    return report


def migrate_action_log_event_payload(
    payload: object,
    *,
    index: int | None = None,
) -> dict[str, object]:
    """Normalize one action-log row to the current trace schema."""
    if not isinstance(payload, dict):
        raise TraceMigrationError("action log event must be a JSON object")
    event = cast(dict[str, object], deepcopy(payload))
    source_version = _source_version(event)
    _require_supported_version(source_version)
    migrated = _migrate_event(event, index)
    migrated["trace_schema_migration"] = {
        "from_version": source_version,
        "to_version": TRACE_SCHEMA_V2.version,
        "applied": source_version != TRACE_SCHEMA_V2.version,
    }
    return migrated


def load_and_migrate_trace_report(path: Path) -> dict[str, object]:
    """Read and migrate a final-report JSON file."""
    return migrate_trace_report_payload(json.loads(path.read_text(encoding="utf-8")))


def _migrate_event(event: dict[str, object], index: int | None) -> dict[str, object]:
    event.setdefault("phase", "unknown")
    event.setdefault("message", "")
    event.setdefault("metadata", {})
    event["trace_schema_version"] = TRACE_SCHEMA_V2.version
    if index is not None:
        event.setdefault("index", index)
    return event


def _migrated_list_of_objects(
    value: object,
    field_name: str,
) -> list[dict[str, object]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise TraceMigrationError(f"{field_name} must be a list")
    result: list[dict[str, object]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise TraceMigrationError(f"{field_name}[{index}] must be an object")
        result.append(cast(dict[str, object], item))
    return result


def _source_version(payload: dict[str, object]) -> str:
    raw_version = payload.get("trace_schema_version", "1")
    if not isinstance(raw_version, str | int):
        raise TraceMigrationError("trace_schema_version must be a string or integer")
    return str(raw_version)


def _require_supported_version(version: str) -> None:
    if version not in SUPPORTED_TRACE_SCHEMA_VERSIONS:
        raise TraceMigrationError(f"unsupported trace schema version: {version}")
