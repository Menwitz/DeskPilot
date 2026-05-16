from pathlib import Path
from types import SimpleNamespace
from typing import Any

from pytest import MonkeyPatch

from desktop_agent import screen
from desktop_agent.config import RuntimeConfig
from desktop_agent.redaction import RedactionPolicy
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
    monkeypatch.setattr(
        screen,
        "detect_active_window_process",
        lambda: {"process_id": 1234, "process_name": "notepad.exe"},
    )
    monkeypatch.setattr(
        screen,
        "detect_focused_element",
        lambda: {"name": "Routine", "class_name": "Edit"},
    )

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
    assert observation.metadata["active_window_process"] == {
        "process_id": 1234,
        "process_name": "notepad.exe",
    }
    assert observation.metadata["focused_element"] == {
        "name": "Routine",
        "class_name": "Edit",
    }


def test_mss_capture_region_writes_png_with_keyword_output(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    observer = MssScreenObserver()
    monitor = MonitorInfo(left=10, top=20, width=800, height=600, is_primary=True)
    captured_boxes: list[dict[str, int]] = []
    png_calls: list[dict[str, object]] = []

    class FakeScreenCapture:
        def __enter__(self) -> "FakeScreenCapture":
            return self

        def __exit__(
            self,
            exc_type: object,
            exc_value: object,
            traceback: object,
        ) -> None:
            _ = exc_type, exc_value, traceback

        def grab(self, capture_box: dict[str, int]) -> SimpleNamespace:
            captured_boxes.append(capture_box)
            return SimpleNamespace(
                bgra=b"bgra-pixels",
                rgb=b"rgb-pixels",
                size=(30, 40),
            )

    class FakeMssModule:
        def mss(self) -> FakeScreenCapture:
            return FakeScreenCapture()

    class FakeToolsModule:
        def to_png(
            self,
            data: bytes,
            size: tuple[int, int],
            *,
            output: str,
        ) -> None:
            # The Windows mss version rejects a third positional path argument.
            png_calls.append({"data": data, "size": size, "output": output})
            Path(output).write_bytes(b"png")

    def fake_import_module(module_name: str) -> Any:
        if module_name == "mss":
            return FakeMssModule()
        if module_name == "mss.tools":
            return FakeToolsModule()
        raise AssertionError(f"unexpected module import: {module_name}")

    monkeypatch.setattr(screen, "import_module", fake_import_module)

    screenshot_path = observer.capture_region(
        Bounds(x=1, y=2, width=30, height=40),
        monitor,
        RuntimeConfig(trace_root=tmp_path),
    )

    assert screenshot_path is not None
    assert screenshot_path.exists()
    assert captured_boxes == [{"left": 11, "top": 22, "width": 30, "height": 40}]
    assert png_calls == [
        {"data": b"rgb-pixels", "size": (30, 40), "output": str(screenshot_path)}
    ]


def test_mss_capture_region_skips_file_for_metadata_only_policy(
    tmp_path: Path,
) -> None:
    observer = MssScreenObserver()
    monitor = MonitorInfo(left=0, top=0, width=800, height=600, is_primary=True)

    screenshot_path = observer.capture_region(
        Bounds(x=1, y=2, width=30, height=40),
        monitor,
        RuntimeConfig(
            trace_root=tmp_path,
            redaction_policy=RedactionPolicy(evidence_mode="metadata_only"),
        ),
    )

    assert screenshot_path is None
    assert not (tmp_path / "screenshots").exists()
