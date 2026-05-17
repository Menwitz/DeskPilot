import tomllib
from pathlib import Path

from pytest import CaptureFixture

from desktop_agent.config import ExecutionProfile, LocalModelConfig, RuntimeConfig
from desktop_agent.failed_run_analyzer import (
    FailedRunAnalysis,
    FailedRunYamlProposal,
)
from desktop_agent.operator_app import main
from desktop_agent.operator_app_shell import (
    ApprovalDialogState,
    FailureAnalysisReviewPanelState,
    LiveRunPanelState,
    RecorderReviewPanelState,
    RoutinePackManagerState,
    SettingsPanelState,
    TraceHealthPanelState,
    TraceViewerTimelineState,
    default_live_run_panel_state,
    failure_analysis_review_from_analysis,
    operator_app_shell_spec,
    render_approval_dialog_text,
    render_failure_analysis_review_text,
    render_live_run_panel_text,
    render_operator_app_shell_text,
    render_recorder_review_text,
    render_routine_pack_manager_text,
    render_settings_panel_text,
    render_trace_health_panel_text,
    render_trace_viewer_timeline_text,
    settings_panel_from_runtime_config,
    trace_health_panel_from_metadata,
    trace_viewer_timeline_from_report,
)


def test_pyproject_exposes_deskpilot_app_entry_point() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["scripts"]["deskpilot-app"] == (
        "desktop_agent.operator_app:main"
    )


def test_operator_app_check_mode_reports_entry_point(
    capsys: CaptureFixture[str],
) -> None:
    status = main(["--check"])

    output = capsys.readouterr().out
    assert status == 0
    assert "deskpilot-app entry point: ok" in output
    assert "PySide6:" in output


def test_operator_app_shell_exposes_required_pages() -> None:
    shell = operator_app_shell_spec()

    assert shell.default_page_id == "dashboard"
    assert [page.page_id for page in shell.pages] == [
        "dashboard",
        "routine_library",
        "routine_packs",
        "record",
        "run_queue",
        "approvals",
        "trace_viewer",
        "settings",
        "help",
    ]
    assert shell.pages[0].panel_ids == ("live_run", "trace_health")
    packs_page = next(page for page in shell.pages if page.page_id == "routine_packs")
    assert packs_page.panel_ids == ("routine_pack_manager",)
    record_page = next(page for page in shell.pages if page.page_id == "record")
    assert record_page.panel_ids == ("recorder_review",)
    approvals_page = next(page for page in shell.pages if page.page_id == "approvals")
    assert approvals_page.panel_ids == ("approval_dialog",)
    trace_page = next(page for page in shell.pages if page.page_id == "trace_viewer")
    assert trace_page.panel_ids == ("trace_timeline", "failure_analysis_review")
    settings_page = next(page for page in shell.pages if page.page_id == "settings")
    assert settings_page.panel_ids == ("settings",)
    assert shell.metadata()["pages"]


def test_operator_app_describe_shell_prints_pages(
    capsys: CaptureFixture[str],
) -> None:
    status = main(["--describe-shell"])

    output = capsys.readouterr().out
    assert status == 0
    assert "DeskPilot Operator" in output
    assert "Dashboard (default)" in output
    assert "panel: live_run" in output
    assert "panel: trace_health" in output
    assert "Routine Library" in output
    assert "Trace Viewer" in output
    assert output == render_operator_app_shell_text()


def test_live_run_panel_state_tracks_run_status_fields(tmp_path: Path) -> None:
    state = LiveRunPanelState(
        run_id="run-0001",
        current_routine_id="browser.search",
        current_step_id="type-query",
        screenshot_path=tmp_path / "screen.png",
        selected_target="Search box",
        next_action="type_text",
        elapsed_seconds=12.5,
        status="running",
    )

    metadata = state.metadata()
    text = render_live_run_panel_text(state)

    assert metadata["run_id"] == "run-0001"
    assert metadata["current_routine_id"] == "browser.search"
    assert metadata["current_step_id"] == "type-query"
    assert metadata["screenshot_path"] == str(tmp_path / "screen.png")
    assert metadata["selected_target"] == "Search box"
    assert metadata["next_action"] == "type_text"
    assert metadata["elapsed_seconds"] == 12.5
    assert metadata["status"] == "running"
    assert metadata["stop_controls"] == [
        "pause",
        "resume",
        "cancel",
        "emergency_stop",
    ]
    assert "Screenshot preview" in text
    assert "Run ID: run-0001" in text
    assert "Stop controls: pause, resume, cancel, emergency_stop" in text


