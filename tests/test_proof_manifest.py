import json
from pathlib import Path
from typing import cast

from desktop_agent.proof_manifest import validate_proof_bundle


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


def _write_proof_bundle(
    root: Path,
    *,
    include_video: bool = True,
) -> Path:
    trace_dir = root / "trace"
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
    report_path = trace_dir / "browser-fixture-report.json"
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
        "proof_name": "browser-fixture",
        "command": ["desktop-agent", "proof", "browser-fixture"],
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
