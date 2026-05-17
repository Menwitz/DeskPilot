from pathlib import Path

import pytest

from desktop_agent.operator_app_shell import (
    ApprovalDialogState,
    RecorderReviewPanelState,
    TraceViewerTimelineState,
)
from desktop_agent.operator_app_state import (
    OperatorAppController,
    OperatorAppStateError,
)
from desktop_agent.operator_services import (
    LocalTraceService,
    OperatorApprovalDecision,
    OperatorDryRunResult,
    OperatorRunControlResult,
    OperatorRunStartResult,
    RoutineListItem,
)
from desktop_agent.routines import RoutineExecutionGate


def test_operator_app_controller_transitions_run_state_with_fake_runner() -> None:
    runner = _FakeRunnerService(
        {
            "browser.search": RoutineExecutionGate(
                routine_id="browser.search",
                allowed=True,
                reason="validated_catalog_routine",
            ),
        },
    )
    controller = OperatorAppController(runner)

    running = controller.start_routine("browser.search")
    paused = controller.pause_run()
    resumed = controller.resume_run()
    canceled = controller.cancel_run()

    assert running.current_page_id == "dashboard"
    assert running.live_run.run_id == "run-0001"
    assert running.live_run.current_routine_id == "browser.search"
    assert running.live_run.status == "running"
    assert running.live_run.next_action == "observe_screen"
    assert paused.live_run.status == "paused"
    assert resumed.live_run.status == "running"
    assert canceled.live_run.status == "canceled"
    assert canceled.live_run.next_action is None
    assert runner.run_statuses["run-0001"] == "canceled"


def test_operator_app_controller_tracks_dry_run_state() -> None:
    controller = OperatorAppController(
        _FakeRunnerService(
            {
                "browser.search": RoutineExecutionGate(
                    routine_id="browser.search",
                    allowed=True,
                    reason="validated_catalog_routine",
                ),
            },
        ),
    )

    state = controller.dry_run_routine("browser.search")

    assert state.current_page_id == "routine_library"
    assert state.live_run.current_routine_id == "browser.search"
    assert state.live_run.current_step_id == "compiled_task"
    assert state.live_run.status == "dry_run_passed"
    assert state.live_run.next_action == "dry_run_validated"


def test_operator_app_controller_stops_run_with_fake_runner() -> None:
    runner = _FakeRunnerService(
        {
            "browser.search": RoutineExecutionGate(
                routine_id="browser.search",
                allowed=True,
                reason="validated_catalog_routine",
            ),
        },
    )
    controller = OperatorAppController(runner)

    controller.start_routine("browser.search")
    stopped = controller.stop_run()

    assert stopped.live_run.run_id == "run-0001"
    assert stopped.live_run.status == "stopped"
    assert stopped.live_run.next_action is None
    assert runner.run_statuses["run-0001"] == "stopped"


def test_operator_app_controller_emergency_stops_run_with_fake_runner() -> None:
    runner = _FakeRunnerService(
        {
            "browser.search": RoutineExecutionGate(
                routine_id="browser.search",
                allowed=True,
                reason="validated_catalog_routine",
            ),
        },
    )
    controller = OperatorAppController(runner)

    controller.start_routine("browser.search")
    stopped = controller.emergency_stop_run()

    assert stopped.live_run.run_id == "run-0001"
    assert stopped.live_run.status == "emergency_stopped"
    assert stopped.live_run.next_action is None
    assert runner.run_statuses["run-0001"] == "emergency_stopped"


def test_operator_app_controller_blocks_run_when_fake_gate_rejects() -> None:
    controller = OperatorAppController(
        _FakeRunnerService(
            {
                "browser.unknown": RoutineExecutionGate(
                    routine_id="browser.unknown",
                    allowed=False,
                    reason="unknown_routine_id",
                ),
            },
        ),
    )

    state = controller.start_routine("browser.unknown")

    assert state.live_run.current_routine_id == "browser.unknown"
    assert state.live_run.status == "blocked"
    assert state.live_run.next_action == "unknown_routine_id"


def test_operator_app_controller_selects_pages_and_rejects_unknown_page() -> None:
    controller = OperatorAppController(_FakeRunnerService({}))

    state = controller.select_page("trace_viewer")

    assert state.current_page_id == "trace_viewer"
    with pytest.raises(OperatorAppStateError, match="unknown app page"):
        controller.select_page("missing")


