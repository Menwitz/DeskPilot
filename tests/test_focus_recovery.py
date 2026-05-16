from desktop_agent.config import RuntimeConfig
from desktop_agent.focus_recovery import (
    FocusRecoveryResult,
    NoopFocusRecoveryController,
)


def test_noop_focus_recovery_reports_unavailable_metadata() -> None:
    result = NoopFocusRecoveryController().refocus_allowed_window(
        RuntimeConfig(allowed_windows=("DeskPilot Fixture",)),
    )

    metadata = result.metadata()
    assert result.attempted is False
    assert result.success is False
    assert metadata["focus_recovery_attempted"] is False
    assert metadata["focus_recovery_allowed_windows"] == ["DeskPilot Fixture"]


def test_focus_recovery_result_serializes_before_after_titles() -> None:
    result = FocusRecoveryResult(
        attempted=True,
        success=True,
        message="allowed window refocused",
        before_active_window_title="Unexpected Window",
        after_active_window_title="DeskPilot Fixture",
        matched_window_title="DeskPilot Fixture",
        allowed_windows=("DeskPilot Fixture",),
    )

    metadata = result.metadata()
    assert metadata["focus_recovery_success"] is True
    assert metadata["focus_recovery_before_active_window_title"] == (
        "Unexpected Window"
    )
    assert metadata["focus_recovery_after_active_window_title"] == "DeskPilot Fixture"
    assert metadata["focus_recovery_matched_window_title"] == "DeskPilot Fixture"
