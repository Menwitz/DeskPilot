from pathlib import Path
from typing import cast

import pytest

from desktop_agent.routine_migrations import (
    CURRENT_ROUTINE_SCHEMA_VERSION,
    RoutineMigrationError,
    migrate_routine_definition_payload,
)
from desktop_agent.routines import (
    RoutineDefinitionError,
    load_routine_catalog,
    routine_definition_from_mapping,
)


def test_migrate_legacy_routine_adds_defaults_and_task_reference() -> None:
    legacy = {
        "id": "browser.legacy-review",
        "name": "Legacy browser review",
        "description": "Review a browser page from an older routine pack.",
        "goal": "Open the reviewed page and collect a short summary.",
        "task_path": "tasks/legacy-review.yaml",
    }

    migrated = migrate_routine_definition_payload(legacy)
    reference = cast(dict[str, object], migrated["reference"])

    assert migrated["routine_schema_version"] == CURRENT_ROUTINE_SCHEMA_VERSION
    assert migrated["tags"] == []
    assert migrated["safety_class"] == "low"
    assert migrated["schedule_policy"] == "manual"
    assert migrated["approval_policy"] == "none"
    assert migrated["expected_duration_seconds"] == 60
    assert reference == {"type": "task", "path": "tasks/legacy-review.yaml"}
    assert "reference" not in legacy

    routine = routine_definition_from_mapping(legacy)
    metadata = routine.report_metadata()
    migration = cast(dict[str, object], metadata["routine_schema_migration"])

    assert routine.schema_version == CURRENT_ROUTINE_SCHEMA_VERSION
    assert routine.reference.kind == "task"
    assert routine.reference.task_path == Path("tasks/legacy-review.yaml")
    assert migration["applied"] is True


def test_migrate_current_routine_marks_noop() -> None:
    migrated = migrate_routine_definition_payload(
        {
            "routine_schema_version": CURRENT_ROUTINE_SCHEMA_VERSION,
            "id": "native.current-note",
            "name": "Current note routine",
            "description": "Write a reviewed note in a native app.",
            "goal": "Draft a short local note.",
            "tags": ["native", "writing"],
            "inputs": ["topic"],
            "outputs": ["draft note"],
            "safety_class": "low",
            "schedule_policy": "manual",
            "approval_policy": "none",
            "expected_duration_seconds": 45,
            "reference": {
                "type": "task",
                "path": "tasks/current-note.yaml",
            },
        },
    )
    migration = cast(dict[str, object], migrated["routine_schema_migration"])

    assert migration == {
        "from_version": CURRENT_ROUTINE_SCHEMA_VERSION,
        "to_version": CURRENT_ROUTINE_SCHEMA_VERSION,
        "applied": False,
    }


def test_catalog_load_migrates_legacy_routine_files(tmp_path: Path) -> None:
    routine_path = tmp_path / "browser" / "legacy.routine.yaml"
    routine_path.parent.mkdir(parents=True)
    routine_path.write_text(
        "\n".join(
            [
                "id: browser.legacy-search",
                "name: Legacy browser search",
                "description: Search from an older routine pack.",
                "goal: Reach search results from a legacy definition.",
                "required_app: Microsoft Edge",
                "required_site: example.com",
                "tags:",
                "  - browser",
                "task_path: tasks/legacy-search.yaml",
                "",
            ],
        ),
        encoding="utf-8",
    )

    catalog = load_routine_catalog(tmp_path)
    routine = catalog.by_id("browser.legacy-search")
    search_results = catalog.search("legacy search")

    assert routine is not None
    assert routine.schema_version == CURRENT_ROUTINE_SCHEMA_VERSION
    assert routine.inputs == ()
    assert routine.outputs == ()
    assert routine.approval_policy == "none"
    assert routine.reference.task_path == (
        routine_path.parent / "tasks/legacy-search.yaml"
    )
    assert search_results[0].routine.id == "browser.legacy-search"


def test_routine_migration_rejects_unknown_schema_version() -> None:
    with pytest.raises(RoutineMigrationError, match="unsupported routine schema"):
        migrate_routine_definition_payload({"routine_schema_version": "99"})

    with pytest.raises(RoutineDefinitionError, match="unsupported routine schema"):
        routine_definition_from_mapping({"routine_schema_version": "99"})
