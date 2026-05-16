"""Proof manifest schema for local Windows evidence bundles."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

REQUIRED_WINDOWS_PROOF_NAMES: tuple[str, ...] = (
    "browser-fixture",
    "native-fixture",
    "mixed-fixture",
    "recovery-fixture",
)


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
