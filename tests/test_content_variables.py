from pathlib import Path

import pytest

from desktop_agent.content_variables import (
    ContentVariableError,
    ContentVariables,
    load_content_variables,
)


def test_content_variables_load_from_variables_mapping(tmp_path: Path) -> None:
    variables_path = tmp_path / "content.yaml"
    variables_path.write_text(
        "\n".join(
            [
                "variables:",
                "  post_text: Hello from ops",
                "  tags:",
                "    - '#launch'",
                "    - '#ops'",
                "  urgent: true",
                "",
            ],
        ),
        encoding="utf-8",
    )

    variables = load_content_variables(variables_path)

    assert variables.values["post_text"] == "Hello from ops"
    assert variables.values["tags"] == "#launch #ops"
    assert variables.values["urgent"] == "true"


def test_content_variables_resolve_templates_and_fingerprint() -> None:
    variables = ContentVariables({"post_text": "Hello", "post_url": "https://e.test"})

    resolved = variables.resolve("{{post_text}} {{ post_url }}")

    assert resolved.value == "Hello https://e.test"
    assert resolved.variable_names == ("post_text", "post_url")
    assert variables.fingerprint(resolved.variable_names).startswith("sha256:")


def test_content_variables_reject_missing_values() -> None:
    variables = ContentVariables({"post_text": "Hello"})

    with pytest.raises(ContentVariableError, match="missing content variable"):
        variables.resolve("{{post_text}} {{missing_url}}")


def test_content_variables_reject_nested_values(tmp_path: Path) -> None:
    variables_path = tmp_path / "content.yaml"
    variables_path.write_text(
        "variables:\n  post_text:\n    nested: value\n",
        encoding="utf-8",
    )

    with pytest.raises(ContentVariableError, match="values must be"):
        load_content_variables(variables_path)
