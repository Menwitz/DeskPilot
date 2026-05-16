import json
from pathlib import Path
from typing import cast

from desktop_agent.proof_manifest import (
    render_proof_suite_report,
    validate_proof_bundle,
    validate_proof_suite,
    write_proof_suite_report,
)


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
