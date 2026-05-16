from pathlib import Path

import pytest

from desktop_agent.routines import (
    RoutineDefinitionError,
    load_routine_catalog,
    load_routine_definition,
    routine_definition_from_mapping,
)


def test_routine_definition_schema_loads_task_reference(tmp_path: Path) -> None:
    routine_path = tmp_path / "browser" / "search.yaml"
    routine_path.parent.mkdir()
    routine_path.write_text(
        "\n".join(
            [
                "id: browser.search",
                "name: Browser search",
                "description: Search from a browser input.",
                "goal: Submit a search query and verify results.",
                "required_app: Microsoft Edge",
                "required_site: example.com",
                "tags:",
                "  - browser",
                "  - search",
                "inputs:",
                "  - query",
                "outputs:",
                "  - results page",
                "safety_class: low",
                "schedule_policy: manual",
                "approval_policy: none",
                "expected_duration_seconds: 30",
                "reference:",
                "  type: task",
                "  path: tasks/browser-search.yaml",
                "",
            ],
        ),
        encoding="utf-8",
    )

    routine = load_routine_definition(routine_path)

    assert routine.id == "browser.search"
    assert routine.required_app == "Microsoft Edge"
    assert routine.required_site == "example.com"
    assert routine.tags == ("browser", "search")
    assert routine.inputs == ("query",)
    assert routine.outputs == ("results page",)
    assert routine.reference.kind == "task"
    assert routine.reference.task_path == (
        routine_path.parent / "tasks/browser-search.yaml"
    )
    assert routine.report_metadata()["routine_reference_kind"] == "task"


def test_routine_definition_schema_loads_playbook_reference() -> None:
    routine = routine_definition_from_mapping(
        {
            "id": "social.linkedin.open-search",
            "name": "Open LinkedIn search",
            "description": "Open LinkedIn and run a search flow.",
            "goal": "Reach search results for a query.",
            "required_app": "Microsoft Edge",
            "required_site": "linkedin.com",
            "tags": ["social", "search"],
            "inputs": ["query"],
            "outputs": ["search results"],
            "safety_class": "medium",
            "schedule_policy": "on_demand",
            "approval_policy": "confirm",
            "expected_duration_seconds": 45,
            "reference": {
                "type": "playbook",
                "site": "linkedin",
                "flow": "open-search",
            },
        },
    )

    assert routine.reference.kind == "playbook"
    assert routine.reference.playbook_site == "linkedin"
    assert routine.reference.playbook_flow == "open-search"
    assert routine.report_metadata()["routine_safety_class"] == "medium"


def test_routine_definition_schema_rejects_invalid_policies() -> None:
    with pytest.raises(RoutineDefinitionError, match="unsupported safety_class"):
        routine_definition_from_mapping(
            {
                "id": "bad.routine",
                "name": "Bad routine",
                "description": "Invalid safety class.",
                "goal": "Show validation failure.",
                "tags": [],
                "inputs": [],
                "outputs": [],
                "safety_class": "unsafe",
                "schedule_policy": "manual",
                "approval_policy": "none",
                "expected_duration_seconds": 10,
                "reference": {
                    "type": "task",
                    "path": "tasks/bad.yaml",
                },
            },
        )


def test_routine_definition_schema_requires_task_or_playbook_reference() -> None:
    with pytest.raises(RoutineDefinitionError, match="reference type"):
        routine_definition_from_mapping(
            {
                "id": "bad.reference",
                "name": "Bad reference",
                "description": "Invalid reference kind.",
                "goal": "Show validation failure.",
                "tags": [],
                "inputs": [],
                "outputs": [],
                "safety_class": "low",
                "schedule_policy": "manual",
                "approval_policy": "none",
                "expected_duration_seconds": 10,
                "reference": {
                    "type": "script",
                    "path": "scripts/bad.py",
                },
            },
        )


def test_routine_catalog_loads_definitions_and_searches_metadata(
    tmp_path: Path,
) -> None:
    _write_routine(
        tmp_path / "browser" / "search.routine.yaml",
        routine_id="browser.search",
        name="Browser search",
        description="Search from a browser input.",
        goal="Reach browser search results.",
        tags=("browser", "search"),
        required_app="Microsoft Edge",
        required_site="example.com",
        task_path="tasks/browser-search.yaml",
    )
    _write_routine(
        tmp_path / "native" / "notepad.routine.yaml",
        routine_id="native.notepad-draft",
        name="Notepad draft",
        description="Open Notepad and draft local text.",
        goal="Prepare a local draft.",
        tags=("native", "writing"),
        required_app="Notepad",
        required_site=None,
        task_path="tasks/notepad-draft.yaml",
    )

    catalog = load_routine_catalog(tmp_path)
    browser_results = catalog.search("browser search")
    notepad_results = catalog.search("notepad")

    assert [routine.id for routine in catalog.routines] == [
        "browser.search",
        "native.notepad-draft",
    ]
    assert catalog.by_id("browser.search") is not None
    assert browser_results[0].routine.id == "browser.search"
    assert browser_results[0].score > 0
    assert "name" in browser_results[0].matched_fields
    assert notepad_results[0].routine.id == "native.notepad-draft"


def test_routine_catalog_rejects_duplicate_ids(tmp_path: Path) -> None:
    _write_routine(
        tmp_path / "browser" / "search.routine.yaml",
        routine_id="duplicate.routine",
        name="Browser duplicate",
        description="First duplicate.",
        goal="Show duplicate validation.",
        tags=("browser",),
        required_app="Microsoft Edge",
        required_site=None,
        task_path="tasks/browser.yaml",
    )
    _write_routine(
        tmp_path / "native" / "search.routine.yaml",
        routine_id="duplicate.routine",
        name="Native duplicate",
        description="Second duplicate.",
        goal="Show duplicate validation.",
        tags=("native",),
        required_app="Notepad",
        required_site=None,
        task_path="tasks/native.yaml",
    )

    with pytest.raises(RoutineDefinitionError, match="duplicate routine id"):
        load_routine_catalog(tmp_path)


def _write_routine(
    path: Path,
    *,
    routine_id: str,
    name: str,
    description: str,
    goal: str,
    tags: tuple[str, ...],
    required_app: str,
    required_site: str | None,
    task_path: str,
) -> None:
    site_lines = []
    if required_site is not None:
        site_lines.append(f"required_site: {required_site}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                f"id: {routine_id}",
                f"name: {name}",
                f"description: {description}",
                f"goal: {goal}",
                f"required_app: {required_app}",
                *site_lines,
                "tags:",
                *(f"  - {tag}" for tag in tags),
                "inputs:",
                "  - input",
                "outputs:",
                "  - output",
                "safety_class: low",
                "schedule_policy: manual",
                "approval_policy: none",
                "expected_duration_seconds: 30",
                "reference:",
                "  type: task",
                f"  path: {task_path}",
                "",
            ],
        ),
        encoding="utf-8",
    )
