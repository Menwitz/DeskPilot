import json
import zipfile
from pathlib import Path
from typing import cast

from desktop_agent.proof_manifest import (
    ProofSuiteValidation,
    proof_suite_promotion_metadata,
    proof_suite_status_metadata,
    render_proof_suite_report,
    render_proof_suite_review_template,
    render_proof_suite_runbook,
    run_proof_preflight,
    validate_proof_bundle,
    validate_proof_review,
    validate_proof_suite,
    verify_proof_suite_promotion,
    write_proof_preflight_report,
    write_proof_review_status,
    write_proof_suite_archive,
    write_proof_suite_promotion,
    write_proof_suite_report,
    write_proof_suite_review_template,
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


def test_validate_proof_suite_can_require_passing_review_status(
    tmp_path: Path,
) -> None:
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
    _write_completed_review_status(tmp_path)

    result = validate_proof_suite(
        tmp_path,
        require_video=False,
        require_review=True,
    )

    assert result.passed
    assert result.review_status_path == tmp_path / "proof-suite-review-status.json"
    assert result.review_errors == ()


def test_validate_proof_suite_reports_missing_required_review_status(
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
        require_review=True,
    )

    assert not result.passed
    assert (
        f"proof review status not found: {tmp_path / 'proof-suite-review-status.json'}"
        in result.errors
    )


def test_validate_proof_suite_reports_failed_required_review_status(
    tmp_path: Path,
) -> None:
    _write_proof_bundle(
        tmp_path,
        proof_name="browser-fixture",
        trace_dir_name="browser-fixture",
        include_video=False,
    )
    review_path = tmp_path / "proof-suite-review.md"
    review_path.write_text(
        "\n".join(
            [
                "# DeskPilot Windows Proof Suite Review",
                "- Reviewer: Ada",
                "- Review date: 2026-05-16",
                "- [ ] Pass",
                "- [x] Fail",
                "- [x] The run happened on an owned, unlocked Windows desktop or VM.",
                "",
            ],
        ),
        encoding="utf-8",
    )
    write_proof_review_status(validate_proof_review(review_path))

    result = validate_proof_suite(
        tmp_path,
        require_video=False,
        require_review=True,
    )

    assert not result.passed
    assert "proof review status is not passed: failed" in result.errors
    assert "proof review decision is not pass: fail" in result.errors


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
    assert payload["review_status_path"] is None
    assert payload["missing_proofs"] == [
        "native-fixture",
        "mixed-fixture",
        "recovery-fixture",
    ]
    proofs = cast(list[dict[str, object]], payload["proofs"])
    assert proofs[0]["proof_name"] == "browser-fixture"
    assert proofs[0]["status"] == "passed"
    assert proofs[1]["status"] == "missing"


def test_write_proof_suite_promotion_records_final_gates(tmp_path: Path) -> None:
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
    _write_completed_review_status(tmp_path)
    result = validate_proof_suite(
        tmp_path,
        require_video=False,
        require_preflight=True,
        require_review=True,
    )

    payload = proof_suite_promotion_metadata(result, require_video=False)
    promotion_path = write_proof_suite_promotion(result, require_video=False)
    saved_payload = json.loads(promotion_path.read_text(encoding="utf-8"))

    assert result.passed
    assert promotion_path == tmp_path / "proof-suite-promotion.json"
    assert saved_payload == payload
    assert payload["status"] == "passed"
    assert payload["promotion_ready"] is True
    assert payload["gates"] == {
        "proof_bundles": "passed",
        "preflight": "passed",
        "human_review": "passed",
        "video": "external_or_disabled",
    }
    artifact_digests = cast(list[dict[str, object]], payload["artifact_digests"])
    archive_names = {str(item["archive_name"]) for item in artifact_digests}
    assert "proof-preflight.json" in archive_names
    assert "proof-suite-review-status.json" in archive_names
    assert "browser-fixture/proof-manifest.json" in archive_names
    assert "proof-suite-promotion.json" not in archive_names
    assert all(str(item["sha256"]) for item in artifact_digests)
    assert all(isinstance(item["size_bytes"], int) for item in artifact_digests)


def test_write_proof_suite_promotion_requires_preflight_and_review(
    tmp_path: Path,
) -> None:
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
    result = validate_proof_suite(tmp_path, require_video=False)

    payload = proof_suite_promotion_metadata(result, require_video=False)

    assert payload["status"] == "failed"
    assert payload["promotion_ready"] is False
    assert payload["gates"] == {
        "proof_bundles": "passed",
        "preflight": "missing",
        "human_review": "missing",
        "video": "external_or_disabled",
    }
    errors = cast(list[str], payload["errors"])
    assert (
        f"proof preflight report not found: {tmp_path / 'proof-preflight.json'}"
        in errors
    )
    assert (
        f"proof review status not found: {tmp_path / 'proof-suite-review-status.json'}"
        in errors
    )


def test_verify_proof_suite_promotion_accepts_matching_digests(
    tmp_path: Path,
) -> None:
    result = _write_review_ready_suite(tmp_path)
    promotion_path = write_proof_suite_promotion(result, require_video=False)

    verification = verify_proof_suite_promotion(promotion_path)

    assert verification.passed
    assert "proof-preflight.json" in verification.checked_artifacts
    assert "browser-fixture/proof-manifest.json" in verification.checked_artifacts


def test_verify_proof_suite_promotion_rejects_tampered_artifact(
    tmp_path: Path,
) -> None:
    result = _write_review_ready_suite(tmp_path)
    promotion_path = write_proof_suite_promotion(result, require_video=False)
    (tmp_path / "browser-fixture" / "action-log.jsonl").write_text(
        "tampered\n",
        encoding="utf-8",
    )

    verification = verify_proof_suite_promotion(promotion_path)

    assert not verification.passed
    assert any(
        "browser-fixture/action-log.jsonl sha256 mismatch" in error
        for error in verification.errors
    )


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
        f"{tmp_path} --allow-missing-video --require-preflight --require-review "
        "--write-report "
        "--write-status-json --write-runbook"
    ) in runbook


