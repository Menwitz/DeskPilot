import json
from dataclasses import replace
from pathlib import Path

from pytest import CaptureFixture, MonkeyPatch

from desktop_agent.actuation import ActuationProfile, DryRunActuator
from desktop_agent.approval_manifest import (
    ApprovalManifestError,
    apply_approval_manifest,
    load_approval_manifest,
)
from desktop_agent.cli import main
from desktop_agent.config import RuntimeConfig
from desktop_agent.safety import EmergencyStopMonitor
from desktop_agent.site_playbooks import SiteTaskCompiler, load_site_playbook
from desktop_agent.task_dsl import TaskDefinition


def test_approval_manifest_loads_required_fields(tmp_path: Path) -> None:
    manifest_path = _write_manifest(tmp_path, approved_steps=("publish-post",))

    manifest = load_approval_manifest(manifest_path)

    assert manifest.site_id == "sensitive-site"
    assert manifest.flow_id == "publish-post"
    assert manifest.approved_steps == ("publish-post",)
    assert manifest.approver == "qa-lead@example.test"
    assert manifest.reason == "Preapproved fixture publish flow for regression testing."
    assert manifest.approved_at == "2026-05-15T00:00:00+00:00"
    assert manifest.content_fingerprint == "fixture-content-v1"
    assert manifest.metadata()["site_approval_manifest_status"] == "validated"


def test_approval_manifest_rejects_invalid_approved_at(tmp_path: Path) -> None:
    manifest_path = _write_manifest(tmp_path, approved_steps=("publish-post",))
    manifest_path.write_text(
        manifest_path.read_text(encoding="utf-8").replace(
            "approved_at: 2026-05-15T00:00:00Z",
            "approved_at: not-a-timestamp",
        ),
        encoding="utf-8",
    )

    try:
        load_approval_manifest(manifest_path)
    except ApprovalManifestError as exc:
        assert "approved_at must be an ISO timestamp" in str(exc)
    else:
        raise AssertionError("approval manifest should reject invalid timestamps")


def test_approval_manifest_rejects_unknown_approved_step(tmp_path: Path) -> None:
    task = _compiled_sensitive_task(tmp_path)
    manifest_path = _write_manifest(tmp_path, approved_steps=("missing-step",))

    try:
        apply_approval_manifest(task, RuntimeConfig(), manifest_path)
    except ApprovalManifestError as exc:
        assert "approved unknown step" in str(exc)
    else:
        raise AssertionError("approval manifest should reject unknown steps")


def test_approval_manifest_rejects_site_scope_mismatch(tmp_path: Path) -> None:
    task = _compiled_sensitive_task(tmp_path)
    manifest_path = _write_manifest(
        tmp_path,
        approved_steps=("publish-post",),
        site_id="wrong-site",
    )

    try:
        apply_approval_manifest(task, RuntimeConfig(), manifest_path)
    except ApprovalManifestError as exc:
        assert "site_id mismatch" in str(exc)
    else:
        raise AssertionError("approval manifest should reject wrong site")


def test_approval_manifest_rejects_flow_scope_mismatch(tmp_path: Path) -> None:
    task = _compiled_sensitive_task(tmp_path)
    manifest_path = _write_manifest(
        tmp_path,
        approved_steps=("publish-post",),
        flow_id="wrong-flow",
    )

    try:
        apply_approval_manifest(task, RuntimeConfig(), manifest_path)
    except ApprovalManifestError as exc:
        assert "flow_id mismatch" in str(exc)
    else:
        raise AssertionError("approval manifest should reject wrong flow")


def test_approval_manifest_rejects_missing_sensitive_step(tmp_path: Path) -> None:
    task = _compiled_sensitive_task(tmp_path)
    manifest_path = _write_manifest(tmp_path, approved_steps=("open-preview",))

    try:
        apply_approval_manifest(task, RuntimeConfig(), manifest_path)
    except ApprovalManifestError as exc:
        assert "missing sensitive step" in str(exc)
    else:
        raise AssertionError("approval manifest should require sensitive approval")


def test_approval_manifest_rejects_content_fingerprint_mismatch(
    tmp_path: Path,
) -> None:
    task = _compiled_sensitive_task(tmp_path)
    task = replace(
        task,
        metadata={
            **task.metadata,
            "content_variables_fingerprint": "sha256:expected",
        },
    )
    manifest_path = _write_manifest(tmp_path, approved_steps=("publish-post",))

    try:
        apply_approval_manifest(task, RuntimeConfig(), manifest_path)
    except ApprovalManifestError as exc:
        assert "content_fingerprint mismatch" in str(exc)
    else:
        raise AssertionError("approval manifest should reject stale content")


