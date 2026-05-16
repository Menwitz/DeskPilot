from pathlib import Path
from types import SimpleNamespace

from pytest import MonkeyPatch

from desktop_agent.config import RuntimeConfig
from desktop_agent.perception import (
    ConfidenceTargetSelector,
    ElementCandidate,
)
from desktop_agent.platforms.windows import uia as uia_module
from desktop_agent.platforms.windows.uia import (
    UiaElementSnapshot,
    WindowsUiaPerceptionEngine,
    WindowsUiaUnavailableError,
    _snapshot_from_element,
    write_uia_tree_snapshot,
)
from desktop_agent.screen import Bounds, ScreenObservation
from desktop_agent.task_dsl import TaskStep


class Rect:
    left = 10
    top = 20
    right = 110
    bottom = 60


class FakeElement:
    element_info = SimpleNamespace(name="Submit", control_type="Button")

    def __init__(self, children: tuple[object, ...] = ()) -> None:
        self._children = children

    def window_text(self) -> str:
        return "Submit"

    def rectangle(self) -> Rect:
        return Rect()

    def is_enabled(self) -> bool:
        return True

    def is_visible(self) -> bool:
        return True

    def children(self) -> tuple[object, ...]:
        return self._children


class FakeAdapter:
    def candidates(self) -> tuple[ElementCandidate, ...]:
        return (
            ElementCandidate(
                id="uia-0",
                source="uia",
                label="Submit",
                bounds=Bounds(10, 20, 100, 40),
                confidence=0.95,
            ),
        )


class UnavailableAdapter:
    def candidates(self) -> tuple[ElementCandidate, ...]:
        raise WindowsUiaUnavailableError("unavailable")


class FakeDesktop:
    def __init__(self) -> None:
        self.point: tuple[int, int] | None = None

    def from_point(self, x: int, y: int) -> FakeElement:
        self.point = (x, y)
        return FakeElement()


class FakePywinauto:
    def __init__(self, desktop: FakeDesktop) -> None:
        self._desktop = desktop

    def Desktop(self, *, backend: str) -> FakeDesktop:
        assert backend == "uia"
        return self._desktop


def test_snapshot_extracts_uia_element_fields() -> None:
    snapshot = _snapshot_from_element(FakeElement())

    assert snapshot == UiaElementSnapshot(
        name="Submit",
        control_type="Button",
        bounds=Bounds(x=10, y=20, width=100, height=40),
        enabled=True,
        visible=True,
        children=(),
    )


def test_uia_perception_engine_returns_candidates() -> None:
    engine = WindowsUiaPerceptionEngine(FakeAdapter())

    candidates = engine.detect(
        TaskStep(id="submit", action="click_text", target="Submit"),
        ScreenObservation(),
        RuntimeConfig(),
    )

    assert candidates[0].source == "uia"
    assert candidates[0].metadata == {}


def test_uia_perception_engine_falls_back_when_unavailable() -> None:
    engine = WindowsUiaPerceptionEngine(UnavailableAdapter())

    candidates = engine.detect(
        TaskStep(id="submit", action="click_text", target="Submit"),
        ScreenObservation(),
        RuntimeConfig(),
    )

    assert candidates == ()


def test_uia_adapter_captures_element_at_point(monkeypatch: MonkeyPatch) -> None:
    desktop = FakeDesktop()
    monkeypatch.setattr(
        uia_module,
        "import_module",
        lambda _name: FakePywinauto(desktop),
    )

    snapshot = uia_module.WindowsUiaAdapter().element_at_point((120, 240))

    assert desktop.point == (120, 240)
    assert snapshot.name == "Submit"
    assert snapshot.control_type == "Button"
    assert snapshot.bounds == Bounds(x=10, y=20, width=100, height=40)


def test_selector_prefers_uia_when_confidence_is_similar() -> None:
    selector = ConfidenceTargetSelector()
    candidates = (
        ElementCandidate(
            id="ocr-0",
            source="ocr",
            label="Submit",
            bounds=Bounds(10, 20, 100, 40),
            confidence=0.97,
        ),
        ElementCandidate(
            id="uia-0",
            source="uia",
            label="Submit",
            bounds=Bounds(10, 20, 100, 40),
            confidence=0.94,
        ),
    )

    selected = selector.select(
        TaskStep(id="submit", action="click_text", target="Submit"),
        candidates,
        RuntimeConfig(confidence_threshold=0.8),
    )

    assert selected is not None
    assert selected.id == "uia-0"


def test_write_uia_tree_snapshot(tmp_path: Path) -> None:
    output_path = tmp_path / "uia" / "tree.json"

    write_uia_tree_snapshot(
        output_path,
        {
            "active_window": {"title": "Fixture"},
            "elements": [{"name": "Submit"}],
        },
    )

    assert output_path.read_text(encoding="utf-8").endswith("\n")
