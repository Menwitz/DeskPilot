"""Approval manifest validation for sensitive site workflows."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import cast

import yaml

from desktop_agent.config import RuntimeConfig
from desktop_agent.task_dsl import TaskDefinition, step_category


class ApprovalManifestError(ValueError):
    """Raised when an approval manifest cannot authorize a site workflow."""


@dataclass(frozen=True)
class ApprovalManifest:
    """Run preapproval record for an audited site workflow."""

    site_id: str
    flow_id: str
    approved_steps: tuple[str, ...]
    approver: str
    reason: str
    approved_at: str
    content_fingerprint: str
    source_path: Path

    def metadata(self) -> dict[str, object]:
        return {
            "site_approval_manifest_path": str(self.source_path),
            "site_approval_manifest_status": "validated",
            "site_approval_approver": self.approver,
            "site_approval_reason": self.reason,
            "site_approval_approved_at": self.approved_at,
            "site_approved_step_ids": list(self.approved_steps),
            "content_variables_fingerprint": self.content_fingerprint,
        }


def load_approval_manifest(path: Path) -> ApprovalManifest:
    """Load and validate the local YAML approval manifest shape."""

    if not path.exists():
        raise ApprovalManifestError(f"approval manifest not found: {path}")
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ApprovalManifestError("approval manifest must contain a mapping")
    data = cast(dict[str, object], loaded)
    approved_steps = _string_tuple(data, "approved_steps")
    manifest = ApprovalManifest(
        site_id=_required_string(data, "site_id"),
        flow_id=_required_string(data, "flow_id"),
        approved_steps=approved_steps,
        approver=_required_string(data, "approver"),
        reason=_required_string(data, "reason"),
        approved_at=_required_timestamp(data, "approved_at"),
        content_fingerprint=_required_string(data, "content_fingerprint"),
        source_path=path,
    )
    if len(set(manifest.approved_steps)) != len(manifest.approved_steps):
        raise ApprovalManifestError("approved_steps must not contain duplicates")
    return manifest


def site_task_requires_approval_manifest(task: TaskDefinition) -> bool:
    """Return whether a compiled site task has externally visible actions."""

    return any(_site_sensitive_step_ids(task))


def apply_approval_manifest(
    task: TaskDefinition,
    config: RuntimeConfig,
    manifest_path: Path,
) -> tuple[TaskDefinition, RuntimeConfig]:
    """Validate a manifest, attach trace metadata, and confirm approved steps."""

    manifest = load_approval_manifest(manifest_path)
    _validate_manifest_for_task(task, manifest)
    confirmed_steps = tuple(
        dict.fromkeys((*config.confirmed_steps, *manifest.approved_steps))
    )
    approved_task = replace(
        task,
        metadata={
            **task.metadata,
            **manifest.metadata(),
        },
    )
    return approved_task, replace(
        config,
        confirmed_steps=confirmed_steps,
        require_operator_approval=True,
    )


def require_approval_manifest_if_needed(
    task: TaskDefinition,
    manifest_path: Path | None,
) -> None:
    """Fail early when a sensitive site workflow lacks ops-team preapproval."""

    if manifest_path is None and site_task_requires_approval_manifest(task):
        site_id = task.metadata.get("site_id", "unknown")
        flow_id = task.metadata.get("site_flow_id", "unknown")
        raise ApprovalManifestError(
            "approval manifest is required for sensitive site flow "
            f"{site_id}/{flow_id}",
        )


def _validate_manifest_for_task(
    task: TaskDefinition,
    manifest: ApprovalManifest,
) -> None:
    site_id = _metadata_string(task, "site_id")
    flow_id = _metadata_string(task, "site_flow_id")
    if manifest.site_id != site_id:
        raise ApprovalManifestError(
            f"approval manifest site_id mismatch: {manifest.site_id} != {site_id}",
        )
    if manifest.flow_id != flow_id:
        raise ApprovalManifestError(
            f"approval manifest flow_id mismatch: {manifest.flow_id} != {flow_id}",
        )

    known_step_ids = {step.id for step in task.steps}
    unknown_steps = sorted(set(manifest.approved_steps) - known_step_ids)
    if unknown_steps:
        raise ApprovalManifestError(
            "approval manifest approved unknown step(s): "
            + ", ".join(unknown_steps),
        )

    sensitive_step_ids = set(_site_sensitive_step_ids(task))
    missing_steps = sorted(sensitive_step_ids - set(manifest.approved_steps))
    if missing_steps:
        raise ApprovalManifestError(
            "approval manifest missing sensitive step(s): "
            + ", ".join(missing_steps),
        )

    task_fingerprint = task.metadata.get("content_variables_fingerprint")
    if (
        isinstance(task_fingerprint, str)
        and manifest.content_fingerprint != task_fingerprint
    ):
        raise ApprovalManifestError("approval manifest content_fingerprint mismatch")


def _site_sensitive_step_ids(task: TaskDefinition) -> tuple[str, ...]:
    step_ids: list[str] = []
    for step in task.steps:
        sensitive_category = step.metadata.get("site_sensitive_category")
        if (
            isinstance(sensitive_category, str)
            or step.requires_confirmation
            or step_category(step) == "submission"
        ):
            step_ids.append(step.id)
    return tuple(step_ids)


def _metadata_string(task: TaskDefinition, key: str) -> str:
    value = task.metadata.get(key)
    if not isinstance(value, str) or not value:
        raise ApprovalManifestError(f"task metadata missing {key}")
    return value


def _required_string(data: dict[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ApprovalManifestError(f"{key} is required")
    return value.strip()


def _required_timestamp(data: dict[str, object], key: str) -> str:
    raw_value = data.get(key)
    # PyYAML parses unquoted ISO timestamps into datetime objects, so accept
    # both authored strings and YAML-native timestamps for operator manifests.
    if isinstance(raw_value, datetime):
        value = raw_value.isoformat()
    elif isinstance(raw_value, str) and raw_value.strip():
        value = raw_value.strip()
    else:
        raise ApprovalManifestError(f"{key} is required")
    normalized = value.replace("Z", "+00:00")
    try:
        datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ApprovalManifestError(f"{key} must be an ISO timestamp") from exc
    return value


def _string_tuple(data: dict[str, object], key: str) -> tuple[str, ...]:
    value = data.get(key)
    if not isinstance(value, list) or not value:
        raise ApprovalManifestError(f"{key} must be a non-empty list of strings")
    if not all(isinstance(item, str) and item.strip() for item in value):
        raise ApprovalManifestError(f"{key} must be a non-empty list of strings")
    return tuple(cast(str, item).strip() for item in value)
