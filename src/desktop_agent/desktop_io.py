"""First-class desktop I/O action schema compiled from semantic task steps."""

from __future__ import annotations

from dataclasses import dataclass, field

from desktop_agent.action_safety import action_safety_metadata
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


class DesktopIoValidationError(ValueError):
    """Raised when a compiled desktop I/O action schema is invalid."""


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
        metadata: dict[str, object] = {
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
        safety_metadata = self.metadata.get("safety")
        if isinstance(safety_metadata, dict):
            metadata["safety"] = safety_metadata
        return metadata


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


def compile_desktop_io_plan(
    step: TaskStep,
    *,
    allowed_windows: tuple[str, ...] = (),
) -> DesktopIoPlan:
    """Compile one YAML task step into ordered desktop I/O schema actions."""

    operations = desktop_io_operations_for_action(step.action)
    safety_metadata = action_safety_metadata(step, allowed_windows=allowed_windows)
    actions = tuple(
        DesktopIoAction(
            id=f"{step.id}:{index}:{operation}",
            step_id=step.id,
            kind=operation,
            order=index,
            source_action=step.action,
            metadata={"safety": safety_metadata},
        )
        for index, operation in enumerate(operations, start=1)
    )
    plan = DesktopIoPlan(
        step_id=step.id,
        source_action=step.action,
        actions=actions,
    )
    validate_desktop_io_plan(plan)
    return plan


def desktop_io_operations_for_action(action: str) -> tuple[str, ...]:
    """Return the stable low-level operation sequence for a semantic action."""

    return DESKTOP_IO_OPERATIONS_BY_ACTION.get(
        action,
        ("observe", action, "verify"),
    )


def desktop_io_kind_spec(kind: str) -> DesktopIoKindSpec | None:
    """Return the contract for a supported low-level operation kind."""

    return DESKTOP_IO_KIND_SPECS.get(kind)


def validate_desktop_io_plan(plan: DesktopIoPlan) -> None:
    """Validate action identity, ordering, support, and safety metadata."""

    errors: list[str] = []
    if not plan.step_id.strip():
        errors.append("desktop I/O plan step_id must not be empty")
    if not plan.source_action.strip():
        errors.append("desktop I/O plan source_action must not be empty")
    if not plan.actions:
        errors.append("desktop I/O plan must contain at least one action")
    expected_order = tuple(range(1, len(plan.actions) + 1))
    actual_order = tuple(action.order for action in plan.actions)
    if actual_order != expected_order:
        errors.append("desktop I/O action order must be contiguous from 1")
    for action in plan.actions:
        errors.extend(_desktop_io_action_errors(action, plan))
    if errors:
        raise DesktopIoValidationError("; ".join(errors))


def validate_desktop_io_action(action: DesktopIoAction) -> None:
    """Validate one standalone desktop I/O action."""

    errors = _desktop_io_action_errors(action)
    if errors:
        raise DesktopIoValidationError("; ".join(errors))


def _desktop_io_action_errors(
    action: DesktopIoAction,
    plan: DesktopIoPlan | None = None,
) -> list[str]:
    errors: list[str] = []
    if not action.id.strip():
        errors.append("desktop I/O action id must not be empty")
    if not action.step_id.strip():
        errors.append("desktop I/O action step_id must not be empty")
    if not action.source_action.strip():
        errors.append("desktop I/O action source_action must not be empty")
    if action.order <= 0:
        errors.append("desktop I/O action order must be greater than zero")
    if desktop_io_kind_spec(action.kind) is None:
        errors.append(f"unsupported desktop I/O action kind: {action.kind}")
    if "safety" not in action.metadata:
        errors.append(f"desktop I/O action {action.id} missing safety metadata")
    if plan is not None:
        if action.step_id != plan.step_id:
            errors.append(f"desktop I/O action {action.id} step_id mismatch")
        if action.source_action != plan.source_action:
            errors.append(f"desktop I/O action {action.id} source_action mismatch")
    return errors
