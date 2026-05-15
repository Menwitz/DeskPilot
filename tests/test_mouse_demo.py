from pathlib import Path

import pytest
from pytest import MonkeyPatch

from desktop_agent.mouse_demo import (
    MouseDemoError,
    _demo_actuation_profile,
    run_mouse_demo,
)


def test_demo_actuation_profile_uses_visible_human_like_motion() -> None:
    profile = _demo_actuation_profile(123, 0.75)

    assert profile.movement_duration_seconds == (0.35, 0.90)
    assert profile.movement_steps == 32
    assert profile.movement_smoothness == 0.75
    assert profile.overshoot_probability == 0.35
    assert profile.scroll_interval_seconds == (0.08, 0.18)
    assert profile.random_seed == 123


def test_run_mouse_demo_requires_windows(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr("desktop_agent.mouse_demo.sys.platform", "darwin")

    with pytest.raises(MouseDemoError, match="requires Windows"):
        run_mouse_demo(trace_root=tmp_path)