def test_operator_app_controller_resolves_approval_dialog() -> None:
    approvals = _FakeApprovalService()
    controller = OperatorAppController(_FakeRunnerService({}), approvals=approvals)
    dialog = ApprovalDialogState(
        routine_id="social.publish",
        step_id="submit-post",
        risk_class="high",
        checkpoint_evidence="checkpoint screenshot present",
        content_fingerprint="sha256:abc123",
    )

    pending = controller.request_approval(dialog)
    approved = controller.resolve_approval(
        "approve",
        approver="qa@example.test",
        reason="Checkpoint matches approved draft.",
    )

    assert pending.current_page_id == "approvals"
    assert pending.approval_dialog is not None
    assert pending.approval_dialog.status == "pending"
    assert approved.approval_dialog is not None
    assert approved.approval_dialog.status == "approve"
    assert approved.approval_dialog.approver == "qa@example.test"
    assert approved.approval_dialog.reason == "Checkpoint matches approved draft."
    assert approved.approval_dialog.decided_at == "2026-05-16T00:00:00+00:00"
    assert approvals.decisions[0].approved is True
    with pytest.raises(OperatorAppStateError, match="unsupported approval action"):
        controller.resolve_approval("maybe")


def test_operator_app_controller_tracks_recorder_review_state() -> None:
    controller = OperatorAppController(_FakeRunnerService({}))
    review = RecorderReviewPanelState(
        generated_yaml="name: Recorded routine\nsteps: []\n",
        selected_targets=("Submit", "Done"),
        verification_suggestions=("visible_text: Done",),
        status="ready_for_save",
    )

    state = controller.review_recording(review)
    metadata = state.metadata()

    assert state.current_page_id == "record"
    assert state.recorder_review == review
    assert metadata["recorder_review"] == review.metadata()


def test_operator_app_controller_tracks_trace_viewer_state(tmp_path: Path) -> None:
    controller = OperatorAppController(_FakeRunnerService({}))
    timeline = TraceViewerTimelineState(
        video_path=tmp_path / "proof-video.mp4",
        screenshot_paths=(tmp_path / "screenshots" / "after.png",),
        action_log_path=tmp_path / "action-log.jsonl",
        candidate_reasoning=("selected candidate-1",),
        state_delta=("visible text added Success",),
        verification_results=("visible text verification passed",),
        proof_gates=("suite_validation: passed",),
        final_report_path=tmp_path / "final-report.json",
        status="loaded",
    )

    state = controller.view_trace(timeline)
    metadata = state.metadata()

    assert state.current_page_id == "trace_viewer"
    assert state.trace_viewer == timeline
    assert metadata["trace_viewer"] == timeline.metadata()
    trace_viewer = metadata["trace_viewer"]
    assert isinstance(trace_viewer, dict)
    assert trace_viewer["proof_gates"] == ["suite_validation: passed"]


def test_operator_app_controller_loads_trace_report_state(
    tmp_path: Path,
) -> None:
    trace_root = tmp_path / "traces"
    trace_dir = trace_root / "proof-suite"
    trace_dir.mkdir(parents=True)
    (trace_dir / "proof-finalization-status.json").write_text(
        (
            '{"status":"passed","gates":{"suite_validation":"passed"},'
            '"summary":{"expected_count":4,"artifact_count":7,"error_count":0},'
            '"checked_artifacts":{"promotion":[],"archive":[]},'
            '"warnings":["browser-fixture: video_path is not present"]}'
        ),
        encoding="utf-8",
    )
    controller = OperatorAppController(
        _FakeRunnerService({}),
        traces=LocalTraceService(trace_root),
    )

    state = controller.view_trace_report(trace_dir)

    assert state.current_page_id == "trace_viewer"
    assert state.trace_viewer is not None
    assert state.trace_viewer.trace_kind == "proof_suite"
    assert state.trace_viewer.proof_gates == ("suite_validation: passed",)
    assert state.trace_viewer.verification_results == (
        "expected_count: 4",
        "artifact_count: 7",
        "error_count: 0",
        "warning: browser-fixture: video_path is not present",
    )
    assert state.trace_viewer.final_report_path == (
        trace_dir / "proof-finalization-status.json"
    )


