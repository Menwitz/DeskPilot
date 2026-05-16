"""Proof manifest schema for local Windows evidence bundles."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import sys
import zipfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

REQUIRED_WINDOWS_PROOF_NAMES: tuple[str, ...] = (
    "browser-fixture",
    "native-fixture",
    "mixed-fixture",
    "recovery-fixture",
)
PROOF_SUITE_REPORT_NAME = "proof-suite-report.md"
PROOF_SUITE_STATUS_NAME = "proof-suite-status.json"
PROOF_SUITE_RUNBOOK_NAME = "proof-suite-next-actions.md"
PROOF_SUITE_ARCHIVE_NAME = "proof-suite-artifacts.zip"


@dataclass(frozen=True)
class ProofManifestArtifacts:
    """Local artifact paths produced by one visible Windows proof run."""

    trace_dir: Path
    report_path: Path
    action_log_path: Path
    proof_manifest_path: Path
    screenshots: tuple[Path, ...] = ()
    video_path: Path | None = None
    video_log_path: Path | None = None

    def metadata(self) -> dict[str, object]:
        return {
            "trace_dir": str(self.trace_dir),
            "report_path": str(self.report_path),
            "action_log_path": str(self.action_log_path),
            "proof_manifest_path": str(self.proof_manifest_path),
            "screenshots": [str(path) for path in self.screenshots],
            "video_path": str(self.video_path) if self.video_path else None,
            "video_log_path": str(self.video_log_path)
            if self.video_log_path
            else None,
        }


@dataclass(frozen=True)
class ProofManifestStep:
    """Reviewed step summary recorded in the proof manifest."""

    step_id: str
    action: str
    has_post_action_evidence: bool

    def metadata(self) -> dict[str, object]:
        return {
            "step_id": self.step_id,
            "action": self.action,
            "has_post_action_evidence": self.has_post_action_evidence,
        }


@dataclass(frozen=True)
class ProofManifest:
    """Stable artifact index for proving a local Windows workflow."""

    proof_name: str
    command: tuple[str, ...]
    status: str
    reason: str | None
    started_at: str
    completed_at: str
    executable_version: str
    python_version: str
    windows_version: str | None
    platform: str
    monitor_geometry: Mapping[str, object] | None
    dpi_scale: tuple[float, float]
    artifacts: ProofManifestArtifacts
    video_capture: dict[str, object] | None
    steps: tuple[ProofManifestStep, ...]
    schema_version: int = 1

    def metadata(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "proof_name": self.proof_name,
            "command": list(self.command),
            "status": self.status,
            "reason": self.reason,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "executable_version": self.executable_version,
            "python_version": self.python_version,
            "windows_version": self.windows_version,
            "platform": self.platform,
            "monitor_geometry": self.monitor_geometry,
            "dpi_scale": list(self.dpi_scale),
            "artifacts": self.artifacts.metadata(),
            "video_capture": self.video_capture,
            "step_count": len(self.steps),
            "steps": [step.metadata() for step in self.steps],
        }


@dataclass(frozen=True)
class ProofBundleValidation:
    """Review-only validation result for an existing proof artifact bundle."""

    trace_dir: Path
    manifest_path: Path
    proof_name: str | None
    status: str
    errors: tuple[str, ...]
    warnings: tuple[str, ...]
    artifact_paths: tuple[tuple[str, Path], ...]

    @property
    def passed(self) -> bool:
        return not self.errors


@dataclass(frozen=True)
class ProofSuiteValidation:
    """Validation result for a complete multi-workflow Windows proof set."""

    trace_root: Path
    expected_proofs: tuple[str, ...]
    bundle_results: tuple[ProofBundleValidation, ...]
    missing_proofs: tuple[str, ...]
    duplicate_proofs: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.errors

    @property
    def errors(self) -> tuple[str, ...]:
        errors = [f"missing proof bundle: {name}" for name in self.missing_proofs]
        for result in self.bundle_results:
            proof_name = result.proof_name or str(result.trace_dir)
            errors.extend(f"{proof_name}: {error}" for error in result.errors)
        return tuple(errors)


@dataclass(frozen=True)
class ProofPreflightCheck:
    """One no-input readiness check before a Windows proof run."""

    name: str
    status: str
    message: str

    def metadata(self) -> dict[str, object]:
        return {
            "name": self.name,
            "status": self.status,
            "message": self.message,
        }


@dataclass(frozen=True)
class ProofPreflightResult:
    """No-input readiness result for collecting proof suite evidence."""

    trace_root: Path
    checks: tuple[ProofPreflightCheck, ...]

    @property
    def passed(self) -> bool:
        return all(check.status != "failed" for check in self.checks)

    def metadata(self) -> dict[str, object]:
        return {
            "trace_root": str(self.trace_root),
            "status": "passed" if self.passed else "failed",
            "checks": [check.metadata() for check in self.checks],
        }


def run_proof_preflight(
    trace_root: Path,
    *,
    require_windows: bool = True,
    require_video: bool = True,
    ffmpeg_path: str = "ffmpeg",
    platform_name: str = sys.platform,
    path_lookup: Callable[[str], str | None] = shutil.which,
) -> ProofPreflightResult:
    """Check local proof-suite prerequisites without sending desktop input."""

    checks = (
        _windows_preflight_check(platform_name, require_windows),
        _trace_root_preflight_check(trace_root),
        _video_preflight_check(ffmpeg_path, require_video, path_lookup),
    )
    return ProofPreflightResult(trace_root=trace_root, checks=checks)


def validate_proof_bundle(
    trace_dir: Path,
    *,
    require_video: bool = True,
) -> ProofBundleValidation:
    """Validate a saved proof bundle without rerunning desktop input."""

    manifest_path = trace_dir / "proof-manifest.json"
    errors: list[str] = []
    warnings: list[str] = []
    artifact_paths: list[tuple[str, Path]] = []
    manifest = _load_json_object(manifest_path, errors, "proof manifest")
    if manifest is None:
        return ProofBundleValidation(
            trace_dir=trace_dir,
            manifest_path=manifest_path,
            proof_name=None,
            status="failed",
            errors=tuple(errors),
            warnings=tuple(warnings),
            artifact_paths=(),
        )

    proof_name = _string_value(manifest.get("proof_name"))
    status = _string_value(manifest.get("status"))
    if status != "passed":
        errors.append(f"proof status is not passed: {status or 'missing'}")
    _validate_manifest_metadata(manifest, errors)

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        errors.append("proof manifest artifacts must be a JSON object")
        artifacts = {}

    trace_path = _required_artifact_path(
        artifacts,
        "trace_dir",
        manifest_path,
        errors,
        artifact_paths,
    )
    report_path = _required_artifact_path(
        artifacts,
        "report_path",
        manifest_path,
        errors,
        artifact_paths,
    )
    action_log_path = _required_artifact_path(
        artifacts,
        "action_log_path",
        manifest_path,
        errors,
        artifact_paths,
    )
    proof_manifest_artifact = _required_artifact_path(
        artifacts,
        "proof_manifest_path",
        manifest_path,
        errors,
        artifact_paths,
    )
    if trace_path is not None and not trace_path.is_dir():
        errors.append(f"artifact trace_dir is not a directory: {trace_path}")
    if proof_manifest_artifact is not None and proof_manifest_artifact != manifest_path:
        warnings.append(
            "proof_manifest_path points at a different path than the reviewed trace",
        )

    screenshot_paths = _screenshot_paths(artifacts, manifest_path, artifact_paths)
    if not screenshot_paths:
        errors.append("proof manifest must list at least one screenshot artifact")
    for screenshot_path in screenshot_paths:
        _require_existing_file("screenshot", screenshot_path, errors)

    video_path = _optional_artifact_path(
        artifacts,
        "video_path",
        manifest_path,
        artifact_paths,
    )
    video_log_path = _optional_artifact_path(
        artifacts,
        "video_log_path",
        manifest_path,
        artifact_paths,
    )
    if require_video:
        if video_path is None:
            errors.append("proof manifest must include video_path")
        else:
            _require_existing_file("video_path", video_path, errors)
            if video_path.exists() and video_path.stat().st_size == 0:
                errors.append(f"video_path is empty: {video_path}")
        if video_log_path is not None:
            _require_existing_file("video_log_path", video_log_path, errors)
        video_capture = manifest.get("video_capture")
        if not isinstance(video_capture, dict):
            errors.append("video_capture metadata is required when video is required")
        elif video_capture.get("status") != "passed":
            errors.append(
                "video_capture status is not passed: "
                f"{video_capture.get('status', 'missing')}",
            )
    elif video_path is None:
        warnings.append("video_path is not present; video requirement was disabled")

    if report_path is not None:
        _validate_report(report_path, manifest_path, errors)
    if action_log_path is not None:
        _validate_action_log(action_log_path, errors)
    _validate_manifest_steps(manifest, errors)

    return ProofBundleValidation(
        trace_dir=trace_dir,
        manifest_path=manifest_path,
        proof_name=proof_name,
        status="passed" if not errors else "failed",
        errors=tuple(errors),
        warnings=tuple(warnings),
        artifact_paths=tuple(artifact_paths),
    )


def validate_proof_suite(
    trace_root: Path,
    *,
    expected_proofs: tuple[str, ...] = REQUIRED_WINDOWS_PROOF_NAMES,
    require_video: bool = True,
) -> ProofSuiteValidation:
    """Validate that a trace root contains every required Windows proof bundle."""

    warnings: list[str] = []
    manifests_by_name: dict[str, list[Path]] = {}
    for manifest_path in sorted(trace_root.glob("*/proof-manifest.json")):
        errors: list[str] = []
        manifest = _load_json_object(manifest_path, errors, "proof manifest")
        if manifest is None:
            warnings.extend(errors)
            continue
        proof_name = _string_value(manifest.get("proof_name"))
        if proof_name is None:
            warnings.append(f"proof manifest missing proof_name: {manifest_path}")
            continue
        manifests_by_name.setdefault(proof_name, []).append(manifest_path.parent)

    missing = tuple(name for name in expected_proofs if name not in manifests_by_name)
    duplicates = tuple(
        name
        for name, trace_dirs in sorted(manifests_by_name.items())
        if len(trace_dirs) > 1
    )
    bundle_results: list[ProofBundleValidation] = []
    for proof_name in expected_proofs:
        trace_dirs = manifests_by_name.get(proof_name)
        if not trace_dirs:
            continue
        # Use the most recent directory name when repeated proof attempts exist.
        bundle_results.append(
            validate_proof_bundle(
                sorted(trace_dirs)[-1],
                require_video=require_video,
            ),
        )

    return ProofSuiteValidation(
        trace_root=trace_root,
        expected_proofs=expected_proofs,
        bundle_results=tuple(bundle_results),
        missing_proofs=missing,
        duplicate_proofs=duplicates,
        warnings=tuple(warnings),
    )


def render_proof_suite_report(validation: ProofSuiteValidation) -> str:
    """Render a reviewer-facing Markdown report for a proof suite validation."""

    bundles_by_name = {
        bundle.proof_name: bundle
        for bundle in validation.bundle_results
        if bundle.proof_name is not None
    }
    lines = [
        "# DeskPilot Windows Proof Suite Report",
        "",
        f"- Trace root: `{validation.trace_root}`",
        f"- Status: `{'passed' if validation.passed else 'failed'}`",
        f"- Expected proofs: `{', '.join(validation.expected_proofs)}`",
        "",
        "## Proofs",
        "",
    ]
    for proof_name in validation.expected_proofs:
        bundle = bundles_by_name.get(proof_name)
        if bundle is None:
            lines.extend(
                [
                    f"### {proof_name}",
                    "",
                    "- Status: `missing`",
                    "",
                ],
            )
            continue
        lines.extend(
            [
                f"### {proof_name}",
                "",
                f"- Status: `{'passed' if bundle.passed else 'failed'}`",
                f"- Trace directory: `{bundle.trace_dir}`",
                f"- Manifest: `{bundle.manifest_path}`",
            ],
        )
        if bundle.artifact_paths:
            lines.append("- Artifacts:")
            lines.extend(
                f"  - `{label}`: `{path}`" for label, path in bundle.artifact_paths
            )
        if bundle.warnings:
            lines.append("- Warnings:")
            lines.extend(f"  - {warning}" for warning in bundle.warnings)
        proof_errors = tuple(_proof_errors_for_bundle(validation, proof_name))
        if proof_errors:
            lines.append("- Errors:")
            lines.extend(f"  - {error}" for error in proof_errors)
        lines.append("")

    lines.extend(["## Suite Findings", ""])
    if validation.missing_proofs:
        lines.append("- Missing proofs:")
        lines.extend(f"  - `{proof_name}`" for proof_name in validation.missing_proofs)
    if validation.duplicate_proofs:
        lines.append("- Duplicate proofs:")
        lines.extend(
            f"  - `{proof_name}`" for proof_name in validation.duplicate_proofs
        )
    if validation.warnings:
        lines.append("- Warnings:")
        lines.extend(f"  - {warning}" for warning in validation.warnings)
    has_no_findings = (
        not validation.errors
        and not validation.warnings
        and not validation.duplicate_proofs
    )
    if has_no_findings:
        lines.append("- No blocking findings.")
    else:
        suite_errors = [
            error
            for error in validation.errors
            if error.startswith("missing proof bundle:")
        ]
        if suite_errors:
            lines.append("- Errors:")
            lines.extend(f"  - {error}" for error in suite_errors)
    lines.append("")
    return "\n".join(lines)


def write_proof_suite_report(
    validation: ProofSuiteValidation,
    output_path: Path | None = None,
) -> Path:
    """Write a Markdown report for an existing proof suite validation."""

    report_path = output_path or validation.trace_root / PROOF_SUITE_REPORT_NAME
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_proof_suite_report(validation), encoding="utf-8")
    return report_path


def proof_suite_status_metadata(validation: ProofSuiteValidation) -> dict[str, object]:
    """Build a machine-readable proof suite status payload for monitoring."""

    bundles_by_name = {
        bundle.proof_name: bundle
        for bundle in validation.bundle_results
        if bundle.proof_name is not None
    }
    proofs: list[dict[str, object]] = []
    for proof_name in validation.expected_proofs:
        bundle = bundles_by_name.get(proof_name)
        if bundle is None:
            proofs.append(
                {
                    "proof_name": proof_name,
                    "status": "missing",
                    "trace_dir": None,
                    "manifest_path": None,
                    "warnings": [],
                    "errors": [f"missing proof bundle: {proof_name}"],
                    "artifacts": [],
                },
            )
            continue
        proofs.append(
            {
                "proof_name": proof_name,
                "status": "passed" if bundle.passed else "failed",
                "trace_dir": str(bundle.trace_dir),
                "manifest_path": str(bundle.manifest_path),
                "warnings": list(bundle.warnings),
                "errors": _proof_errors_for_bundle(validation, proof_name),
                "artifacts": [
                    {"label": label, "path": str(path)}
                    for label, path in bundle.artifact_paths
                ],
            },
        )

    return {
        "schema_version": 1,
        "trace_root": str(validation.trace_root),
        "status": "passed" if validation.passed else "failed",
        "expected_proofs": list(validation.expected_proofs),
        "missing_proofs": list(validation.missing_proofs),
        "duplicate_proofs": list(validation.duplicate_proofs),
        "warnings": list(validation.warnings),
        "errors": list(validation.errors),
        "proofs": proofs,
    }


def write_proof_suite_status(
    validation: ProofSuiteValidation,
    output_path: Path | None = None,
) -> Path:
    """Write machine-readable proof suite status for CI and monitors."""

    status_path = output_path or validation.trace_root / PROOF_SUITE_STATUS_NAME
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(
        json.dumps(proof_suite_status_metadata(validation), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return status_path


def render_proof_suite_runbook(
    validation: ProofSuiteValidation,
    *,
    require_video: bool = True,
) -> str:
    """Render the next operator commands for collecting a proof suite."""

    invalid_bundles = tuple(
        bundle for bundle in validation.bundle_results if not bundle.passed
    )
    lines = [
        "# DeskPilot Windows Proof Suite Next Actions",
        "",
        f"- Trace root: `{validation.trace_root}`",
        f"- Suite status: `{'passed' if validation.passed else 'failed'}`",
        f"- Video required: `{'yes' if require_video else 'no'}`",
        "",
        "## Missing Proof Commands",
        "",
    ]
    if validation.missing_proofs:
        lines.extend(
            _proof_collection_command(validation.trace_root, proof_name, require_video)
            for proof_name in validation.missing_proofs
        )
    else:
        lines.append("- No missing proof bundles.")

    lines.extend(["", "## Invalid Bundle Review", ""])
    if invalid_bundles:
        lines.extend(
            _proof_bundle_validation_command(bundle.trace_dir, require_video)
            for bundle in invalid_bundles
        )
    else:
        lines.append("- No invalid proof bundles found.")

    lines.extend(["", "## Duplicate Bundle Review", ""])
    if validation.duplicate_proofs:
        lines.extend(
            f"- Review duplicate `{name}` bundles and keep one."
            for name in validation.duplicate_proofs
        )
    else:
        lines.append("- No duplicate proof bundles found.")

    lines.extend(
        [
            "",
            "## Promotion Commands",
            "",
            _proof_suite_validation_command(validation.trace_root, require_video),
            "",
            "## Blocking Findings",
            "",
        ],
    )
    if validation.errors:
        lines.extend(f"- {error}" for error in validation.errors)
    else:
        lines.append("- No blocking findings.")
    if validation.warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warning}" for warning in validation.warnings)
    lines.append("")
    return "\n".join(lines)


def write_proof_suite_runbook(
    validation: ProofSuiteValidation,
    output_path: Path | None = None,
    *,
    require_video: bool = True,
) -> Path:
    """Write operator next actions for collecting or promoting a proof suite."""

    runbook_path = output_path or validation.trace_root / PROOF_SUITE_RUNBOOK_NAME
    runbook_path.parent.mkdir(parents=True, exist_ok=True)
    runbook_path.write_text(
        render_proof_suite_runbook(validation, require_video=require_video),
        encoding="utf-8",
    )
    return runbook_path


def write_proof_suite_archive(
    validation: ProofSuiteValidation,
    output_path: Path | None = None,
    *,
    require_video: bool = True,
) -> Path:
    """Write one local archive with generated suite docs and proof artifacts."""

    archive_path = output_path or validation.trace_root / PROOF_SUITE_ARCHIVE_NAME
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    written_names: set[str] = set()
    with zipfile.ZipFile(
        archive_path,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        _write_zip_text(
            archive,
            written_names,
            PROOF_SUITE_REPORT_NAME,
            render_proof_suite_report(validation),
        )
        _write_zip_text(
            archive,
            written_names,
            PROOF_SUITE_STATUS_NAME,
            json.dumps(
                proof_suite_status_metadata(validation),
                indent=2,
                sort_keys=True,
            ),
        )
        _write_zip_text(
            archive,
            written_names,
            PROOF_SUITE_RUNBOOK_NAME,
            render_proof_suite_runbook(validation, require_video=require_video),
        )
        for artifact_path in _proof_suite_archive_files(validation):
            archive_name = _archive_name(validation.trace_root, artifact_path)
            if archive_name in written_names:
                continue
            archive.write(artifact_path, archive_name)
            written_names.add(archive_name)
    return archive_path


def _proof_errors_for_bundle(
    validation: ProofSuiteValidation,
    proof_name: str,
) -> list[str]:
    prefix = f"{proof_name}: "
    return [
        error.removeprefix(prefix)
        for error in validation.errors
        if error.startswith(prefix)
    ]


def _write_zip_text(
    archive: zipfile.ZipFile,
    written_names: set[str],
    archive_name: str,
    text: str,
) -> None:
    if archive_name in written_names:
        return
    archive.writestr(archive_name, text)
    written_names.add(archive_name)


def _proof_suite_archive_files(
    validation: ProofSuiteValidation,
) -> tuple[Path, ...]:
    paths: list[Path] = []
    for bundle in validation.bundle_results:
        paths.append(bundle.manifest_path)
        paths.extend(path for _, path in bundle.artifact_paths)
    return tuple(path for path in paths if path.exists() and path.is_file())


def _archive_name(trace_root: Path, artifact_path: Path) -> str:
    try:
        relative = artifact_path.resolve().relative_to(trace_root.resolve())
    except ValueError:
        relative = Path("external-artifacts") / artifact_path.name
    return relative.as_posix()


def _windows_preflight_check(
    platform_name: str,
    require_windows: bool,
) -> ProofPreflightCheck:
    if not require_windows:
        return ProofPreflightCheck(
            name="windows-platform",
            status="warning",
            message="Windows platform requirement was disabled for this preflight.",
        )
    if platform_name == "win32":
        return ProofPreflightCheck(
            name="windows-platform",
            status="passed",
            message="Running on Windows.",
        )
    return ProofPreflightCheck(
        name="windows-platform",
        status="failed",
        message=(
            "Proof suite must run on Windows; "
            f"current platform is {platform_name}."
        ),
    )


def _trace_root_preflight_check(trace_root: Path) -> ProofPreflightCheck:
    if trace_root.exists() and not trace_root.is_dir():
        return ProofPreflightCheck(
            name="trace-root",
            status="failed",
            message=f"Trace root exists but is not a directory: {trace_root}",
        )
    writable_path = trace_root if trace_root.exists() else trace_root.parent
    if not writable_path.exists():
        return ProofPreflightCheck(
            name="trace-root",
            status="failed",
            message=f"Trace root parent does not exist: {writable_path}",
        )
    if not os.access(writable_path, os.W_OK):
        return ProofPreflightCheck(
            name="trace-root",
            status="failed",
            message=f"Trace root is not writable: {writable_path}",
        )
    return ProofPreflightCheck(
        name="trace-root",
        status="passed",
        message=f"Trace root can be written: {trace_root}",
    )


def _video_preflight_check(
    ffmpeg_path: str,
    require_video: bool,
    path_lookup: Callable[[str], str | None],
) -> ProofPreflightCheck:
    if not require_video:
        return ProofPreflightCheck(
            name="video-capture",
            status="warning",
            message="Video capture is disabled; external recording must be justified.",
        )
    if _ffmpeg_available(ffmpeg_path, path_lookup):
        return ProofPreflightCheck(
            name="video-capture",
            status="passed",
            message=f"ffmpeg is available for proof video capture: {ffmpeg_path}",
        )
    return ProofPreflightCheck(
        name="video-capture",
        status="failed",
        message=f"ffmpeg was not found for proof video capture: {ffmpeg_path}",
    )


def _ffmpeg_available(
    ffmpeg_path: str,
    path_lookup: Callable[[str], str | None],
) -> bool:
    path = Path(ffmpeg_path)
    if path.is_absolute() or len(path.parts) > 1:
        return path.exists() and path.is_file()
    return path_lookup(ffmpeg_path) is not None


def _proof_collection_command(
    trace_root: Path,
    proof_name: str,
    require_video: bool,
) -> str:
    video_args = (
        "--record-video --video-fps 15"
        if require_video
        else "--video-policy disabled"
    )
    return (
        f"- `desktop-agent proof {proof_name} --trace-root "
        f"{_shell_arg(trace_root)} --countdown-seconds 5 {video_args}`"
    )


def _proof_bundle_validation_command(trace_dir: Path, require_video: bool) -> str:
    allow_missing_video = "" if require_video else " --allow-missing-video"
    return (
        f"- `desktop-agent proof validate {_shell_arg(trace_dir)}"
        f"{allow_missing_video}`"
    )


def _proof_suite_validation_command(trace_root: Path, require_video: bool) -> str:
    allow_missing_video = "" if require_video else " --allow-missing-video"
    return (
        f"- `desktop-agent proof validate-suite {_shell_arg(trace_root)}"
        f"{allow_missing_video} --write-report --write-status-json "
        "--write-runbook`"
    )


def _shell_arg(path: Path) -> str:
    return shlex.quote(str(path))


def _load_json_object(
    path: Path,
    errors: list[str],
    label: str,
) -> dict[str, object] | None:
    if not path.exists():
        errors.append(f"{label} not found: {path}")
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"{label} is not valid JSON: {exc}")
        return None
    if not isinstance(payload, dict):
        errors.append(f"{label} must contain a JSON object")
        return None
    return payload


def _validate_manifest_metadata(
    manifest: Mapping[str, object],
    errors: list[str],
) -> None:
    if manifest.get("schema_version") != 1:
        errors.append("proof manifest schema_version must be 1")
    if not _string_value(manifest.get("proof_name")):
        errors.append("proof manifest missing proof_name")
    command = manifest.get("command")
    if not (
        isinstance(command, list)
        and command
        and all(_string_value(item) for item in command)
    ):
        errors.append("proof manifest command must be a non-empty string list")
    for key in (
        "started_at",
        "completed_at",
        "executable_version",
        "python_version",
        "platform",
    ):
        if not _string_value(manifest.get(key)):
            errors.append(f"proof manifest missing {key}")
    platform_name = _string_value(manifest.get("platform"))
    if platform_name == "win32" and not _string_value(manifest.get("windows_version")):
        errors.append("proof manifest missing windows_version for win32 proof")
    _validate_monitor_geometry(manifest.get("monitor_geometry"), errors)
    _validate_dpi_scale(manifest.get("dpi_scale"), errors)


def _validate_monitor_geometry(value: object, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append("proof manifest monitor_geometry must be a JSON object")
        return
    for key in ("left", "top", "width", "height"):
        if not isinstance(value.get(key), int):
            errors.append(f"proof manifest monitor_geometry missing integer {key}")
    width = value.get("width")
    height = value.get("height")
    if isinstance(width, int) and width <= 0:
        errors.append("proof manifest monitor_geometry width must be positive")
    if isinstance(height, int) and height <= 0:
        errors.append("proof manifest monitor_geometry height must be positive")


def _validate_dpi_scale(value: object, errors: list[str]) -> None:
    if not (
        isinstance(value, list)
        and len(value) == 2
        and all(_is_json_number(item) for item in value)
    ):
        errors.append("proof manifest dpi_scale must be a two-number list")
        return
    if any(float(item) <= 0 for item in value):
        errors.append("proof manifest dpi_scale values must be positive")


def _is_json_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _required_artifact_path(
    artifacts: Mapping[object, object],
    key: str,
    manifest_path: Path,
    errors: list[str],
    artifact_paths: list[tuple[str, Path]],
) -> Path | None:
    path = _optional_artifact_path(artifacts, key, manifest_path, artifact_paths)
    if path is None:
        errors.append(f"proof manifest missing artifact: {key}")
        return None
    if key != "trace_dir":
        _require_existing_file(key, path, errors)
    return path


def _optional_artifact_path(
    artifacts: Mapping[object, object],
    key: str,
    manifest_path: Path,
    artifact_paths: list[tuple[str, Path]],
) -> Path | None:
    value = artifacts.get(key)
    if not isinstance(value, str) or not value:
        return None
    path = _artifact_path(value, manifest_path)
    artifact_paths.append((key, path))
    return path


def _artifact_path(value: str, manifest_path: Path) -> Path:
    path = Path(value)
    if path.is_absolute() or path.exists():
        return path
    # Older manifests may contain paths relative to the trace directory.
    return manifest_path.parent / path


def _screenshot_paths(
    artifacts: Mapping[object, object],
    manifest_path: Path,
    artifact_paths: list[tuple[str, Path]],
) -> tuple[Path, ...]:
    screenshots = artifacts.get("screenshots")
    if not isinstance(screenshots, list):
        return ()
    paths: list[Path] = []
    for index, value in enumerate(screenshots, start=1):
        if not isinstance(value, str) or not value:
            continue
        path = _artifact_path(value, manifest_path)
        paths.append(path)
        artifact_paths.append((f"screenshot_{index}", path))
    return tuple(paths)


def _require_existing_file(label: str, path: Path, errors: list[str]) -> None:
    if not path.exists():
        errors.append(f"artifact {label} does not exist: {path}")
    elif not path.is_file():
        errors.append(f"artifact {label} is not a file: {path}")


def _validate_report(
    report_path: Path,
    manifest_path: Path,
    errors: list[str],
) -> None:
    report = _load_json_object(report_path, errors, "proof report")
    if report is None:
        return
    if report.get("status") != "passed":
        errors.append(f"proof report status is not passed: {report.get('status')}")

    steps = report.get("steps")
    if not isinstance(steps, list) or not steps:
        errors.append("proof report must contain at least one reviewed step")
        return

    for index, item in enumerate(steps, start=1):
        if not isinstance(item, dict):
            errors.append(f"proof report step {index} must be a JSON object")
            continue
        step_id = _string_value(item.get("step_id")) or f"#{index}"
        metadata = item.get("metadata")
        if not isinstance(metadata, dict):
            errors.append(f"proof report step {step_id} missing metadata")
            continue
        evidence = metadata.get("post_action_evidence")
        if not isinstance(evidence, dict):
            errors.append(
                f"proof report step {step_id} missing post_action_evidence",
            )
            continue
        _validate_step_evidence(step_id, evidence, manifest_path, errors)


def _validate_step_evidence(
    step_id: str,
    evidence: Mapping[object, object],
    manifest_path: Path,
    errors: list[str],
) -> None:
    if evidence.get("status") != "passed":
        errors.append(
            f"proof report step {step_id} evidence status is not passed: "
            f"{evidence.get('status')}",
        )
    if not _string_value(evidence.get("active_window_title")):
        errors.append(f"proof report step {step_id} missing active_window_title")
    cursor_position = evidence.get("cursor_position")
    if not (
        isinstance(cursor_position, list)
        and len(cursor_position) == 2
        and all(isinstance(value, int) for value in cursor_position)
    ):
        errors.append(f"proof report step {step_id} missing cursor_position")
    screenshot_value = evidence.get("screenshot_path")
    if not isinstance(screenshot_value, str) or not screenshot_value:
        errors.append(f"proof report step {step_id} missing screenshot_path")
        return
    screenshot_path = _artifact_path(screenshot_value, manifest_path)
    _require_existing_file(f"step {step_id} screenshot_path", screenshot_path, errors)


def _validate_action_log(action_log_path: Path, errors: list[str]) -> None:
    if not action_log_path.exists() or not action_log_path.is_file():
        return
    lines = [
        line
        for line in action_log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not lines:
        errors.append(f"action_log_path is empty: {action_log_path}")


def _validate_manifest_steps(
    manifest: Mapping[str, object],
    errors: list[str],
) -> None:
    steps = manifest.get("steps")
    if not isinstance(steps, list) or not steps:
        errors.append("proof manifest must contain at least one step summary")
        return
    for index, item in enumerate(steps, start=1):
        if not isinstance(item, dict):
            errors.append(f"proof manifest step {index} must be a JSON object")
            continue
        step_id = _string_value(item.get("step_id")) or f"#{index}"
        if item.get("has_post_action_evidence") is not True:
            errors.append(f"proof manifest step {step_id} has no post-action evidence")


def _string_value(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None
