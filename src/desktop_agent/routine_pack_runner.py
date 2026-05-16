"""Pack-level validation and proof bundle generation for routine packs."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from desktop_agent.config import RuntimeConfig
from desktop_agent.routine_pack_manifest import (
    RoutinePackManifest,
    load_routine_pack_manifests,
)
from desktop_agent.routines import RoutineDefinition, load_routine_definition
from desktop_agent.task_dsl import BasicTaskValidator, YamlTaskLoader


@dataclass(frozen=True)
class RoutinePackTestResult:
    """Pack-level validation result used by reports and proof bundles."""

    pack_id: str
    status: str
    routine_count: int
    validated_routine_count: int
    errors: tuple[str, ...] = ()

    def metadata(self) -> dict[str, object]:
        return {
            "pack_id": self.pack_id,
            "status": self.status,
            "routine_count": self.routine_count,
            "validated_routine_count": self.validated_routine_count,
            "errors": list(self.errors),
        }


@dataclass(frozen=True)
class RoutinePackProofBundleResult:
    """Paths written for a local routine-pack proof bundle."""

    pack_id: str
    bundle_dir: Path
    report_path: Path
    checklist_path: Path
    manifest_copy_path: Path
    proof_status: str
    test_result: RoutinePackTestResult

    def metadata(self) -> dict[str, object]:
        return {
            "pack_id": self.pack_id,
            "bundle_dir": str(self.bundle_dir),
            "report_path": str(self.report_path),
            "checklist_path": str(self.checklist_path),
            "manifest_copy_path": str(self.manifest_copy_path),
            "proof_status": self.proof_status,
            "test_result": self.test_result.metadata(),
        }


def run_routine_pack_tests(
    routine_pack_root: Path,
    pack_id: str,
) -> RoutinePackTestResult:
    """Validate one installed routine pack without real desktop input."""
    manifest = _manifest_by_id(routine_pack_root, pack_id)
    routines, errors = _load_pack_routines(manifest)
    validation_errors = [*errors]
    validated_count = 0
    for routine in routines:
        routine_errors = _validate_routine_reference(routine)
        if routine_errors:
            validation_errors.extend(routine_errors)
        else:
            validated_count += 1
    status = "passed"
    if validation_errors:
        status = "failed"
    elif not routines:
        status = "empty"
    return RoutinePackTestResult(
        pack_id=manifest.id,
        status=status,
        routine_count=len(routines),
        validated_routine_count=validated_count,
        errors=tuple(validation_errors),
    )


def write_routine_pack_proof_bundle(
    routine_pack_root: Path,
    pack_id: str,
    output_dir: Path,
) -> RoutinePackProofBundleResult:
    """Write a local review bundle for one routine pack."""
    manifest = _manifest_by_id(routine_pack_root, pack_id)
    test_result = run_routine_pack_tests(routine_pack_root, pack_id)
    proof_status = _proof_status(manifest, test_result)
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "pack-test-report.json"
    checklist_path = output_dir / "proof-checklist.md"
    manifest_copy_path = output_dir / "routine-pack.yaml"
    report_path.write_text(
        json.dumps(
            {
                "manifest": manifest.metadata(),
                "proof_status": proof_status,
                "test_result": test_result.metadata(),
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    checklist_path.write_text(
        _proof_checklist_markdown(manifest, test_result),
        encoding="utf-8",
    )
    if manifest.source_path is not None:
        shutil.copyfile(manifest.source_path, manifest_copy_path)
    return RoutinePackProofBundleResult(
        pack_id=manifest.id,
        bundle_dir=output_dir,
        report_path=report_path,
        checklist_path=checklist_path,
        manifest_copy_path=manifest_copy_path,
        proof_status=proof_status,
        test_result=test_result,
    )


def _manifest_by_id(root: Path, pack_id: str) -> RoutinePackManifest:
    for manifest in load_routine_pack_manifests(root):
        if manifest.id == pack_id:
            return manifest
    raise ValueError(f"unknown routine pack: {pack_id}")


def _load_pack_routines(
    manifest: RoutinePackManifest,
) -> tuple[tuple[RoutineDefinition, ...], tuple[str, ...]]:
    if manifest.source_path is None:
        return (), (f"pack {manifest.id} has no source path",)
    pack_root = manifest.source_path.parent
    routines: list[RoutineDefinition] = []
    errors: list[str] = []
    routine_paths: set[Path] = set()
    for pattern in manifest.routine_globs:
        routine_paths.update(pack_root.glob(pattern))
    for routine_path in sorted(path for path in routine_paths if path.is_file()):
        try:
            routines.append(load_routine_definition(routine_path))
        except ValueError as exc:
            errors.append(f"{routine_path}: {exc}")
    return tuple(routines), tuple(errors)


def _validate_routine_reference(routine: RoutineDefinition) -> tuple[str, ...]:
    if routine.reference.kind != "task":
        return ()
    if routine.reference.task_path is None:
        return (f"{routine.id}: missing task path",)
    try:
        task = YamlTaskLoader().load(routine.reference.task_path)
        BasicTaskValidator().validate(task, RuntimeConfig())
    except ValueError as exc:
        return (f"{routine.id}: {exc}",)
    return ()


def _proof_checklist_markdown(
    manifest: RoutinePackManifest,
    test_result: RoutinePackTestResult,
) -> str:
    proof_status = _proof_status(manifest, test_result)
    lines = [
        f"# Routine Pack Proof: {manifest.name}",
        "",
        "## Manifest",
        "",
        f"- Pack ID: `{manifest.id}`",
        f"- Version: `{manifest.version}`",
        f"- Trust level: `{manifest.trust_level}`",
        f"- Max safety class: `{manifest.safety.max_safety_class}`",
        "",
        "## Pack Test",
        "",
        f"- Proof status: `{proof_status}`",
        f"- Status: `{test_result.status}`",
        f"- Routines: `{test_result.routine_count}`",
        f"- Validated routines: `{test_result.validated_routine_count}`",
        "",
        "## Expected Proof Artifacts",
        "",
    ]
    lines.extend(
        f"- [ ] `{artifact}`" for artifact in manifest.proof.expected_artifacts
    )
    lines.extend(
        [
            "",
            "## Review",
            "",
            "- [ ] Manifest trust level and safety metadata reviewed.",
            "- [ ] Routine YAML and referenced task/playbook files reviewed.",
            "- [ ] Dry-run or fixture evidence attached for promoted routines.",
            "- [ ] Windows proof attached when `windows_proof_required` is true.",
            "",
        ],
    )
    if test_result.errors:
        lines.extend(["## Errors", ""])
        lines.extend(f"- `{error}`" for error in test_result.errors)
        lines.append("")
    return "\n".join(lines)


def _proof_status(
    manifest: RoutinePackManifest,
    test_result: RoutinePackTestResult,
) -> str:
    """Return the pack-level proof status shown in reports and review bundles."""
    if test_result.status != "passed":
        return "failed_validation"
    if manifest.proof.windows_proof_required:
        return "windows_proof_required"
    return "ready_for_review"