def test_write_proof_suite_review_template_lists_signoff_checks(
    tmp_path: Path,
) -> None:
    _write_proof_bundle(
        tmp_path,
        proof_name="browser-fixture",
        trace_dir_name="browser-fixture",
        include_video=False,
    )
    result = validate_proof_suite(tmp_path, require_video=False)

    review = render_proof_suite_review_template(result)
    review_path = write_proof_suite_review_template(result)

    assert review_path == tmp_path / "proof-suite-review.md"
    assert review_path.read_text(encoding="utf-8") == review
    assert "# DeskPilot Windows Proof Suite Review" in review
    assert "- [ ] Pass" in review
    assert "- [ ] Fail" in review
    assert "### browser-fixture" in review
    assert "- [ ] Video or justified external recording reviewed." in review
    assert "- [ ] missing proof bundle: native-fixture" in review


def test_validate_proof_review_accepts_completed_pass_review(tmp_path: Path) -> None:
    review_path = tmp_path / "proof-suite-review.md"
    review_path.write_text(
        "\n".join(
            [
                "# DeskPilot Windows Proof Suite Review",
                "- Reviewer: Ada",
                "- Review date: 2026-05-16",
                "- [x] Pass",
                "- [ ] Fail",
                "- [x] The run happened on an owned, unlocked Windows desktop or VM.",
                "- [x] Video or justified external recording reviewed.",
                "",
            ],
        ),
        encoding="utf-8",
    )

    result = validate_proof_review(review_path)
    status_path = write_proof_review_status(result)
    payload = json.loads(status_path.read_text(encoding="utf-8"))

    assert result.passed
    assert result.decision == "pass"
    assert result.checked_count == 2
    assert status_path == tmp_path / "proof-suite-review-status.json"
    assert payload["status"] == "passed"


def test_validate_proof_review_reports_incomplete_review(tmp_path: Path) -> None:
    review_path = tmp_path / "proof-suite-review.md"
    review_path.write_text(
        "\n".join(
            [
                "# DeskPilot Windows Proof Suite Review",
                "- Reviewer:",
                "- Review date:",
                "- [ ] Pass",
                "- [ ] Fail",
                "- [ ] The run happened on an owned, unlocked Windows desktop or VM.",
                "",
            ],
        ),
        encoding="utf-8",
    )

    result = validate_proof_review(review_path)

    assert not result.passed
    assert "proof review missing reviewer" in result.errors
    assert "proof review missing review date" in result.errors
    assert "proof review missing pass/fail decision" in result.errors
    assert "proof review has unchecked required items" in result.errors


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
    _write_completed_review_status(tmp_path)
    result = validate_proof_suite(tmp_path, require_video=False)
    write_proof_suite_promotion(result, require_video=False)

    archive_path = write_proof_suite_archive(result, require_video=False)

    assert archive_path == tmp_path / "proof-suite-artifacts.zip"
    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
    assert "proof-suite-report.md" in names
    assert "proof-suite-status.json" in names
    assert "proof-suite-next-actions.md" in names
    assert "proof-suite-review.md" in names
    assert "proof-preflight.json" in names
    assert "proof-suite-review-status.json" in names
    assert "proof-suite-promotion.json" in names
    assert "browser-fixture/proof-manifest.json" in names
    assert "browser-fixture/browser-fixture-report.json" in names
    assert "browser-fixture/action-log.jsonl" in names
    assert "browser-fixture/screenshots/shot-1.png" in names


def _write_completed_review_status(root: Path) -> Path:
    review_path = root / "proof-suite-review.md"
    review_path.write_text(
        "\n".join(
            [
                "# DeskPilot Windows Proof Suite Review",
                "- Reviewer: Ada",
                "- Review date: 2026-05-16",
                "- [x] Pass",
                "- [ ] Fail",
                "- [x] The run happened on an owned, unlocked Windows desktop or VM.",
                "- [x] Video or justified external recording reviewed.",
                "",
            ],
        ),
        encoding="utf-8",
    )
    return write_proof_review_status(validate_proof_review(review_path))


def _write_review_ready_suite(root: Path) -> ProofSuiteValidation:
    for proof_name in (
        "browser-fixture",
        "native-fixture",
        "mixed-fixture",
        "recovery-fixture",
    ):
        _write_proof_bundle(
            root,
            proof_name=proof_name,
            trace_dir_name=proof_name,
            include_video=False,
        )
    write_proof_preflight_report(
        run_proof_preflight(
            root,
            require_windows=False,
            require_video=False,
        ),
    )
    _write_completed_review_status(root)
    return validate_proof_suite(
        root,
        require_video=False,
        require_preflight=True,
        require_review=True,
    )


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
