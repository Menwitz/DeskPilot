"""Import and export operations for validated local routine packs."""

from __future__ import annotations

import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

from desktop_agent.routine_pack_manifest import (
    ROUTINE_PACK_MANIFEST_FILENAME,
    RoutinePackManifest,
    RoutinePackManifestError,
    RoutinePackTrustWarning,
    load_routine_pack_manifest,
    load_routine_pack_manifests,
    routine_pack_trust_warnings,
)


class RoutinePackOperationError(ValueError):
    """Raised when a routine pack import or export cannot be completed."""


@dataclass(frozen=True)
class RoutinePackImportResult:
    """Result of installing one routine pack into a local pack root."""

    manifest: RoutinePackManifest
    source_path: Path
    installed_path: Path
    replaced_existing: bool
    trust_warnings: tuple[RoutinePackTrustWarning, ...] = ()


@dataclass(frozen=True)
class RoutinePackExportResult:
    """Result of exporting one installed routine pack."""

    manifest: RoutinePackManifest
    source_path: Path
    output_path: Path
    archive: bool
    trust_warnings: tuple[RoutinePackTrustWarning, ...] = ()


@dataclass(frozen=True)
class RoutinePackRemoveResult:
    """Result of removing one installed routine pack."""

    manifest: RoutinePackManifest
    removed_path: Path


def import_routine_pack(
    source: Path,
    routine_pack_root: Path,
    *,
    replace: bool = False,
) -> RoutinePackImportResult:
    """Validate and install a routine pack directory or zip archive."""
    if source.suffix.lower() == ".zip":
        with tempfile.TemporaryDirectory() as temp_dir:
            extracted_root = Path(temp_dir)
            _extract_pack_archive(source, extracted_root)
            pack_dir = _resolve_extracted_pack_dir(extracted_root)
            return _import_routine_pack_dir(
                pack_dir,
                routine_pack_root,
                original_source=source,
                replace=replace,
            )
    return _import_routine_pack_dir(
        source,
        routine_pack_root,
        original_source=source,
        replace=replace,
    )


def export_routine_pack(
    routine_pack_root: Path,
    pack_id: str,
    output: Path,
    *,
    replace: bool = False,
) -> RoutinePackExportResult:
    """Validate and export one installed routine pack as a directory or zip."""
    manifest = _manifest_by_id(routine_pack_root, pack_id)
    if manifest.source_path is None:
        raise RoutinePackOperationError(f"routine pack has no source path: {pack_id}")
    source_dir = manifest.source_path.parent
    if output.exists() and not replace:
        raise RoutinePackOperationError(f"export output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.suffix.lower() == ".zip":
        if output.exists():
            output.unlink()
        _write_pack_archive(source_dir, output)
        return RoutinePackExportResult(
            manifest=manifest,
            source_path=source_dir,
            output_path=output,
            archive=True,
            trust_warnings=routine_pack_trust_warnings(manifest),
        )
    if output.exists():
        shutil.rmtree(output)
    shutil.copytree(source_dir, output)
    return RoutinePackExportResult(
        manifest=manifest,
        source_path=source_dir,
        output_path=output,
        archive=False,
        trust_warnings=routine_pack_trust_warnings(manifest),
    )


def remove_routine_pack(
    routine_pack_root: Path,
    pack_id: str,
) -> RoutinePackRemoveResult:
    """Validate and remove one installed routine pack directory."""
    manifest = _manifest_by_id(routine_pack_root, pack_id)
    if manifest.source_path is None:
        raise RoutinePackOperationError(f"routine pack has no source path: {pack_id}")
    pack_dir = manifest.source_path.parent
    shutil.rmtree(pack_dir)
    return RoutinePackRemoveResult(manifest=manifest, removed_path=pack_dir)


def _import_routine_pack_dir(
    source_dir: Path,
    routine_pack_root: Path,
    *,
    original_source: Path,
    replace: bool,
) -> RoutinePackImportResult:
    manifest = load_routine_pack_manifest(source_dir)
    destination = routine_pack_root / manifest.id
    replaced_existing = destination.exists()
    if replaced_existing and not replace:
        raise RoutinePackOperationError(
            f"routine pack already installed: {manifest.id}",
        )
    routine_pack_root.mkdir(parents=True, exist_ok=True)
    if replaced_existing:
        shutil.rmtree(destination)
    shutil.copytree(source_dir, destination)
    installed_manifest = load_routine_pack_manifest(destination)
    return RoutinePackImportResult(
        manifest=installed_manifest,
        source_path=original_source,
        installed_path=destination,
        replaced_existing=replaced_existing,
        trust_warnings=routine_pack_trust_warnings(installed_manifest),
    )


def _manifest_by_id(root: Path, pack_id: str) -> RoutinePackManifest:
    for manifest in load_routine_pack_manifests(root):
        if manifest.id == pack_id:
            return manifest
    raise RoutinePackOperationError(f"unknown routine pack: {pack_id}")


def _extract_pack_archive(source: Path, destination: Path) -> None:
    if not source.exists():
        raise RoutinePackOperationError(f"routine pack archive not found: {source}")
    with zipfile.ZipFile(source) as archive:
        for member in archive.namelist():
            path = Path(member)
            if path.is_absolute() or ".." in path.parts:
                raise RoutinePackOperationError(
                    f"unsafe routine pack archive member: {member}",
                )
        archive.extractall(destination)


def _resolve_extracted_pack_dir(extracted_root: Path) -> Path:
    if (extracted_root / ROUTINE_PACK_MANIFEST_FILENAME).exists():
        return extracted_root
    candidates = sorted(
        path.parent
        for path in extracted_root.glob(f"*/{ROUTINE_PACK_MANIFEST_FILENAME}")
    )
    if len(candidates) != 1:
        raise RoutinePackManifestError(
            "routine pack archive must contain exactly one manifest",
        )
    return candidates[0]


def _write_pack_archive(source_dir: Path, output: Path) -> None:
    # Store the pack under its directory name so zip import has a stable root.
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source_dir.rglob("*")):
            if path.is_file():
                archive.write(
                    path,
                    Path(source_dir.name) / path.relative_to(source_dir),
                )