def test_live_run_panel_defaults_to_idle() -> None:
    state = default_live_run_panel_state()

    assert state.status == "idle"
    assert state.current_routine_id is None


def test_trace_health_panel_tracks_counts() -> None:
    state = trace_health_panel_from_metadata(
        {
            "schema_version": "trace_health_v1",
            "generated_at": "2026-05-17T00:00:00+00:00",
            "trace_count": 3,
            "artifact_trace_count": 1,
            "warning_trace_count": 1,
            "by_kind": {"run": 1, "goal_plan": 1, "proof_suite": 1},
            "by_status": {"passed": 2, "failed": 1},
            "health_status": "attention",
            "attention_traces": [{"trace_dir": "traces/failed-run"}],
            "artifact_traces": [
                {
                    "kind": "benchmark",
                    "trace_health_summary": {
                        "health_status": "ok",
                        "artifact_trace_count": 1,
                        "warning_trace_count": 1,
                    },
                },
            ],
            "latest": [
                {
                    "kind": "proof_suite",
                    "proof_summary": {
                        "expected_count": 4,
                        "artifact_count": 7,
                        "error_count": 0,
                    },
                    "proof_warnings": [
                        "browser-fixture: video_path is external",
                        "native-fixture: video_path is external",
                    ],
                },
            ],
        },
    )
    empty = TraceHealthPanelState()
    metadata = state.metadata()
    text = render_trace_health_panel_text(state)

    assert empty.status == "empty"
    assert metadata["trace_count"] == 3
    assert metadata["attention_count"] == 1
    assert metadata["artifact_count"] == 1
    assert metadata["warning_trace_count"] == 1
    assert metadata["kind_counts"] == {
        "goal_plan": 1,
        "proof_suite": 1,
        "run": 1,
    }
    assert metadata["status_counts"] == {"failed": 1, "passed": 2}
    assert metadata["status"] == "attention"
    assert metadata["schema_version"] == "trace_health_v1"
    assert metadata["generated_at"] == "2026-05-17T00:00:00+00:00"
    assert metadata["benchmark_health_status"] == "ok"
    assert metadata["benchmark_artifact_count"] == 1
    assert metadata["benchmark_warning_trace_count"] == 1
    assert metadata["proof_expected_count"] == 4
    assert metadata["proof_artifact_count"] == 7
    assert metadata["proof_error_count"] == 0
    assert metadata["proof_warning_count"] == 2
    assert "Trace Health" in text
    assert "Schema version: trace_health_v1" in text
    assert "Generated at: 2026-05-17T00:00:00+00:00" in text
    assert "proof_suite=1" in text
    assert "Status: attention" in text
    assert "Attention traces: 1" in text
    assert "Artifact traces: 1" in text
    assert "Warning traces: 1" in text
    assert "Benchmark health: ok" in text
    assert "Benchmark health artifacts: 1" in text
    assert "Benchmark health warnings: 1" in text
    assert "Proof expected: 4" in text
    assert "Proof artifacts: 7" in text
    assert "Proof errors: 0" in text
    assert "Proof warnings: 2" in text
    assert "passed=2" in text


def test_trace_health_panel_uses_latest_benchmark_health_fallback() -> None:
    state = trace_health_panel_from_metadata(
        {
            "trace_count": 1,
            "artifact_trace_count": 0,
            "health_status": "ok",
            "artifact_traces": [],
            "latest": [
                {
                    "kind": "benchmark",
                    "trace_health_summary": {
                        "health_status": "ok",
                        "artifact_trace_count": 0,
                    },
                },
            ],
        },
    )

    assert state.benchmark_health_status == "ok"
    assert state.benchmark_artifact_count == 0
    assert state.benchmark_warning_trace_count is None


