from desktop_agent.local_model_validation import (
    validate_missing_input_response,
    validate_routine_ranking_response,
    validate_screen_summary_response,
    validate_trace_summary_response,
    validate_yaml_improvement_response,
)


def test_validate_routine_ranking_accepts_known_candidates_only() -> None:
    result = validate_routine_ranking_response(
        {
            "selected_routine_id": "browser.search",
            "candidate_order": ["browser.search", "browser.read"],
            "explanation": "Search is a better fit.",
        },
        candidate_ids=("browser.read", "browser.search"),
    )

    assert result.accepted is True
    assert result.metadata()["status"] == "accepted"


def test_validate_routine_ranking_rejects_unknown_and_duplicate_ids() -> None:
    result = validate_routine_ranking_response(
        {
            "selected_routine_id": "invented.raw-action",
            "candidate_order": ["browser.read", "browser.read"],
        },
        candidate_ids=("browser.read",),
    )

    assert result.accepted is False
    assert "selected_routine_id must reference a candidate" in result.errors
    assert "candidate_order contains duplicate routine IDs" in result.errors


def test_validate_missing_input_response_rejects_unknown_keys() -> None:
    result = validate_missing_input_response(
        {
            "inputs": {"recipient": "Sam", "unexpected": "value"},
            "unknown_inputs": ["message"],
        },
        required_inputs=("recipient", "message"),
    )

    assert result.accepted is False
    assert "inputs contains unknown key(s): unexpected" in result.errors


def test_validate_phase_10_advisory_outputs_accept_known_references() -> None:
    missing_inputs = validate_missing_input_response(
        {
            "inputs": {"recipient": "Sam", "message": "Daily update"},
            "unknown_inputs": [],
            "explanation": "Both values are present in the goal text.",
        },
        required_inputs=("recipient", "message"),
    )
    trace_summary = validate_trace_summary_response(
        {
            "summary": "The click missed the submit button.",
            "likely_failure_reason": "ambiguous selector",
            "evidence_references": ["action-log.jsonl#3"],
        },
        event_references=("action-log.jsonl#3",),
    )
    yaml_improvement = validate_yaml_improvement_response(
        {
            "proposals": [
                {
                    "step_id": "click-submit",
                    "rationale": "Use a narrower region.",
                    "yaml_snippet": "- id: click-submit\n  region:\n    x: REVIEW",
                    "review_required": True,
                    "applies_automatically": False,
                },
            ],
        },
        known_step_ids=("click-submit",),
    )

    assert missing_inputs.accepted is True
    assert trace_summary.accepted is True
    assert yaml_improvement.accepted is True
    assert trace_summary.normalized_output["evidence_references"] == [
        "action-log.jsonl#3",
    ]
    assert yaml_improvement.normalized_output["proposals"] == [
        {
            "step_id": "click-submit",
            "rationale": "Use a narrower region.",
            "yaml_snippet": "- id: click-submit\n  region:\n    x: REVIEW",
            "review_required": True,
            "applies_automatically": False,
        },
    ]


def test_validate_trace_summary_response_requires_known_evidence_refs() -> None:
    result = validate_trace_summary_response(
        {
            "summary": "Click missed the target.",
            "likely_failure_reason": None,
            "evidence_references": ["action-log.jsonl#3", "unknown"],
        },
        event_references=("action-log.jsonl#3",),
    )

    assert result.accepted is False
    assert any("unknown reference" in error for error in result.errors)


def test_validate_screen_summary_response_requires_structured_strings() -> None:
    result = validate_screen_summary_response(
        {
            "summary": "A form is visible.",
            "notable_targets": ["Submit"],
            "uncertainties": [],
        },
    )

    assert result.accepted is True
    assert result.normalized_output["notable_targets"] == ["Submit"]


def test_validate_yaml_improvement_response_is_review_only() -> None:
    result = validate_yaml_improvement_response(
        {
            "proposals": [
                {
                    "step_id": "click-submit",
                    "rationale": "Selector is ambiguous.",
                    "yaml_snippet": "- id: click-submit",
                    "review_required": False,
                    "applies_automatically": True,
                },
            ],
        },
        known_step_ids=("click-submit",),
    )

    assert result.accepted is False
    assert "proposal 0 review_required must be true" in result.errors
    assert "proposal 0 applies_automatically must be false" in result.errors
