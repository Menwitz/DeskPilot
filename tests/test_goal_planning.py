from typing import cast

import pytest

from desktop_agent.goal_planning import (
    GoalPlan,
    GoalPlanApproval,
    GoalPlanCandidate,
    GoalPlanError,
    goal_plan_from_mapping,
    validate_goal_plan,
)


def test_goal_plan_schema_tracks_candidates_selection_and_readiness() -> None:
    plan = GoalPlan(
        user_goal="Check the morning page",
        normalized_intent="browser morning review",
        candidate_routines=(
            GoalPlanCandidate(
                routine_id="browser.read-page",
                routine_name="Browser read page",
                score=7.5,
                matched_fields=("tags", "outputs"),
                safety_class="low",
            ),
        ),
        selected_routine_id="browser.read-page",
        explanation="The browser reading routine matches the requested page review.",
        execution_status="ready",
    )

    validate_goal_plan(plan)
    metadata = plan.metadata()
    candidates = cast(list[dict[str, object]], metadata["candidate_routines"])

    assert plan.execution_ready is True
    assert plan.selected_candidate is not None
    assert plan.selected_candidate.routine_id == "browser.read-page"
    assert metadata["execution_ready"] is True
    assert candidates[0]["matched_fields"] == [
        "tags",
        "outputs",
    ]


def test_goal_plan_schema_blocks_missing_inputs_and_unsatisfied_approvals() -> None:
    plan = goal_plan_from_mapping(
        {
            "user_goal": "Publish the approved LinkedIn draft",
            "normalized_intent": "linkedin approved publish",
            "candidate_routines": [
                {
                    "routine_id": "social-content.linkedin-approved-publish",
                    "routine_name": "LinkedIn approved publish",
                    "score": 12,
                    "matched_fields": ["required_site", "tags"],
                    "safety_class": "high",
                    "approval_policy": "manifest_required",
                },
            ],
            "selected_routine_id": "social-content.linkedin-approved-publish",
            "missing_inputs": ["approval manifest"],
            "approvals": [
                {
                    "policy": "manifest_required",
                    "required": True,
                    "satisfied": False,
                    "reason": "Publishing requires reviewed content approval.",
                },
            ],
            "explanation": "Publishing is selected but blocked on approval.",
            "execution_status": "blocked",
        },
    )

    assert plan.execution_ready is False
    assert plan.missing_inputs == ("approval manifest",)
    assert plan.approvals[0].required is True
    assert plan.metadata()["execution_status"] == "blocked"


def test_goal_plan_schema_rejects_invalid_selection() -> None:
    with pytest.raises(GoalPlanError, match="selected_routine_id"):
        goal_plan_from_mapping(
            {
                "user_goal": "Read a page",
                "normalized_intent": "browser read",
                "candidate_routines": [
                    {
                        "routine_id": "browser.read-page",
                        "routine_name": "Browser read page",
                        "score": 4,
                    },
                ],
                "selected_routine_id": "browser.search-web",
            },
        )


def test_goal_plan_schema_rejects_ready_plan_with_missing_approval() -> None:
    with pytest.raises(GoalPlanError, match="ready goal plans"):
        validate_goal_plan(
            GoalPlan(
                user_goal="Publish draft",
                normalized_intent="publish draft",
                candidate_routines=(
                    GoalPlanCandidate(
                        routine_id="social-content.linkedin-approved-publish",
                        routine_name="LinkedIn approved publish",
                        score=10,
                    ),
                ),
                selected_routine_id="social-content.linkedin-approved-publish",
                approvals=(
                    GoalPlanApproval(
                        policy="manifest_required",
                        required=True,
                        satisfied=False,
                        reason="Approval manifest required.",
                    ),
                ),
                execution_status="ready",
            ),
        )


def test_goal_plan_schema_rejects_duplicate_candidates_and_bad_scores() -> None:
    with pytest.raises(GoalPlanError, match="candidate routine IDs"):
        validate_goal_plan(
            GoalPlan(
                user_goal="Read a page",
                normalized_intent="browser read",
                candidate_routines=(
                    GoalPlanCandidate(
                        routine_id="browser.read-page",
                        routine_name="Browser read page",
                        score=1,
                    ),
                    GoalPlanCandidate(
                        routine_id="browser.read-page",
                        routine_name="Browser read page duplicate",
                        score=-1,
                    ),
                ),
            ),
        )
