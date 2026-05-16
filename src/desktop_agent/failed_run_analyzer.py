"""Review-only failed-run analysis and YAML improvement proposals."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path


@dataclass(frozen=True)
class FailedRunYamlProposal:
    """One suggested YAML change that must be reviewed before use."""

    step_id: str
    proposal_type: str
    rationale: str
    yaml_snippet: str
    review_required: bool = True
    applies_automatically: bool = False

    def metadata(self) -> dict[str, object]:
        return {
            "step_id": self.step_id,
            "proposal_type": self.proposal_type,
            "rationale": self.rationale,
            "yaml_snippet": self.yaml_snippet,
            "review_required": self.review_required,
            "applies_automatically": self.applies_automatically,
        }


@dataclass(frozen=True)
class FailedRunArtifact:
    """One local artifact that can support failed-run diagnosis."""

    name: str
    path: str
    present: bool
    required: bool

    def metadata(self) -> dict[str, object]:
        return {
            "name": self.name,
            "path": self.path,
            "present": self.present,
            "required": self.required,
        }


@dataclass(frozen=True)
class FailedRunAnalysis:
    """Summary of review-only proposals for one failed run report."""

    task_name: str
    status: str
    routine_id: str | None
    proposals: tuple[FailedRunYamlProposal, ...]
    diagnostic_ready: bool = False
    artifacts: tuple[FailedRunArtifact, ...] = ()

    def metadata(self) -> dict[str, object]:
        return {
            "task_name": self.task_name,
            "status": self.status,
            "routine_id": self.routine_id,
            "proposal_count": len(self.proposals),
            "diagnostic_ready": self.diagnostic_ready,
            "desktop_input_rerun_required": False,
            "artifacts": [artifact.metadata() for artifact in self.artifacts],
            "proposals": [proposal.metadata() for proposal in self.proposals],
        }


def analyze_failed_run_report(report: Mapping[str, object]) -> FailedRunAnalysis:
    """Build review-only YAML proposals from a final-report payload."""
    task_name = _string_value(report.get("task_name"), "unknown")
    status = _string_value(report.get("status"), "unknown")
    routine_id = _routine_id(report)
    proposals: list[FailedRunYamlProposal] = []
    if status == "passed":
        return FailedRunAnalysis(task_name, status, routine_id, ())

    steps = report.get("steps")
    if not isinstance(steps, list):
        return FailedRunAnalysis(task_name, status, routine_id, ())
    for step in steps:
        if isinstance(step, dict):
            proposals.extend(_proposals_for_failed_step(step))
    return FailedRunAnalysis(task_name, status, routine_id, tuple(proposals))


def analyze_failed_run_trace(trace_dir: Path) -> FailedRunAnalysis:
    """Read one trace directory and analyze its final report."""
    report_path = trace_dir / "final-report.json"
    if not report_path.exists():
        raise FileNotFoundError(f"final report not found: {report_path}")
    loaded = json.loads(report_path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("final-report.json must contain a JSON object")
    analysis = analyze_failed_run_report(loaded)
    artifacts = _local_diagnostic_artifacts(trace_dir)
    return replace(
        analysis,
        diagnostic_ready=all(
            artifact.present for artifact in artifacts if artifact.required
        ),
        artifacts=artifacts,
    )


def write_failed_run_analysis(trace_dir: Path, analysis: FailedRunAnalysis) -> None:
    """Write machine and human readable analysis artifacts next to the trace."""
    (trace_dir / "failed-run-analysis.json").write_text(
        json.dumps(analysis.metadata(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (trace_dir / "failed-run-analysis.md").write_text(
        render_failed_run_analysis_markdown(analysis),
        encoding="utf-8",
    )


def render_failed_run_analysis_markdown(analysis: FailedRunAnalysis) -> str:
    lines = [
        "# DeskPilot Failed Run Analysis",
        "",
        f"- Task: `{analysis.task_name}`",
        f"- Status: `{analysis.status}`",
        f"- Routine: `{analysis.routine_id or 'none'}`",
        f"- Proposal count: `{len(analysis.proposals)}`",
        f"- Diagnostic ready: `{str(analysis.diagnostic_ready).lower()}`",
        "- Desktop input rerun required: `false`",
        "- Applies automatically: `false`",
        "",
        "## Local Artifacts",
    ]
    if not analysis.artifacts:
        lines.append("- No trace artifact index available.")
    for artifact in analysis.artifacts:
        marker = "present" if artifact.present else "missing"
        required = "required" if artifact.required else "optional"
        lines.append(
            f"- `{artifact.name}`: `{marker}` `{required}` `{artifact.path}`",
        )
    lines.extend(
        [
            "",
            "## Proposals",
        ],
    )
    if not analysis.proposals:
        lines.append("- No YAML proposals generated.")
        return "\n".join(lines) + "\n"
    for proposal in analysis.proposals:
        lines.extend(
            [
                f"- Step `{proposal.step_id}`: `{proposal.proposal_type}`",
                f"  - Rationale: {proposal.rationale}",
                "  - Review required: `true`",
                "  - YAML snippet:",
                "```yaml",
                proposal.yaml_snippet,
                "```",
            ],
        )
    return "\n".join(lines) + "\n"


def _proposals_for_failed_step(
    step: Mapping[str, object],
) -> tuple[FailedRunYamlProposal, ...]:
    status = step.get("status")
    if status == "passed":
        return ()
    step_id = _string_value(step.get("step_id"), "unknown-step")
    metadata = step.get("metadata")
    if not isinstance(metadata, dict):
        return ()
    failure_category = _string_value(metadata.get("failure_category"), "unknown")
    if failure_category in {"selection_ambiguity", "layout_change"}:
        proposal_type = (
            "recovery_review"
            if failure_category == "layout_change"
            else "selector_region_review"
        )
        return (
            FailedRunYamlProposal(
                step_id=step_id,
                proposal_type=proposal_type,
                rationale=_selector_rationale(metadata, failure_category),
                yaml_snippet=_selector_yaml_snippet(step_id, failure_category),
            ),
        )
    if failure_category in {"verification_failure", "verification_inconclusive"}:
        return (
            FailedRunYamlProposal(
                step_id=step_id,
                proposal_type="verification_checkpoint_review",
                rationale="Verification failed or stayed inconclusive after action.",
                yaml_snippet=_verification_yaml_snippet(step_id),
            ),
        )
    if failure_category == "safety_stop":
        return (
            FailedRunYamlProposal(
                step_id=step_id,
                proposal_type="allowed_window_review",
                rationale="Safety stopped before input; review allowed windows.",
                yaml_snippet="allowed_windows:\n  - REVIEWED_WINDOW_TITLE",
            ),
        )
    return ()


def _selector_rationale(metadata: Mapping[object, object], category: str) -> str:
    diagnostic = metadata.get("diagnostic_bundle")
    if not isinstance(diagnostic, dict):
        return f"Target selection failed with category {category}."
    candidate_count = diagnostic.get("candidate_count")
    sources = diagnostic.get("candidates_by_source")
    return (
        f"Target selection failed with category {category}; "
        f"candidate_count={candidate_count}, candidates_by_source={sources}."
    )


def _selector_yaml_snippet(step_id: str, category: str) -> str:
    if category == "layout_change":
        return (
            f"- id: {step_id}\n"
            "  recovery:\n"
            "    - reason: layout_change\n"
            "      actions:\n"
            "        - retry_alternate_selector_family\n"
            "        - abort_with_trace"
        )
    # Ambiguous target failures need both a more stable selector and a tighter
    # region hint so review can choose the least brittle YAML change.
    return (
        f"- id: {step_id}\n"
        "  selector:\n"
        "    text: REVIEW_TARGET_TEXT\n"
        "    role: REVIEW_ROLE\n"
        "  region:\n"
        "    x: REVIEW\n"
        "    y: REVIEW\n"
        "    width: REVIEW\n"
        "    height: REVIEW"
    )


def _verification_yaml_snippet(step_id: str) -> str:
    return (
        f"- id: {step_id}\n"
        "  checkpoint:\n"
        "    type: visible_text\n"
        "    text: REVIEW_EXPECTED_TEXT"
    )


def _routine_id(report: Mapping[str, object]) -> str | None:
    metadata = report.get("metadata")
    if not isinstance(metadata, dict):
        return None
    routine_id = metadata.get("routine_id")
    return routine_id if isinstance(routine_id, str) else None


def _string_value(value: object, fallback: str) -> str:
    return value if isinstance(value, str) else fallback


def _local_diagnostic_artifacts(trace_dir: Path) -> tuple[FailedRunArtifact, ...]:
    return (
        _artifact(trace_dir, "final_report", "final-report.json", required=True),
        _artifact(trace_dir, "action_log", "action-log.jsonl", required=True),
        _artifact(trace_dir, "task_snapshot", "task.json", required=False),
        _artifact(trace_dir, "config_snapshot", "config.json", required=False),
        _artifact(trace_dir, "trace_schema", "trace-schema.json", required=False),
        _artifact(trace_dir, "safety_audit", "safety-audit.md", required=False),
        _artifact(trace_dir, "replay_summary", "replay-summary.md", required=False),
        _artifact(trace_dir, "screenshots", "screenshots", required=False),
    )


def _artifact(
    trace_dir: Path,
    name: str,
    relative_path: str,
    *,
    required: bool,
) -> FailedRunArtifact:
    path = trace_dir / relative_path
    return FailedRunArtifact(
        name=name,
        path=str(path),
        present=path.exists(),
        required=required,
    )
