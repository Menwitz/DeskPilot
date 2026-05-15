import pytest

from desktop_agent.window_allowlist import (
    WindowAllowlistError,
    effective_allowed_windows,
    window_allowlist_errors,
    window_title_matches,
)


def test_plain_window_patterns_match_exact_and_case_insensitive_contains() -> None:
    assert window_title_matches("DeskPilot Fixture", ("DeskPilot Fixture",))
    assert window_title_matches("LinkedIn - Google Chrome", ("linkedin",))
    assert not window_title_matches("Mail", ("LinkedIn",))


def test_regex_window_patterns_match_active_title() -> None:
    assert window_title_matches("Medium - Brave", ("regex:^medium\\b",))
    assert not window_title_matches("Newsletter Draft", ("regex:^medium\\b",))


def test_invalid_regex_entries_fail_closed() -> None:
    assert window_allowlist_errors(("regex:[",)) == [
        "allowed_windows invalid regex 'regex:[': unterminated character set at "
        "position 0",
    ]

    with pytest.raises(WindowAllowlistError):
        window_title_matches("Any Window", ("regex:[",))


def test_effective_allowed_windows_combines_task_and_runtime_rules() -> None:
    assert effective_allowed_windows(
        ("DeskPilot Fixture", "Chrome"),
        ("Chrome", "regex:.*Medium.*"),
    ) == ("DeskPilot Fixture", "Chrome", "regex:.*Medium.*")
