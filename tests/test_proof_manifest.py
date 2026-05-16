import json
import zipfile
from pathlib import Path
from typing import cast

from desktop_agent.proof_manifest import (
    proof_suite_status_metadata,
    render_proof_suite_report,
    render_proof_suite_runbook,
    run_proof_preflight,
    validate_proof_bundle,
    validate_proof_suite,
    write_proof_preflight_report,
    write_proof_suite_archive,
    write_proof_suite_report,
    write_proof_suite_runbook,
    write_proof_suite_status,
)


def test_run_proof_preflight_passes_on_windows_with_video_tool(
    tmp_path: Path,
) -> None:
    result = run_proof_preflight(
        tmp_path / "traces",
        platform_name="win32",
        path_lookup=lambda command: "/usr/bin/ffmpeg" if command == "ffmpeg" else None,
    )

    assert result.passed
    assert result.metadata()["status"] == "passed"
    assert tuple(check.name for check in result.checks) == (
        "windows-platform",
        "trace-root",
        "video-capture",
    )


def test_run_proof_preflight_reports_platform_and_video_failures(
    tmp_path: Path,
) -> None:
    result = run_proof_preflight(
        tmp_path / "traces",
        platform_name="darwin",
        path_lookup=lambda _command: None,
    )

    assert not result.passed
    statuses = {check.name: check.status for check in result.checks}
    assert statuses["windows-platform"] == "failed"
    assert statuses["trace-root"] == "passed"
    assert statuses["video-capture"] == "failed"


def test_write_proof_preflight_report_records_readiness_checks(
    tmp_path: Path,
) -> None:
    result = run_proof_preflight(
        tmp_path / "traces",
        platform_name="darwin",
        path_lookup=lambda _command: None,
    )

    report_path = write_proof_preflight_report(result)
    payload = json.loads(report_path.read_text(encoding="utf-8"))

    assert report_path == tmp_path / "traces" / "proof-preflight.json"
    assert payload["status"] == "failed"
    assert payload["trace_root"] == str(tmp_path / "traces")
    assert [check["name"] for check in payload["checks"]] == [
        "windows-platform",
        "trace-root",
        "video-capture",
    ]


def test_validate_proof_bundle_accepts_complete_evidence(tmp_path: Path) -> None:
    trace_dir = _write_proof_bundle(tmp_path)

    result = validate_proof_bundle(trace_dir)

    assert result.passed
    assert result.errors == ()
    assert ("video_path", trace_dir / "proof-video.mp4") in result.artifact_paths


def test_validate_proof_bundle_reports_missing_video_and_step_evidence(
    tmp_path: Path,
) -> None:
    trace_dir = _write_proof_bundle(tmp_path)
    (trace_dir / "proof-video.mp4").unlink()
    report_path = trace_dir / "browser-fixture-report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["steps"][0]["metadata"].pop("post_action_evidence")
    report_path.write_text(json.dumps(report), encoding="utf-8")

    result = validate_proof_bundle(trace_dir)

    assert not result.passed
    assert any("video_path does not exist" in error for error in result.errors)
    assert any(
        "proof report step click-submit missing post_action_evidence" in error
        for error in result.errors
    )


def test_validate_proof_bundle_can_allow_missing_video_for_disabled_capture(
    tmp_path: Path,
) -> None:
    trace_dir = _write_proof_bundle(tmp_path, include_video=False)

    result = validate_proof_bundle(trace_dir, require_video=False)

    assert result.passed
    assert result.warnings == (
        "video_path is not present; video requirement was disabled",
    )


def test_validate_proof_bundle_reports_missing_manifest_metadata(
    tmp_path: Path,
) -> None:
    trace_dir = _write_proof_bundle(tmp_path)
    manifest_path = trace_dir / "proof-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for key in ("command", "started_at", "monitor_geometry", "dpi_scale"):
        manifest.pop(key)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = validate_proof_bundle(trace_dir)

    assert not result.passed
    assert "proof manifest command must be a non-empty string list" in result.errors
    assert "proof manifest missing started_at" in result.errors
    assert "proof manifest monitor_geometry must be a JSON object" in result.errors
    assert "proof manifest dpi_scale must be a two-number list" in result.errors


def test_validate_proof_suite_requires_all_fixture_bundles(tmp_path: Path) -> None:
    for proof_name in (
        "browser-fixture",
        "native-fixture",
        "mixed-fixture",
        "recovery-fixture",
    ):
        _write_proof_bundle(
            tmp_path,
            proof_name=proof_name,
            trace_dir_name=proof_name,
        )

    result = validate_proof_suite(tmp_path)

    assert result.passed
    assert result.missing_proofs == ()
    assert tuple(bundle.proof_name for bundle in result.bundle_results) == (
        "browser-fixture",
        "native-fixture",
        "mixed-fixture",
        "recovery-fixture",
    )


