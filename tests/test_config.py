from pathlib import Path

import pytest

from desktop_agent.config import (
    ConfigError,
    ConfigOverrides,
    ExecutionProfile,
    RuntimeConfig,
    YamlConfigLoader,
    execution_profile_for_activity,
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
                "policy_preset: strict_qa",
                "require_operator_approval: true",
                "confirmed_steps:",
                "  - submit-payment",
                "execution_profile:",
                "  activity_profile: careful",
                "  persona: careful",
                "  enabled: true",
                "  action_delay_seconds: [0.1, 0.3]",
                "  retry_delay_seconds: [0.5, 1.5]",
                "  action_delay_distribution: center_weighted",
                "  retry_delay_distribution: uniform",
                "  action_variant_distribution: center_weighted",
                "  hesitation_probability: 0.25",
                "  movement_smoothness: 0.7",
                "  keyboard_interval_seconds: [0.01, 0.03]",
                "  scroll_interval_seconds: [0.02, 0.04]",
                "  random_seed: 7",
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
    assert resolved.policy_preset == "strict_qa"
    assert resolved.require_operator_approval is True
    assert resolved.confirmed_steps == ("submit-payment",)
    assert resolved.execution_profile.activity_profile == "careful"
    assert resolved.execution_profile.persona == "careful"
    assert resolved.execution_profile.enabled is True
    assert resolved.execution_profile.action_delay_seconds == (0.1, 0.3)
    assert resolved.execution_profile.retry_delay_seconds == (0.5, 1.5)
    assert resolved.execution_profile.action_delay_distribution == "center_weighted"
    assert resolved.execution_profile.retry_delay_distribution == "uniform"
    assert resolved.execution_profile.action_variant_distribution == "center_weighted"
    assert resolved.execution_profile.hesitation_probability == 0.25
    assert resolved.execution_profile.movement_smoothness == 0.7
    assert resolved.execution_profile.keyboard_interval_seconds == (0.01, 0.03)
    assert resolved.execution_profile.scroll_interval_seconds == (0.02, 0.04)
    assert resolved.execution_profile.random_seed == 7


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
                "  policy_preset: exploratory_testing",
                "  require_operator_approval: true",
                "  confirmed_steps:",
                "    - submit",
                "  execution_profile:",
                "    persona: fast",
                "    enabled: true",
                "    action_delay_seconds: [0.05, 0.1]",
                "    keyboard_interval_seconds: [0.01, 0.02]",
                "    scroll_interval_seconds: [0.02, 0.03]",
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
    assert task.config_overrides.policy_preset == "exploratory_testing"
    assert task.config_overrides.require_operator_approval is True
    assert task.config_overrides.confirmed_steps == ("submit",)
    assert task.config_overrides.execution_profile is not None
    assert task.config_overrides.execution_profile.activity_profile is None
    assert task.config_overrides.execution_profile.persona == "fast"
    assert task.config_overrides.execution_profile.enabled is True
    assert task.config_overrides.execution_profile.action_delay_seconds == (0.05, 0.1)
    assert task.config_overrides.execution_profile.keyboard_interval_seconds == (
        0.01,
        0.02,
    )
    assert task.config_overrides.execution_profile.scroll_interval_seconds == (
        0.02,
        0.03,
    )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        (ConfigOverrides(default_timeout_seconds=0), "default_timeout_seconds"),
        (ConfigOverrides(max_retries_per_step=-1), "max_retries_per_step"),
        (ConfigOverrides(max_runtime_seconds=0), "max_runtime_seconds"),
        (ConfigOverrides(confidence_threshold=1.5), "confidence_threshold"),
        (ConfigOverrides(confirmed_steps=("",)), "confirmed_steps"),
        (ConfigOverrides(policy_preset="anything_goes"), "policy_preset"),
        (
            ConfigOverrides(
                execution_profile=ExecutionProfile(
                    action_delay_seconds=(1.0, 0.5),
                ),
            ),
            "execution_profile.action_delay_seconds",
        ),
        (
            ConfigOverrides(
                execution_profile=ExecutionProfile(hesitation_probability=1.5),
            ),
            "execution_profile.hesitation_probability",
        ),
        (
            ConfigOverrides(
                execution_profile=ExecutionProfile(
                    keyboard_interval_seconds=(0.2, 0.1),
                ),
            ),
            "execution_profile.keyboard_interval_seconds",
        ),
        (
            ConfigOverrides(
                execution_profile=ExecutionProfile(
                    scroll_interval_seconds=(0.3, 0.1),
                ),
            ),
            "execution_profile.scroll_interval_seconds",
        ),
        (
            ConfigOverrides(
                execution_profile=ExecutionProfile(persona="reckless"),
            ),
            "execution_profile.persona",
        ),
        (
            ConfigOverrides(
                execution_profile=ExecutionProfile(activity_profile="stealth"),
            ),
            "execution_profile.activity_profile",
        ),
        (
            ConfigOverrides(
                execution_profile=ExecutionProfile(
                    action_delay_distribution="random_walk",
                ),
            ),
            "execution_profile.action_delay_distribution",
        ),
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


def test_execution_activity_profiles_apply_bounded_timing_presets(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "\n".join(
            [
                "execution_profile:",
                "  activity_profile: background_assist",
                "  action_delay_seconds: [0.5, 1.0]",
                "  random_seed: 9",
                "",
            ],
        ),
        encoding="utf-8",
    )

    config = YamlConfigLoader().load(config_path)
    focused = execution_profile_for_activity("focused")

    assert focused.enabled is True
    assert focused.activity_profile == "focused"
    assert config.execution_profile.activity_profile == "background_assist"
    assert config.execution_profile.enabled is True
    assert config.execution_profile.persona == "careful"
    assert config.execution_profile.action_delay_seconds == (0.5, 1.0)
    assert config.execution_profile.retry_delay_seconds == (2.0, 6.0)
    assert config.execution_profile.random_seed == 9
