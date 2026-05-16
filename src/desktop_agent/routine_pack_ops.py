"""Import and export operations for validated local routine packs."""

from __future__ import annotations

import shutil
import tempfile
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import yaml

from desktop_agent.routine_pack_manifest import (
    ROUTINE_PACK_MANIFEST_FILENAME,
    RoutinePackManifest,
    RoutinePackManifestError,
    RoutinePackTrustWarning,
    load_routine_pack_manifest,
    load_routine_pack_manifests,
    routine_pack_trust_warnings,
)
from desktop_agent.routines import RoutineDefinition, load_routine_definition


class RoutinePackOperationError(ValueError):
    """Raised when a routine pack import or export cannot be completed."""


@dataclass(frozen=True)
class RoutinePackConflict:
    """Conflict found before installing or replacing a routine pack."""

    kind: str
    severity: str
    incoming: str
    existing: str
    message: str

    def metadata(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "severity": self.severity,
            "incoming": self.incoming,
            "existing": self.existing,
            "message": self.message,
        }


@dataclass(frozen=True)
class RoutinePackImportResult:
    """Result of installing one routine pack into a local pack root."""

    manifest: RoutinePackManifest
    source_path: Path
    installed_path: Path
    replaced_existing: bool
    trust_warnings: tuple[RoutinePackTrustWarning, ...] = ()
    conflicts: tuple[RoutinePackConflict, ...] = ()


@dataclass(frozen=True)
class RoutinePackExportResult:
    """Result of exporting one installed routine pack."""

    manifest: RoutinePackManifest
    source_path: Path
    output_path: Path
    archive: bool
    trust_warnings: tuple[RoutinePackTrustWarning, ...] = ()
    conflicts: tuple[RoutinePackConflict, ...] = ()


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


def detect_routine_pack_conflicts(
    source: Path,
    routine_pack_root: Path,
) -> tuple[RoutinePackConflict, ...]:
    """Compare an incoming pack with installed packs before installation."""
    incoming_manifest = load_routine_pack_manifest(source)
    installed_manifests = (
        load_routine_pack_manifests(routine_pack_root)
        if routine_pack_root.exists()
        else ()
    )
    incoming_records = _pack_routine_records(incoming_manifest)
    installed_records = tuple(
        record
        for manifest in installed_manifests
        for record in _pack_routine_records(manifest)
    )
    conflicts: list[RoutinePackConflict] = []
    conflicts.extend(_pack_version_conflicts(incoming_manifest, installed_manifests))
    conflicts.extend(_routine_id_conflicts(incoming_records, installed_records))
    conflicts.extend(_routine_input_conflicts(incoming_records, installed_records))
    conflicts.extend(_selector_conflicts(incoming_records, installed_records))
    return tuple(conflicts)


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
    conflicts = detect_routine_pack_conflicts(source_dir, routine_pack_root)
    blocking_conflicts = tuple(
        conflict for conflict in conflicts if conflict.severity == "error"
    )
    if blocking_conflicts and not replace:
        raise RoutinePackOperationError(
            "routine pack conflicts: "
            + "; ".join(conflict.message for conflict in blocking_conflicts),
        )
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
        conflicts=conflicts,
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


@dataclass(frozen=True)
class _RoutineRecord:
    pack_id: str
    routine: RoutineDefinition
    selectors: tuple[str, ...]


def _pack_routine_records(manifest: RoutinePackManifest) -> tuple[_RoutineRecord, ...]:
    if manifest.source_path is None:
        return ()
    pack_root = manifest.source_path.parent
    records: list[_RoutineRecord] = []
    for routine_path in _routine_paths_for_manifest(pack_root, manifest.routine_globs):
        try:
            routine = load_routine_definition(routine_path)
        except ValueError:
            continue
        records.append(
            _RoutineRecord(
                pack_id=manifest.id,
                routine=routine,
                selectors=_selector_signatures_for_routine(routine),
            ),
        )
    return tuple(records)


def _routine_paths_for_manifest(
    pack_root: Path,
    routine_globs: Iterable[str],
) -> tuple[Path, ...]:
    paths: set[Path] = set()
    for pattern in routine_globs:
        paths.update(pack_root.glob(pattern))
    return tuple(sorted(path for path in paths if path.is_file()))