def test_trace_health_panel_rejects_boolean_top_level_counts() -> None:
    state = trace_health_panel_from_metadata(
        {
            "trace_count": True,
            "artifact_trace_count": False,
            "warning_trace_count": True,
            "health_status": "ok",
        },
    )

    assert state.trace_count == 0
    assert state.artifact_count == 0
    assert state.warning_trace_count == 0


def test_approval_dialog_state_tracks_required_review_fields() -> None:
    state = ApprovalDialogState(
        routine_id="social.publish",
        step_id="submit-post",
        risk_class="high",
        checkpoint_evidence="checkpoint screenshot present",
        content_fingerprint="sha256:abc123",
        approver="operator@example.test",
        reason="Reviewed checkpoint.",
        decided_at="2026-05-16T00:00:00+00:00",
    )

    metadata = state.metadata()
    text = render_approval_dialog_text(state)

    assert metadata["routine_id"] == "social.publish"
    assert metadata["step_id"] == "submit-post"
    assert metadata["risk_class"] == "high"
    assert metadata["checkpoint_evidence"] == "checkpoint screenshot present"
    assert metadata["content_fingerprint"] == "sha256:abc123"
    assert metadata["approver"] == "operator@example.test"
    assert metadata["reason"] == "Reviewed checkpoint."
    assert metadata["decided_at"] == "2026-05-16T00:00:00+00:00"
    assert metadata["actions"] == ["approve", "deny"]
    assert "Approver: operator@example.test" in text
    assert "Actions: approve, deny" in text


def test_recorder_review_panel_tracks_generated_yaml_and_evidence(
    tmp_path: Path,
) -> None:
    state = RecorderReviewPanelState(
        generated_yaml="name: recorded routine",
        selected_targets=("Search box", "Submit"),
        screenshot_paths=(tmp_path / "before.png", tmp_path / "after.png"),
        verification_suggestions=("visible_text: Success",),
        status="review",
    )

    metadata = state.metadata()
    text = render_recorder_review_text(state)

    assert metadata["generated_yaml"] == "name: recorded routine"
    assert metadata["selected_targets"] == ["Search box", "Submit"]
    assert metadata["screenshot_paths"] == [
        str(tmp_path / "before.png"),
        str(tmp_path / "after.png"),
    ]
    assert metadata["verification_suggestions"] == ["visible_text: Success"]
    assert metadata["status"] == "review"
    assert "Recorder Review" in text
    assert "Generated YAML" in text
    assert "Search box, Submit" in text


def test_trace_viewer_timeline_tracks_evidence_paths_and_reasoning(
    tmp_path: Path,
) -> None:
    state = TraceViewerTimelineState(
        video_path=tmp_path / "proof-video.mp4",
        screenshot_paths=(tmp_path / "before.png", tmp_path / "after.png"),
        action_log_path=tmp_path / "action-log.jsonl",
        candidate_reasoning=("selected candidate-1", "rejected candidate-2"),
        state_delta=("visible_text_changed",),
        verification_results=("click-submit passed",),
        final_report_path=tmp_path / "final-report.json",
        status="loaded",
    )

    metadata = state.metadata()
    text = render_trace_viewer_timeline_text(state)

    assert metadata["video_path"] == str(tmp_path / "proof-video.mp4")
    assert metadata["screenshot_paths"] == [
        str(tmp_path / "before.png"),
        str(tmp_path / "after.png"),
    ]
    assert metadata["action_log_path"] == str(tmp_path / "action-log.jsonl")
    assert metadata["trace_kind"] == "run"
    assert metadata["candidate_reasoning"] == [
        "selected candidate-1",
        "rejected candidate-2",
    ]
    assert metadata["state_delta"] == ["visible_text_changed"]
    assert metadata["verification_results"] == ["click-submit passed"]
    assert metadata["proof_gates"] == []
    assert metadata["final_report_path"] == str(tmp_path / "final-report.json")
    assert metadata["status"] == "loaded"
    assert "Trace Timeline" in text
    assert "Trace kind: run" in text
    assert "proof-video.mp4" in text
    assert "selected candidate-1" in text
    assert "click-submit passed" in text