def test_operator_app_controller_loads_benchmark_trace_report_state(
    tmp_path: Path,
) -> None:
    trace_root = tmp_path / "traces"
    trace_dir = trace_root / "benchmark"
    trace_dir.mkdir(parents=True)
    (trace_dir / "benchmark-report.json").write_text(
        (
            '{"acceptance":{"status":"passed"},'
            '"schema_version":"benchmark_report_v1",'
            '"generated_at":"2026-05-17T00:00:00+00:00",'
            '"baseline_comparison":{"status":"neutral"},'
            '"observability_contract":{"configured":true},'
            '"monitoring_coverage":{"configured":true,"passed":true},'
            '"trace_health_summary":{"health_status":"ok",'
            '"artifact_trace_count":1},'
            '"report_artifacts":{"metrics":"runs.jsonl"}}'
        ),
        encoding="utf-8",
    )
    controller = OperatorAppController(
        _FakeRunnerService({}),
        traces=LocalTraceService(trace_root),
    )

    state = controller.view_trace_report(trace_dir)

    assert state.current_page_id == "trace_viewer"
    assert state.trace_viewer is not None
    assert state.trace_viewer.trace_kind == "benchmark"
    assert state.trace_viewer.verification_results == (
        "schema: benchmark_report_v1",
        "generated_at: 2026-05-17T00:00:00+00:00",
        "acceptance: passed",
        "baseline: neutral",
        "monitoring coverage: passed",
        "trace health: ok",
        "trace health artifacts: 1",
        "artifact metrics: runs.jsonl",
    )
    assert state.trace_viewer.final_report_path == trace_dir / "benchmark-report.json"


def test_operator_app_controller_refreshes_trace_health(
    tmp_path: Path,
) -> None:
    trace_root = tmp_path / "traces"
    trace_dir = trace_root / "run"
    trace_dir.mkdir(parents=True)
    (trace_dir / "final-report.json").write_text(
        '{"status":"failed"}',
        encoding="utf-8",
    )
    controller = OperatorAppController(
        _FakeRunnerService({}),
        traces=LocalTraceService(trace_root),
    )

    state = controller.refresh_trace_health()
    metadata = state.metadata()

    assert state.current_page_id == "dashboard"
    assert state.trace_health is not None
    assert state.trace_health.trace_count == 1
    assert state.trace_health.attention_count == 1
    assert state.trace_health.status == "attention"
    trace_health = metadata["trace_health"]
    assert isinstance(trace_health, dict)
    assert trace_health["attention_count"] == 1
    assert trace_health["artifact_count"] == 0
    assert trace_health["kind_counts"] == {"run": 1}
    assert trace_health["status_counts"] == {"failed": 1}
    assert trace_health["status"] == "attention"
    assert trace_health["schema_version"] == "trace_health_v1"
    assert isinstance(trace_health["generated_at"], str)
    assert trace_health["benchmark_health_status"] is None
    assert trace_health["benchmark_artifact_count"] is None
    assert trace_health["proof_expected_count"] is None
    assert trace_health["proof_artifact_count"] is None
    assert trace_health["proof_error_count"] is None


def test_operator_app_controller_refreshes_benchmark_trace_health(
    tmp_path: Path,
) -> None:
    trace_root = tmp_path / "traces"
    trace_dir = trace_root / "benchmark"
    trace_dir.mkdir(parents=True)
    (trace_dir / "benchmark-report.json").write_text(
        (
            '{"acceptance":{"status":"passed"},'
            '"trace_health_summary":{"health_status":"ok",'
            '"artifact_trace_count":0}}'
        ),
        encoding="utf-8",
    )
    controller = OperatorAppController(
        _FakeRunnerService({}),
        traces=LocalTraceService(trace_root),
    )

    state = controller.refresh_trace_health()
    metadata = state.metadata()

    trace_health = metadata["trace_health"]
    assert isinstance(trace_health, dict)
    assert trace_health["status"] == "ok"
    assert trace_health["benchmark_health_status"] == "ok"
    assert trace_health["benchmark_artifact_count"] == 0


def test_operator_app_controller_refreshes_proof_trace_summary(
    tmp_path: Path,
) -> None:
    trace_root = tmp_path / "traces"
    trace_dir = trace_root / "proof"
    trace_dir.mkdir(parents=True)
    (trace_dir / "proof-finalization-status.json").write_text(
        (
            '{"status":"passed",'
            '"summary":{"expected_count":4,"artifact_count":7,"error_count":0},'
            '"gates":{"suite_validation":"passed"},'
            '"checked_artifacts":{"promotion":[],"archive":[]}}'
        ),
        encoding="utf-8",
    )
    controller = OperatorAppController(
        _FakeRunnerService({}),
        traces=LocalTraceService(trace_root),
    )

    state = controller.refresh_trace_health()
    metadata = state.metadata()

    trace_health = metadata["trace_health"]
    assert isinstance(trace_health, dict)
    assert trace_health["proof_expected_count"] == 4
    assert trace_health["proof_artifact_count"] == 7
    assert trace_health["proof_error_count"] == 0