def test_validate_proof_suite_reports_missing_bundle(tmp_path: Path) -> None:
    _write_proof_bundle(
        tmp_path,
        proof_name="browser-fixture",
        trace_dir_name="browser-fixture",
        include_video=False,
    )

    result = validate_proof_suite(tmp_path, require_video=False)

    assert not result.passed
    assert "missing proof bundle: native-fixture" in result.errors
    assert "missing proof bundle: mixed-fixture" in result.errors
    assert "missing proof bundle: recovery-fixture" in result.errors


def test_validate_proof_suite_can_require_passing_preflight(tmp_path: Path) -> None:
    for proof_name in (
        "browser-fixture",
        "native-fixture",
        "mixed-fixture",
        "recovery-fixture",
    ):
        _write_proof_bundle(
            tmp_path,
            proof_name=proof_name,
            trace_dir_name=proof_name,
            include_video=False,
        )
    write_proof_preflight_report(
        run_proof_preflight(
            tmp_path,
            require_windows=False,
            require_video=False,
        ),
    )

    result = validate_proof_suite(
        tmp_path,
        require_video=False,
        require_preflight=True,
    )

    assert result.passed
    assert result.preflight_report_path == tmp_path / "proof-preflight.json"
    assert result.preflight_errors == ()


def test_validate_proof_suite_reports_missing_required_preflight(
    tmp_path: Path,
) -> None:
    _write_proof_bundle(
        tmp_path,
        proof_name="browser-fixture",
        trace_dir_name="browser-fixture",
        include_video=False,
    )

    result = validate_proof_suite(
        tmp_path,
        require_video=False,
        require_preflight=True,
    )

    assert not result.passed
    assert (
        f"proof preflight report not found: {tmp_path / 'proof-preflight.json'}"
        in result.errors
    )


def test_validate_proof_suite_reports_failed_required_preflight(
    tmp_path: Path,
) -> None:
    _write_proof_bundle(
        tmp_path,
        proof_name="browser-fixture",
        trace_dir_name="browser-fixture",
        include_video=False,
    )
    write_proof_preflight_report(
        run_proof_preflight(
            tmp_path,
            platform_name="darwin",
            path_lookup=lambda _command: None,
        ),
    )

    result = validate_proof_suite(
        tmp_path,
        require_video=False,
        require_preflight=True,
    )

    assert not result.passed
    assert "proof preflight status is not passed: failed" in result.errors
    assert (
        "proof preflight check windows-platform is not passed: failed"
        in result.errors
    )


def test_write_proof_suite_report_summarizes_bundle_status(tmp_path: Path) -> None:
    _write_proof_bundle(
        tmp_path,
        proof_name="browser-fixture",
        trace_dir_name="browser-fixture",
        include_video=False,
    )
    result = validate_proof_suite(tmp_path, require_video=False)

    report = render_proof_suite_report(result)
    report_path = write_proof_suite_report(result)

    assert report_path == tmp_path / "proof-suite-report.md"
    assert report_path.read_text(encoding="utf-8") == report
    assert "# DeskPilot Windows Proof Suite Report" in report
    assert "- Status: `failed`" in report
    assert "### browser-fixture" in report
    assert "- Status: `passed`" in report
    assert "### native-fixture" in report
    assert "- Status: `missing`" in report
    assert "- Missing proofs:" in report


def test_write_proof_suite_status_records_monitoring_payload(
    tmp_path: Path,
) -> None:
    _write_proof_bundle(
        tmp_path,
        proof_name="browser-fixture",
        trace_dir_name="browser-fixture",
        include_video=False,
    )
    result = validate_proof_suite(tmp_path, require_video=False)

    payload = proof_suite_status_metadata(result)
    status_path = write_proof_suite_status(result)
    saved_payload = json.loads(status_path.read_text(encoding="utf-8"))

    assert status_path == tmp_path / "proof-suite-status.json"
    assert saved_payload == payload
    assert payload["status"] == "failed"
    assert payload["preflight_report_path"] is None
    assert payload["missing_proofs"] == [
        "native-fixture",
        "mixed-fixture",
        "recovery-fixture",
    ]
    proofs = cast(list[dict[str, object]], payload["proofs"])
    assert proofs[0]["proof_name"] == "browser-fixture"
    assert proofs[0]["status"] == "passed"
    assert proofs[1]["status"] == "missing"


