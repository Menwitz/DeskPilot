import json
from pathlib import Path

from desktop_agent.goal_planning import (
    GoalModelRanking,
    GoalPlan,
    GoalPlanCandidate,
)
from desktop_agent.goal_reporting import (
    goal_model_disclosure_metadata,
    write_goal_plan_trace,
)


def test_goal_plan_trace_writes_model_disclosure_fields(tmp_path: Path) -> None:
    plan = GoalPlan(
        user_goal="Search the web",
        normalized_intent="browser search",
        candidate_routines=(
            GoalPlanCandidate(
                routine_id="browser.search-web",
                routine_name="Browser web search",
                score=10,
                safety_class="low",
                approval_policy="none",
            ),
        ),
        selected_routine_id="browser.search-web",
        explanation="Model-assisted ranking kept the search routine.",
        execution_status="ready",
        model_ranking=GoalModelRanking(
            provider="ollama",
            model="llama3.1",
            enabled=True,
            attempted=True,
            status="applied",
            selected_routine_id="browser.search-web",
            candidate_order=("browser.search-web",),
            output_hash="abc123",
            affected_selection=True,
        ),
    )

    trace_dir = write_goal_plan_trace(plan, tmp_path / "traces")

    goal_plan = json.loads((trace_dir / "goal-plan.json").read_text())
    report = json.loads((trace_dir / "goal-plan-report.json").read_text())
    action_log = [
        json.loads(line)
        for line in (trace_dir / "action-log.jsonl").read_text().splitlines()
    ]
    model_event = next(
        event for event in action_log if event["phase"] == "model_assistance"
    )
    metadata = model_event["metadata"]

    assert (trace_dir / "trace-schema.json").exists()
    assert (trace_dir / "goal-plan-report.md").exists()
    assert report["trace_schema"]["sections"]["model_assistance"]
    assert report["model_disclosure"]["provider"] == "ollama"
    assert metadata["provider"] == "ollama"
    assert metadata["model"] == "llama3.1"
    assert metadata["prompt_class"] == "goal_routine_ranking"
    assert metadata["input_artifact_references"] == [
        "goal-plan.json#user_goal",
        "goal-plan.json#normalized_intent",
        "goal-plan.json#candidate_routines",
    ]
    assert metadata["output_hash"] == "abc123"
    assert metadata["affected_selection"] is True
    assert goal_plan["model_ranking"]["input_artifact_references"] == metadata[
        "input_artifact_references"
    ]


def test_goal_model_disclosure_metadata_returns_none_without_model() -> None:
    assert (
        goal_model_disclosure_metadata(
            GoalPlan(user_goal="Read page", normalized_intent="browser read"),
        )
        is None
    )
