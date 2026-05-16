import json
from pathlib import Path

import pytest
import yaml
from pytest import CaptureFixture

from desktop_agent.cli import main
from desktop_agent.config import RuntimeConfig
from desktop_agent.routines import (
    RoutineCatalog,
    RoutineDefinitionError,
    RoutineFailureCounters,
    load_routine_catalog,
    load_routine_definition,
    render_routine_catalog_index,
    render_routine_documentation_template,
    require_validated_routine_for_execution,
    routine_definition_from_mapping,
    routine_execution_gate,
    routine_failure_counters_from_trace_root,
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


def test_routine_definition_schema_loads_schedule_constraints(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    routine_path = tmp_path / "scheduled" / "morning.routine.yaml"
    export_path = tmp_path / "scheduled-export.yaml"
    routine_path.parent.mkdir()
    routine_path.write_text(
        "\n".join(
            [
                "id: browser.morning-review",
                "name: Browser morning review",
                "description: Review an owned browser page during work hours.",
                "goal: Check the page only inside reviewed windows.",
                "required_app: Microsoft Edge",
                "required_site: example.com",
                "tags:",
                "  - browser",
                "  - morning",
                "inputs:",
                "  - review url",
                "outputs:",
                "  - review notes",
                "safety_class: medium",
                "schedule_policy: scheduled",
                "approval_policy: confirm",
                "expected_duration_seconds: 120",
                "schedule:",
                "  allowed_time_windows:",
                "    - days: [mon, tue, wed, thu, fri]",
                "      start: '09:00'",
                "      end: '11:30'",
                "      timezone: local",
                "  cooldown_seconds: 1800",
                "  max_runs_per_day: 2",
                "  max_runs_per_week: 8",
                "  max_external_mutations: 1",
                "  stop_conditions:",
                "    - active_window_not_allowed",
                "    - operator_check_in_required",
                "reference:",
                "  type: task",
                "  path: tasks/morning-review.yaml",
                "",
            ],
        ),
        encoding="utf-8",
    )

    routine = load_routine_definition(routine_path)
    catalog = load_routine_catalog(tmp_path)
    search_results = catalog.search("operator check morning")

    assert routine.schedule.cooldown_seconds == 1800
    assert routine.schedule.max_runs_per_day == 2
    assert routine.schedule.max_external_mutations == 1
    assert routine.schedule.stop_conditions == (
        "active_window_not_allowed",
        "operator_check_in_required",
    )
    assert routine.schedule.allowed_time_windows[0].days == (
        "mon",
        "tue",
        "wed",
        "thu",
        "fri",
    )
    metadata = routine.report_metadata()["routine_schedule"]
    assert isinstance(metadata, dict)
    assert metadata["max_runs_per_week"] == 8
    assert search_results[0].routine.id == "browser.morning-review"

    assert (
        main(
            [
                "show-routine",
                "browser.morning-review",
                "--routine-pack-root",
                str(tmp_path),
            ],
        )
        == 0
    )
    show_output = capsys.readouterr().out
    assert "max_external_mutations: 1" in show_output
    assert "operator_check_in_required" in show_output

    assert (
        main(
            [
                "export-routine",
                "browser.morning-review",
                "--routine-pack-root",
                str(tmp_path),
                "--output",
                str(export_path),
            ],
        )
        == 0
    )
    exported = yaml.safe_load(export_path.read_text(encoding="utf-8"))
    assert exported["schedule"]["max_runs_per_day"] == 2
    assert exported["schedule"]["allowed_time_windows"][0]["start"] == "09:00"


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


def test_routine_definition_schema_rejects_invalid_schedule() -> None:
    with pytest.raises(RoutineDefinitionError, match="start must be HH:MM"):
        routine_definition_from_mapping(
            {
                "id": "bad.schedule",
                "name": "Bad schedule",
                "description": "Invalid time window.",
                "goal": "Show schedule validation failure.",
                "tags": [],
                "inputs": [],
                "outputs": [],
                "safety_class": "low",
                "schedule_policy": "scheduled",
                "approval_policy": "none",
                "expected_duration_seconds": 10,
                "schedule": {
                    "allowed_time_windows": [
                        {
                            "days": ["mon", "funday"],
                            "start": "9am",
                            "end": "09:00",
                        },
                    ],
                    "cooldown_seconds": 1,
                },
                "reference": {
                    "type": "task",
                    "path": "tasks/bad.yaml",
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


def test_routine_failure_counters_scan_trace_reports(tmp_path: Path) -> None:
    _write_final_report(
        tmp_path / "traces" / "run-1" / "final-report.json",
        routine_id="browser.search",
        status="failed",
    )
    _write_final_report(
        tmp_path / "traces" / "run-2" / "final-report.json",
        routine_id="browser.search",
        status="aborted",
    )
    _write_final_report(
        tmp_path / "traces" / "run-3" / "final-report.json",
        routine_id="browser.search",
        status="passed",
    )
    _write_final_report(
        tmp_path / "traces" / "run-4" / "final-report.json",
        routine_id="native.notepad",
        status="emergency_stopped",
    )

    counters = routine_failure_counters_from_trace_root(tmp_path / "traces")

    browser = counters["browser.search"]
    native = counters["native.notepad"]
    assert browser.total_runs == 3
    assert browser.passed_runs == 1
    assert browser.failure_count == 2
    assert browser.metadata()["routine_historical_failure_count"] == 2
    assert native.total_runs == 1
    assert native.failure_count == 1


def test_routine_quarantine_status_uses_configured_history_threshold() -> None:
    routine = routine_definition_from_mapping(
        {
            "id": "browser.brittle",
            "name": "Brittle browser routine",
            "description": "A routine with historical failures.",
            "goal": "Show configured quarantine thresholds.",
            "tags": ["browser"],
            "inputs": [],
            "outputs": [],
            "safety_class": "low",
            "schedule_policy": "manual",
            "approval_policy": "none",
            "expected_duration_seconds": 30,
            "failed_evidence_count": 1,
            "quarantine_failure_threshold": 2,
            "reference": {
                "type": "task",
                "path": "tasks/brittle.yaml",
            },
        },
    )
    counter = RoutineFailureCounters(
        routine_id="browser.brittle",
        total_runs=2,
        failed_runs=2,
    )
    catalog = RoutineCatalog(root=Path("routine_packs"), routines=(routine,))

    gate = routine_execution_gate(
        catalog,
        "browser.brittle",
        {"browser.brittle": counter},
    )

    assert routine_quarantine_status(routine) == "active"
    assert routine_quarantine_status(routine, counter) == "quarantined"
    assert routine.report_metadata()["routine_quarantine_failure_threshold"] == 2
    assert gate.allowed is False
    assert gate.reason == "routine_quarantined"


def test_routine_execution_gate_allows_only_validated_catalog_routines() -> None:
    routine = routine_definition_from_mapping(
        {
            "id": "browser.search",
            "name": "Browser search",
            "description": "Search from a browser input.",
            "goal": "Reach browser search results.",
            "tags": ["browser", "search"],
            "inputs": ["query"],
            "outputs": ["results"],
            "safety_class": "low",
            "schedule_policy": "manual",
            "approval_policy": "none",
            "expected_duration_seconds": 30,
            "reference": {
                "type": "task",
                "path": "tasks/browser-search.yaml",
            },
        },
    )
    catalog = RoutineCatalog(root=Path("routine_packs"), routines=(routine,))

    allowed = routine_execution_gate(catalog, "browser.search")
    invalid = routine_execution_gate(catalog, "../browser.search")
    unknown = routine_execution_gate(catalog, "browser.unknown")

    assert allowed.allowed is True
    assert allowed.reason == "validated_catalog_routine"
    assert allowed.metadata()["routine_found"] is True
    assert require_validated_routine_for_execution(catalog, "browser.search") == routine
    assert invalid.allowed is False
    assert invalid.reason == "invalid_routine_id"
    assert unknown.allowed is False
    assert unknown.reason == "unknown_routine_id"


def test_routine_execution_gate_blocks_quarantined_routines() -> None:
    routine = routine_definition_from_mapping(
        {
            "id": "browser.flaky",
            "name": "Flaky browser routine",
            "description": "A routine with repeated failed evidence.",
            "goal": "Show quarantine blocking.",
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
    catalog = RoutineCatalog(root=Path("routine_packs"), routines=(routine,))

    gate = routine_execution_gate(catalog, "browser.flaky")

    assert gate.allowed is False
    assert gate.reason == "routine_quarantined"
    with pytest.raises(RoutineDefinitionError, match="routine_quarantined"):
        require_validated_routine_for_execution(catalog, "browser.flaky")


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
        quarantine_failure_threshold=1,
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

    _write_final_report(
        tmp_path / "history" / "failed" / "final-report.json",
        routine_id="browser.search",
        status="failed",
    )
    assert (
        main(
            [
                "dry-run-routine",
                "browser.search",
                "--routine-pack-root",
                str(root),
                "--failure-history-root",
                str(tmp_path / "history"),
            ],
        )
        == 2
    )
    assert "routine_quarantined" in capsys.readouterr().out


def test_routine_docs_generation_renders_index_and_template(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    root = tmp_path / "routine_packs"
    routine_path = root / "browser" / "search.routine.yaml"
    history_root = tmp_path / "traces"
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
    _write_final_report(
        history_root / "failed-search" / "final-report.json",
        routine_id="browser.search",
        status="failed",
    )
    catalog = load_routine_catalog(root)
    counters = routine_failure_counters_from_trace_root(history_root)

    index = render_routine_catalog_index(catalog, counters)
    template = render_routine_documentation_template()

    assert "# DeskPilot Routine Catalog Index" in index
    assert "- Total routines: 1" in index
    assert "- Historical failed runs: 1" in index
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
                "--failure-history-root",
                str(history_root),
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


def _write_final_report(path: Path, *, routine_id: str, status: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "status": status,
                "metadata": {"routine_id": routine_id},
                "steps": [],
                "events": [],
            },
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
    quarantine_failure_threshold: int | None = None,
) -> None:
    site_lines = []
    if required_site is not None:
        site_lines.append(f"required_site: {required_site}")
    threshold_lines = []
    if quarantine_failure_threshold is not None:
        threshold_lines.append(
            f"quarantine_failure_threshold: {quarantine_failure_threshold}",
        )
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
                *threshold_lines,
                "reference:",
                "  type: task",
                f"  path: {task_path}",
                "",
            ],
        ),
        encoding="utf-8",
    )