def test_run_site_requires_manifest_for_sensitive_real_run(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    playbook_dir = _write_playbook_dir(tmp_path)

    status = main(
        [
            "run-site",
            "sensitive-site",
            "publish-post",
            "--playbook-dir",
            str(playbook_dir),
        ],
    )

    output = capsys.readouterr().out
    assert status == 2
    assert "approval manifest is required" in output


def test_run_site_uses_manifest_without_operator_prompt(
    tmp_path: Path,
    capsys: CaptureFixture[str],
    monkeypatch: MonkeyPatch,
) -> None:
    playbook_dir = _write_playbook_dir(tmp_path)
    manifest_path = _write_manifest(tmp_path, approved_steps=("publish-post",))
    config_path = _write_config(tmp_path)
    monkeypatch.setattr("builtins.input", lambda _prompt: "no")
    monkeypatch.setattr("desktop_agent.cli.create_platform_actuator", _dry_actuator)

    status = main(
        [
            "run-site",
            "sensitive-site",
            "publish-post",
            "--playbook-dir",
            str(playbook_dir),
            "--config",
            str(config_path),
            "--approval-manifest",
            str(manifest_path),
        ],
    )

    output = capsys.readouterr().out
    assert status == 0
    assert "step publish-post: passed" in output


def test_dry_run_site_records_manifest_metadata_in_report(
    tmp_path: Path,
) -> None:
    playbook_dir = _write_playbook_dir(tmp_path)
    manifest_path = _write_manifest(tmp_path, approved_steps=("publish-post",))
    config_path = _write_config(tmp_path)

    status = main(
        [
            "dry-run-site",
            "sensitive-site",
            "publish-post",
            "--playbook-dir",
            str(playbook_dir),
            "--config",
            str(config_path),
            "--approval-manifest",
            str(manifest_path),
            "--no-screenshots",
        ],
    )

    trace_dir = _single_trace_dir(tmp_path)
    report_path = trace_dir / "final-report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    action_log_text = (trace_dir / "action-log.jsonl").read_text(encoding="utf-8")
    action_log = [
        json.loads(line)
        for line in action_log_text.splitlines()
    ]
    load_task_event = next(
        event for event in action_log if event["phase"] == "load_task"
    )
    metadata = report["metadata"]
    assert status == 0
    for payload in (metadata, load_task_event["metadata"]):
        assert payload["site_approval_manifest_status"] == "validated"
        assert payload["site_approved_step_ids"] == ["publish-post"]
        assert payload["site_approval_approver"] == "qa-lead@example.test"
        assert (
            payload["site_approval_reason"]
            == "Preapproved fixture publish flow for regression testing."
        )
        assert payload["site_approval_approved_at"] == "2026-05-15T00:00:00+00:00"
        assert payload["content_variables_fingerprint"] == "fixture-content-v1"


def _dry_actuator(
    profile: ActuationProfile | None = None,
    emergency_stop_monitor: EmergencyStopMonitor | None = None,
) -> DryRunActuator:
    _ = profile, emergency_stop_monitor
    return DryRunActuator()


def _compiled_sensitive_task(tmp_path: Path) -> TaskDefinition:
    playbook_dir = _write_playbook_dir(tmp_path)
    playbook = load_site_playbook(playbook_dir / "sensitive-site.yaml")
    return SiteTaskCompiler().compile(playbook, "publish-post")


def _write_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(f"trace_root: {tmp_path / 'traces'}\n", encoding="utf-8")
    return config_path


def _write_manifest(
    tmp_path: Path,
    *,
    approved_steps: tuple[str, ...],
    site_id: str = "sensitive-site",
    flow_id: str = "publish-post",
    content_fingerprint: str = "fixture-content-v1",
) -> Path:
    manifest_path = tmp_path / "approval.yaml"
    approved_step_lines = "\n".join(f"  - {step}" for step in approved_steps)
    manifest_path.write_text(
        "\n".join(
            [
                f"site_id: {site_id}",
                f"flow_id: {flow_id}",
                "approved_steps:",
                approved_step_lines,
                "approver: qa-lead@example.test",
                "reason: Preapproved fixture publish flow for regression testing.",
                "approved_at: 2026-05-15T00:00:00Z",
                f"content_fingerprint: {content_fingerprint}",
                "",
            ],
        ),
        encoding="utf-8",
    )
    return manifest_path


def _write_playbook_dir(tmp_path: Path) -> Path:
    playbook_dir = tmp_path / "playbooks"
    playbook_dir.mkdir(exist_ok=True)
    (playbook_dir / "sensitive-site.yaml").write_text(
        """site_id: sensitive-site
version: "1"
domains:
  - host: sensitive.example
allowed_window_titles:
  - Sensitive
landmarks: []
flows:
  - id: publish-post
    timeout_seconds: 30
    steps:
      - id: open-preview
        action: press_key
        text: tab
      - id: publish-post
        action: press_key
        text: enter
        requires_confirmation: true
        sensitive_category: publish
blocked_states:
  - id: captcha
    detector: "candidate_count:>1"
    reason: CAPTCHA challenges are not automated.
""",
        encoding="utf-8",
    )
    return playbook_dir


def _single_trace_dir(tmp_path: Path) -> Path:
    trace_dirs = sorted((tmp_path / "traces").iterdir())
    assert len(trace_dirs) == 1
    return trace_dirs[0]
