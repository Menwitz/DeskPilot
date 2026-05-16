"""Prompt contracts for optional local model assistance."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

PROMPT_CLASS_ROUTINE_RANKING = "goal_routine_ranking"
PROMPT_CLASS_MISSING_INPUT_EXTRACTION = "missing_input_extraction"
PROMPT_CLASS_TRACE_SUMMARIZATION = "trace_summarization"
PROMPT_CLASS_SCREEN_SUMMARY = "screen_summary"
PROMPT_CLASS_YAML_IMPROVEMENT = "yaml_improvement_suggestions"

LOCAL_MODEL_PROMPT_CLASSES: frozenset[str] = frozenset(
    {
        PROMPT_CLASS_ROUTINE_RANKING,
        PROMPT_CLASS_MISSING_INPUT_EXTRACTION,
        PROMPT_CLASS_TRACE_SUMMARIZATION,
        PROMPT_CLASS_SCREEN_SUMMARY,
        PROMPT_CLASS_YAML_IMPROVEMENT,
    },
)

COMMON_LOCAL_MODEL_CONSTRAINTS: tuple[str, ...] = (
    "Return JSON only.",
    "Do not execute desktop input or issue commands.",
    "Do not invent routine IDs, step IDs, URLs, selectors, or actions.",
    "Treat output as advisory until deterministic validation accepts it.",
)


@dataclass(frozen=True)
class LocalModelPrompt:
    """A typed local-model prompt with traceable metadata."""

    prompt_class: str
    purpose: str
    response_schema: Mapping[str, object]
    payload: Mapping[str, object]
    input_artifact_references: tuple[str, ...] = ()
    constraints: tuple[str, ...] = COMMON_LOCAL_MODEL_CONSTRAINTS

    @property
    def text(self) -> str:
        return json.dumps(self.body(), sort_keys=True)

    @property
    def text_hash(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()

    def body(self) -> dict[str, object]:
        return {
            "prompt_class": self.prompt_class,
            "purpose": self.purpose,
            "response_schema": dict(self.response_schema),
            "input_artifact_references": list(self.input_artifact_references),
            "constraints": list(self.constraints),
            **dict(self.payload),
        }

    def metadata(self) -> dict[str, object]:
        return {
            "prompt_class": self.prompt_class,
            "purpose": self.purpose,
            "input_artifact_references": list(self.input_artifact_references),
            "response_schema": dict(self.response_schema),
            "text_hash": self.text_hash,
        }


def build_routine_ranking_prompt(
    *,
    user_goal: str,
    normalized_intent: str,
    candidates: Sequence[Mapping[str, object]],
) -> LocalModelPrompt:
    """Build the advisory routine-ranking prompt used by goal planning."""
    return LocalModelPrompt(
        prompt_class=PROMPT_CLASS_ROUTINE_RANKING,
        purpose="Rank known DeskPilot routines for a user goal.",
        response_schema={
            "selected_routine_id": "one candidate routine_id or null",
            "candidate_order": "array of candidate routine_id values",
            "explanation": "short operator-facing reason",
        },
        payload={
            "task": (
                "Rank these existing DeskPilot routine candidates for the user "
                "goal."
            ),
            "user_goal": user_goal,
            "normalized_intent": normalized_intent,
            "candidates": [dict(candidate) for candidate in candidates],
        },
        input_artifact_references=("goal_plan.candidate_routines",),
        constraints=(
            "Use only routine_id values present in candidates.",
            *COMMON_LOCAL_MODEL_CONSTRAINTS,
            (
                "Safety, inputs, approvals, and execution eligibility are "
                "enforced outside the model."
            ),
        ),
    )


def build_missing_input_extraction_prompt(
    *,
    user_goal: str,
    required_inputs: Sequence[str],
    provided_context: Mapping[str, object],
) -> LocalModelPrompt:
    """Build a prompt for extracting draft routine inputs from user text."""
    return LocalModelPrompt(
        prompt_class=PROMPT_CLASS_MISSING_INPUT_EXTRACTION,
        purpose="Extract draft values for known missing routine inputs.",
        response_schema={
            "inputs": "object keyed by required input name",
            "unknown_inputs": "array of required input names that need operator input",
            "explanation": "short operator-facing reason",
        },
        payload={
            "task": "Extract draft input values from the user goal and context.",
            "user_goal": user_goal,
            "required_inputs": list(required_inputs),
            "provided_context": dict(provided_context),
        },
        input_artifact_references=("goal_plan.missing_inputs",),
    )


def build_trace_summarization_prompt(
    *,
    trace_summary: Mapping[str, object],
    event_references: Sequence[str],
) -> LocalModelPrompt:
    """Build a prompt for summarizing local trace artifacts for review."""
    return LocalModelPrompt(
        prompt_class=PROMPT_CLASS_TRACE_SUMMARIZATION,
        purpose="Summarize a local trace without changing routine behavior.",
        response_schema={
            "summary": "short operator-facing summary",
            "likely_failure_reason": "string or null",
            "evidence_references": "array of supplied event reference IDs",
        },
        payload={
            "task": "Summarize this DeskPilot trace for operator review.",
            "trace_summary": dict(trace_summary),
            "event_references": list(event_references),
        },
        input_artifact_references=tuple(event_references),
    )


def build_screen_summary_prompt(
    *,
    screen_summary: Mapping[str, object],
    artifact_references: Sequence[str],
) -> LocalModelPrompt:
    """Build a prompt for review-only screen explanation and authoring."""
    return LocalModelPrompt(
        prompt_class=PROMPT_CLASS_SCREEN_SUMMARY,
        purpose="Describe visible screen state for review and authoring.",
        response_schema={
            "summary": "short visible-state summary",
            "notable_targets": "array of labels already visible in supplied artifacts",
            "uncertainties": "array of things the model cannot determine",
        },
        payload={
            "task": "Explain the visible screen state using only supplied artifacts.",
            "screen_summary": dict(screen_summary),
        },
        input_artifact_references=tuple(artifact_references),
        constraints=(
            *COMMON_LOCAL_MODEL_CONSTRAINTS,
            "Do not decide a click target; deterministic perception selects targets.",
        ),
    )


def build_yaml_improvement_prompt(
    *,
    failure_summary: Mapping[str, object],
    task_yaml_excerpt: str,
    known_step_ids: Sequence[str],
) -> LocalModelPrompt:
    """Build a prompt for review-only YAML improvement suggestions."""
    return LocalModelPrompt(
        prompt_class=PROMPT_CLASS_YAML_IMPROVEMENT,
        purpose="Suggest review-only YAML edits for a failed known routine.",
        response_schema={
            "proposals": "array of review-only proposal objects",
            "proposal.step_id": "one supplied step ID",
            "proposal.rationale": "short reason grounded in supplied evidence",
            "proposal.yaml_snippet": "editable YAML snippet for operator review",
        },
        payload={
            "task": "Suggest YAML improvements for operator review only.",
            "failure_summary": dict(failure_summary),
            "task_yaml_excerpt": task_yaml_excerpt,
            "known_step_ids": list(known_step_ids),
        },
        input_artifact_references=("failed_run.analysis", "task.yaml"),
        constraints=(
            "Use only supplied step IDs.",
            *COMMON_LOCAL_MODEL_CONSTRAINTS,
            "Do not apply YAML changes automatically.",
        ),
    )
