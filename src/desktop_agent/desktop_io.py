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


@dataclass(frozen=True)
class DesktopIoKindSpec:
    """Schema contract for a supported low-level desktop I/O kind."""

    kind: str
    input_channel: str
    emits_desktop_input: bool
    requires_target: bool
    bounded: bool

    def to_metadata(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "input_channel": self.input_channel,
            "emits_desktop_input": self.emits_desktop_input,
            "requires_target": self.requires_target,
            "bounded": self.bounded,
            "supported": True,
        }


DESKTOP_IO_KIND_SPECS: dict[str, DesktopIoKindSpec] = {
    "observe": DesktopIoKindSpec(
        "observe",
        input_channel="screen",
        emits_desktop_input=False,
        requires_target=False,
        bounded=True,
    ),
    "move": DesktopIoKindSpec(
        "move",
        input_channel="pointer",
        emits_desktop_input=True,
        requires_target=True,
        bounded=True,
    ),
    "click": DesktopIoKindSpec(
        "click",
        input_channel="pointer",
        emits_desktop_input=True,
        requires_target=True,
        bounded=True,
    ),
    "double_click": DesktopIoKindSpec(
        "double_click",
        input_channel="pointer",
        emits_desktop_input=True,
        requires_target=True,
        bounded=True,
    ),
    "drag": DesktopIoKindSpec(
        "drag",
        input_channel="pointer",
        emits_desktop_input=True,
        requires_target=True,
        bounded=True,
    ),
    "wheel": DesktopIoKindSpec(
        "wheel",
        input_channel="scroll",
        emits_desktop_input=True,
        requires_target=False,
        bounded=True,
    ),
    "type": DesktopIoKindSpec(
        "type",
        input_channel="keyboard",
        emits_desktop_input=True,
        requires_target=False,
        bounded=True,
    ),
    "hotkey": DesktopIoKindSpec(
        "hotkey",
        input_channel="keyboard",
        emits_desktop_input=True,
        requires_target=False,
        bounded=True,
    ),
    "wait": DesktopIoKindSpec(
        "wait",
        input_channel="clock",
        emits_desktop_input=False,
        requires_target=False,
        bounded=True,
    ),
    "verify": DesktopIoKindSpec(
        "verify",
        input_channel="verification",
        emits_desktop_input=False,
        requires_target=False,
        bounded=True,
    ),
    "handoff": DesktopIoKindSpec(
        "handoff",
        input_channel="operator",
        emits_desktop_input=False,
        requires_target=False,
        bounded=False,
    ),
}
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
        kind_spec = desktop_io_kind_spec(self.kind)
        return {
            "id": self.id,
            "step_id": self.step_id,
            "kind": self.kind,
            "order": self.order,
            "source_action": self.source_action,
            "kind_contract": kind_spec.to_metadata()
            if kind_spec is not None
            else {"kind": self.kind, "supported": False},
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


def desktop_io_kind_spec(kind: str) -> DesktopIoKindSpec | None:
    """Return the contract for a supported low-level operation kind."""

    return DESKTOP_IO_KIND_SPECS.get(kind)
