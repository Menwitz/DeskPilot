import json
from pathlib import Path
from typing import cast

from pytest import CaptureFixture

from desktop_agent.cli import main


def test_final_report_includes_site_id_and_flow_id(tmp_path: Path) -> None:
    trace_dir = _run_seed_site_trace(tmp_path)

    report = _read_final_report(trace_dir)

    metadata = _metadata(report)
    assert metadata["site_id"] == "youtube"
    assert metadata["site_flow_id"] == "open-search"


def test_action_log_includes_selected_playbook_version(tmp_path: Path) -> None:
    trace_dir = _run_seed_site_trace(tmp_path)

    events = _read_action_log(trace_dir)
    load_task = next(event for event in events if event["phase"] == "load_task")

    assert _metadata(load_task)["site_playbook_version"] == "1"


def test_sensitive_blocked_step_appears_in_trace_metadata(tmp_path: Path) -> None:
    trace_dir = _run_sensitive_site_trace(tmp_path, "candidate_count:>1")

    events = _read_action_log(trace_dir)
    confirmation = next(event for event in events if event["phase"] == "confirmation")

    metadata = _metadata(confirmation)
    assert metadata["site_sensitive_category"] == "publish"
    assert metadata["sensitive_step_confirmation_state"] == "blocked"


def test_blocked_state_reason_appears_in_final_report(tmp_path: Path) -> None:
    trace_dir = _run_sensitive_site_trace(tmp_path, "visible_text:challenge")

    report = _read_final_report(trace_dir)

    step = _steps(report)[0]
    assert _metadata(step)["site_blocked_state_reason"] == (
        "CAPTCHA challenges are not automated."
    )
    assert "blocked state detected" in str(step["message"])


def test_replay_prints_site_and_flow_when_present(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    trace_dir = _run_seed_site_trace(tmp_path)

    status = main(["replay", str(trace_dir)])

    output = capsys.readouterr().out
    assert status == 0
    assert "site: youtube" in output
    assert "flow: open-search" in output


def _run_seed_site_trace(tmp_path: Path) -> Path:
    config_path = _write_config(tmp_path)
    status = main(
        [
            "dry-run-site",
            "youtube",
            "open-search",
            "--config",
            str(config_path),
            "--no-screenshots",
        ],
    )
    assert status == 0
    return _single_trace_dir(tmp_path)


def _run_sensitive_site_trace(tmp_path: Path, detector: str) -> Path:
    playbook_dir = tmp_path / "playbooks"
    playbook_dir.mkdir()
    (playbook_dir / "sensitive-site.yaml").write_text(
        _sensitive_playbook(detector),
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
            "--no-screenshots",
        ],
    )
    assert status == 1
    return _single_trace_dir(tmp_path)


def _write_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(f"trace_root: {tmp_path / 'traces'}\n", encoding="utf-8")
    return config_path


def _single_trace_dir(tmp_path: Path) -> Path:
    trace_dirs = sorted((tmp_path / "traces").iterdir())
    assert len(trace_dirs) == 1
    return trace_dirs[0]


def _read_final_report(trace_dir: Path) -> dict[str, object]:
    loaded = json.loads((trace_dir / "final-report.json").read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _read_action_log(trace_dir: Path) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    action_log = (trace_dir / "action-log.jsonl").read_text(encoding="utf-8")
    for line in action_log.splitlines():
        loaded = json.loads(line)
        assert isinstance(loaded, dict)
        events.append(loaded)
    return events


def _metadata(payload: dict[str, object]) -> dict[str, object]:
    return cast(dict[str, object], payload["metadata"])


def _steps(report: dict[str, object]) -> list[dict[str, object]]:
    return cast(list[dict[str, object]], report["steps"])


def _sensitive_playbook(detector: str) -> str:
    return f"""site_id: sensitive-site
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
        timeout_seconds: 0.1
        requires_confirmation: true
        sensitive_category: publish
blocked_states:
  - id: captcha
    detector: "{detector}"
    reason: CAPTCHA challenges are not automated.
"""