def test_write_proof_suite_runbook_lists_next_operator_commands(
    tmp_path: Path,
) -> None:
    _write_proof_bundle(
        tmp_path,
        proof_name="browser-fixture",
        trace_dir_name="browser-fixture",
        include_video=False,
    )
    result = validate_proof_suite(tmp_path, require_video=False)

    runbook = render_proof_suite_runbook(result, require_video=False)
    runbook_path = write_proof_suite_runbook(result, require_video=False)

    assert runbook_path == tmp_path / "proof-suite-next-actions.md"
    assert runbook_path.read_text(encoding="utf-8") == runbook
    assert "# DeskPilot Windows Proof Suite Next Actions" in runbook
    assert (
        "desktop-agent proof native-fixture --trace-root "
        f"{tmp_path} --countdown-seconds 5 --video-policy disabled"
    ) in runbook
    assert (
        "desktop-agent proof validate-suite "
        f"{tmp_path} --allow-missing-video --require-preflight --write-report "
        "--write-status-json --write-runbook"
    ) in runbook


def test_write_proof_suite_archive_packages_review_artifacts(
    tmp_path: Path,
) -> None:
    _write_proof_bundle(
        tmp_path,
        proof_name="browser-fixture",
        trace_dir_name="browser-fixture",
        include_video=False,
    )
    write_proof_preflight_report(
        run_proof_preflight(
            tmp_path,
            require_windows=False,
            require_video=False,
        ),
    )
    result = validate_proof_suite(tmp_path, require_video=False)

    archive_path = write_proof_suite_archive(result, require_video=False)

    assert archive_path == tmp_path / "proof-suite-artifacts.zip"
    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
    assert "proof-suite-report.md" in names
    assert "proof-suite-status.json" in names
    assert "proof-suite-next-actions.md" in names
    assert "proof-preflight.json" in names
    assert "browser-fixture/proof-manifest.json" in names
    assert "browser-fixture/browser-fixture-report.json" in names
    assert "browser-fixture/action-log.jsonl" in names
    assert "browser-fixture/screenshots/shot-1.png" in names


def _write_proof_bundle(
    root: Path,
    *,
    proof_name: str = "browser-fixture",
    trace_dir_name: str = "trace",
    include_video: bool = True,
) -> Path:
    trace_dir = root / trace_dir_name
    screenshot_dir = trace_dir / "screenshots"
    screenshot_dir.mkdir(parents=True)
    screenshot_path = screenshot_dir / "shot-1.png"
    screenshot_path.write_bytes(b"png")
    action_log_path = trace_dir / "action-log.jsonl"
    action_log_path.write_text(
        json.dumps(
            {
                "phase": "demo_step",
                "metadata": {
                    "step_id": "click-submit",
                    "post_action_evidence": {"status": "passed"},
                },
            },
        )
        + "\n",
        encoding="utf-8",
    )
    report_path = trace_dir / f"{proof_name}-report.json"
    report_path.write_text(
        json.dumps(
            {
                "status": "passed",
                "steps": [
                    {
                        "step_id": "click-submit",
                        "action": "click",
                        "metadata": {
                            "post_action_evidence": {
                                "status": "passed",
                                "active_window_title": "Browser Fixture - Edge",
                                "cursor_position": [320, 240],
                                "screenshot_path": str(screenshot_path),
                            },
                        },
                    },
                ],
            },
        ),
        encoding="utf-8",
    )
    video_path = trace_dir / "proof-video.mp4"
    video_log_path = trace_dir / "video-capture.log"
    if include_video:
        video_path.write_bytes(b"mp4")
        video_log_path.write_text("ffmpeg complete\n", encoding="utf-8")

    manifest: dict[str, object] = {
        "schema_version": 1,
        "proof_name": proof_name,
        "command": ["desktop-agent", "proof", proof_name],
        "status": "passed",
        "started_at": "2026-05-16T00:00:00+00:00",
        "completed_at": "2026-05-16T00:00:01+00:00",
        "executable_version": "0.1.0",
        "python_version": "3.12.0",
        "windows_version": "Windows-11-Fixture",
        "platform": "win32",
        "monitor_geometry": {
            "left": 0,
            "top": 0,
            "width": 1280,
            "height": 720,
        },
        "dpi_scale": [1.0, 1.0],
        "artifacts": {
            "trace_dir": str(trace_dir),
            "report_path": str(report_path),
            "action_log_path": str(action_log_path),
            "proof_manifest_path": str(trace_dir / "proof-manifest.json"),
            "screenshots": [str(screenshot_path)],
        },
        "steps": [
            {
                "step_id": "click-submit",
                "action": "click",
                "has_post_action_evidence": True,
            },
        ],
    }
    if include_video:
        artifacts = cast(dict[str, object], manifest["artifacts"])
        artifacts["video_path"] = str(video_path)
        artifacts["video_log_path"] = str(video_log_path)
        manifest["video_capture"] = {"status": "passed"}
    (trace_dir / "proof-manifest.json").write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )
    return trace_dir
