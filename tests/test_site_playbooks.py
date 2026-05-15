from pathlib import Path

import pytest

from desktop_agent.config import RuntimeConfig
from desktop_agent.site_playbooks import (
    SitePlaybookValidationError,
    SiteTaskCompiler,
    load_site_playbook,
)
from desktop_agent.task_dsl import BasicTaskValidator, TaskDefinition


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


def test_basic_navigation_flow_compiles_to_task_definition(tmp_path: Path) -> None:
    playbook = load_site_playbook(_write_playbook(tmp_path, _valid_playbook()))

    task = SiteTaskCompiler().compile(playbook, "open-search")

    assert isinstance(task, TaskDefinition)
    assert task.name == "example-site:open-search"


def test_compiled_task_passes_basic_task_validator(tmp_path: Path) -> None:
    playbook = load_site_playbook(_write_playbook(tmp_path, _valid_playbook()))
    task = SiteTaskCompiler().compile(playbook, "open-search")

    BasicTaskValidator().validate(task, RuntimeConfig())


def test_domain_and_title_rules_compile_to_allowed_windows(tmp_path: Path) -> None:
    playbook = load_site_playbook(_write_playbook(tmp_path, _valid_playbook()))
    task = SiteTaskCompiler().compile(playbook, "open-search")

    assert task.allowed_windows == ("Example", "example.com")


def test_flow_timeout_compiles_to_task_timeout(tmp_path: Path) -> None:
    playbook = load_site_playbook(
        _write_playbook(
            tmp_path,
            _valid_playbook().replace("timeout_seconds: 30", "timeout_seconds: 45"),
        ),
    )

    task = SiteTaskCompiler().compile(playbook, "open-search")

    assert task.timeout_seconds == 45


def test_flow_retry_defaults_compile_to_steps(tmp_path: Path) -> None:
    playbook = load_site_playbook(
        _write_playbook(
            tmp_path,
            _valid_playbook().replace("retry: 1", "retry: 3"),
        ),
    )

    task = SiteTaskCompiler().compile(playbook, "open-search")

    assert task.steps[0].retry == 3


def test_sensitive_steps_preserve_confirmation(tmp_path: Path) -> None:
    playbook = load_site_playbook(
        _write_playbook(tmp_path, _sensitive_playbook("publish")),
    )

    task = SiteTaskCompiler().compile(playbook, "publish-post")

    assert task.steps[-1].id == "publish-post"
    assert task.steps[-1].requires_confirmation is True
    assert task.steps[-1].category == "submission"


def test_blocked_state_checks_compile_before_sensitive_final_actions(
    tmp_path: Path,
) -> None:
    playbook = load_site_playbook(
        _write_playbook(tmp_path, _sensitive_playbook("publish")),
    )

    task = SiteTaskCompiler().compile(playbook, "publish-post")

    assert task.steps[0].id == "blocked-state-logged-out-before-publish-post"
    assert task.steps[0].metadata["site_blocked_state_check"] is True
    assert task.steps[-1].id == "publish-post"


def test_unknown_site_flow_fails_before_task_execution(tmp_path: Path) -> None:
    playbook = load_site_playbook(_write_playbook(tmp_path, _valid_playbook()))

    with pytest.raises(SitePlaybookValidationError, match="unknown flow"):
        SiteTaskCompiler().compile(playbook, "missing-flow")


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


def _sensitive_playbook(category: str) -> str:
    return _valid_playbook().replace(
        """  - id: open-search
    timeout_seconds: 30
    retry: 1
    steps:
      - id: open-search
        action: click_text
        landmark: search""",
        f"""  - id: publish-post
    timeout_seconds: 30
    retry: 1
    confidence_threshold: 0.9
    steps:
      - id: publish-post
        action: click_text
        landmark: search
        requires_confirmation: true
        sensitive_category: {category}""",
    )
