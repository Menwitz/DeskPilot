from pathlib import Path

import pytest

from desktop_agent.config import RuntimeConfig
from desktop_agent.content_variables import ContentVariableError, ContentVariables
from desktop_agent.redaction import RedactionPolicy
from desktop_agent.site_playbooks import (
    SitePlaybookValidationError,
    SiteTaskCompiler,
    load_site_playbook,
    load_site_playbooks,
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


@pytest.mark.parametrize(
    ("action", "step_body", "flow_body", "extra_steps", "expected"),
    [
        ("click_text", "        target: Search\n", "", "", {"target": "Search"}),
        (
            "click_image",
            "        image: button.png\n",
            "",
            "",
            {"image": Path("button.png")},
        ),
        ("click_uia", "        target: SearchBox\n", "", "", {"target": "SearchBox"}),
        (
            "type_text",
            "        text: example query\n",
            "",
            "",
            {"text": "example query"},
        ),
        ("press_key", "        text: Enter\n", "", "", {"text": "Enter"}),
        ("scroll", "", "", "", {}),
        (
            "scroll_until",
            "",
            """    search_region:
      x: 10
      y: 20
      width: 200
      height: 100
""",
            "",
            {},
        ),
        ("wait_for", "        target: Results\n", "", "", {"target": "Results"}),
        ("assert_visible", "        target: Results\n", "", "", {"target": "Results"}),
        (
            "branch_if_visible",
            """        target: Empty state
        on_failure: fallback
""",
            "",
            """      - id: fallback
        action: wait_for
        target: Results
""",
            {"target": "Empty state", "on_failure": "fallback"},
        ),
    ],
)
def test_site_steps_compile_supported_task_actions(
    tmp_path: Path,
    action: str,
    step_body: str,
    flow_body: str,
    extra_steps: str,
    expected: dict[str, object],
) -> None:
    playbook = load_site_playbook(
        _write_playbook(
            tmp_path,
            _action_playbook(action, step_body, flow_body, extra_steps),
        ),
    )

    task = SiteTaskCompiler().compile(playbook, "action-flow")

    BasicTaskValidator().validate(task, RuntimeConfig())
    compiled_step = task.steps[0]
    assert compiled_step.id == "action-step"
    assert compiled_step.action == action
    for field_name, expected_value in expected.items():
        assert getattr(compiled_step, field_name) == expected_value
    if action == "scroll_until":
        assert compiled_step.region is not None
        assert compiled_step.region.width == 200


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


def test_flow_confidence_threshold_compiles_to_config_override(
    tmp_path: Path,
) -> None:
    playbook = load_site_playbook(
        _write_playbook(
            tmp_path,
            _valid_playbook().replace(
                "retry: 1\n    steps:",
                "retry: 1\n    confidence_threshold: 0.84\n    steps:",
            ),
        ),
    )

    task = SiteTaskCompiler().compile(playbook, "open-search")

    assert task.config_overrides.confidence_threshold == 0.84


def test_compiled_task_metadata_includes_site_domains(tmp_path: Path) -> None:
    playbook = load_site_playbook(_write_playbook(tmp_path, _valid_playbook()))

    task = SiteTaskCompiler().compile(playbook, "open-search")

    assert task.metadata["site_domains"] == ["example.com"]


def test_compiled_task_metadata_includes_sensitive_step_ids(
    tmp_path: Path,
) -> None:
    playbook = load_site_playbook(
        _write_playbook(tmp_path, _sensitive_playbook("publish")),
    )

    task = SiteTaskCompiler().compile(playbook, "publish-post")

    assert task.metadata["site_sensitive_step_ids"] == ["publish-post"]


def test_site_flow_resolves_content_variables_and_records_fingerprint(
    tmp_path: Path,
) -> None:
    playbook = load_site_playbook(
        _write_playbook(tmp_path, _variable_playbook()),
    )
    variables = ContentVariables(
        {
            "post_text": "DeskPilot launch note",
            "post_url": "https://example.test/launch",
        },
        source_path=tmp_path / "content.yaml",
    )

    task = SiteTaskCompiler(variables).compile(playbook, "publish-post")

    assert task.steps[0].text == "DeskPilot launch note https://example.test/launch"
    assert task.steps[0].metadata["content_variable_names"] == [
        "post_text",
        "post_url",
    ]
    assert task.metadata["content_variable_names"] == ["post_text", "post_url"]
    assert task.metadata["content_variable_name_redaction"] == "fingerprint_only"
    assert str(task.metadata["content_variables_fingerprint"]).startswith("sha256:")
    assert task.metadata["content_variables_redacted"] is True


def test_site_compiler_masks_content_variable_names_when_configured(
    tmp_path: Path,
) -> None:
    playbook = load_site_playbook(
        _write_playbook(tmp_path, _variable_playbook()),
    )
    variables = ContentVariables(
        {
            "post_text": "DeskPilot launch note",
            "post_url": "https://example.test/launch",
        },
    )

    task = SiteTaskCompiler(
        variables,
        RedactionPolicy(content_variables="mask_names"),
    ).compile(playbook, "publish-post")

    assert task.steps[0].metadata["content_variable_names"] == [
        "variable_1",
        "variable_2",
    ]
    assert task.metadata["content_variable_names"] == ["variable_1", "variable_2"]
    assert task.metadata["content_variable_count"] == 2
    assert task.metadata["content_variable_name_redaction"] == "mask_names"


def test_site_flow_rejects_missing_content_variables(tmp_path: Path) -> None:
    playbook = load_site_playbook(
        _write_playbook(tmp_path, _variable_playbook()),
    )

    with pytest.raises(ContentVariableError, match="post_url"):
        SiteTaskCompiler(ContentVariables({"post_text": "DeskPilot"})).compile(
            playbook,
            "publish-post",
        )


def test_site_flow_resolves_checkpoint_content_variables(tmp_path: Path) -> None:
    playbook = load_site_playbook(
        _write_playbook(tmp_path, _checkpoint_variable_playbook()),
    )

    task = SiteTaskCompiler(
        ContentVariables({"post_text": "Reviewed launch note"}),
    ).compile(playbook, "publish-post")

    publish_step = task.steps[-1]
    assert publish_step.checkpoint is not None
    assert publish_step.checkpoint.text == "Reviewed launch note"
    assert publish_step.metadata["content_variable_names"] == ["post_text"]


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


def test_all_seed_playbooks_validate() -> None:
    playbooks = load_site_playbooks()

    assert {playbook.site_id for playbook in playbooks} == {
        "facebook",
        "instagram",
        "linkedin",
        "medium",
        "tiktok",
        "x-twitter",
        "youtube",
    }


def test_every_seed_playbook_has_read_only_navigation_flow() -> None:
    for playbook in load_site_playbooks():
        read_only_flows = [
            flow
            for flow in playbook.flows
            if all(
                not step.requires_confirmation and step.sensitive_category is None
                for step in flow.steps
            )
        ]
        assert read_only_flows, playbook.site_id


def test_seed_sensitive_actions_require_confirmation() -> None:
    for playbook in load_site_playbooks():
        for flow in playbook.flows:
            for step in flow.steps:
                if step.sensitive_category is not None:
                    assert step.requires_confirmation is True


def test_only_linkedin_and_medium_seed_playbooks_have_publish_flows() -> None:
    publish_sites = {
        playbook.site_id
        for playbook in load_site_playbooks()
        for flow in playbook.flows
        if any(
            step.sensitive_category == "publish" for step in flow.steps
        )
    }

    assert publish_sites == {"linkedin", "medium"}


def test_seed_linkedin_publish_flow_uses_variables_and_checkpoint() -> None:
    playbook = load_site_playbook(Path("navigation_playbooks/linkedin.yaml"))

    task = SiteTaskCompiler(_seed_content_variables()).compile(
        playbook,
        "publish-post",
    )

    fill_step = next(step for step in task.steps if step.id == "fill-post")
    publish_step = task.steps[-1]
    assert "DeskPilot launch note" in (fill_step.text or "")
    assert "https://example.test/launch" in (fill_step.text or "")
    assert publish_step.id == "publish-post"
    assert publish_step.requires_confirmation is True
    assert publish_step.checkpoint is not None
    assert publish_step.checkpoint.text == "DeskPilot launch note"
    blocked_checks = {step.id for step in task.steps if step.id.startswith("blocked-")}
    assert blocked_checks == {
        f"blocked-state-{state.id}-before-publish-post"
        for state in playbook.blocked_states
        if state.detector.startswith("visible_text:")
    }
    assert task.metadata["content_variables_redacted"] is True


def test_seed_medium_publish_flow_uses_variables_and_checkpoint() -> None:
    playbook = load_site_playbook(Path("navigation_playbooks/medium.yaml"))

    task = SiteTaskCompiler(_seed_content_variables()).compile(
        playbook,
        "publish-story",
    )

    title_step = next(step for step in task.steps if step.id == "type-title")
    body_step = next(step for step in task.steps if step.id == "type-body")
    publish_step = task.steps[-1]
    assert title_step.text == "Medium launch note"
    assert "Reviewed Medium article body" in (body_step.text or "")
    assert publish_step.id == "publish-story"
    assert publish_step.requires_confirmation is True
    assert publish_step.checkpoint is not None
    assert publish_step.checkpoint.text == "Medium launch note"
    blocked_checks = {step.id for step in task.steps if step.id.startswith("blocked-")}
    assert blocked_checks == {
        f"blocked-state-{state.id}-before-publish-story"
        for state in playbook.blocked_states
        if state.detector.startswith("visible_text:")
    }
    assert task.metadata["content_variables_redacted"] is True


def test_all_seed_flows_compile_and_validate() -> None:
    compiler = SiteTaskCompiler(_seed_content_variables())
    validator = BasicTaskValidator()

    for playbook in load_site_playbooks():
        for flow in playbook.flows:
            task = compiler.compile(playbook, flow.id)
            validator.validate(task, RuntimeConfig())


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


def _variable_playbook() -> str:
    return """site_id: example-site
version: "1"
domains:
  - host: example.com
allowed_window_titles:
  - Example
flows:
  - id: publish-post
    timeout_seconds: 30
    steps:
      - id: fill-post
        action: type_text
        text: "{{post_text}} {{post_url}}"
      - id: publish-post
        action: press_key
        text: enter
        requires_confirmation: true
        sensitive_category: publish
blocked_states:
  - id: logged-out
    detector: "visible_text:Sign in"
    reason: Sign in manually before running this flow.
"""


def _checkpoint_variable_playbook() -> str:
    return """site_id: example-site
version: "1"
domains:
  - host: example.com
allowed_window_titles:
  - Example
flows:
  - id: publish-post
    timeout_seconds: 30
    steps:
      - id: publish-post
        action: press_key
        text: enter
        requires_confirmation: true
        sensitive_category: publish
        checkpoint:
          type: visible_text
          text: "{{post_text}}"
blocked_states:
  - id: logged-out
    detector: "visible_text:Sign in"
    reason: Sign in manually before running this flow.
"""


def _seed_content_variables() -> ContentVariables:
    return ContentVariables(
        {
            "post_text": "DeskPilot launch note",
            "post_url": "https://example.test/launch",
            "post_tags": "#ops #automation",
            "article_title": "Medium launch note",
            "article_subtitle": "Approved ops update",
            "article_body": "Reviewed Medium article body",
            "canonical_url": "https://example.test/medium",
        },
    )


def _action_playbook(
    action: str,
    step_body: str,
    flow_body: str,
    extra_steps: str,
) -> str:
    return f"""site_id: example-site
version: "1"
domains:
  - host: example.com
    include_subdomains: true
allowed_window_titles:
  - Example
flows:
  - id: action-flow
    timeout_seconds: 30
    retry: 1
{flow_body}    steps:
      - id: action-step
        action: {action}
{step_body}{extra_steps}blocked_states:
  - id: logged-out
    detector: "visible_text:Sign in"
    reason: Sign in manually before running this flow.
"""