def test_trace_viewer_timeline_loads_proof_suite_status(
    tmp_path: Path,
) -> None:
    state = trace_viewer_timeline_from_report(
        {
            "status": "passed",
            "summary": {
                "expected_count": 4,
                "reported_count": 4,
                "artifact_count": 7,
                "error_count": 0,
                "warning_count": False,
            },
            "gates": {
                "suite_validation": "passed",
                "promotion_verification": "passed",
                "archive_verification": "passed",
            },
            "checked_artifacts": {"promotion": [], "archive": []},
            "warnings": ["browser-fixture: video_path is not present"],
        },
        report_path=tmp_path / "proof-finalization-status.json",
    )
    metadata = state.metadata()
    text = render_trace_viewer_timeline_text(state)

    assert metadata["trace_kind"] == "proof_suite"
    assert metadata["proof_gates"] == [
        "suite_validation: passed",
        "promotion_verification: passed",
        "archive_verification: passed",
    ]
    assert metadata["verification_results"] == [
        "expected_count: 4",
        "reported_count: 4",
        "artifact_count: 7",
        "error_count: 0",
        "warning: browser-fixture: video_path is not present",
    ]
    assert metadata["final_report_path"] == str(
        tmp_path / "proof-finalization-status.json",
    )
    assert "Trace kind: proof_suite" in text
    assert "suite_validation: passed" in text
    assert "artifact_count: 7" in text
    assert "warning: browser-fixture: video_path is not present" in text


def test_trace_viewer_timeline_loads_goal_candidate_reasoning(
    tmp_path: Path,
) -> None:
    state = trace_viewer_timeline_from_report(
        {
            "status": "ready",
            "selected_routine_id": "browser.search-web",
            "candidate_routines": [
                {
                    "routine_id": "browser.search-web",
                    "score": 12.5,
                    "matched_fields": ["tags", "outputs"],
                },
            ],
        },
        report_path=tmp_path / "goal-plan-report.json",
    )
    metadata = state.metadata()
    text = render_trace_viewer_timeline_text(state)

    assert metadata["trace_kind"] == "goal_plan"
    assert metadata["candidate_reasoning"] == [
        "browser.search-web: score 12.5 matched tags, outputs",
    ]
    assert "browser.search-web: score 12.5 matched tags, outputs" in text


def test_trace_viewer_timeline_loads_benchmark_report(
    tmp_path: Path,
) -> None:
    state = trace_viewer_timeline_from_report(
        {
            "schema_version": "benchmark_report_v1",
            "generated_at": "2026-05-17T00:00:00+00:00",
            "acceptance": {"status": "passed"},
            "baseline_comparison": {"status": "neutral"},
            "observability_contract": {"configured": True},
            "monitoring_coverage": {"configured": True, "passed": True},
            "trace_health_summary": {
                "health_status": "ok",
                "artifact_trace_count": 2,
                "warning_trace_count": 1,
            },
            "report_artifacts": {
                "metrics": str(tmp_path / "runs.jsonl"),
                "summary": str(tmp_path / "benchmark-summary.md"),
            },
        },
        report_path=tmp_path / "benchmark-report.json",
    )
    metadata = state.metadata()
    text = render_trace_viewer_timeline_text(state)

    assert metadata["trace_kind"] == "benchmark"
    assert metadata["status"] == "passed"
    assert metadata["verification_results"] == [
        "schema: benchmark_report_v1",
        "generated_at: 2026-05-17T00:00:00+00:00",
        "acceptance: passed",
        "baseline: neutral",
        "monitoring coverage: passed",
        "trace health: ok",
        "trace health artifacts: 2",
        "trace health warnings: 1",
        f"artifact metrics: {tmp_path / 'runs.jsonl'}",
        f"artifact summary: {tmp_path / 'benchmark-summary.md'}",
    ]
    assert "Trace kind: benchmark" in text
    assert "schema: benchmark_report_v1" in text
    assert "trace health artifacts: 2" in text
    assert "trace health warnings: 1" in text
    assert "artifact metrics:" in text
    assert "monitoring coverage: passed" in text


