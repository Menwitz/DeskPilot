from pathlib import Path

import pytest

from desktop_agent.config import RuntimeConfig
from desktop_agent.task_dsl import (
    BasicTaskValidator,
    TaskValidationError,
    YamlTaskLoader,
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
                "steps:",
                "  - id: click-submit-image",
                "    action: click_image",
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
    assert task.steps[0].region is not None
    assert task.steps[0].verify is not None
    assert task.steps[0].verify.text == "Success"
    assert task.steps[0].requires_confirmation is True


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