def _pack_version_conflicts(
    incoming: RoutinePackManifest,
    installed: tuple[RoutinePackManifest, ...],
) -> tuple[RoutinePackConflict, ...]:
    conflicts: list[RoutinePackConflict] = []
    for existing in installed:
        if existing.id == incoming.id:
            conflicts.append(
                RoutinePackConflict(
                    kind="pack_version",
                    severity="error",
                    incoming=f"{incoming.id}@{incoming.version}",
                    existing=f"{existing.id}@{existing.version}",
                    message=(
                        f"pack {incoming.id} already installed "
                        f"as version {existing.version}"
                    ),
                ),
            )
    return tuple(conflicts)


def _routine_id_conflicts(
    incoming: tuple[_RoutineRecord, ...],
    installed: tuple[_RoutineRecord, ...],
) -> tuple[RoutinePackConflict, ...]:
    conflicts: list[RoutinePackConflict] = []
    installed_by_id = {record.routine.id: record for record in installed}
    for record in incoming:
        existing = installed_by_id.get(record.routine.id)
        if existing is not None:
            conflicts.append(
                RoutinePackConflict(
                    kind="routine_id",
                    severity="error",
                    incoming=record.routine.id,
                    existing=f"{existing.pack_id}:{existing.routine.id}",
                    message=f"duplicate routine id: {record.routine.id}",
                ),
            )
    return tuple(conflicts)


def _routine_input_conflicts(
    incoming: tuple[_RoutineRecord, ...],
    installed: tuple[_RoutineRecord, ...],
) -> tuple[RoutinePackConflict, ...]:
    conflicts: list[RoutinePackConflict] = []
    installed_by_inputs = {
        record.routine.inputs: record for record in installed if record.routine.inputs
    }
    for record in incoming:
        if not record.routine.inputs:
            continue
        existing = installed_by_inputs.get(record.routine.inputs)
        if existing is not None and existing.routine.id != record.routine.id:
            signature = ",".join(record.routine.inputs)
            conflicts.append(
                RoutinePackConflict(
                    kind="input_signature",
                    severity="warning",
                    incoming=f"{record.routine.id}:{signature}",
                    existing=f"{existing.routine.id}:{signature}",
                    message=f"duplicate routine input signature: {signature}",
                ),
            )
    return tuple(conflicts)


def _selector_conflicts(
    incoming: tuple[_RoutineRecord, ...],
    installed: tuple[_RoutineRecord, ...],
) -> tuple[RoutinePackConflict, ...]:
    conflicts: list[RoutinePackConflict] = []
    installed_by_selector = {
        selector: record for record in installed for selector in record.selectors
    }
    for record in incoming:
        for selector in record.selectors:
            existing = installed_by_selector.get(selector)
            if existing is not None and existing.routine.id != record.routine.id:
                conflicts.append(
                    RoutinePackConflict(
                        kind="selector_signature",
                        severity="warning",
                        incoming=f"{record.routine.id}:{selector}",
                        existing=f"{existing.routine.id}:{selector}",
                        message=f"duplicate selector signature: {selector}",
                    ),
                )
    return tuple(conflicts)


def _selector_signatures_for_routine(routine: RoutineDefinition) -> tuple[str, ...]:
    if routine.reference.kind != "task" or routine.reference.task_path is None:
        return ()
    task_path = routine.reference.task_path
    if not task_path.exists():
        return ()
    loaded = yaml.safe_load(task_path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        return ()
    steps = loaded.get("steps")
    if not isinstance(steps, list):
        return ()
    selectors: list[str] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        action = step.get("action")
        target = step.get("target")
        if isinstance(action, str) and isinstance(target, str) and target:
            selectors.append(f"{action}:{target}")
    return tuple(selectors)


def _write_pack_archive(source_dir: Path, output: Path) -> None:
    # Store the pack under its directory name so zip import has a stable root.
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source_dir.rglob("*")):
            if path.is_file():
                archive.write(
                    path,
                    Path(source_dir.name) / path.relative_to(source_dir),
                )
