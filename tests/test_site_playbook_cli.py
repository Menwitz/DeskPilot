from pathlib import Path

from pytest import CaptureFixture

from desktop_agent.cli import main
from desktop_agent.config import RuntimeConfig
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
