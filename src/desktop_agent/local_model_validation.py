"""Structured response validation for optional local model prompts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from desktop_agent.local_model_prompts import (
    PROMPT_CLASS_MISSING_INPUT_EXTRACTION,
    PROMPT_CLASS_ROUTINE_RANKING,
    PROMPT_CLASS_SCREEN_SUMMARY,
    PROMPT_CLASS_TRACE_SUMMARIZATION,
    PROMPT_CLASS_YAML_IMPROVEMENT,
)

ValidationStatus = Literal["accepted", "rejected"]


@dataclass(frozen=True)
class LocalModelValidationResult:
    """Validation result for a structured local-model response."""

    prompt_class: str
    status: ValidationStatus
    normalized_output: Mapping[str, object]
    errors: tuple[str, ...] = ()

    @property
    def accepted(self) -> bool:
        return self.status == "accepted"

    def metadata(self) -> dict[str, object]:
        return {
            "prompt_class": self.prompt_class,
            "status": self.status,
            "accepted": self.accepted,
            "errors": list(self.errors),
            "normalized_output": dict(self.normalized_output),
        }


def validate_routine_ranking_response(
    output: Mapping[str, object],
    *,
    candidate_ids: Sequence[str],
) -> LocalModelValidationResult:
    """Validate that routine ranking output references known routine IDs only."""
    allowed_ids = tuple(candidate_ids)
    errors: list[str] = []
    selected = _optional_string(output.get("selected_routine_id"))
    order = _string_list(output.get("candidate_order"), "candidate_order", errors)
    explanation = _optional_string(output.get("explanation")) or ""

    if selected is not None and selected not in allowed_ids:
        errors.append("selected_routine_id must reference a candidate")
    unknown_ids = sorted(
        {routine_id for routine_id in order if routine_id not in allowed_ids},
    )
    if unknown_ids:
        errors.append(
            "candidate_order contains unknown routine id(s): " + ", ".join(unknown_ids),
        )
    if len(order) != len(set(order)):
        errors.append("candidate_order contains duplicate routine IDs")

    normalized: dict[str, object] = {
        "selected_routine_id": selected,
        "candidate_order": order,
        "explanation": explanation,
    }
    return _validation_result(PROMPT_CLASS_ROUTINE_RANKING, normalized, errors)


def validate_missing_input_response(
    output: Mapping[str, object],
    *,
    required_inputs: Sequence[str],
) -> LocalModelValidationResult:
    """Validate draft input extraction output against known required inputs."""
    allowed_inputs = tuple(required_inputs)
    errors: list[str] = []
    inputs = output.get("inputs")
    if not isinstance(inputs, Mapping):
        errors.append("inputs must be an object")
        normalized_inputs: dict[str, object] = {}
    else:
        normalized_inputs = {
            str(key): value
            for key, value in inputs.items()
            if isinstance(key, str)
        }
        unknown_keys = sorted(set(normalized_inputs) - set(allowed_inputs))
        if unknown_keys:
            errors.append("inputs contains unknown key(s): " + ", ".join(unknown_keys))
    unknown_inputs = _string_list(
        output.get("unknown_inputs"),
        "unknown_inputs",
        errors,
    )
    invalid_unknowns = sorted(set(unknown_inputs) - set(allowed_inputs))
    if invalid_unknowns:
        errors.append(
            "unknown_inputs contains unknown key(s): " + ", ".join(invalid_unknowns),
        )
    normalized = {
        "inputs": normalized_inputs,
        "unknown_inputs": unknown_inputs,
        "explanation": _optional_string(output.get("explanation")) or "",
    }
    return _validation_result(
        PROMPT_CLASS_MISSING_INPUT_EXTRACTION,
        normalized,
        errors,
    )


def validate_trace_summary_response(
    output: Mapping[str, object],
    *,
    event_references: Sequence[str],
) -> LocalModelValidationResult:
    """Validate trace summary output against supplied evidence references."""
    allowed_refs = tuple(event_references)
    errors: list[str] = []
    summary = _required_string(output.get("summary"), "summary", errors)
    reason = _nullable_string(
        output.get("likely_failure_reason"),
        "likely_failure_reason",
        errors,
    )
    evidence_refs = _string_list(
        output.get("evidence_references"),
        "evidence_references",
        errors,
    )
    invalid_refs = sorted(set(evidence_refs) - set(allowed_refs))
    if invalid_refs:
        errors.append(
            "evidence_references contains unknown reference(s): "
            + ", ".join(invalid_refs),
        )
    normalized = {
        "summary": summary,
        "likely_failure_reason": reason,
        "evidence_references": evidence_refs,
    }
    return _validation_result(PROMPT_CLASS_TRACE_SUMMARIZATION, normalized, errors)


def validate_screen_summary_response(
    output: Mapping[str, object],
) -> LocalModelValidationResult:
    """Validate review-only screen summary output."""
    errors: list[str] = []
    normalized = {
        "summary": _required_string(output.get("summary"), "summary", errors),
        "notable_targets": _string_list(
            output.get("notable_targets"),
            "notable_targets",
            errors,
        ),
        "uncertainties": _string_list(
            output.get("uncertainties"),
            "uncertainties",
            errors,
        ),
    }
    return _validation_result(PROMPT_CLASS_SCREEN_SUMMARY, normalized, errors)


def validate_yaml_improvement_response(
    output: Mapping[str, object],
    *,
    known_step_ids: Sequence[str],
) -> LocalModelValidationResult:
    """Validate review-only YAML improvement proposals."""
    allowed_steps = tuple(known_step_ids)
    errors: list[str] = []
    proposals = output.get("proposals")
    normalized_proposals: list[dict[str, object]] = []
    if not isinstance(proposals, Sequence) or isinstance(proposals, (str, bytes)):
        errors.append("proposals must be an array")
    else:
        for index, proposal in enumerate(proposals):
            if not isinstance(proposal, Mapping):
                errors.append(f"proposal {index} must be an object")
                continue
            normalized_proposals.append(
                _validate_yaml_proposal(proposal, index, allowed_steps, errors),
            )
    normalized = {"proposals": normalized_proposals}
    return _validation_result(PROMPT_CLASS_YAML_IMPROVEMENT, normalized, errors)


def _validate_yaml_proposal(
    proposal: Mapping[object, object],
    index: int,
    allowed_steps: Sequence[str],
    errors: list[str],
) -> dict[str, object]:
    step_id = _optional_string(proposal.get("step_id"))
    rationale = _required_string(proposal.get("rationale"), "rationale", errors)
    yaml_snippet = _required_string(
        proposal.get("yaml_snippet"),
        "yaml_snippet",
        errors,
    )
    review_required = proposal.get("review_required", True)
    applies_automatically = proposal.get("applies_automatically", False)
    if step_id is None or step_id not in allowed_steps:
        errors.append(f"proposal {index} step_id must reference a known step")
    if review_required is not True:
        errors.append(f"proposal {index} review_required must be true")
    if applies_automatically is not False:
        errors.append(f"proposal {index} applies_automatically must be false")
    return {
        "step_id": step_id,
        "rationale": rationale,
        "yaml_snippet": yaml_snippet,
        "review_required": review_required,
        "applies_automatically": applies_automatically,
    }


def _validation_result(
    prompt_class: str,
    normalized_output: Mapping[str, object],
    errors: Sequence[str],
) -> LocalModelValidationResult:
    return LocalModelValidationResult(
        prompt_class=prompt_class,
        status="rejected" if errors else "accepted",
        normalized_output=normalized_output,
        errors=tuple(errors),
    )


def _required_string(value: object, field_name: str, errors: list[str]) -> str:
    text = _optional_string(value)
    if text is None:
        errors.append(f"{field_name} must be a non-empty string")
        return ""
    return text


def _nullable_string(value: object, field_name: str, errors: list[str]) -> str | None:
    if value is None:
        return None
    text = _optional_string(value)
    if text is None:
        errors.append(f"{field_name} must be a string or null")
        return None
    return text


def _optional_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _string_list(value: object, field_name: str, errors: list[str]) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        errors.append(f"{field_name} must be an array of strings")
        return []
    items: list[str] = []
    for index, item in enumerate(value):
        text = _optional_string(item)
        if text is None:
            errors.append(f"{field_name}[{index}] must be a non-empty string")
            continue
        items.append(text)
    return items
