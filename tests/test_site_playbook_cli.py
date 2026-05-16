import json
from pathlib import Path

from pytest import CaptureFixture

from desktop_agent.cli import main
from desktop_agent.config import RuntimeConfig
from desktop_agent.content_variables import load_content_variables
from desktop_agent.site_playbooks import SiteTaskCompiler, load_site_playbook
from desktop_agent.task_dsl import BasicTaskValidator, YamlTaskLoader

SEED_SITES = {
    "facebook",
    "instagram",
    "linkedin",
    "medium",
    "tiktok",
    "x-twitter",
    "youtube",
}


def test_list_sites_prints_all_seed_sites(capsys: CaptureFixture[str]) -> None:
    status = main(["list-sites"])

    output = set(capsys.readouterr().out.splitlines())
    assert status == 0
    assert output == SEED_SITES


def test_list_flows_linkedin_prints_flows(capsys: CaptureFixture[str]) -> None:
    status = main(["list-flows", "linkedin"])

    output = capsys.readouterr().out
    assert status == 0
    assert "open-search" in output
    assert "Open LinkedIn search" in output


def test_compile_site_writes_valid_task_yaml(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    output_path = tmp_path / "youtube-open-search.yaml"

    status = main(
        [
            "compile-site",
            "youtube",
            "open-search",
            "--output",
            str(output_path),
        ],
    )

    task = YamlTaskLoader().load(output_path)
    BasicTaskValidator().validate(task, RuntimeConfig())
    output = capsys.readouterr().out
    assert status == 0
    assert "compiled: youtube open-search" in output
    assert task.metadata["site_id"] == "youtube"


def test_compile_site_resolves_content_variables(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    playbook_dir = tmp_path / "playbooks"
    playbook_dir.mkdir()
    (playbook_dir / "variable-site.yaml").write_text(
        _variable_playbook(),
        encoding="utf-8",
    )
    variables_path = tmp_path / "content.yaml"
    variables_path.write_text(
        "variables:\n  post_text: Hello team\n",
        encoding="utf-8",
    )
    output_path = tmp_path / "compiled.yaml"

    status = main(
        [
            "compile-site",
            "variable-site",
            "publish-post",
            "--playbook-dir",
            str(playbook_dir),
            "--variables",
            str(variables_path),
            "--output",
            str(output_path),
        ],
    )

    task = YamlTaskLoader().load(output_path)
    output = capsys.readouterr().out
    assert status == 0
    assert "compiled: variable-site publish-post" in output
    assert task.steps[0].text == "Hello team"
    assert task.metadata["content_variable_names"] == ["post_text"]


def test_compile_site_medium_publish_writes_checkpoint(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    output_path = tmp_path / "medium-publish.yaml"

    status = main(
        [
            "compile-site",
            "medium",
            "publish-story",
            "--variables",
            "examples/medium-content-variables.yaml",
            "--output",
            str(output_path),
        ],
    )

    task = YamlTaskLoader().load(output_path)
    publish_step = task.steps[-1]
    output = capsys.readouterr().out
    assert status == 0
    assert "compiled: medium publish-story" in output
    assert publish_step.id == "publish-story"
    assert publish_step.checkpoint is not None
    assert publish_step.checkpoint.text == (
        "Local-first automation for approved ops workflows"
    )


def test_dry_run_site_validates_without_desktop_input(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    config_path = _write_config(tmp_path)

    status = main(
        [
            "dry-run-site",
            "medium",
            "open-editor",
            "--config",
            str(config_path),
            "--no-screenshots",
        ],
    )

    output = capsys.readouterr().out
    assert status == 0
    assert "task: medium:open-editor" in output
    assert "status: passed" in output


def test_dry_run_site_linkedin_publish_records_manifest_and_variables(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    config_path = _write_config(tmp_path)
    variables_path = Path("examples/linkedin-content-variables.yaml")
    fingerprint = _compiled_fingerprint(
        Path("navigation_playbooks/linkedin.yaml"),
        "publish-post",
        variables_path,
    )
    manifest_path = _write_approval_manifest(
        tmp_path,
        site_id="linkedin",
        flow_id="publish-post",
        approved_step_id="publish-post",
        content_fingerprint=fingerprint,
    )

    status = main(
        [
            "dry-run-site",
            "linkedin",
            "publish-post",
            "--variables",
            str(variables_path),
            "--approval-manifest",
            str(manifest_path),
            "--config",
            str(config_path),
            "--no-screenshots",
        ],
    )

    report = json.loads((_single_trace_dir(tmp_path) / "final-report.json").read_text())
    output = capsys.readouterr().out
    assert status == 0
    assert "status: passed" in output
    assert report["metadata"]["site_approved_step_ids"] == ["publish-post"]
    assert report["metadata"]["content_variable_names"] == [
        "post_text",
        "post_url",
        "post_tags",
    ]
    assert report["metadata"]["content_variables_redacted"] is True


def test_dry_run_site_medium_publish_records_manifest_and_variables(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    config_path = _write_config(tmp_path)
    variables_path = Path("examples/medium-content-variables.yaml")
    fingerprint = _compiled_fingerprint(
        Path("navigation_playbooks/medium.yaml"),
        "publish-story",
        variables_path,
    )
    manifest_path = _write_approval_manifest(
        tmp_path,
        site_id="medium",
        flow_id="publish-story",
        approved_step_id="publish-story",
        content_fingerprint=fingerprint,
    )

    status = main(
        [
            "dry-run-site",
            "medium",
            "publish-story",
            "--variables",
            str(variables_path),
            "--approval-manifest",
            str(manifest_path),
            "--config",
            str(config_path),
            "--no-screenshots",
        ],
    )

    report = json.loads((_single_trace_dir(tmp_path) / "final-report.json").read_text())
    output = capsys.readouterr().out
    assert status == 0
    assert "status: passed" in output
    assert report["metadata"]["site_approved_step_ids"] == ["publish-story"]
    assert report["metadata"]["content_variable_names"] == [
        "article_title",
        "article_subtitle",
        "article_body",
        "canonical_url",
    ]
    assert report["metadata"]["content_variables_redacted"] is True


def test_dry_run_site_linkedin_publish_rejects_missing_variables(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    variables_path = tmp_path / "content.yaml"
    variables_path.write_text(
        "variables:\n  post_text: Missing URL and tags\n",
        encoding="utf-8",
    )

    status = main(
        [
            "dry-run-site",
            "linkedin",
            "publish-post",
            "--variables",
            str(variables_path),
        ],
    )

    output = capsys.readouterr().out
    assert status == 2
    assert "missing content variable" in output


def test_dry_run_site_accepts_runtime_safety_flags(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    config_path = _write_config(tmp_path)

    status = main(
        [
            "dry-run-site",
            "medium",
            "open-search",
            "--config",
            str(config_path),
            "--verbose",
            "--no-screenshots",
            "--max-runtime-seconds",
            "5",
            "--confidence-threshold",
            "0.75",
            "--allowed-window",
            "Medium",
            "--confirm-step",
            "open-search",
        ],
    )

    output = capsys.readouterr().out
    assert status == 0
    assert "status: passed" in output
    assert "event" in output


def test_run_site_returns_nonzero_when_platform_actuation_is_unavailable(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    playbook_dir = tmp_path / "playbooks"
    playbook_dir.mkdir()
    (playbook_dir / "keypress-site.yaml").write_text(
        _keypress_playbook(),
        encoding="utf-8",
    )
    config_path = _write_config(tmp_path)

    status = main(
        [
            "run-site",
            "keypress-site",
            "press-enter",
            "--playbook-dir",
            str(playbook_dir),
            "--config",
            str(config_path),
        ],
    )

    output = capsys.readouterr().out
    assert status == 1
    assert "desktop actuation is unavailable on this platform" in output


def test_run_site_linkedin_publish_requires_approval_manifest(
    capsys: CaptureFixture[str],
) -> None:
    status = main(
        [
            "run-site",
            "linkedin",
            "publish-post",
            "--variables",
            "examples/linkedin-content-variables.yaml",
        ],
    )

    output = capsys.readouterr().out
    assert status == 2
    assert "approval manifest is required" in output


def test_missing_confirmation_returns_clear_message(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    playbook_dir = tmp_path / "playbooks"
    playbook_dir.mkdir()
    (playbook_dir / "sensitive-site.yaml").write_text(
        _sensitive_playbook(),
        encoding="utf-8",
    )
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
        ],
    )

    output = capsys.readouterr().out
    assert status == 1
    assert "requires explicit confirmation" in output


def test_confirm_step_allows_sensitive_site_dry_run(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    playbook_dir = tmp_path / "playbooks"
    playbook_dir.mkdir()
    (playbook_dir / "sensitive-site.yaml").write_text(
        _sensitive_playbook(),
        encoding="utf-8",
    )
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
            "--confirm-step",
            "publish-post",
        ],
    )

    output = capsys.readouterr().out
    assert status == 0
    assert "status: passed" in output


def test_unknown_site_returns_clear_message(capsys: CaptureFixture[str]) -> None:
    status = main(["list-flows", "missing-site"])

    output = capsys.readouterr().out
    assert status == 2
    assert "unknown site: missing-site" in output


def test_unknown_flow_returns_clear_message(capsys: CaptureFixture[str]) -> None:
    status = main(["dry-run-site", "medium", "missing-flow"])

    output = capsys.readouterr().out
    assert status == 2
    assert "unknown flow: missing-flow" in output


def test_invalid_playbook_returns_validation_error(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    playbook_dir = tmp_path / "playbooks"
    playbook_dir.mkdir()
    (playbook_dir / "bad.yaml").write_text("site_id: Bad Site\n", encoding="utf-8")

    status = main(["list-sites", "--playbook-dir", str(playbook_dir)])

    output = capsys.readouterr().out
    assert status == 2
    assert "site_id is required and must be slug-safe" in output


def _write_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(f"trace_root: {tmp_path / 'traces'}\n", encoding="utf-8")
    return config_path


def _compiled_fingerprint(
    playbook_path: Path,
    flow_id: str,
    variables_path: Path,
) -> str:
    variables = load_content_variables(variables_path)
    playbook = load_site_playbook(playbook_path)
    task = SiteTaskCompiler(variables).compile(playbook, flow_id)
    fingerprint = task.metadata["content_variables_fingerprint"]
    assert isinstance(fingerprint, str)
    return fingerprint


def _write_approval_manifest(
    tmp_path: Path,
    *,
    site_id: str,
    flow_id: str,
    approved_step_id: str,
    content_fingerprint: str,
) -> Path:
    manifest_path = tmp_path / "approval.yaml"
    manifest_path.write_text(
        "\n".join(
            [
                f"site_id: {site_id}",
                f"flow_id: {flow_id}",
                "approved_steps:",
                f"  - {approved_step_id}",
                "approver: qa-lead@example.test",
                "reason: Approved publish flow for regression testing.",
                "approved_at: 2026-05-15T00:00:00Z",
                f"content_fingerprint: {content_fingerprint}",
                "",
            ],
        ),
        encoding="utf-8",
    )
    return manifest_path


def _single_trace_dir(tmp_path: Path) -> Path:
    trace_dirs = sorted((tmp_path / "traces").iterdir())
    assert len(trace_dirs) == 1
    return trace_dirs[0]


def _sensitive_playbook() -> str:
    return """site_id: sensitive-site
version: "1"
domains:
  - host: sensitive.example
allowed_window_titles:
  - Sensitive
landmarks:
  - id: publish
    action: click_text
    target: Publish
flows:
  - id: publish-post
    timeout_seconds: 30
    steps:
      - id: publish-post
        action: click_text
        landmark: publish
        requires_confirmation: true
        sensitive_category: publish
        checkpoint:
          type: visible_text
          text: Publish
blocked_states:
  - id: ambiguous-target
    detector: "candidate_count:>1"
    reason: Choose a narrower target before continuing.
"""


def _keypress_playbook() -> str:
    return """site_id: keypress-site
version: "1"
domains:
  - host: keypress.example
allowed_window_titles:
  - Keypress
landmarks: []
flows:
  - id: press-enter
    timeout_seconds: 30
    steps:
      - id: press-enter
        action: press_key
        text: enter
blocked_states:
  - id: ambiguous-target
    detector: "candidate_count:>1"
    reason: Choose a narrower target before continuing.
"""


def _variable_playbook() -> str:
    return """site_id: variable-site
version: "1"
domains:
  - host: variable.example
allowed_window_titles:
  - Variable
flows:
  - id: publish-post
    timeout_seconds: 30
    steps:
      - id: fill-post
        action: type_text
        text: "{{post_text}}"
      - id: publish-post
        action: press_key
        text: enter
        requires_confirmation: true
        sensitive_category: publish
        checkpoint:
          type: visible_text
          text: "{{post_text}}"
blocked_states:
  - id: ambiguous-target
    detector: "candidate_count:>1"
    reason: Choose a narrower target before continuing.
"""
