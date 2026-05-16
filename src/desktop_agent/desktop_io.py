"""First-class desktop I/O action schema compiled from semantic task steps."""

from __future__ import annotations

from dataclasses import dataclass, field

from desktop_agent.task_dsl import TaskStep

DESKTOP_IO_MODEL_VERSION = "desktop_io_v1"
SUPPORTED_DESKTOP_IO_KINDS: tuple[str, ...] = (
    "observe",
    "move",
    "click",
    "double_click",
    "drag",
    "wheel",
    "type",
    "hotkey",
    "wait",
    "verify",
    "handoff",
)
DESKTOP_IO_OPERATIONS_BY_ACTION: dict[str, tuple[str, ...]] = {
    "click_text": ("observe", "move", "click", "verify"),
    "click_image": ("observe", "move", "click", "verify"),
    "click_uia": ("observe", "move", "click", "verify"),
    "double_click": ("observe", "move", "double_click", "verify"),
    "drag": ("observe", "move", "drag", "verify"),
    "type_text": ("observe", "type", "verify"),
    "press_key": ("observe", "hotkey", "verify"),
    "scroll": ("observe", "wheel", "verify"),
    "scroll_until": ("observe", "wheel", "observe", "verify"),
    "wait_for": ("observe", "wait", "verify"),
    "assert_visible": ("observe", "verify"),
    "branch_if_visible": ("observe", "verify"),
}


@dataclass(frozen=True)
class DesktopIoAction:
    """One low-level desktop I/O operation derived from a semantic step."""

    id: str
    step_id: str
    kind: str
    order: int
    source_action: str
    metadata: dict[str, object] = field(default_factory=dict)

    def to_metadata(self) -> dict[str, object]:
        return {
            "id": self.id,
            "step_id": self.step_id,
            "kind": self.kind,
            "order": self.order,
            "source_action": self.source_action,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class DesktopIoPlan:
    """Ordered desktop I/O action plan for one task step."""

    step_id: str
    source_action: str
    actions: tuple[DesktopIoAction, ...]

    @property
    def operations(self) -> tuple[str, ...]:
        return tuple(action.kind for action in self.actions)

    def to_metadata(self) -> dict[str, object]:
        return {
            "schema_version": DESKTOP_IO_MODEL_VERSION,
            "step_id": self.step_id,
            "source_action": self.source_action,
            "operations": list(self.operations),
            "actions": [action.to_metadata() for action in self.actions],
        }


def compile_desktop_io_plan(step: TaskStep) -> DesktopIoPlan:
    """Compile one YAML task step into ordered desktop I/O schema actions."""

    operations = desktop_io_operations_for_action(step.action)
    actions = tuple(
        DesktopIoAction(
            id=f"{step.id}:{index}:{operation}",
            step_id=step.id,
            kind=operation,
            order=index,
            source_action=step.action,
        )
        for index, operation in enumerate(operations, start=1)
    )
    return DesktopIoPlan(
        step_id=step.id,
        source_action=step.action,
        actions=actions,
    )


def desktop_io_operations_for_action(action: str) -> tuple[str, ...]:
    """Return the stable low-level operation sequence for a semantic action."""

    return DESKTOP_IO_OPERATIONS_BY_ACTION.get(
        action,
        ("observe", action, "verify"),
    )
