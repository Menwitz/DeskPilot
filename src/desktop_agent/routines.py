"""Routine catalog schema contracts for personal assistant packs."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

import yaml

ROUTINE_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
SUPPORTED_ROUTINE_SAFETY_CLASSES: frozenset[str] = frozenset(
    {"low", "medium", "high", "sensitive"},
)
SUPPORTED_SCHEDULE_POLICIES: frozenset[str] = frozenset(
    {"manual", "on_demand", "scheduled"},
)
SUPPORTED_APPROVAL_POLICIES: frozenset[str] = frozenset(
    {"none", "confirm", "manifest_required", "manual_handoff"},
)
RoutineReferenceKind = Literal["task", "playbook"]


class RoutineDefinitionError(ValueError):
    """Raised when a routine definition fails schema validation."""


@dataclass(frozen=True)
class RoutineReference:
    """Reference to executable routine implementation content."""

    kind: RoutineReferenceKind
    task_path: Path | None = None
    playbook_site: str | None = None
    playbook_flow: str | None = None


@dataclass(frozen=True)
class RoutineDefinition:
    """Reviewed routine metadata stored in routine packs."""

    id: str
    name: str
    description: str
    goal: str
    required_app: str | None
    required_site: str | None
    tags: tuple[str, ...]
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    safety_class: str
    schedule_policy: str
    approval_policy: str
    expected_duration_seconds: float
    reference: RoutineReference
    source_path: Path | None = None

    def report_metadata(self) -> dict[str, object]:
        """Return JSON-safe routine fields for traces and catalog reports."""
        return {
            "routine_id": self.id,
            "routine_name": self.name,
            "routine_tags": list(self.tags),
            "routine_safety_class": self.safety_class,
            "routine_schedule_policy": self.schedule_policy,
            "routine_approval_policy": self.approval_policy,
            "routine_expected_duration_seconds": self.expected_duration_seconds,
            "routine_reference_kind": self.reference.kind,
        }


def load_routine_definition(path: Path) -> RoutineDefinition:
    """Load one routine YAML definition from a routine pack."""
    if not path.exists():
        raise RoutineDefinitionError(f"routine definition not found: {path}")
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    data = _mapping(loaded, "routine definition must contain a mapping")
    routine = routine_definition_from_mapping(data, source_path=path)
    validate_routine_definition(routine)
    return routine


def routine_definition_from_mapping(
    data: Mapping[str, object],
    *,
    source_path: Path | None = None,
) -> RoutineDefinition:
    """Parse a routine definition mapping into a typed schema object."""
    base_dir = source_path.parent if source_path is not None else Path(".")
    routine = RoutineDefinition(
        id=_required_string(data, "id"),
        name=_required_string(data, "name"),
        description=_required_string(data, "description"),
        goal=_required_string(data, "goal"),
        required_app=_optional_string(data, "required_app"),
        required_site=_optional_string(data, "required_site"),
        tags=_string_tuple(data.get("tags"), "tags"),
        inputs=_string_tuple(data.get("inputs"), "inputs"),
        outputs=_string_tuple(data.get("outputs"), "outputs"),
        safety_class=_required_string(data, "safety_class"),
        schedule_policy=_required_string(data, "schedule_policy"),
        approval_policy=_required_string(data, "approval_policy"),
        expected_duration_seconds=_positive_float(
            data.get("expected_duration_seconds"),
            "expected_duration_seconds",
        ),
        reference=_reference_from_value(data.get("reference"), base_dir),
        source_path=source_path,
    )
    validate_routine_definition(routine)
    return routine


def validate_routine_definition(routine: RoutineDefinition) -> None:
    """Validate one routine definition before catalog indexing."""
    errors: list[str] = []
    if not ROUTINE_ID_PATTERN.fullmatch(routine.id):
        errors.append("id is required and must be slug-safe")
    for field_name in ("name", "description", "goal"):
        if not getattr(routine, field_name):
            errors.append(f"{field_name} is required")
    if routine.safety_class not in SUPPORTED_ROUTINE_SAFETY_CLASSES:
        errors.append(f"unsupported safety_class: {routine.safety_class}")
    if routine.schedule_policy not in SUPPORTED_SCHEDULE_POLICIES:
        errors.append(f"unsupported schedule_policy: {routine.schedule_policy}")
    if routine.approval_policy not in SUPPORTED_APPROVAL_POLICIES:
        errors.append(f"unsupported approval_policy: {routine.approval_policy}")
    if routine.expected_duration_seconds <= 0:
        errors.append("expected_duration_seconds must be greater than zero")
    errors.extend(_reference_errors(routine.reference))
    if errors:
        raise RoutineDefinitionError("; ".join(errors))


def _reference_from_value(value: object, base_dir: Path) -> RoutineReference:
    data = _mapping(value, "reference must be a mapping")
    kind_value = _required_string(data, "type")
    if kind_value == "task":
        raw_path = _required_string(data, "path")
        task_path = Path(raw_path)
        if not task_path.is_absolute():
            task_path = base_dir / task_path
        return RoutineReference(kind="task", task_path=task_path)
    if kind_value == "playbook":
        return RoutineReference(
            kind="playbook",
            playbook_site=_required_string(data, "site"),
            playbook_flow=_required_string(data, "flow"),
        )
    raise RoutineDefinitionError("reference type must be task or playbook")


def _reference_errors(reference: RoutineReference) -> list[str]:
    if reference.kind == "task":
        if reference.task_path is not None:
            return []
        return ["task reference path is required"]
    if reference.kind == "playbook":
        errors: list[str] = []
        if not reference.playbook_site:
            errors.append("playbook reference site is required")
        if not reference.playbook_flow:
            errors.append("playbook reference flow is required")
        return errors
    return ["reference type must be task or playbook"]


def _mapping(value: object, message: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise RoutineDefinitionError(message)
    return cast(Mapping[str, object], value)


def _required_string(data: Mapping[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise RoutineDefinitionError(f"{key} is required")
    return value


def _optional_string(data: Mapping[str, object], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise RoutineDefinitionError(f"{key} must be a string")
    return value or None


def _string_tuple(value: object, key: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list | tuple):
        raise RoutineDefinitionError(f"{key} must be a list")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item:
            raise RoutineDefinitionError(f"{key} must contain non-empty strings")
        result.append(item)
    return tuple(result)


def _positive_float(value: object, key: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise RoutineDefinitionError(f"{key} must be numeric")
    result = float(value)
    if result <= 0:
        raise RoutineDefinitionError(f"{key} must be greater than zero")
    return result
