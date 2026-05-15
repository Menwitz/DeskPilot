from pathlib import Path

from pytest import MonkeyPatch

from desktop_agent import screen
from desktop_agent.config import RuntimeConfig
from desktop_agent.screen import Bounds, MonitorInfo, MssScreenObserver


def test_mss_observer_populates_active_window_title(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    observer = MssScreenObserver()
    monitor = MonitorInfo(left=0, top=0, width=800, height=600, is_primary=True)

    monkeypatch.setattr(screen, "ensure_desktop_available", lambda: None)
    monkeypatch.setattr(observer, "detect_monitors", lambda: (monitor,))
    monkeypatch.setattr(screen, "detect_active_window_title", lambda: "DeskPilot")

    def capture_region(
        region: Bounds,
        active_monitor: MonitorInfo,
        config: RuntimeConfig,
    ) -> Path:
        _ = region, active_monitor, config
        return tmp_path / "screen.png"

    monkeypatch.setattr(observer, "capture_region", capture_region)

    observation = observer.observe(RuntimeConfig(trace_root=tmp_path))

    assert observation.active_window_title == "DeskPilot"
    assert observation.size == (800, 600)
