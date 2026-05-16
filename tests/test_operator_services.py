import json
from pathlib import Path
from typing import cast

import pytest

from desktop_agent.operator_services import (
    LocalCatalogService,
    LocalRoutinePackService,
    LocalSchedulerService,
    LocalTraceService,
    OperatorServiceError,
    default_local_operator_services,
)
from desktop_agent.scheduler import RunQueue


def test_local_operator_services_expose_catalog_runner_approvals_and_queue(
    tmp_path: Path,
) -> None:
    root = tmp_path / "routine_packs"
    _write_routine(
        root / "browser" / "search.routine.yaml",
        routine_id="browser.search",
        approval_policy="none",
    )
    _write_routine(
        root / "social" / "publish.routine.yaml",
        routine_id="social.publish",
        approval_policy="manifest_required",
    )
    services = default_local_operator_services(
        routine_pack_root=root,
        trace_root=tmp_path / "traces",
    )

    all_routines = services.catalog.list_routines()
    search_results = services.catalog.list_routines("search")
    approval_rows = services.approvals.routines_requiring_approval()
    gate = services.runner.execution_gate("browser.search")
    unknown_gate = services.runner.execution_gate("browser.unknown")
    queue_metadata = services.scheduler.queue_metadata()

    assert [item.routine_id for item in all_routines] == [
        "browser.search",
        "social.publish",
    ]
    assert search_results[0].routine_id == "browser.search"
    assert [item.routine_id for item in approval_rows] == ["social.publish"]
    assert gate.allowed is True
    assert gate.reason == "validated_catalog_routine"
    assert unknown_gate.allowed is False
    assert queue_metadata["run_queue_size"] == 0
    assert "generate_yaml" in services.recorder.capabilities()
    assert services.routine_packs.list_packs() == ()


def test_local_trace_service_lists_and_reads_reports(tmp_path: Path) -> None:
    trace_root = tmp_path / "traces"
    trace_dir = trace_root / "20260516T000000Z-goal-plan"
    trace_dir.mkdir(parents=True)
    report_path = trace_dir / "goal-plan-report.json"
    report_path.write_text(
        json.dumps({"status": "ready", "selected_routine_id": "browser.search"}),
        encoding="utf-8",
    )
    service = LocalTraceService(trace_root)

    traces = service.list_traces()
    report = service.read_report(trace_dir)

    assert len(traces) == 1
    assert traces[0].kind == "goal_plan"
    assert traces[0].status == "ready"
    assert traces[0].metadata()["report_path"] == str(report_path)
    assert report["selected_routine_id"] == "browser.search"


def test_local_catalog_service_raises_for_unknown_routine(tmp_path: Path) -> None:
    root = tmp_path / "routine_packs"
    _write_routine(
        root / "browser" / "search.routine.yaml",
        routine_id="browser.search",
        approval_policy="none",
    )
    service = LocalCatalogService(root)

    assert service.routine("browser.search").id == "browser.search"
    with pytest.raises(OperatorServiceError, match="unknown routine"):
        service.routine("browser.unknown")


def test_scheduler_service_reports_injected_queue() -> None:
    queue = RunQueue().enqueue("browser.search", reason="manual app request")

    metadata = LocalSchedulerService(queue).queue_metadata()
    entries = cast(list[dict[str, object]], metadata["run_queue_entries"])

    assert metadata["run_queue_size"] == 1
    assert entries[0]["routine_id"] == "browser.search"


def test_routine_pack_service_installs_lists_and_removes_packs(tmp_path: Path) -> None:
    source = _write_pack(tmp_path / "source-pack", pack_id="sample-pack")
    service = LocalRoutinePackService(tmp_path / "installed")

    install_result = service.install_pack(source)
    packs = service.list_packs()
    remove_result = service.remove_pack("sample-pack")

    assert install_result.installed_path == tmp_path / "installed" / "sample-pack"
    assert [pack.pack_id for pack in packs] == ["sample-pack"]
    assert packs[0].trust_level == "trusted_local"
    assert packs[0].trust_warning_count == 0
    assert remove_result.removed_path == tmp_path / "installed" / "sample-pack"
    assert not remove_result.removed_path.exists()


def _write_routine(path: Path, *, routine_id: str, approval_policy: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                f"id: {routine_id}",
                f"name: {routine_id}",
                "description: Operator service test routine.",
                "goal: Exercise the operator service boundary.",
                "required_app: Microsoft Edge",
                "tags:",
                "  - browser",
                "  - search",
                "inputs:",
                "  - query",
                "outputs:",
                "  - results",
                "safety_class: low",
                "schedule_policy: manual",
                f"approval_policy: {approval_policy}",
                "expected_duration_seconds: 30",
                "reference:",
                "  type: task",
                "  path: tasks/test.yaml",
                "",
            ],
        ),
        encoding="utf-8",
    )


def _write_pack(root: Path, *, pack_id: str) -> Path:
    root.mkdir(parents=True)
    (root / "README.md").write_text("# Sample Pack\n", encoding="utf-8")
    (root / "routine-pack.yaml").write_text(
        "\n".join(
            [
                'pack_schema_version: "1"',
                f"id: {pack_id}",
                "name: Sample Pack",
                "description: Sample pack for operator service tests.",
                'version: "0.1.0"',
                "publisher: Local Operator",
                "trust_level: trusted_local",
                "routine_globs:",
                '  - "*.routine.yaml"',
                "docs:",
                "  - README.md",
                "fixtures: []",
                "tests: []",
                "safety:",
                "  max_safety_class: low",
                "  requires_review: true",
                "  external_mutation_allowed: false",
                "  approval_required: false",
                "proof:",
                "  windows_proof_required: false",
                "  expected_artifacts:",
                "    - final-report.json",
                "",
            ],
        ),
        encoding="utf-8",
    )
    return root
