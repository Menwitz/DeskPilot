"""Website navigation playbook contracts and validation helpers."""

from __future__ import annotations

from dataclasses import dataclass, field


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
