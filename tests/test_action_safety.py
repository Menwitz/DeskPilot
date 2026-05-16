import pytest

from desktop_agent.action_safety import (
    ACTION_SAFETY_CLASSES,
    action_safety_class_supported,
    action_safety_metadata,
)
from desktop_agent.task_dsl import TaskStep


@pytest.mark.parametrize(
    ("step", "expected_class"),
    [
        (TaskStep(id="read", action="assert_visible", target="Ready"), "read_only"),
        (TaskStep(id="type", action="type_text", text="Draft"), "local_mutation"),
        (
            TaskStep(id="submit", action="click_text", category="submission"),
            "external_mutation",
        ),
        (
            TaskStep(
                id="login",
                action="type_text",
                text="secret",
                metadata={"site_sensitive_category": "login"},
            ),
            "credential",
        ),
        (
            TaskStep(
                id="pay",
                action="click_text",
                metadata={"site_sensitive_category": "transaction"},
            ),
            "payment",
        ),
        (
            TaskStep(
                id="delete",
                action="click_text",
                metadata={"site_sensitive_category": "delete"},
            ),
            "delete",
        ),
        (
            TaskStep(
                id="publish",
                action="click_text",
                metadata={"site_sensitive_category": "publish"},
            ),
            "message_or_publish",
        ),
    ],
)
def test_action_safety_resolves_public_safety_classes(
    step: TaskStep,
    expected_class: str,
) -> None:
    metadata = action_safety_metadata(step)

    assert metadata["action_safety_class"] == expected_class
    assert action_safety_class_supported(expected_class) is True


def test_action_safety_class_contract_lists_expected_classes() -> None:
    assert {
        "read_only",
        "local_mutation",
        "external_mutation",
        "credential",
        "payment",
        "delete",
        "message_or_publish",
    } == ACTION_SAFETY_CLASSES
    assert action_safety_class_supported("unsupported") is False
