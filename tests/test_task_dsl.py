from pathlib import Path

import pytest

from desktop_agent.config import RuntimeConfig
from desktop_agent.task_dsl import (
    BasicTaskValidator,
    ExpectedStateTransition,
    TaskStep,
    TaskValidationError,
    YamlTaskLoader,
    step_category,
)


def validate_task(path: Path) -> None:
    task = YamlTaskLoader().load(path)
    BasicTaskValidator().validate(task, RuntimeConfig())


def test_task_dsl_accepts_complete_task_with_region_and_verification(
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "submit.png"
    image_path.write_bytes(b"fixture")
    task_path = tmp_path / "task.yaml"
    task_path.write_text(
        "\n".join(
            [
                "name: complete-fixture",
                "allowed_windows:",
                "  - DeskPilot Fixture",
                "timeout_seconds: 30",
                "entropy_budget: 2.5",
                "steps:",
                "  - id: click-submit-image",
                "    action: click_image",
                "    category: submission",
                "    entropy_budget: 1.0",
                "    image: submit.png",
                "    region:",
                "      x: 0",
                "      y: 0",
                "      width: 640",
                "      height: 480",
                "    verify:",
                "      type: visible_text",
                "      text: Success",
                "    requires_confirmation: true",
                "",
            ],
        ),
        encoding="utf-8",
    )

    task = YamlTaskLoader().load(task_path)
    BasicTaskValidator().validate(task, RuntimeConfig())

    assert task.steps[0].image == image_path
    assert task.entropy_budget == 2.5
    assert task.steps[0].region is not None
    assert task.steps[0].verify is not None
    assert task.steps[0].verify.text == "Success"
    assert task.steps[0].requires_confirmation is True
    assert task.steps[0].category == "submission"
    assert task.steps[0].entropy_budget == 1.0


def test_task_dsl_loads_dependencies_and_expected_state(tmp_path: Path) -> None:
    task_path = tmp_path / "task.yaml"
    task_path.write_text(
        "\n".join(
            [
                "name: stateful-task",
                "allowed_windows:",
                "  - DeskPilot Fixture",
                "timeout_seconds: 30",
                "steps:",
                "  - id: open-editor",
                "    action: click_text",
                "    target: Edit",
                "    expected_state:",
                "      after: editor-open",
                "  - id: type-title",
                "    action: type_text",
                "    text: Draft",
                "    depends_on:",
                "      - open-editor",
                "    expected_state:",
                "      before: editor-open",
                "      after: title-entered",
                "",
            ],
        ),
        encoding="utf-8",
    )

    task = YamlTaskLoader().load(task_path)

    assert task.steps[1].depends_on == ("open-editor",)
    assert task.steps[1].expected_state == ExpectedStateTransition(
        before="editor-open",
        after="title-entered",
    )


def test_task_dsl_rejects_unknown_action(tmp_path: Path) -> None:
    task_path = tmp_path / "task.yaml"
    task_path.write_text(
        "\n".join(
            [
                "name: bad-action",
                "allowed_windows:",
                "  - DeskPilot Fixture",
                "timeout_seconds: 30",
                "steps:",
                "  - id: bad",
                "    action: teleport",
                "",
            ],
        ),
        encoding="utf-8",
    )

    with pytest.raises(TaskValidationError, match="unknown action"):
        validate_task(task_path)


def test_task_dsl_rejects_unknown_step_category(tmp_path: Path) -> None:
    task_path = tmp_path / "task.yaml"
    task_path.write_text(
        "\n".join(
            [
                "name: bad-category",
                "allowed_windows:",
                "  - DeskPilot Fixture",
                "timeout_seconds: 30",
                "steps:",
                "  - id: click-submit",
                "    action: click_text",
                "    target: Submit",
                "    category: improvisation",
                "",
            ],
        ),
        encoding="utf-8",
    )

    with pytest.raises(TaskValidationError, match="unknown step category"):
        validate_task(task_path)


def test_task_dsl_rejects_invalid_entropy_budgets(tmp_path: Path) -> None:
    task_path = tmp_path / "task.yaml"
    task_path.write_text(
        "\n".join(
            [
                "name: bad-entropy",
                "allowed_windows:",
                "  - DeskPilot Fixture",
                "timeout_seconds: 30",
                "entropy_budget: 0.5",
                "steps:",
                "  - id: click-submit",
                "    action: click_text",
                "    target: Submit",
                "    entropy_budget: 0.75",
                "",
            ],
        ),
        encoding="utf-8",
    )

    with pytest.raises(TaskValidationError, match="step entropy_budget total"):
        validate_task(task_path)


def test_task_dsl_accepts_safe_action_variants_for_equivalent_actions(
    tmp_path: Path,
) -> None:
    task_path = tmp_path / "task.yaml"
    task_path.write_text(
        "\n".join(
            [
                "name: safe-variant",
                "allowed_windows:",
                "  - DeskPilot Fixture",
                "timeout_seconds: 30",
                "steps:",
                "  - id: click-submit",
                "    action: click_text",
                "    target: Submit",
                "    safe_action_variants:",
                "      - click_uia",
                "    recovery:",
                "      - reason: transient_loading",
                "        actions:",
                "          - wait_for_loading",
                "          - abort_with_trace",
                "",
            ],
        ),
        encoding="utf-8",
    )

    task = YamlTaskLoader().load(task_path)
    BasicTaskValidator().validate(task, RuntimeConfig())

    assert task.steps[0].safe_action_variants == ("click_uia",)
    assert task.steps[0].recovery[0].reason == "transient_loading"
    assert task.steps[0].recovery[0].actions == (
        "wait_for_loading",
        "abort_with_trace",
    )


def test_task_dsl_rejects_non_equivalent_safe_action_variants(
    tmp_path: Path,
) -> None:
    task_path = tmp_path / "task.yaml"
    task_path.write_text(
        "\n".join(
            [
                "name: bad-variant",
                "allowed_windows:",
                "  - DeskPilot Fixture",
                "timeout_seconds: 30",
                "steps:",
                "  - id: click-submit",
                "    action: click_text",
                "    target: Submit",
                "    safe_action_variants:",
                "      - type_text",
                "",
            ],
        ),
        encoding="utf-8",
    )

    with pytest.raises(TaskValidationError, match="safe_action_variants"):
        validate_task(task_path)


def test_task_dsl_rejects_unknown_recovery_actions(tmp_path: Path) -> None:
    task_path = tmp_path / "task.yaml"
    task_path.write_text(
        "\n".join(
            [
                "name: bad-recovery",
                "allowed_windows:",
                "  - DeskPilot Fixture",
                "timeout_seconds: 30",
                "steps:",
                "  - id: click-submit",
                "    action: click_text",
                "    target: Submit",
                "    recovery:",
                "      - reason: transient_loading",
                "        actions:",
                "          - teleport",
                "",
            ],
        ),
        encoding="utf-8",
    )

    with pytest.raises(TaskValidationError, match="unknown recovery action"):
        validate_task(task_path)


def test_step_category_uses_explicit_or_action_default() -> None:
    assert step_category(TaskStep(id="submit", action="click_text")) == "navigation"
    assert (
        step_category(
            TaskStep(id="submit", action="click_text", category="submission")
        )
        == "submission"
    )
    assert step_category(TaskStep(id="type", action="type_text")) == "data_entry"


def test_task_dsl_rejects_unknown_verification_type(tmp_path: Path) -> None:
    task_path = tmp_path / "task.yaml"
    task_path.write_text(
        "\n".join(
            [
                "name: bad-verify",
                "allowed_windows:",
                "  - DeskPilot Fixture",
                "timeout_seconds: 30",
                "steps:",
                "  - id: wait",
                "    action: wait_for",
                "    verify:",
                "      type: impossible",
                "",
            ],
        ),
        encoding="utf-8",
    )

    with pytest.raises(TaskValidationError, match="unknown verification type"):
        validate_task(task_path)


def test_task_dsl_rejects_duplicate_step_ids(tmp_path: Path) -> None:
    task_path = tmp_path / "task.yaml"
    task_path.write_text(
        "\n".join(
            [
                "name: duplicate",
                "allowed_windows:",
                "  - DeskPilot Fixture",
                "timeout_seconds: 30",
                "steps:",
                "  - id: same",
                "    action: scroll",
                "  - id: same",
                "    action: scroll",
                "",
            ],
        ),
        encoding="utf-8",
    )

    with pytest.raises(TaskValidationError, match="duplicate step id"):
        validate_task(task_path)


def test_task_dsl_rejects_missing_image_template(tmp_path: Path) -> None:
    task_path = tmp_path / "task.yaml"
    task_path.write_text(
        "\n".join(
            [
                "name: missing-image",
                "allowed_windows:",
                "  - DeskPilot Fixture",
                "timeout_seconds: 30",
                "steps:",
                "  - id: image",
                "    action: click_image",
                "    image: missing.png",
                "",
            ],
        ),
        encoding="utf-8",
    )

    with pytest.raises(TaskValidationError, match="image template not found"):
        YamlTaskLoader().load(task_path)


def test_task_dsl_rejects_missing_required_action_fields(tmp_path: Path) -> None:
    task_path = tmp_path / "task.yaml"
    task_path.write_text(
        "\n".join(
            [
                "name: missing-action-field",
                "allowed_windows:",
                "  - DeskPilot Fixture",
                "timeout_seconds: 30",
                "steps:",
                "  - id: type",
                "    action: type_text",
                "",
            ],
        ),
        encoding="utf-8",
    )

    with pytest.raises(TaskValidationError, match="text is required"):
        validate_task(task_path)
