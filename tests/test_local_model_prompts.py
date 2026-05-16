import json

from desktop_agent.goal_planning import GoalModelRanking
from desktop_agent.local_model_prompts import (
    LOCAL_MODEL_PROMPT_CLASSES,
    PROMPT_CLASS_MISSING_INPUT_EXTRACTION,
    PROMPT_CLASS_ROUTINE_RANKING,
    PROMPT_CLASS_SCREEN_SUMMARY,
    PROMPT_CLASS_TRACE_SUMMARIZATION,
    PROMPT_CLASS_YAML_IMPROVEMENT,
    build_missing_input_extraction_prompt,
    build_routine_ranking_prompt,
    build_screen_summary_prompt,
    build_trace_summarization_prompt,
    build_yaml_improvement_prompt,
)


def test_local_model_prompt_classes_cover_phase_10_use_cases() -> None:
    assert {
        PROMPT_CLASS_ROUTINE_RANKING,
        PROMPT_CLASS_MISSING_INPUT_EXTRACTION,
        PROMPT_CLASS_TRACE_SUMMARIZATION,
        PROMPT_CLASS_SCREEN_SUMMARY,
        PROMPT_CLASS_YAML_IMPROVEMENT,
    } == LOCAL_MODEL_PROMPT_CLASSES
    assert GoalModelRanking().prompt_class == PROMPT_CLASS_ROUTINE_RANKING


def test_routine_ranking_prompt_uses_known_candidate_ids_only() -> None:
    prompt = build_routine_ranking_prompt(
        user_goal="Check my morning inbox",
        normalized_intent="check morning inbox",
        candidates=(
            {
                "routine_id": "email.read-inbox",
                "name": "Read inbox",
                "score": 8,
            },
        ),
    )
    body = json.loads(prompt.text)

    assert body["prompt_class"] == PROMPT_CLASS_ROUTINE_RANKING
    assert body["response_schema"]["selected_routine_id"]
    assert body["candidates"][0]["routine_id"] == "email.read-inbox"
    assert "Use only routine_id values present in candidates." in body["constraints"]
    assert prompt.metadata()["text_hash"]


def test_missing_input_prompt_extracts_only_known_inputs() -> None:
    prompt = build_missing_input_extraction_prompt(
        user_goal="Send the weekly note to Sam",
        required_inputs=("recipient", "message"),
        provided_context={"routine_id": "email.send-draft"},
    )
    body = json.loads(prompt.text)

    assert body["prompt_class"] == PROMPT_CLASS_MISSING_INPUT_EXTRACTION
    assert body["required_inputs"] == ["recipient", "message"]
    assert "unknown_inputs" in body["response_schema"]


def test_trace_and_screen_summary_prompts_are_review_only() -> None:
    trace_prompt = build_trace_summarization_prompt(
        trace_summary={"status": "failed", "abort_reason": "missed target"},
        event_references=("action-log.jsonl#3",),
    )
    screen_prompt = build_screen_summary_prompt(
        screen_summary={"ocr_text": "Submit Cancel"},
        artifact_references=("screenshots/after.png",),
    )

    trace_body = json.loads(trace_prompt.text)
    screen_body = json.loads(screen_prompt.text)

    assert trace_body["prompt_class"] == PROMPT_CLASS_TRACE_SUMMARIZATION
    assert trace_body["input_artifact_references"] == ["action-log.jsonl#3"]
    assert screen_body["prompt_class"] == PROMPT_CLASS_SCREEN_SUMMARY
    assert "deterministic perception selects targets" in " ".join(
        screen_body["constraints"],
    )


def test_yaml_improvement_prompt_requires_review_only_proposals() -> None:
    prompt = build_yaml_improvement_prompt(
        failure_summary={"step_id": "click-submit", "reason": "ambiguous label"},
        task_yaml_excerpt="- id: click-submit\n  action: click_text",
        known_step_ids=("click-submit",),
    )
    body = json.loads(prompt.text)

    assert body["prompt_class"] == PROMPT_CLASS_YAML_IMPROVEMENT
    assert body["known_step_ids"] == ["click-submit"]
    assert "proposal.yaml_snippet" in body["response_schema"]
    assert "Do not apply YAML changes automatically." in body["constraints"]
