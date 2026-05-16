"""Proof manifest schema for local Windows evidence bundles."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


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
