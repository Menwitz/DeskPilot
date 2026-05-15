"""Website navigation playbook contracts and validation helpers."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import yaml

from desktop_agent.config import ConfigOverrides
from desktop_agent.task_dsl import (
    SUPPORTED_ACTIONS,
    TaskDefinition,
    TaskRegion,
    TaskStep,
    VerificationDefinition,
)

_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_SENSITIVE_CATEGORIES: frozenset[str] = frozenset(
    {
        "login",
        "publish",
        "engage",
        "comment",
        "message",
        "transaction",
        "delete",
        "account_settings",
    },
)


class SitePlaybookValidationError(ValueError):
    """Raised when a website navigation playbook is invalid."""


@dataclass(frozen=True)
class SiteDomain:
    """Domain rule used to recognize a supported public website."""

    host: str
    include_subdomains: bool = True
    purpose: str | None = None


@dataclass(frozen=True)
class SiteLandmark:
    """Reusable selector or label for a stable site navigation target."""

    id: str
    action: str
    target: str | None = None
    text: str | None = None
    image: str | None = None
    selector: str | None = None
    description: str | None = None


@dataclass(frozen=True)
class SiteFlowStep:
    """One playbook-authored step before it is compiled into the task DSL."""

    id: str
    action: str
    landmark: str | None = None
    target: str | None = None
    text: str | None = None
    image: str | None = None
    requires_confirmation: bool = False
    sensitive_category: str | None = None
    timeout_seconds: float | None = None
    retry: int | None = None


@dataclass(frozen=True)
class BlockedState:
    """Known public-site state that must stop or redirect safe execution."""

    id: str
    detector: str
    reason: str
    recovery_hint: str | None = None


@dataclass(frozen=True)
class SiteFlow:
    """Named website flow that can be compiled into a DeskPilot task."""

    id: str
    description: str | None = None
    timeout_seconds: float | None = None
    retry: int | None = None
    confidence_threshold: float | None = None
    search_region: TaskRegion | None = None
    steps: tuple[SiteFlowStep, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SitePlaybook:
    """Validated website navigation playbook loaded from YAML."""

    site_id: str
    version: str
    domains: tuple[SiteDomain, ...]
    allowed_window_titles: tuple[str, ...]
    landmarks: tuple[SiteLandmark, ...] = field(default_factory=tuple)
    flows: tuple[SiteFlow, ...] = field(default_factory=tuple)
    blocked_states: tuple[BlockedState, ...] = field(default_factory=tuple)
    source_path: str | None = None


class SiteTaskCompiler:
    """Compiles validated website playbook flows into DeskPilot tasks."""

    def compile(self, playbook: SitePlaybook, flow_id: str) -> TaskDefinition:
        validate_site_playbook(playbook)
        flow = resolve_site_flow(playbook, flow_id)
        steps: list[TaskStep] = []
        for site_step in flow.steps:
            compiled_step = _compile_site_step(playbook, flow, site_step)
            steps.extend(_blocked_state_checks(playbook, compiled_step))
            steps.append(compiled_step)
        return TaskDefinition(
            name=f"{playbook.site_id}:{flow.id}",
            allowed_windows=_compiled_allowed_windows(playbook),
            timeout_seconds=flow.timeout_seconds or 30.0,
            steps=tuple(steps),
            config_overrides=ConfigOverrides(
                confidence_threshold=flow.confidence_threshold,
            ),
            metadata=_compiled_task_metadata(playbook, flow, tuple(steps)),
        )


def load_site_playbook(playbook_path: Path) -> SitePlaybook:
    """Load one website navigation playbook YAML file."""

    if not playbook_path.exists():
        raise SitePlaybookValidationError(f"playbook file not found: {playbook_path}")
    loaded = yaml.safe_load(playbook_path.read_text(encoding="utf-8"))
    data = _mapping(loaded, "playbook file must contain a mapping")
    playbook = _playbook_from_mapping(data, playbook_path)
    validate_site_playbook(playbook)
    return playbook


def load_site_playbooks(playbook_dir: Path = Path("navigation_playbooks")) -> tuple[
    SitePlaybook,
    ...,
]:
    """Load every YAML playbook in a catalog directory."""

    if not playbook_dir.exists():
        raise SitePlaybookValidationError(
            f"playbook directory not found: {playbook_dir}",
        )
    return tuple(
        load_site_playbook(path)
        for path in sorted(playbook_dir.glob("*.yaml"))
        if not path.name.startswith("_")
    )


def resolve_site_flow(playbook: SitePlaybook, flow_id: str) -> SiteFlow:
    """Return one flow from a validated site playbook."""

    for flow in playbook.flows:
        if flow.id == flow_id:
            return flow
    raise SitePlaybookValidationError(f"unknown flow: {flow_id}")


def validate_site_playbook(playbook: SitePlaybook) -> None:
    """Validate public-site schema rules before a playbook can be compiled."""

    errors: list[str] = []
    if not _is_slug(playbook.site_id):
        errors.append("site_id is required and must be slug-safe")
    if not playbook.domains:
        errors.append("at least one domain is required")
    for domain in playbook.domains:
        if not domain.host:
            errors.append("domain host is required")
    if not playbook.allowed_window_titles:
        errors.append("at least one allowed window-title pattern is required")
    for title in playbook.allowed_window_titles:
        if not title:
            errors.append("allowed window-title pattern must not be empty")

    landmark_ids = {landmark.id for landmark in playbook.landmarks if landmark.id}
    errors.extend(_validate_landmarks(playbook.landmarks))
    errors.extend(_validate_unique_ids("flow", (flow.id for flow in playbook.flows)))
    for flow in playbook.flows:
        errors.extend(_validate_flow(flow, landmark_ids))
    errors.extend(_validate_blocked_states(playbook.blocked_states))

    if errors:
        raise SitePlaybookValidationError("; ".join(errors))


def _playbook_from_mapping(
    data: Mapping[str, object],
    source_path: Path,
) -> SitePlaybook:
    return SitePlaybook(
        site_id=str(data.get("site_id", "")),
        version=str(data.get("version", "1")),
        domains=tuple(_domain_from_value(item) for item in _sequence(data, "domains")),
        allowed_window_titles=_string_tuple(data.get("allowed_window_titles", ())),
        landmarks=tuple(
            _landmark_from_mapping(item) for item in _sequence(data, "landmarks")
        ),
        flows=tuple(_flow_from_mapping(item) for item in _sequence(data, "flows")),
        blocked_states=tuple(
            _blocked_state_from_mapping(item)
            for item in _sequence(data, "blocked_states")
        ),
        source_path=str(source_path),
    )


def _domain_from_value(value: object) -> SiteDomain:
    if isinstance(value, str):
        return SiteDomain(host=value)
    data = _mapping(value, "each domain must be a string or mapping")
    return SiteDomain(
        host=str(data.get("host", "")),
        include_subdomains=_optional_bool(data.get("include_subdomains"), True),
        purpose=_optional_str(data.get("purpose")),
    )


def _landmark_from_mapping(value: object) -> SiteLandmark:
    data = _mapping(value, "each landmark must be a mapping")
    return SiteLandmark(
        id=str(data.get("id", "")),
        action=str(data.get("action", "")),
        target=_optional_str(data.get("target")),
        text=_optional_str(data.get("text")),
        image=_optional_str(data.get("image")),
        selector=_optional_str(data.get("selector")),
        description=_optional_str(data.get("description")),
    )


def _flow_from_mapping(value: object) -> SiteFlow:
    data = _mapping(value, "each flow must be a mapping")
    return SiteFlow(
        id=str(data.get("id", "")),
        description=_optional_str(data.get("description")),
        timeout_seconds=_optional_float(data.get("timeout_seconds")),
        retry=_optional_int(data.get("retry")),
        confidence_threshold=_optional_float(data.get("confidence_threshold")),
        search_region=_optional_region(data.get("search_region")),
        steps=tuple(_flow_step_from_mapping(item) for item in _sequence(data, "steps")),
    )


def _flow_step_from_mapping(value: object) -> SiteFlowStep:
    data = _mapping(value, "each flow step must be a mapping")
    return SiteFlowStep(
        id=str(data.get("id", "")),
        action=str(data.get("action", "")),
        landmark=_optional_str(data.get("landmark")),
        target=_optional_str(data.get("target")),
        text=_optional_str(data.get("text")),
        image=_optional_str(data.get("image")),
        requires_confirmation=_optional_bool(data.get("requires_confirmation"), False),
        sensitive_category=_optional_str(data.get("sensitive_category")),
        timeout_seconds=_optional_float(data.get("timeout_seconds")),
        retry=_optional_int(data.get("retry")),
    )


def _blocked_state_from_mapping(value: object) -> BlockedState:
    data = _mapping(value, "each blocked state must be a mapping")
    return BlockedState(
        id=str(data.get("id", "")),
        detector=str(data.get("detector", "")),
        reason=str(data.get("reason", "")),
        recovery_hint=_optional_str(data.get("recovery_hint")),
    )


def _compile_site_step(
    playbook: SitePlaybook,
    flow: SiteFlow,
    site_step: SiteFlowStep,
) -> TaskStep:
    landmark = _landmark_by_id(playbook, site_step.landmark)
    image = site_step.image or (landmark.image if landmark else None)
    return TaskStep(
        id=site_step.id,
        action=site_step.action,
        target=site_step.target or _landmark_target(landmark),
        text=site_step.text or (landmark.text if landmark else None),
        image=Path(image) if image else None,
        region=flow.search_region,
        timeout_seconds=site_step.timeout_seconds,
        retry=site_step.retry if site_step.retry is not None else flow.retry,
        requires_confirmation=site_step.requires_confirmation,
        category=_site_step_category(site_step),
    )


def _landmark_by_id(
    playbook: SitePlaybook,
    landmark_id: str | None,
) -> SiteLandmark | None:
    if landmark_id is None:
        return None
    for landmark in playbook.landmarks:
        if landmark.id == landmark_id:
            return landmark
    raise SitePlaybookValidationError(f"landmark does not exist: {landmark_id}")


def _landmark_target(landmark: SiteLandmark | None) -> str | None:
    if landmark is None:
        return None
    return landmark.target or landmark.text or landmark.selector


def _site_step_category(site_step: SiteFlowStep) -> str | None:
    if site_step.sensitive_category is None:
        return None
    return "submission"


def _blocked_state_checks(
    playbook: SitePlaybook,
    step: TaskStep,
) -> tuple[TaskStep, ...]:
    if not step.requires_confirmation:
        return ()
    checks: list[TaskStep] = []
    for blocked_state in playbook.blocked_states:
        detector_text = _detector_text(blocked_state.detector)
        if detector_text is None:
            continue
        checks.append(
            TaskStep(
                id=f"blocked-state-{blocked_state.id}-before-{step.id}",
                action="wait_for",
                target=detector_text,
                verify=VerificationDefinition(
                    type="not_visible_text",
                    text=detector_text,
                ),
                timeout_seconds=step.timeout_seconds,
                retry=0,
                category="verification",
                metadata={
                    "site_id": playbook.site_id,
                    "site_blocked_state_id": blocked_state.id,
                    "site_blocked_state_detector": blocked_state.detector,
                    "site_blocked_state_reason": blocked_state.reason,
                    "site_blocked_state_check": True,
                },
            ),
        )
    return tuple(checks)


def _detector_text(detector: str) -> str | None:
    prefix = "visible_text:"
    if detector.startswith(prefix):
        return detector[len(prefix) :].strip()
    return None


def _compiled_allowed_windows(playbook: SitePlaybook) -> tuple[str, ...]:
    windows = [*playbook.allowed_window_titles]
    windows.extend(domain.host for domain in playbook.domains)
    return tuple(dict.fromkeys(windows))


def _compiled_task_metadata(
    playbook: SitePlaybook,
    flow: SiteFlow,
    steps: tuple[TaskStep, ...],
) -> dict[str, object]:
    return {
        "site_id": playbook.site_id,
        "site_flow_id": flow.id,
        "site_playbook_version": playbook.version,
        "site_domains": [domain.host for domain in playbook.domains],
        "site_sensitive_step_ids": [
            step.id for step in steps if step.requires_confirmation
        ],
        "site_blocked_state_ids": [state.id for state in playbook.blocked_states],
        "site_playbook_validation_status": "passed",
        "site_compilation_source": "in_memory",
        "site_compiled_step_count": len(steps),
        "site_compiled_task_summary": (
            f"{playbook.site_id}:{flow.id} ({len(steps)} steps)"
        ),
    }


def _validate_landmarks(landmarks: tuple[SiteLandmark, ...]) -> list[str]:
    errors = _validate_unique_ids(
        "landmark",
        (landmark.id for landmark in landmarks),
    )
    for landmark in landmarks:
        if landmark.action not in SUPPORTED_ACTIONS:
            errors.append(f"unknown action: {landmark.action}")
    return errors


def _validate_flow(
    flow: SiteFlow,
    landmark_ids: set[str],
) -> list[str]:
    errors: list[str] = []
    if not flow.id:
        errors.append("flow id is required")
    errors.extend(_validate_unique_ids("step", (step.id for step in flow.steps)))
    for step in flow.steps:
        if not step.id:
            errors.append(f"flow {flow.id} step id is required")
        if step.action not in SUPPORTED_ACTIONS:
            errors.append(f"unknown action: {step.action}")
        if step.landmark is not None and step.landmark not in landmark_ids:
            errors.append(f"step {step.id} landmark does not exist: {step.landmark}")
        if step.retry is not None and step.retry < 0:
            errors.append(f"step {step.id} retry must not be negative")
        if step.timeout_seconds is not None and step.timeout_seconds <= 0:
            errors.append(f"step {step.id} timeout_seconds must be greater than zero")
        # A sensitive category is an author-declared safety intent; validation
        # must enforce confirmation even before the compiler sees the step.
        if step.sensitive_category is not None:
            if step.sensitive_category not in _SENSITIVE_CATEGORIES:
                errors.append(f"unknown sensitive category: {step.sensitive_category}")
            if not step.requires_confirmation:
                errors.append(
                    f"step {step.id} sensitive steps require confirmation",
                )
    return errors


def _optional_region(value: object) -> TaskRegion | None:
    if value is None:
        return None
    data = _mapping(value, "search_region must be a mapping")
    region = TaskRegion(
        x=_required_int(data, "x"),
        y=_required_int(data, "y"),
        width=_required_int(data, "width"),
        height=_required_int(data, "height"),
    )
    if region.width <= 0 or region.height <= 0:
        raise SitePlaybookValidationError(
            "search_region width and height must be greater than zero",
        )
    return region


def _required_int(data: Mapping[str, object], key: str) -> int:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise SitePlaybookValidationError(f"search_region.{key} must be an integer")
    return value


def _validate_blocked_states(
    blocked_states: tuple[BlockedState, ...],
) -> list[str]:
    errors = _validate_unique_ids(
        "blocked state",
        (state.id for state in blocked_states),
    )
    for state in blocked_states:
        if not state.detector:
            errors.append(f"blocked state {state.id} detector is required")
        if not state.reason:
            errors.append(f"blocked state {state.id} reason is required")
    return errors


def _validate_unique_ids(label: str, ids: Iterable[str]) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for item_id in ids:
        if not item_id:
            errors.append(f"{label} id is required")
        elif item_id in seen:
            errors.append(f"duplicate {label} id: {item_id}")
        seen.add(item_id)
    return errors


def _is_slug(value: str) -> bool:
    return bool(_SLUG_PATTERN.fullmatch(value))


def _mapping(value: object, message: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise SitePlaybookValidationError(message)
    return cast(Mapping[str, object], value)


def _sequence(data: Mapping[str, object], key: str) -> Sequence[object]:
    value = data.get(key, ())
    if value in (None, ()):
        return ()
    if not isinstance(value, list):
        raise SitePlaybookValidationError(f"{key} must be a list")
    return value


def _string_tuple(value: object) -> tuple[str, ...]:
    if value in (None, ()):
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise SitePlaybookValidationError(
            "allowed_window_titles must be a list of strings",
        )
    return tuple(value)


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise SitePlaybookValidationError("string field must be a string")
    return value


def _optional_bool(value: object, default: bool) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise SitePlaybookValidationError("boolean field must be true or false")
    return value


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise SitePlaybookValidationError("numeric field must be a number")
    return float(value)


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise SitePlaybookValidationError("integer field must be an integer")
    return value