class _FakeRunnerService:
    def __init__(self, gates: dict[str, RoutineExecutionGate]) -> None:
        self._gates = gates
        self.run_statuses: dict[str, str] = {}
        self.run_routines: dict[str, str] = {}

    def execution_gate(self, routine_id: str) -> RoutineExecutionGate:
        return self._gates.get(
            routine_id,
            RoutineExecutionGate(
                routine_id=routine_id,
                allowed=False,
                reason="unknown_routine_id",
            ),
        )

    def dry_run_routine(self, routine_id: str) -> OperatorDryRunResult:
        gate = self.execution_gate(routine_id)
        return OperatorDryRunResult(
            routine_id=routine_id,
            status="passed" if gate.allowed else "blocked",
            reason="dry_run_validated" if gate.allowed else gate.reason,
            task_name=routine_id if gate.allowed else None,
            step_count=1 if gate.allowed else 0,
            desktop_input_required=False,
            preview="dry-run preview:",
            compiled_task={"step_order": ["observe"]} if gate.allowed else {},
            execution_gate=gate,
        )

    def start_routine(self, routine_id: str) -> OperatorRunStartResult:
        gate = self.execution_gate(routine_id)
        if not gate.allowed:
            return OperatorRunStartResult(
                run_id=None,
                routine_id=routine_id,
                status="blocked",
                reason=gate.reason,
                next_action=None,
                execution_gate=gate,
            )
        self.run_statuses["run-0001"] = "running"
        self.run_routines["run-0001"] = routine_id
        return OperatorRunStartResult(
            run_id="run-0001",
            routine_id=routine_id,
            status="running",
            reason="operator_app_start",
            next_action="observe_screen",
            execution_gate=gate,
        )

    def pause_run(self, run_id: str) -> OperatorRunControlResult:
        return self._transition_run(run_id, "paused", "operator_app_pause")

    def resume_run(self, run_id: str) -> OperatorRunControlResult:
        return self._transition_run(run_id, "running", "operator_app_resume")

    def cancel_run(self, run_id: str) -> OperatorRunControlResult:
        return self._transition_run(run_id, "canceled", "operator_app_cancel")

    def stop_run(self, run_id: str) -> OperatorRunControlResult:
        return self._transition_run(run_id, "stopped", "operator_app_stop")

    def emergency_stop_run(self, run_id: str) -> OperatorRunControlResult:
        return self._transition_run(
            run_id,
            "emergency_stopped",
            "operator_app_emergency_stop",
        )

    def _transition_run(
        self,
        run_id: str,
        status: str,
        reason: str,
    ) -> OperatorRunControlResult:
        self.run_statuses[run_id] = status
        next_action = "observe_screen" if status == "running" else None
        if status == "paused":
            next_action = "resume_or_cancel"
        return OperatorRunControlResult(
            run_id=run_id,
            routine_id=self.run_routines[run_id],
            status=status,
            reason=reason,
            next_action=next_action,
        )


class _FakeApprovalService:
    def __init__(self) -> None:
        self.decisions: list[OperatorApprovalDecision] = []

    def routines_requiring_approval(self) -> tuple[RoutineListItem, ...]:
        return ()

    def resolve_step_approval(
        self,
        *,
        routine_id: str,
        step_id: str,
        action: str,
        risk_class: str,
        checkpoint_evidence: str,
        content_fingerprint: str,
        approver: str,
        reason: str,
        decided_at: str | None = None,
    ) -> OperatorApprovalDecision:
        decision = OperatorApprovalDecision(
            routine_id=routine_id,
            step_id=step_id,
            action=action,
            risk_class=risk_class,
            checkpoint_evidence=checkpoint_evidence,
            content_fingerprint=content_fingerprint,
            approver=approver,
            reason=reason,
            decided_at=decided_at or "2026-05-16T00:00:00+00:00",
        )
        self.decisions.append(decision)
        return decision

    def approval_decisions(self) -> tuple[OperatorApprovalDecision, ...]:
        return tuple(self.decisions)
