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
    dry_run = services.runner.dry_run_routine("browser.search")
    run = services.runner.start_routine("browser.search")
    assert run.run_id is not None
    pause = services.runner.pause_run(run.run_id)
    resume = services.runner.resume_run(run.run_id)
    blocked_run = services.runner.start_routine("browser.unknown")
    cancel = services.runner.cancel_run(run.run_id)
    stopped_run = services.runner.start_routine("browser.search")
    assert stopped_run.run_id is not None
    stop = services.runner.stop_run(stopped_run.run_id)
    emergency_run = services.runner.start_routine("browser.search")
    assert emergency_run.run_id is not None
    emergency_stop = services.runner.emergency_stop_run(emergency_run.run_id)
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
    assert dry_run.status == "passed"
    assert dry_run.reason == "dry_run_validated"
    assert dry_run.desktop_input_required is False
    assert dry_run.step_count == 1
    assert "dry-run preview:" in dry_run.preview
    assert dry_run.compiled_task["step_order"] == ["observe"]
    assert run.run_id == "run-0001"
    assert run.status == "running"
    assert run.next_action == "observe_screen"
    assert pause.status == "paused"
    assert pause.next_action == "resume_or_cancel"
    assert resume.status == "running"
    assert cancel.status == "canceled"
    assert stop.status == "stopped"
    assert emergency_stop.status == "emergency_stopped"
    assert blocked_run.status == "blocked"
    assert blocked_run.reason == "unknown_routine_id"
    assert queue_metadata["run_queue_size"] == 3
    assert queue_entries[0]["routine_id"] == "browser.search"
    assert queue_entries[0]["status"] == "canceled"
    assert queue_entries[1]["status"] == "stopped"
    assert queue_entries[2]["status"] == "emergency_stopped"
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


def test_local_trace_service_lists_proof_suite_finalization_rollups(
    tmp_path: Path,
) -> None:
    trace_root = tmp_path / "traces"
    trace_dir = trace_root / "20260516T010000Z-proof-suite"
    trace_dir.mkdir(parents=True)
    report_path = trace_dir / "proof-finalization-status.json"
    report_path.write_text(
        json.dumps(
            {
                "status": "passed",
                "gates": {
                    "suite_validation": "passed",
                    "promotion_verification": "passed",
                    "archive_verification": "passed",
                },
            },
        ),
        encoding="utf-8",
    )
    service = LocalTraceService(trace_root)

    traces = service.list_traces()
    report = service.read_report(trace_dir)

    assert len(traces) == 1
    assert traces[0].kind == "proof_suite"
    assert traces[0].status == "passed"
    assert traces[0].metadata()["report_path"] == str(report_path)
    assert report["gates"] == {
        "suite_validation": "passed",
        "promotion_verification": "passed",
        "archive_verification": "passed",
    }


def test_local_trace_service_reports_trace_health_counts(tmp_path: Path) -> None:
    trace_root = tmp_path / "traces"
    run_trace = trace_root / "20260516T000000Z-run"
    goal_trace = trace_root / "20260516T010000Z-goal"
    proof_trace = trace_root / "20260516T020000Z-proof"
    for trace_dir in (run_trace, goal_trace, proof_trace):
        trace_dir.mkdir(parents=True)
    (run_trace / "final-report.json").write_text(
        json.dumps({"status": "failed"}),
        encoding="utf-8",
    )
    (goal_trace / "goal-plan-report.json").write_text(
        json.dumps({"status": "ready"}),
        encoding="utf-8",
    )
    (proof_trace / "proof-finalization-status.json").write_text(
        json.dumps({"status": "passed"}),
        encoding="utf-8",
    )
    service = LocalTraceService(trace_root)

    health = service.trace_health()

    assert health["trace_count"] == 3
    assert health["by_kind"] == {"proof_suite": 1, "goal_plan": 1, "run": 1}
    assert health["by_status"] == {"passed": 1, "ready": 1, "failed": 1}
    assert health["health_status"] == "attention"
    assert health["attention_statuses"] == ["failed"]
    attention_traces = cast(list[dict[str, object]], health["attention_traces"])
    assert attention_traces == [
        {
            "trace_dir": str(run_trace),
            "report_path": str(run_trace / "final-report.json"),
            "status": "failed",
            "kind": "run",
        },
    ]
    latest = cast(list[dict[str, object]], health["latest"])
    assert latest[0]["kind"] == "proof_suite"


def test_local_trace_service_inspects_failed_trace_for_app_review(
    tmp_path: Path,
) -> None:
    trace_root = tmp_path / "traces"
    trace_dir = trace_root / "failed-run"
    trace_dir.mkdir(parents=True)
    (trace_dir / "task.yaml").write_text("name: Browser search\n", encoding="utf-8")
    (trace_dir / "config.json").write_text("{}", encoding="utf-8")
    (trace_dir / "trace-schema.json").write_text("{}", encoding="utf-8")
    (trace_dir / "action-log.jsonl").write_text("", encoding="utf-8")
    (trace_dir / "final-report.json").write_text(
        json.dumps(
            {
                "task_name": "Browser search",
                "status": "failed",
                "metadata": {"routine_id": "browser.search"},
                "steps": [
                    {
                        "step_id": "click-submit",
                        "status": "failed",
                        "metadata": {"failure_category": "selection_ambiguity"},
                    },
                ],
            },
        ),
        encoding="utf-8",
    )
    service = LocalTraceService(trace_root)

    inspection = service.inspect_failed_trace(trace_dir)

    assert inspection.status == "failed"
    assert inspection.task_name == "Browser search"
    assert inspection.routine_id == "browser.search"
    assert inspection.failure_reasons == ("step click-submit: selection_ambiguity",)
    assert inspection.proposal_count == 1
    assert inspection.diagnostic_ready is True
    assert inspection.analysis_json_path.exists()
    assert inspection.analysis_markdown_path.exists()
    assert inspection.metadata()["proposal_count"] == 1


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
    task_path = path.parent / "tasks" / "test.yaml"
    task_path.parent.mkdir(parents=True, exist_ok=True)
    task_path.write_text(
        "\n".join(
            [
                f"name: {routine_id} task",
                "allowed_windows:",
                "  - DeskPilot Fixture",
                "timeout_seconds: 30",
                "steps:",
                "  - id: observe",
                "    action: wait_for",
                "    verify:",
                "      type: visible_text",
                "      text: Ready",
                "    timeout_seconds: 1",
                "",
            ],
        ),
        encoding="utf-8",
    )
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
