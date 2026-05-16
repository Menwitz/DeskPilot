from pathlib import Path

import pytest
import yaml
from pytest import CaptureFixture

from desktop_agent.cli import main
from desktop_agent.config import RuntimeConfig
from desktop_agent.routines import (
    RoutineDefinitionError,
    load_routine_catalog,
    load_routine_definition,
    render_routine_catalog_index,
    render_routine_documentation_template,
    routine_definition_from_mapping,
    routine_promotion_gates,
    routine_quarantine_status,
)
from desktop_agent.task_dsl import BasicTaskValidator, YamlTaskLoader


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


def test_routine_promotion_gates_include_required_review_steps() -> None:
    routine = routine_definition_from_mapping(
        {
            "id": "native.notepad-draft",
            "name": "Notepad draft",
            "description": "Draft text in a native app.",
            "goal": "Prepare local text.",
            "required_app": "Notepad",
            "tags": ["native"],
            "inputs": ["draft text"],
            "outputs": ["saved draft"],
            "safety_class": "low",
            "schedule_policy": "manual",
            "approval_policy": "none",
            "expected_duration_seconds": 30,
            "reference": {
                "type": "task",
                "path": "tasks/notepad.yaml",
            },
        },
    )

    gates = {gate.id: gate for gate in routine_promotion_gates(routine)}
    metadata = routine.report_metadata()

    assert set(gates) == {
        "schema_validation",
        "dry_run",
        "fixture_test",
        "trace_replay_review",
        "documentation",
        "windows_proof",
    }
    assert gates["windows_proof"].required is True
    gate_metadata = metadata["routine_promotion_gates"]
    assert isinstance(gate_metadata, list)
    assert isinstance(gate_metadata[-1], dict)
    assert gate_metadata[-1]["id"] == "windows_proof"


def test_routine_quarantine_status_uses_failed_evidence_count() -> None:
    routine = routine_definition_from_mapping(
        {
            "id": "browser.flaky",
            "name": "Flaky browser routine",
            "description": "A routine with repeated failed evidence.",
            "goal": "Show quarantine status.",
            "tags": ["browser"],
            "inputs": [],
            "outputs": [],
            "safety_class": "low",
            "schedule_policy": "manual",
            "approval_policy": "none",
            "expected_duration_seconds": 30,
            "failed_evidence_count": 3,
            "reference": {
                "type": "task",
                "path": "tasks/flaky.yaml",
            },
        },
    )

    assert routine_quarantine_status(routine) == "quarantined"
    assert routine.report_metadata()["routine_quarantine_status"] == "quarantined"


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


def test_routine_cli_lists_shows_compiles_exports_and_dry_runs(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    root = tmp_path / "routine_packs"
    task_path = root / "browser" / "tasks" / "browser-search.yaml"
    routine_path = root / "browser" / "search.routine.yaml"
    compiled_path = tmp_path / "compiled-browser-search.yaml"
    exported_path = tmp_path / "exported-browser-search.routine.yaml"
    config_path = tmp_path / "config.yaml"
    _write_task(task_path)
    _write_routine(
        routine_path,
        routine_id="browser.search",
        name="Browser search",
        description="Search from a browser input.",
        goal="Reach browser search results.",
        tags=("browser", "search"),
        required_app="Microsoft Edge",
        required_site="example.com",
        task_path="tasks/browser-search.yaml",
    )
    config_path.write_text(f"trace_root: {tmp_path / 'traces'}\n", encoding="utf-8")

    assert main(["list-routines", "--routine-pack-root", str(root)]) == 0
    assert "browser.search\tBrowser search" in capsys.readouterr().out

    assert (
        main(
            [
                "list-routines",
                "--routine-pack-root",
                str(root),
                "--query",
                "search",
            ],
        )
        == 0
    )
    assert "browser.search\tBrowser search" in capsys.readouterr().out

    assert (
        main(["show-routine", "browser.search", "--routine-pack-root", str(root)])
        == 0
    )
    show_output = capsys.readouterr().out
    assert "safety_class: low" in show_output
    assert "quarantine_status: active" in show_output
    assert "reference: task:" in show_output
    assert "promotion_gates:" in show_output
    assert "windows_proof: required" in show_output

    assert (
        main(
            [
                "compile-routine",
                "browser.search",
                "--routine-pack-root",
                str(root),
                "--output",
                str(compiled_path),
            ],
        )
        == 0
    )
    compiled_task = YamlTaskLoader().load(compiled_path)
    BasicTaskValidator().validate(compiled_task, RuntimeConfig())
    assert compiled_task.name == "Browser search"
    assert compiled_task.metadata["routine_id"] == "browser.search"

    assert (
        main(
            [
                "export-routine",
                "browser.search",
                "--routine-pack-root",
                str(root),
                "--output",
                str(exported_path),
            ],
        )
        == 0
    )
    exported = yaml.safe_load(exported_path.read_text(encoding="utf-8"))
    assert exported["id"] == "browser.search"
    assert exported["reference"]["type"] == "task"
    assert exported["quarantine_status"] == "active"

    assert (
        main(
            [
                "dry-run-routine",
                "browser.search",
                "--routine-pack-root",
                str(root),
                "--config",
                str(config_path),
                "--no-screenshots",
            ],
        )
        == 0
    )
    assert "task: Browser search" in capsys.readouterr().out


def test_routine_docs_generation_renders_index_and_template(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    root = tmp_path / "routine_packs"
    routine_path = root / "browser" / "search.routine.yaml"
    index_path = tmp_path / "docs" / "routine-catalog-index.md"
    template_path = tmp_path / "docs" / "routine-documentation-template.md"
    _write_routine(
        routine_path,
        routine_id="browser.search",
        name="Browser search",
        description="Search from a browser input.",
        goal="Reach browser search results.",
        tags=("browser", "search"),
        required_app="Microsoft Edge",
        required_site="example.com",
        task_path="tasks/browser-search.yaml",
    )
    catalog = load_routine_catalog(root)

    index = render_routine_catalog_index(catalog)
    template = render_routine_documentation_template()

    assert "# DeskPilot Routine Catalog Index" in index
    assert "- Total routines: 1" in index
    assert "| browser.search | browser | Browser search |" in index
    assert "Promotion gates" in index
    assert "# <Routine Name>" in template
    assert "- [ ] Dry-run report path:" in template

    assert (
        main(
            [
                "generate-routine-docs",
                "--routine-pack-root",
                str(root),
                "--index-output",
                str(index_path),
                "--template-output",
                str(template_path),
            ],
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "routine catalog index:" in output
    assert index_path.read_text(encoding="utf-8") == index
    assert template_path.read_text(encoding="utf-8") == template


def _write_task(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "name: raw browser task",
                "allowed_windows:",
                "  - Browser Fixture",
                "timeout_seconds: 30",
                "steps:",
                "  - id: click-search",
                "    action: click_text",
                "    target: Search",
                "    verify:",
                "      type: visible_text",
                "      text: Results",
                "",
            ],
        ),
        encoding="utf-8",
    )


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
