"""Routine pack manifest schema for trusted local routine ecosystems."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import yaml

PACK_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
ROUTINE_PACK_MANIFEST_FILENAME = "routine-pack.yaml"
SUPPORTED_PACK_SCHEMA_VERSIONS: frozenset[str] = frozenset({"1"})
SUPPORTED_PACK_TRUST_LEVELS: frozenset[str] = frozenset(
    {"builtin", "trusted_local", "unverified_local"},
)
SUPPORTED_PACK_SAFETY_CLASSES: frozenset[str] = frozenset(
    {"low", "medium", "high", "sensitive"},
)


class RoutinePackManifestError(ValueError):
    """Raised when a routine pack manifest cannot be trusted or loaded."""


@dataclass(frozen=True)
class RoutinePackSafetyMetadata:
    """Safety declaration made by a routine pack manifest."""

    max_safety_class: str
    requires_review: bool
    external_mutation_allowed: bool
    approval_required: bool

    def metadata(self) -> dict[str, object]:
        return {
            "max_safety_class": self.max_safety_class,
            "requires_review": self.requires_review,
            "external_mutation_allowed": self.external_mutation_allowed,
            "approval_required": self.approval_required,
        }


@dataclass(frozen=True)
class RoutinePackProofExpectations:
    """Proof artifacts expected before a pack is promoted."""

    windows_proof_required: bool
    expected_artifacts: tuple[str, ...]

    def metadata(self) -> dict[str, object]:
        return {
            "windows_proof_required": self.windows_proof_required,
            "expected_artifacts": list(self.expected_artifacts),
        }


@dataclass(frozen=True)
class RoutinePackTrustWarning:
    """Operator-facing warning for a routine pack that needs review."""

    pack_id: str
    trust_level: str
    message: str

    def metadata(self) -> dict[str, object]:
        return {
            "pack_id": self.pack_id,
            "trust_level": self.trust_level,
            "message": self.message,
        }


@dataclass(frozen=True)
class RoutinePackManifest:
    """Reviewed local metadata for one installable routine pack."""

    schema_version: str
    id: str
    name: str
    description: str
    version: str
    publisher: str
    trust_level: str
    routine_globs: tuple[str, ...]
    docs: tuple[str, ...]
    fixtures: tuple[str, ...]
    tests: tuple[str, ...]
    safety: RoutinePackSafetyMetadata
    proof: RoutinePackProofExpectations
    source_path: Path | None = None

    def metadata(self) -> dict[str, object]:
        return {
            "pack_schema_version": self.schema_version,
            "pack_id": self.id,
            "pack_name": self.name,
            "pack_version": self.version,
            "pack_publisher": self.publisher,
            "pack_trust_level": self.trust_level,
            "routine_globs": list(self.routine_globs),
            "docs": list(self.docs),
            "fixtures": list(self.fixtures),
            "tests": list(self.tests),
            "safety": self.safety.metadata(),
            "proof": self.proof.metadata(),
            "trust_warnings": [
                warning.metadata()
                for warning in routine_pack_trust_warnings(self)
            ],
        }


def load_routine_pack_manifest(path: Path) -> RoutinePackManifest:
    """Load and validate one routine-pack manifest YAML file or directory."""
    manifest_path = (
        path / ROUTINE_PACK_MANIFEST_FILENAME if path.is_dir() else path
    )
    if not manifest_path.exists():
        raise RoutinePackManifestError(f"routine pack manifest not found: {path}")
    loaded = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest = routine_pack_manifest_from_mapping(
        _mapping(loaded, "routine pack manifest must contain a mapping"),
        source_path=manifest_path,
    )
    validate_routine_pack_manifest(manifest)
    return manifest


def load_routine_pack_manifests(root: Path) -> tuple[RoutinePackManifest, ...]:
    """Load every routine-pack manifest under a root directory."""
    if not root.exists():
        raise RoutinePackManifestError(f"routine pack root not found: {root}")
    manifests = tuple(
        load_routine_pack_manifest(path)
        for path in sorted(root.glob(f"*/{ROUTINE_PACK_MANIFEST_FILENAME}"))
    )
    duplicate_ids = _duplicate_pack_ids(manifests)
    if duplicate_ids:
        raise RoutinePackManifestError(
            "duplicate routine pack id: " + ", ".join(duplicate_ids),
        )
    return manifests


def routine_pack_manifest_from_mapping(
    data: dict[str, object],
    *,
    source_path: Path | None = None,
) -> RoutinePackManifest:
    """Parse a manifest mapping into a typed routine-pack schema object."""
    manifest = RoutinePackManifest(
        schema_version=_required_string(data, "pack_schema_version"),
        id=_required_string(data, "id"),
        name=_required_string(data, "name"),
        description=_required_string(data, "description"),
        version=_required_string(data, "version"),
        publisher=_required_string(data, "publisher"),
        trust_level=_required_string(data, "trust_level"),
        routine_globs=_string_tuple(data.get("routine_globs"), "routine_globs"),
        docs=_string_tuple(data.get("docs"), "docs"),
        fixtures=_string_tuple(data.get("fixtures"), "fixtures"),
        tests=_string_tuple(data.get("tests"), "tests"),
        safety=_safety_metadata_from_value(data.get("safety")),
        proof=_proof_expectations_from_value(data.get("proof")),
        source_path=source_path,
    )
    validate_routine_pack_manifest(manifest)
    return manifest


def validate_routine_pack_manifest(manifest: RoutinePackManifest) -> None:
    """Validate one manifest before import, listing, or report generation."""
    errors: list[str] = []
    if manifest.schema_version not in SUPPORTED_PACK_SCHEMA_VERSIONS:
        errors.append(f"unsupported pack_schema_version: {manifest.schema_version}")
    if not PACK_ID_PATTERN.fullmatch(manifest.id):
        errors.append("id is required and must be slug-safe")
    if manifest.trust_level not in SUPPORTED_PACK_TRUST_LEVELS:
        errors.append(f"unsupported trust_level: {manifest.trust_level}")
    if not manifest.routine_globs:
        errors.append("routine_globs must not be empty")
    if manifest.safety.max_safety_class not in SUPPORTED_PACK_SAFETY_CLASSES:
        errors.append(
            f"unsupported safety.max_safety_class: {manifest.safety.max_safety_class}",
        )
    errors.extend(_relative_path_errors("routine_globs", manifest.routine_globs))
    errors.extend(_relative_path_errors("docs", manifest.docs))
    errors.extend(_relative_path_errors("fixtures", manifest.fixtures))
    errors.extend(_relative_path_errors("tests", manifest.tests))
    errors.extend(
        _relative_path_errors(
            "proof.expected_artifacts",
            manifest.proof.expected_artifacts,
        ),
    )
    if errors:
        raise RoutinePackManifestError("; ".join(errors))


def routine_pack_trust_warnings(
    manifest: RoutinePackManifest,
) -> tuple[RoutinePackTrustWarning, ...]:
    """Return review warnings for packs that should not be silently trusted."""
    warnings: list[RoutinePackTrustWarning] = []
    if manifest.trust_level == "unverified_local":
        warnings.append(
            RoutinePackTrustWarning(
                pack_id=manifest.id,
                trust_level=manifest.trust_level,
                message=(
                    "pack is unverified; review manifest, routines, docs, tests, "
                    "and proof expectations before installing or running"
                ),
            ),
        )
    if (
        manifest.safety.external_mutation_allowed
        and not manifest.safety.approval_required
    ):
        warnings.append(
            RoutinePackTrustWarning(
                pack_id=manifest.id,
                trust_level=manifest.trust_level,
                message=(
                    "pack allows external mutations without declaring approval "
                    "requirements"
                ),
            ),
        )
    return tuple(warnings)


def _safety_metadata_from_value(value: object) -> RoutinePackSafetyMetadata:
    data = _mapping(value, "safety must be a mapping")
    return RoutinePackSafetyMetadata(
        max_safety_class=_required_string(data, "max_safety_class"),
        requires_review=_required_bool(data, "requires_review"),
        external_mutation_allowed=_required_bool(
            data,
            "external_mutation_allowed",
        ),
        approval_required=_required_bool(data, "approval_required"),
    )


def _proof_expectations_from_value(value: object) -> RoutinePackProofExpectations:
    data = _mapping(value, "proof must be a mapping")
    return RoutinePackProofExpectations(
        windows_proof_required=_required_bool(data, "windows_proof_required"),
        expected_artifacts=_string_tuple(
            data.get("expected_artifacts"),
            "proof.expected_artifacts",
        ),
    )


def _duplicate_pack_ids(
    manifests: tuple[RoutinePackManifest, ...],
) -> tuple[str, ...]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for manifest in manifests:
        if manifest.id in seen:
            duplicates.add(manifest.id)
        seen.add(manifest.id)
    return tuple(sorted(duplicates))


def _relative_path_errors(field_name: str, values: tuple[str, ...]) -> list[str]:
    errors: list[str] = []
    for value in values:
        path = Path(value)
        if path.is_absolute() or ".." in path.parts:
            errors.append(f"{field_name} entries must be relative pack paths")
    return errors


def _mapping(value: object, message: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise RoutinePackManifestError(message)
    return cast(dict[str, object], value)


def _required_string(data: dict[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise RoutinePackManifestError(f"{key} is required")
    return value


def _required_bool(data: dict[str, object], key: str) -> bool:
    value = data.get(key)
    if not isinstance(value, bool):
        raise RoutinePackManifestError(f"{key} must be a boolean")
    return value


def _string_tuple(value: object, key: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list | tuple):
        raise RoutinePackManifestError(f"{key} must be a list")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item:
            raise RoutinePackManifestError(f"{key} must contain non-empty strings")
        result.append(item)
    return tuple(result)
