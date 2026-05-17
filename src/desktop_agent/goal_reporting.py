"""Local trace/report artifacts for goal-planning dry-runs."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

from desktop_agent.goal_planning import GoalPlan
from desktop_agent.tracing import TRACE_SCHEMA_V2, TraceEvent


def write_goal_plan_trace(plan: GoalPlan, trace_root: Path) -> Path:
    """Write a local goal-plan trace directory and return its path."""
    trace_dir = _goal_trace_directory(trace_root, plan.user_goal)
    trace_dir.mkdir(parents=True, exist_ok=False)

    goal_plan_path = trace_dir / "goal-plan.json"
    input_refs = _model_input_artifact_references()
    _write_json(goal_plan_path, _goal_plan_payload(plan, input_refs))
    _write_json(trace_dir / "trace-schema.json", TRACE_SCHEMA_V2.to_dict())

    events = [
        TraceEvent(
            phase="goal_plan",
            message=f"goal plan {plan.execution_status}",
            metadata={
                "selected_routine_id": plan.selected_routine_id,
                "execution_status": plan.execution_status,
                "candidate_count": len(plan.candidate_routines),
                "expected_evidence": list(plan.expected_evidence),
                "abort_conditions": list(plan.abort_conditions),
            },
        ),
    ]
    model_disclosure = goal_model_disclosure_metadata(
        plan,
        input_artifact_references=input_refs,
    )
    if model_disclosure is not None:
        events.append(
            TraceEvent(
                phase="model_assistance",
                message=f"model assistance {model_disclosure['status']}",
                metadata=model_disclosure,
            ),
        )

    _write_action_log(trace_dir / "action-log.jsonl", events)
    _write_json(
        trace_dir / "goal-plan-report.json",
        _goal_plan_report_payload(plan, goal_plan_path, model_disclosure),
    )
    (trace_dir / "goal-plan-report.md").write_text(
        _goal_plan_report_markdown(plan, model_disclosure),
        encoding="utf-8",
    )
    return trace_dir


def goal_model_disclosure_metadata(
    plan: GoalPlan,
    *,
    input_artifact_references: tuple[str, ...] = (),
) -> dict[str, object] | None:
    """Return trace-safe model disclosure metadata for a goal plan."""
    if plan.model_ranking is None:
        return None
    ranking = plan.model_ranking
    return {
        "trace_schema_section": "model_assistance",
        "provider": ranking.provider,
        "model": ranking.model,
        "model_name": ranking.model,
        "prompt_class": ranking.prompt_class,
        "input_artifact_references": list(input_artifact_references),
        "output_hash": ranking.output_hash,
        "structured_output_status": _structured_output_status(ranking.status),
        "accepted": ranking.status == "applied",
        "rejected": ranking.status == "rejected",
        "affected_selection": ranking.affected_selection,
        "enabled": ranking.enabled,
        "attempted": ranking.attempted,
        "status": ranking.status,
        "selected_routine_id": ranking.selected_routine_id,
        "candidate_order": list(ranking.candidate_order),
        "error": ranking.error,
    }


def _structured_output_status(status: str) -> str:
    if status == "applied":
        return "accepted"
    if status == "rejected":
        return "rejected"
    return "not_attempted"


def _goal_trace_directory(trace_root: Path, user_goal: str) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    return trace_root / f"{timestamp}-goal-plan-{_slug(user_goal)}"


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip()).strip("-")
    return slug[:64] or "goal"


def _model_input_artifact_references() -> tuple[str, ...]:
    # These fragments point at the deterministic data used to build the prompt.
    return (
        "goal-plan.json#user_goal",
        "goal-plan.json#normalized_intent",
        "goal-plan.json#candidate_routines",
    )


def _goal_plan_payload(
    plan: GoalPlan,
    input_artifact_references: tuple[str, ...],
) -> dict[str, object]:
    payload = plan.metadata()
    model_ranking = payload.get("model_ranking")
    if isinstance(model_ranking, dict):
        model_ranking["input_artifact_references"] = list(input_artifact_references)
    return payload


def _goal_plan_report_payload(
    plan: GoalPlan,
    goal_plan_path: Path,
    model_disclosure: dict[str, object] | None,
) -> dict[str, object]:
    trace_dir = goal_plan_path.parent
    return {
        "trace_schema_version": TRACE_SCHEMA_V2.version,
        "trace_schema": TRACE_SCHEMA_V2.to_dict(),
        "status": plan.execution_status,
        "normalized_intent": plan.normalized_intent,
        "selected_routine_id": plan.selected_routine_id,
        "candidate_count": len(plan.candidate_routines),
        "candidate_routines": [
            candidate.metadata() for candidate in plan.candidate_routines
        ],
        "expected_evidence": list(plan.expected_evidence),
        "abort_conditions": list(plan.abort_conditions),
        "explanation": plan.explanation,
        "trace_dir": str(trace_dir),
        "goal_plan_path": str(goal_plan_path),
        # Goal planning traces are dry-run artifacts; replay must never move I/O.
        "replayable": True,
        "desktop_input_required": False,
        "replay_command": f"desktop-agent replay {trace_dir}",
        "model_disclosure": model_disclosure,
    }


def _goal_plan_report_markdown(
    plan: GoalPlan,
    model_disclosure: dict[str, object] | None,
) -> str:
    lines = [
        f"# DeskPilot Goal Plan Report: {plan.user_goal}",
        "",
        f"- Status: `{plan.execution_status}`",
        f"- Selected routine: `{plan.selected_routine_id or 'none'}`",
        f"- Candidates: `{len(plan.candidate_routines)}`",
        f"- Normalized intent: `{plan.normalized_intent}`",
        f"- Expected evidence: `{_joined_or_none(plan.expected_evidence)}`",
        f"- Abort conditions: `{_joined_or_none(plan.abort_conditions)}`",
    ]
    if plan.candidate_routines:
        lines.extend(["", "## Candidate Ranking", ""])
        for candidate in plan.candidate_routines:
            lines.append(
                "- "
                f"`{candidate.routine_id}` score `{candidate.score:g}` "
                f"matched `{_joined_or_none(candidate.matched_fields)}` "
                f"safety `{candidate.safety_class}` approval "
                f"`{candidate.approval_policy}`",
            )
    if model_disclosure is not None:
        lines.extend(
            [
                "",
                "## Model Assistance",
                "",
                f"- Provider: `{model_disclosure['provider']}`",
                f"- Model: `{model_disclosure['model']}`",
                f"- Prompt class: `{model_disclosure['prompt_class']}`",
                f"- Status: `{model_disclosure['status']}`",
                "- Affected selection: "
                f"`{model_disclosure['affected_selection']}`",
                f"- Output hash: `{model_disclosure['output_hash']}`",
            ],
        )
    return "\n".join(lines) + "\n"


def _joined_or_none(items: tuple[str, ...]) -> str:
    return ", ".join(items) if items else "none"


def _write_action_log(path: Path, events: list[TraceEvent]) -> None:
    lines = [
        json.dumps(
            {
                "trace_schema_version": TRACE_SCHEMA_V2.version,
                "phase": event.phase,
                "message": event.message,
                "metadata": event.metadata,
            },
            sort_keys=True,
        )
        for event in events
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
