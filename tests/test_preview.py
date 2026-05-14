from desktop_agent.config import ExecutionProfile, RuntimeConfig
from desktop_agent.preview import build_dry_run_preview, render_dry_run_preview
from desktop_agent.task_dsl import RecoveryRule, TaskDefinition, TaskStep


def test_dry_run_preview_renders_timing_bounds_and_recovery_paths() -> None:
    task = TaskDefinition(
        name="preview fixture",
        allowed_windows=("DeskPilot Fixture",),
        timeout_seconds=30,
        steps=(
            TaskStep(
                id="click-submit",
                action="click_text",
                target="Submit",
                recovery=(
                    RecoveryRule(
                        reason="missed_target",
                        actions=("wait_and_reobserve", "abort_with_trace"),
                    ),
                ),
            ),
        ),
    )
    config = RuntimeConfig(
        default_timeout_seconds=20,
        max_retries_per_step=2,
        policy_preset="strict_qa",
        execution_profile=ExecutionProfile(
            enabled=True,
            action_delay_seconds=(0.05, 0.25),
            retry_delay_seconds=(0.10, 0.30),
        ),
    )

    rendered = render_dry_run_preview(build_dry_run_preview(task, config))

    assert "policy preset: strict_qa" in rendered
    assert "step click-submit (click_text, navigation)" in rendered
    assert "action 0.050-0.250s x3" in rendered
    assert "retry 0.100-0.300s x2" in rendered
    assert "worst-case wait 1.350s" in rendered
    assert "missed_target -> wait_and_reobserve -> abort_with_trace" in rendered
    assert "chosen wait_and_reobserve constrained" in rendered
