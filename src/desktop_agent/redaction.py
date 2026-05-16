"""Redaction policy schemas for local evidence and reports."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

EVIDENCE_MODES: frozenset[str] = frozenset({"full", "redacted", "metadata_only"})
SCREENSHOT_REDACTION_MODES: frozenset[str] = frozenset(
    {"full", "blur_sensitive_zones", "metadata_only"},
)
TEXT_REDACTION_MODES: frozenset[str] = frozenset({"full", "mask", "suppress"})
CONTENT_VARIABLE_REDACTION_MODES: frozenset[str] = frozenset(
    {"fingerprint_only", "mask_names", "suppress"},
)
VIDEO_REDACTION_MODES: frozenset[str] = frozenset(
    {"full", "redacted", "disabled"},
)
REPORT_REDACTION_MODES: frozenset[str] = frozenset({"full", "redacted"})


@dataclass(frozen=True)
class SensitiveZone:
    """Coordinate region that can be blurred in screenshot evidence."""

    id: str
    x: int
    y: int
    width: int
    height: int
    reason: str = "sensitive"

    def metadata(self) -> dict[str, object]:
        return {
            "id": self.id,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ScreenshotBlurMask:
    """Blur mask derived from a sensitive screenshot zone."""

    zone_id: str
    bounds: SensitiveZone
    reason: str

    def metadata(self) -> dict[str, object]:
        return {
            "zone_id": self.zone_id,
            "bounds": self.bounds.metadata(),
            "reason": self.reason,
        }


@dataclass(frozen=True)
class RedactionPolicy:
    """Resolved redaction policy for global, routine, or run scope."""

    evidence_mode: str = "full"
    screenshots: str = "full"
    ocr_text: str = "full"
    typed_text: str = "full"
    content_variables: str = "fingerprint_only"
    video: str = "full"
    reports: str = "full"
    sensitive_zones: tuple[SensitiveZone, ...] = ()

    def metadata(self) -> dict[str, object]:
        return {
            "evidence_mode": self.evidence_mode,
            "screenshots": self.screenshots,
            "ocr_text": self.ocr_text,
            "typed_text": self.typed_text,
            "content_variables": self.content_variables,
            "video": self.video,
            "reports": self.reports,
            "sensitive_zones": [zone.metadata() for zone in self.sensitive_zones],
        }


def redaction_policy_from_mapping(data: Mapping[str, object]) -> RedactionPolicy:
    """Parse a redaction policy mapping into a typed schema object."""
    defaults = RedactionPolicy()
    return RedactionPolicy(
        evidence_mode=_optional_string(data, "evidence_mode", defaults.evidence_mode),
        screenshots=_optional_string(data, "screenshots", defaults.screenshots),
        ocr_text=_optional_string(data, "ocr_text", defaults.ocr_text),
        typed_text=_optional_string(data, "typed_text", defaults.typed_text),
        content_variables=_optional_string(
            data,
            "content_variables",
            defaults.content_variables,
        ),
        video=_optional_string(data, "video", defaults.video),
        reports=_optional_string(data, "reports", defaults.reports),
        sensitive_zones=_sensitive_zones_from_value(data.get("sensitive_zones")),
    )


def screenshot_blur_masks(policy: RedactionPolicy) -> tuple[ScreenshotBlurMask, ...]:
    """Return screenshot blur masks only when the policy requests zone blurring."""
    if policy.screenshots != "blur_sensitive_zones":
        return ()
    return tuple(
        ScreenshotBlurMask(
            zone_id=zone.id,
            bounds=zone,
            reason=zone.reason,
        )
        for zone in policy.sensitive_zones
    )


def mask_typed_text(text: str, policy: RedactionPolicy) -> str | None:
    """Return a masked text placeholder according to the typed-text policy."""
    if policy.typed_text == "mask":
        return "*" * len(text)
    if policy.typed_text == "suppress":
        return None
    return text


def typed_text_redaction_metadata(
    text: str,
    policy: RedactionPolicy,
) -> dict[str, object]:
    """Return trace-safe typed-text redaction metadata without changing input."""
    metadata: dict[str, object] = {
        "typed_text_redaction": policy.typed_text,
        "typed_text_suppressed": policy.typed_text == "suppress",
    }
    if policy.typed_text != "full":
        metadata["typed_text_value"] = mask_typed_text(text, policy)
    return metadata


def mask_content_variable_names(
    variable_names: Sequence[str],
    policy: RedactionPolicy,
) -> tuple[str, ...]:
    """Mask or suppress content-variable names for trace/report metadata."""
    if policy.content_variables == "suppress":
        return ()
    if policy.content_variables == "mask_names":
        return tuple(f"variable_{index}" for index, _ in enumerate(variable_names, 1))
    return tuple(variable_names)


def content_variable_redaction_metadata(
    variable_names: Sequence[str],
    policy: RedactionPolicy,
) -> dict[str, object]:
    """Return metadata that explains how content-variable names were handled."""
    return {
        "content_variable_names": list(
            mask_content_variable_names(variable_names, policy),
        ),
        "content_variable_count": len(variable_names),
        "content_variable_name_redaction": policy.content_variables,
        "content_variables_redacted": True,
    }


def should_capture_screenshot(policy: RedactionPolicy, *, save_enabled: bool) -> bool:
    """Return whether screenshot files should be written under this policy."""
    if not save_enabled:
        return False
    if policy.evidence_mode == "metadata_only":
        return False
    return policy.screenshots != "metadata_only"


def should_save_ocr_text(policy: RedactionPolicy, *, save_enabled: bool) -> bool:
    """Return whether OCR text artifacts should be written under this policy."""
    if not save_enabled:
        return False
    if policy.evidence_mode == "metadata_only":
        return False
    return policy.ocr_text != "suppress"


def mask_ocr_text(text: str, policy: RedactionPolicy) -> str | None:
    """Return OCR text according to the configured OCR redaction mode."""
    if policy.ocr_text == "mask":
        return "*" * len(text)
    if policy.ocr_text == "suppress":
        return None
    return text


def validate_redaction_policy(
    policy: RedactionPolicy,
    *,
    prefix: str = "redaction_policy",
) -> list[str]:
    """Return schema errors for a redaction policy without applying it."""
    errors: list[str] = []
    _validate_choice(
        policy.evidence_mode,
        EVIDENCE_MODES,
        f"{prefix}.evidence_mode",
        errors,
    )
    _validate_choice(
        policy.screenshots,
        SCREENSHOT_REDACTION_MODES,
        f"{prefix}.screenshots",
        errors,
    )
    _validate_choice(
        policy.ocr_text,
        TEXT_REDACTION_MODES,
        f"{prefix}.ocr_text",
        errors,
    )
    _validate_choice(
        policy.typed_text,
        TEXT_REDACTION_MODES,
        f"{prefix}.typed_text",
        errors,
    )
    _validate_choice(
        policy.content_variables,
        CONTENT_VARIABLE_REDACTION_MODES,
        f"{prefix}.content_variables",
        errors,
    )
    _validate_choice(policy.video, VIDEO_REDACTION_MODES, f"{prefix}.video", errors)
    _validate_choice(
        policy.reports,
        REPORT_REDACTION_MODES,
        f"{prefix}.reports",
        errors,
    )
    errors.extend(_sensitive_zone_errors(policy.sensitive_zones, prefix))
    return errors


def _sensitive_zones_from_value(value: object) -> tuple[SensitiveZone, ...]:
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError("redaction_policy.sensitive_zones must be a list")
    zones: list[SensitiveZone] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise ValueError(
                f"redaction_policy.sensitive_zones[{index}] must be a mapping",
            )
        zones.append(_sensitive_zone_from_mapping(item, index))
    return tuple(zones)


def _sensitive_zone_from_mapping(
    data: Mapping[object, object],
    index: int,
) -> SensitiveZone:
    prefix = f"redaction_policy.sensitive_zones[{index}]"
    return SensitiveZone(
        id=_required_zone_string(data, "id", prefix),
        x=_required_zone_int(data, "x", prefix),
        y=_required_zone_int(data, "y", prefix),
        width=_required_zone_int(data, "width", prefix),
        height=_required_zone_int(data, "height", prefix),
        reason=_optional_zone_string(data, "reason", "sensitive", prefix),
    )


def _sensitive_zone_errors(
    zones: Sequence[SensitiveZone],
    prefix: str,
) -> list[str]:
    errors: list[str] = []
    seen_ids: set[str] = set()
    for index, zone in enumerate(zones):
        field_prefix = f"{prefix}.sensitive_zones[{index}]"
        if not zone.id.strip():
            errors.append(f"{field_prefix}.id is required")
        if zone.id in seen_ids:
            errors.append(f"{field_prefix}.id must be unique")
        seen_ids.add(zone.id)
        if zone.x < 0 or zone.y < 0:
            errors.append(f"{field_prefix}.x and y must not be negative")
        if zone.width <= 0 or zone.height <= 0:
            errors.append(f"{field_prefix}.width and height must be greater than zero")
        if not zone.reason.strip():
            errors.append(f"{field_prefix}.reason is required")
    return errors


def _optional_string(
    data: Mapping[str, object],
    key: str,
    default: str,
) -> str:
    value = data.get(key, default)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"redaction_policy.{key} must be a non-empty string")
    return value.strip()


def _required_zone_string(
    data: Mapping[object, object],
    key: str,
    prefix: str,
) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{prefix}.{key} must be a non-empty string")
    return value.strip()


def _optional_zone_string(
    data: Mapping[object, object],
    key: str,
    default: str,
    prefix: str,
) -> str:
    value = data.get(key, default)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{prefix}.{key} must be a non-empty string")
    return value.strip()


def _required_zone_int(
    data: Mapping[object, object],
    key: str,
    prefix: str,
) -> int:
    value = data.get(key)
    if not isinstance(value, int):
        raise ValueError(f"{prefix}.{key} must be an integer")
    return value


def _validate_choice(
    value: str,
    choices: frozenset[str],
    field_name: str,
    errors: list[str],
) -> None:
    if value not in choices:
        errors.append(f"{field_name} must be one of {', '.join(sorted(choices))}")
