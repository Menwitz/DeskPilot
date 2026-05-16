"""Windows UI Automation adapter built around optional `pywinauto` support."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from importlib import import_module
from pathlib import Path
from typing import Protocol, TypeGuard, cast

from desktop_agent.config import RuntimeConfig
from desktop_agent.perception import ElementCandidate, PerceptionEngine
from desktop_agent.screen import Bounds, ScreenObservation
from desktop_agent.task_dsl import TaskStep


class WindowsUiaUnavailableError(RuntimeError):
    """Raised when Windows UI Automation cannot provide useful data."""


@dataclass(frozen=True)
class ActiveWindowInfo:
    """Basic active-window metadata from Windows UI Automation."""

    title: str
    process_id: int | None = None
    process_name: str | None = None


@dataclass(frozen=True)
class UiaElementSnapshot:
    """Serializable UIA element snapshot used for candidates and reports."""

    name: str
    control_type: str
    bounds: Bounds | None
    enabled: bool
    visible: bool
    children: tuple[UiaElementSnapshot, ...] = field(default_factory=tuple)


class UiaCandidateProvider(Protocol):
    """Interface used by the perception engine for testable UIA fallback."""

    def candidates(self) -> tuple[ElementCandidate, ...]: ...


class RectLike(Protocol):
    """Rectangle shape returned by pywinauto wrappers."""

    left: int
    top: int
    right: int
    bottom: int


class WindowsUiaAdapter:
    """Reads active-window and element data from `pywinauto` on Windows."""

    def active_window_info(self) -> ActiveWindowInfo:
        window = self._active_window()
        return ActiveWindowInfo(
            title=_optional_text(window, "window_text") or "",
            process_id=_optional_int(window, "process_id"),
            process_name=_optional_text(window, "process_name"),
        )

    def visible_elements(self) -> tuple[UiaElementSnapshot, ...]:
        window = self._active_window()
        children = _children(window)
        return tuple(_snapshot_from_element(child) for child in children)

    def element_at_point(self, point: tuple[int, int]) -> UiaElementSnapshot:
        try:
            pywinauto = import_module("pywinauto")
            desktop = pywinauto.Desktop(backend="uia")
            element = desktop.from_point(int(point[0]), int(point[1]))
            return _snapshot_from_element(element)
        except Exception as exc:
            raise WindowsUiaUnavailableError("Windows UIA is unavailable") from exc

    def candidates(self) -> tuple[ElementCandidate, ...]:
        candidates: list[ElementCandidate] = []
        for index, snapshot in enumerate(_flatten(self.visible_elements())):
            candidate = _candidate_from_snapshot(snapshot, index)
            if candidate is not None:
                candidates.append(candidate)
        return tuple(candidates)

    def tree_snapshot(self) -> dict[str, object]:
        active = self.active_window_info()
        return {
            "active_window": {
                "title": active.title,
                "process_id": active.process_id,
                "process_name": active.process_name,
            },
            "elements": [
                _snapshot_to_dict(snapshot) for snapshot in self.visible_elements()
            ],
        }

    def _active_window(self) -> object:
        try:
            pywinauto = import_module("pywinauto")
            desktop = pywinauto.Desktop(backend="uia")
            return cast(object, desktop.get_active())
        except Exception as exc:
            raise WindowsUiaUnavailableError("Windows UIA is unavailable") from exc


class WindowsUiaPerceptionEngine(PerceptionEngine):
    """Perception engine that falls back to no candidates when UIA is unavailable."""

    def __init__(self, adapter: UiaCandidateProvider | None = None) -> None:
        self._adapter = adapter or WindowsUiaAdapter()

    def detect(
        self,
        step: TaskStep,
        observation: ScreenObservation,
        config: RuntimeConfig,
    ) -> tuple[ElementCandidate, ...]:
        _ = step, observation, config
        try:
            return self._adapter.candidates()
        except WindowsUiaUnavailableError:
            return ()


def write_uia_tree_snapshot(path: Path, snapshot: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")


def _snapshot_from_element(element: object) -> UiaElementSnapshot:
    element_info = getattr(element, "element_info", None)
    name = _optional_text(element, "window_text")
    if not name and element_info is not None:
        name = str(getattr(element_info, "name", ""))

    control_type = "unknown"
    if element_info is not None:
        control_type = str(getattr(element_info, "control_type", "unknown"))

    return UiaElementSnapshot(
        name=name or "",
        control_type=control_type,
        bounds=_bounds_from_element(element),
        enabled=_optional_bool(element, "is_enabled", default=True),
        visible=_optional_bool(element, "is_visible", default=True),
        children=tuple(_snapshot_from_element(child) for child in _children(element)),
    )


def _candidate_from_snapshot(
    snapshot: UiaElementSnapshot,
    index: int,
) -> ElementCandidate | None:
    if snapshot.bounds is None:
        return None
    return ElementCandidate(
        id=f"uia-{index}",
        source="uia",
        label=snapshot.name or snapshot.control_type,
        bounds=snapshot.bounds,
        confidence=0.95 if snapshot.enabled and snapshot.visible else 0.5,
        visible=snapshot.visible,
        enabled=snapshot.enabled,
        metadata={"control_type": snapshot.control_type},
    )


def _flatten(
    snapshots: tuple[UiaElementSnapshot, ...],
) -> tuple[UiaElementSnapshot, ...]:
    flattened: list[UiaElementSnapshot] = []
    for snapshot in snapshots:
        flattened.append(snapshot)
        flattened.extend(_flatten(snapshot.children))
    return tuple(flattened)


def _snapshot_to_dict(snapshot: UiaElementSnapshot) -> dict[str, object]:
    return {
        "name": snapshot.name,
        "control_type": snapshot.control_type,
        "bounds": _bounds_to_dict(snapshot.bounds),
        "enabled": snapshot.enabled,
        "visible": snapshot.visible,
        "children": [_snapshot_to_dict(child) for child in snapshot.children],
    }


def _bounds_to_dict(bounds: Bounds | None) -> dict[str, int] | None:
    if bounds is None:
        return None
    return {
        "x": bounds.x,
        "y": bounds.y,
        "width": bounds.width,
        "height": bounds.height,
    }


def _bounds_from_element(element: object) -> Bounds | None:
    rect = _optional_call(element, "rectangle")
    if rect is None or not _is_rect_like(rect):
        return None

    try:
        left = int(rect.left)
        top = int(rect.top)
        right = int(rect.right)
        bottom = int(rect.bottom)
    except Exception:
        return None

    width = right - left
    height = bottom - top
    if width <= 0 or height <= 0:
        return None
    return Bounds(x=left, y=top, width=width, height=height)


def _is_rect_like(value: object) -> TypeGuard[RectLike]:
    return all(
        hasattr(value, attribute) for attribute in ("left", "top", "right", "bottom")
    )


def _children(element: object) -> tuple[object, ...]:
    children = _optional_call(element, "children")
    if children is None:
        return ()
    if isinstance(children, tuple):
        return children
    if isinstance(children, list):
        return tuple(children)
    return ()


def _optional_text(element: object, method_name: str) -> str | None:
    value = _optional_call(element, method_name)
    if value is None:
        return None
    return str(value)


def _optional_int(element: object, method_name: str) -> int | None:
    value = _optional_call(element, method_name)
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _optional_bool(element: object, method_name: str, *, default: bool) -> bool:
    value = _optional_call(element, method_name)
    if value is None:
        return default
    return bool(value)


def _optional_call(element: object, method_name: str) -> object | None:
    method = getattr(element, method_name, None)
    if method is None:
        return None
    if not callable(method):
        return cast(object, method)
    try:
        return cast(object, method())
    except Exception:
        return None
