"""Website navigation playbook contracts and validation helpers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import yaml


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
    search_region: str | None = None
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


def load_site_playbook(playbook_path: Path) -> SitePlaybook:
    """Load one website navigation playbook YAML file."""

    if not playbook_path.exists():
        raise SitePlaybookValidationError(f"playbook file not found: {playbook_path}")
    loaded = yaml.safe_load(playbook_path.read_text(encoding="utf-8"))
    data = _mapping(loaded, "playbook file must contain a mapping")
    return _playbook_from_mapping(data, playbook_path)


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
        search_region=_optional_str(data.get("search_region")),
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
