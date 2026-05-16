"""Routine catalog migration helpers for legacy local routine YAML."""

from __future__ import annotations

from copy import deepcopy
from typing import cast

CURRENT_ROUTINE_SCHEMA_VERSION = "2"
SUPPORTED_ROUTINE_SCHEMA_VERSIONS: frozenset[str] = frozenset({"1", "2"})


class RoutineMigrationError(ValueError):
    """Raised when a routine definition cannot be migrated safely."""


def migrate_routine_definition_payload(payload: object) -> dict[str, object]:
    """Normalize one routine definition payload to the current schema."""
    if not isinstance(payload, dict):
        raise RoutineMigrationError("routine definition must be a JSON/YAML object")
    routine = cast(dict[str, object], deepcopy(payload))
    source_version = _source_version(routine)
    _require_supported_version(source_version)

    if source_version == "1":
        _apply_v1_defaults(routine)

    routine["routine_schema_version"] = CURRENT_ROUTINE_SCHEMA_VERSION
    routine["routine_schema_migration"] = {
        "from_version": source_version,
        "to_version": CURRENT_ROUTINE_SCHEMA_VERSION,
        "applied": source_version != CURRENT_ROUTINE_SCHEMA_VERSION,
    }
    return routine


def _apply_v1_defaults(routine: dict[str, object]) -> None:
    # Legacy routine packs predated these reviewed catalog policy fields.
    routine.setdefault("tags", [])
    routine.setdefault("inputs", [])
    routine.setdefault("outputs", [])
    routine.setdefault("safety_class", "low")
    routine.setdefault("schedule_policy", "manual")
    routine.setdefault("approval_policy", "none")
    routine.setdefault("expected_duration_seconds", 60)
    if "reference" not in routine:
        _migrate_legacy_reference(routine)


def _migrate_legacy_reference(routine: dict[str, object]) -> None:
    task_path = routine.get("task_path")
    if isinstance(task_path, str) and task_path:
        routine["reference"] = {"type": "task", "path": task_path}
        return

    playbook = routine.get("playbook")
    if isinstance(playbook, dict):
        site = playbook.get("site")
        flow = playbook.get("flow")
    else:
        site = routine.get("playbook_site")
        flow = routine.get("playbook_flow")
    if isinstance(site, str) and isinstance(flow, str) and site and flow:
        routine["reference"] = {"type": "playbook", "site": site, "flow": flow}


def _source_version(payload: dict[str, object]) -> str:
    raw_version = payload.get("routine_schema_version", "1")
    if isinstance(raw_version, bool) or not isinstance(raw_version, str | int):
        raise RoutineMigrationError(
            "routine_schema_version must be a string or integer",
        )
    return str(raw_version)


def _require_supported_version(version: str) -> None:
    if version not in SUPPORTED_ROUTINE_SCHEMA_VERSIONS:
        raise RoutineMigrationError(f"unsupported routine schema version: {version}")
