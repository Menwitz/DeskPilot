"""Redaction policy schemas for local evidence and reports."""

from __future__ import annotations

from collections.abc import Mapping
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
class RedactionPolicy:
    """Resolved redaction policy for global, routine, or run scope."""

    evidence_mode: str = "full"
    screenshots: str = "full"
    ocr_text: str = "full"
    typed_text: str = "full"
    content_variables: str = "fingerprint_only"
    video: str = "full"
    reports: str = "full"

    def metadata(self) -> dict[str, object]:
        return {
            "evidence_mode": self.evidence_mode,
            "screenshots": self.screenshots,
            "ocr_text": self.ocr_text,
            "typed_text": self.typed_text,
            "content_variables": self.content_variables,
            "video": self.video,
            "reports": self.reports,
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
    )


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


def _validate_choice(
    value: str,
    choices: frozenset[str],
    field_name: str,
    errors: list[str],
) -> None:
    if value not in choices:
        errors.append(f"{field_name} must be one of {', '.join(sorted(choices))}")