def test_routine_pack_manager_tracks_install_and_remove_state(tmp_path: Path) -> None:
    state = RoutinePackManagerState(
        installed_pack_ids=("browser", "native"),
        selected_pack_id="browser",
        install_source_path=tmp_path / "local-pack",
        pending_action="remove",
        trust_warnings=("pack is unverified",),
        status="review",
    )

    metadata = state.metadata()
    text = render_routine_pack_manager_text(state)

    assert metadata["installed_pack_ids"] == ["browser", "native"]
    assert metadata["selected_pack_id"] == "browser"
    assert metadata["install_source_path"] == str(tmp_path / "local-pack")
    assert metadata["pending_action"] == "remove"
    assert metadata["trust_warnings"] == ["pack is unverified"]
    assert metadata["actions"] == ["install", "replace", "remove", "export"]
    assert "Routine Packs" in text
    assert "pack is unverified" in text
    assert "Actions: install, replace, remove, export" in text


def test_failure_analysis_review_tracks_review_only_yaml_proposals(
    tmp_path: Path,
) -> None:
    analysis = FailedRunAnalysis(
        task_name="Browser search",
        status="failed",
        routine_id="browser.search",
        proposals=(
            FailedRunYamlProposal(
                step_id="click-submit",
                proposal_type="selector_region_review",
                rationale="Ambiguous target.",
                yaml_snippet="- id: click-submit\n  region:\n    x: REVIEW",
            ),
        ),
    )

    state = failure_analysis_review_from_analysis(
        analysis,
        trace_dir=tmp_path / "trace",
    )
    metadata = state.metadata()
    text = render_failure_analysis_review_text(state)

    assert metadata["trace_dir"] == str(tmp_path / "trace")
    assert metadata["analysis_json_path"] == str(
        tmp_path / "trace" / "failed-run-analysis.json",
    )
    assert metadata["proposal_count"] == 1
    proposals = metadata["proposals"]
    assert isinstance(proposals, list)
    proposal = proposals[0]
    assert isinstance(proposal, dict)
    assert proposal["review_required"] is True
    assert proposal["applies_automatically"] is False
    assert "Failure Analysis Review" in text
    assert "Applies automatically: False" in text


def test_failure_analysis_review_defaults_to_empty() -> None:
    state = FailureAnalysisReviewPanelState()

    assert state.status == "empty"
    assert state.metadata()["proposal_count"] == 0


def test_settings_panel_tracks_runtime_config_and_app_toggles(tmp_path: Path) -> None:
    state = settings_panel_from_runtime_config(
        RuntimeConfig(
            trace_root=tmp_path / "traces",
            save_screenshots=False,
            emergency_stop_hotkey="ctrl+shift+esc",
            execution_profile=ExecutionProfile(activity_profile="careful"),
            local_model=LocalModelConfig(enabled=True),
        ),
        video_capture_enabled=True,
        proof_mode=True,
    )

    metadata = state.metadata()
    text = render_settings_panel_text(state)

    assert metadata["trace_root"] == str(tmp_path / "traces")
    assert metadata["screenshots_enabled"] is False
    assert metadata["video_capture_enabled"] is True
    assert metadata["ollama_enabled"] is True
    assert metadata["emergency_hotkey"] == "ctrl+shift+esc"
    assert metadata["default_activity_profile"] == "careful"
    assert metadata["proof_mode"] is True
    assert "Trace root" in text
    assert "Ollama: True" in text


def test_settings_panel_defaults_are_local_and_safe() -> None:
    state = SettingsPanelState()

    assert state.trace_root == Path("traces")
    assert state.screenshots_enabled is True
    assert state.video_capture_enabled is False
    assert state.ollama_enabled is False
    assert state.proof_mode is False
