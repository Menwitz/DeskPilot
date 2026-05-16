import json
from pathlib import Path
from typing import cast

import pytest

from desktop_agent.trace_migrations import (
    TraceMigrationError,
    load_and_migrate_trace_report,
    migrate_action_log_event_payload,
    migrate_trace_report_payload,
)
from desktop_agent.tracing import TRACE_SCHEMA_V2


def test_migrate_legacy_trace_report_adds_schema_and_defaults() -> None:
    migrated = migrate_trace_report_payload(
        {
            "task_name": "legacy",
            "status": "passed",
            "steps": [{"step_id": "open", "action": "click_text"}],
            "events": [{"phase": "observe"}],
        },
    )

    assert migrated["trace_schema_version"] == TRACE_SCHEMA_V2.version
    assert migrated["trace_schema"] == TRACE_SCHEMA_V2.to_dict()
    assert migrated["metadata"] == {}
    events = cast(list[dict[str, object]], migrated["events"])
    assert events[0]["index"] == 1
    assert events[0]["message"] == ""
    assert events[0]["metadata"] == {}
    assert migrated["trace_schema_migration"] == {
        "from_version": "1",
        "to_version": TRACE_SCHEMA_V2.version,
        "applied": True,
    }


def test_migrate_current_trace_report_marks_noop() -> None:
    migrated = migrate_trace_report_payload(
        {
            "trace_schema_version": TRACE_SCHEMA_V2.version,
            "task_name": "current",
            "status": "passed",
            "metadata": {"routine_id": "browser.read"},
            "steps": [],
            "events": [],
        },
    )

    assert migrated["metadata"] == {"routine_id": "browser.read"}
    migration = cast(dict[str, object], migrated["trace_schema_migration"])
    assert migration["applied"] is False


def test_migrate_action_log_event_adds_index_and_schema() -> None:
    migrated = migrate_action_log_event_payload(
        {"phase": "input", "message": "typed"},
        index=7,
    )

    assert migrated["index"] == 7
    assert migrated["trace_schema_version"] == TRACE_SCHEMA_V2.version
    assert migrated["metadata"] == {}


def test_load_and_migrate_trace_report_reads_json(tmp_path: Path) -> None:
    report_path = tmp_path / "final-report.json"
    report_path.write_text(
        json.dumps({"task_name": "legacy", "status": "failed"}),
        encoding="utf-8",
    )

    migrated = load_and_migrate_trace_report(report_path)

    assert migrated["trace_schema_version"] == TRACE_SCHEMA_V2.version
    migration = cast(dict[str, object], migrated["trace_schema_migration"])
    assert migration["from_version"] == "1"


def test_trace_migration_preserves_legacy_fields_without_mutating_payload() -> None:
    legacy = {
        "task_name": "legacy",
        "status": "failed",
        "metadata": {
            "routine_id": "browser.legacy",
            "legacy_context": "kept",
        },
        "steps": [
            {
                "step_id": "open",
                "action": "click_text",
                "legacy_step_metadata": {"selector": "#open"},
            },
        ],
        "events": [
            {
                "phase": "observe",
                "metadata": {"legacy_observation": "active window"},
                "legacy_event_field": "kept",
            },
        ],
        "legacy_report_field": {"operator_note": "old report still useful"},
    }

    migrated = migrate_trace_report_payload(legacy)
    steps = cast(list[dict[str, object]], migrated["steps"])
    events = cast(list[dict[str, object]], migrated["events"])

    assert migrated["metadata"] == {
        "routine_id": "browser.legacy",
        "legacy_context": "kept",
    }
    assert migrated["legacy_report_field"] == {
        "operator_note": "old report still useful",
    }
    assert steps[0]["legacy_step_metadata"] == {"selector": "#open"}
    assert events[0]["metadata"] == {"legacy_observation": "active window"}
    assert events[0]["legacy_event_field"] == "kept"
    assert "trace_schema_version" not in legacy
    assert "message" not in cast(list[dict[str, object]], legacy["events"])[0]


def test_trace_migration_rejects_unknown_schema_version() -> None:
    with pytest.raises(TraceMigrationError, match="unsupported trace schema"):
        migrate_trace_report_payload({"trace_schema_version": "99"})
