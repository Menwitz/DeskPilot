from pathlib import Path

import pytest

from desktop_agent.site_playbooks import (
    SitePlaybookValidationError,
    load_site_playbook,
)


def test_valid_playbook_loads_successfully(tmp_path: Path) -> None:
    playbook_path = _write_playbook(tmp_path, _valid_playbook())

    playbook = load_site_playbook(playbook_path)

    assert playbook.site_id == "example-site"
    assert playbook.flows[0].id == "open-search"


def test_missing_site_id_is_rejected(tmp_path: Path) -> None:
    playbook_path = _write_playbook(
        tmp_path,
        _valid_playbook().replace("site_id: example-site", "site_id: ''"),
    )

    with pytest.raises(SitePlaybookValidationError, match="site_id"):
        load_site_playbook(playbook_path)


def test_invalid_site_id_is_rejected(tmp_path: Path) -> None:
    playbook_path = _write_playbook(
        tmp_path,
        _valid_playbook().replace("site_id: example-site", "site_id: Example Site"),
    )

    with pytest.raises(SitePlaybookValidationError, match="slug-safe"):
        load_site_playbook(playbook_path)


def test_empty_domains_are_rejected(tmp_path: Path) -> None:
    playbook_path = _write_playbook(
        tmp_path,
        _valid_playbook().replace(
            "domains:\n  - host: example.com\n    include_subdomains: true",
            "domains: []",
        ),
    )

    with pytest.raises(SitePlaybookValidationError, match="domain"):
        load_site_playbook(playbook_path)


def test_empty_window_title_patterns_are_rejected(tmp_path: Path) -> None:
    playbook_path = _write_playbook(
        tmp_path,
        _valid_playbook().replace(
            "allowed_window_titles:\n  - Example",
            "allowed_window_titles: []",
        ),
    )

    with pytest.raises(SitePlaybookValidationError, match="window-title"):
        load_site_playbook(playbook_path)


def test_duplicate_flow_ids_are_rejected(tmp_path: Path) -> None:
    playbook_path = _write_playbook(
        tmp_path,
        _valid_playbook().replace(
            "blocked_states:",
            """  - id: open-search
    steps:
      - id: second-step
        action: click_text
        landmark: search
blocked_states:""",
        ),
    )

    with pytest.raises(SitePlaybookValidationError, match="duplicate flow id"):
        load_site_playbook(playbook_path)


def test_duplicate_flow_step_ids_are_rejected(tmp_path: Path) -> None:
    original_step = """      - id: open-search
        action: click_text
        landmark: search"""
    duplicate_steps = """      - id: open-search
        action: click_text
        landmark: search
      - id: open-search
        action: click_text
        landmark: search"""
    playbook_path = _write_playbook(
        tmp_path,
        _valid_playbook().replace(original_step, duplicate_steps),
    )

    with pytest.raises(SitePlaybookValidationError, match="duplicate step id"):
        load_site_playbook(playbook_path)


def test_unknown_step_action_is_rejected(tmp_path: Path) -> None:
    playbook_path = _write_playbook(
        tmp_path,
        _valid_playbook().replace("action: click_text", "action: teleport", 1),
    )

    with pytest.raises(SitePlaybookValidationError, match="unknown action"):
        load_site_playbook(playbook_path)


def test_missing_landmark_reference_is_rejected(tmp_path: Path) -> None:
    playbook_path = _write_playbook(
        tmp_path,
        _valid_playbook().replace("landmark: search", "landmark: missing"),
    )

    with pytest.raises(SitePlaybookValidationError, match="landmark does not exist"):
        load_site_playbook(playbook_path)


def test_sensitive_step_without_confirmation_is_rejected(tmp_path: Path) -> None:
    playbook_path = _write_playbook(
        tmp_path,
        _valid_playbook().replace(
            "landmark: search",
            "landmark: search\n        sensitive_category: publish",
        ),
    )

    with pytest.raises(SitePlaybookValidationError, match="require confirmation"):
        load_site_playbook(playbook_path)


def test_blocked_state_without_reason_is_rejected(tmp_path: Path) -> None:
    playbook_path = _write_playbook(
        tmp_path,
        _valid_playbook().replace(
            "    reason: Sign in manually before running this flow.",
            "    reason: ''",
        ),
    )

    with pytest.raises(SitePlaybookValidationError, match="reason is required"):
        load_site_playbook(playbook_path)


def _write_playbook(tmp_path: Path, content: str) -> Path:
    playbook_path = tmp_path / "example-site.yaml"
    playbook_path.write_text(content, encoding="utf-8")
    return playbook_path


def _valid_playbook() -> str:
    return """site_id: example-site
version: "1"
domains:
  - host: example.com
    include_subdomains: true
allowed_window_titles:
  - Example
landmarks:
  - id: search
    action: click_text
    target: Search
flows:
  - id: open-search
    timeout_seconds: 30
    retry: 1
    steps:
      - id: open-search
        action: click_text
        landmark: search
blocked_states:
  - id: logged-out
    detector: "visible_text:Sign in"
    reason: Sign in manually before running this flow.
"""
