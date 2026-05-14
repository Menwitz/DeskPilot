from pathlib import Path

import pytest

from desktop_agent.config import (
    ConfigError,
    ConfigOverrides,
    RuntimeConfig,
    YamlConfigLoader,
    resolve_runtime_config,
)
from desktop_agent.task_dsl import YamlTaskLoader


def test_config_precedence_cli_over_task_over_file_over_defaults(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "confidence_threshold: 0.4",
                "max_steps: 5",
                "max_retries_per_step: 1",
                "allowed_windows:",
                "  - Config Window",
                "",
            ],
        ),
        encoding="utf-8",
    )

    file_config = YamlConfigLoader().load(config_path)
    resolved = resolve_runtime_config(
        file_config,
        task_overrides=ConfigOverrides(
            confidence_threshold=0.7,
            max_retries_per_step=3,
        ),
        cli_overrides=ConfigOverrides(
            confidence_threshold=0.9,
            allowed_windows=("CLI Window",),
        ),
    )

    assert resolved.confidence_threshold == 0.9
    assert resolved.max_retries_per_step == 3
    assert resolved.max_steps == 5
    assert resolved.allowed_windows == ("CLI Window",)


def test_task_yaml_loads_config_overrides(tmp_path: Path) -> None:
    task_path = tmp_path / "task.yaml"
    task_path.write_text(
        "\n".join(
            [
                "name: fixture",
                "allowed_windows:",
                "  - DeskPilot Fixture",
                "timeout_seconds: 30",
                "config:",
                "  save_screenshots: false",
                "  confidence_threshold: 0.95",
                "steps:",
                "  - id: submit",
                "    action: click_text",
                "",
            ],
        ),
        encoding="utf-8",
    )

    task = YamlTaskLoader().load(task_path)

    assert task.config_overrides.save_screenshots is False
    assert task.config_overrides.confidence_threshold == 0.95


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        (ConfigOverrides(default_timeout_seconds=0), "default_timeout_seconds"),
        (ConfigOverrides(max_retries_per_step=-1), "max_retries_per_step"),
        (ConfigOverrides(max_runtime_seconds=0), "max_runtime_seconds"),
        (ConfigOverrides(confidence_threshold=1.5), "confidence_threshold"),
    ],
)
def test_config_rejects_unsafe_values(
    overrides: ConfigOverrides,
    message: str,
) -> None:
    with pytest.raises(ConfigError, match=message):
        resolve_runtime_config(RuntimeConfig(), cli_overrides=overrides)


def test_yaml_config_loader_rejects_invalid_types(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("max_steps: nope\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="max_steps"):
        YamlConfigLoader().load(config_path)
