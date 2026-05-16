import json
from pathlib import Path
from typing import cast

import pytest

from desktop_agent.operator_services import (
    LocalCatalogService,
    LocalRoutinePackService,
    LocalSchedulerService,
    LocalTraceService,
    OperatorAppService,
    OperatorServiceError,
    default_local_operator_services,
)
from desktop_agent.recorder import RecorderCandidateContext, RecorderEvent
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
    approval = services.approvals.resolve_step_approval(
        routine_id="social.publish",
        step_id="submit-post",
        action="approve",
        risk_class="high",
        checkpoint_evidence="checkpoint screenshot present",
        content_fingerprint="sha256:abc123",
        approver="qa@example.test",
        reason="Reviewed approved draft.",
        decided_at="2026-05-16T00:00:00+00:00",
    )
    denial = services.approvals.resolve_step_approval(
        routine_id="social.publish",
        step_id="submit-post",
        action="deny",
        risk_class="high",
        checkpoint_evidence="checkpoint screenshot changed",
        content_fingerprint="sha256:def456",
        approver="qa@example.test",
        reason="Draft changed.",
        decided_at="2026-05-16T00:01:00+00:00",
    )
    gate = services.runner.execution_gate("browser.search")
    unknown_gate = services.runner.execution_gate("browser.unknown")
    run = services.runner.start_routine("browser.search")
    assert run.run_id is not None
    pause = services.runner.pause_run(run.run_id)
    resume = services.runner.resume_run(run.run_id)
    blocked_run = services.runner.start_routine("browser.unknown")
    cancel = services.runner.cancel_run(run.run_id)
    stopped_run = services.runner.start_routine("browser.search")
    assert stopped_run.run_id is not None
    stop = services.runner.stop_run(stopped_run.run_id)
    queue_metadata = services.scheduler.queue_metadata()
    queue_entries = cast(list[dict[str, object]], queue_metadata["run_queue_entries"])

    assert [item.routine_id for item in all_routines] == [
        "browser.search",
        "social.publish",
    ]
    assert search_results[0].routine_id == "browser.search"
    assert [item.routine_id for item in approval_rows] == ["social.publish"]
    assert approval.approved is True
    assert approval.metadata()["content_fingerprint"] == "sha256:abc123"
    assert denial.approved is False
    decision_actions = [
        decision.action for decision in services.approvals.approval_decisions()
    ]
    assert decision_actions == [
        "approve",
        "deny",
    ]
    assert gate.allowed is True
    assert gate.reason == "validated_catalog_routine"
    assert unknown_gate.allowed is False
    assert run.run_id == "run-0001"
    assert run.status == "running"
    assert run.next_action == "observe_screen"
    assert pause.status == "paused"
    assert pause.next_action == "resume_or_cancel"
    assert resume.status == "running"
    assert cancel.status == "canceled"
    assert stop.status == "stopped"
    assert blocked_run.status == "blocked"
    assert blocked_run.reason == "unknown_routine_id"
    assert queue_metadata["run_queue_size"] == 2
    assert queue_entries[0]["routine_id"] == "browser.search"
    assert queue_entries[0]["status"] == "canceled"
    assert queue_entries[1]["status"] == "stopped"
    assert "generate_yaml" in services.recorder.capabilities()
    assert "save_as_routine" in services.recorder.capabilities()
    assert services.routine_packs.list_packs() == ()


def test_operator_recorder_service_saves_and_reruns_recorded_routine(
    tmp_path: Path,
) -> None:
    root = tmp_path / "routine_packs"
    services = default_local_operator_services(
        routine_pack_root=root,
        trace_root=tmp_path / "traces",
    )

    session = services.recorder.start_recording("Search Fixture", overwrite=True)
    services.recorder.record_event(
        RecorderEvent.create(
            "selected_point",
            active_window="DeskPilot Fixture",
            screenshot_path=str(tmp_path / "screenshots" / "click.png"),
            selected_point=(20, 30),
            candidate_context=(
                RecorderCandidateContext(
                    source="ocr",
                    label="Search",
                    bounds={"x": 10, "y": 20, "width": 80, "height": 24},
                ),
            ),
        ),
    )

    review = services.recorder.review_recording()
    saved = services.recorder.save_recording_as_routine()
    rerun = services.runner.start_routine(saved.routine_id)

    assert session.status == "recording"
    assert review.session_id == session.session_id
    assert "click_text" in review.generated_yaml
    assert review.selected_targets == ("Search",)
    assert review.screenshot_paths == (tmp_path / "screenshots" / "click.png",)
    assert review.status == "ready_for_save"
    assert saved.routine_id == "recorded.search-fixture"
    assert saved.routine_path.exists()
    assert saved.task_path.exists()
    assert saved.saved_recording_path.exists()
    assert rerun.status == "running"
    assert rerun.next_action == "observe_screen"


def test_approval_service_rejects_invalid_app_decisions(tmp_path: Path) -> None:
    root = tmp_path / "routine_packs"
    _write_routine(
        root / "social" / "publish.routine.yaml",
        routine_id="social.publish",
        approval_policy="manifest_required",
    )
    services = default_local_operator_services(
        routine_pack_root=root,
        trace_root=tmp_path / "traces",
    )

    with pytest.raises(OperatorServiceError, match="unsupported approval action"):
        services.approvals.resolve_step_approval(
            routine_id="social.publish",
            step_id="submit-post",
            action="maybe",
            risk_class="high",
            checkpoint_evidence="checkpoint screenshot present",
            content_fingerprint="sha256:abc123",
            approver="qa@example.test",
            reason="Reviewed approved draft.",
        )
    with pytest.raises(OperatorServiceError, match="checkpoint evidence is required"):
        services.approvals.resolve_step_approval(
            routine_id="social.publish",
            step_id="submit-post",
            action="approve",
            risk_class="high",
            checkpoint_evidence="",
            content_fingerprint="sha256:abc123",
            approver="qa@example.test",
            reason="Reviewed approved draft.",
        )
    with pytest.raises(OperatorServiceError, match="unknown routine"):
        services.approvals.resolve_step_approval(
            routine_id="social.missing",
            step_id="submit-post",
            action="approve",
            risk_class="high",
            checkpoint_evidence="checkpoint screenshot present",
            content_fingerprint="sha256:abc123",
            approver="qa@example.test",
            reason="Reviewed approved draft.",
        )


def test_operator_app_service_interface_groups_local_boundaries(
    tmp_path: Path,
) -> None:
    root = tmp_path / "routine_packs"
    _write_routine(
        root / "browser" / "search.routine.yaml",
        routine_id="browser.search",
        approval_policy="none",
    )
    services = default_local_operator_services(
        routine_pack_root=root,
        trace_root=tmp_path / "traces",
    )

    def describe(service: OperatorAppService) -> dict[str, object]:
        return {
            "routine_count": len(service.catalog.list_routines()),
            "recorder_capabilities": service.recorder.capabilities(),
            "queue": service.scheduler.queue_metadata(),
            "trace_count": len(service.traces.list_traces()),
            "pack_count": len(service.routine_packs.list_packs()),
        }

    summary = describe(services)
    recorder_capabilities = cast(tuple[str, ...], summary["recorder_capabilities"])
    queue = cast(dict[str, object], summary["queue"])

    assert summary["routine_count"] == 1
    assert "generate_yaml" in recorder_capabilities
    assert queue["run_queue_size"] == 0
    assert queue["run_queue_entries"] == []
    assert summary["trace_count"] == 0
    assert summary["pack_count"] == 0


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
