from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

from desktop_agent.goal_planning import (
    GoalPlan,
    GoalPlanApproval,
    GoalPlanCandidate,
    GoalPlanError,
    GoalRoutingRequest,
    goal_plan_from_mapping,
    route_goal_to_routine,
    search_routine_index_for_goal,
    validate_goal_plan,
)
from desktop_agent.routines import (
    RoutineCatalog,
    RoutineDefinition,
    routine_definition_from_mapping,
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


def test_goal_routine_index_search_covers_risk_and_schedule_fields() -> None:
    catalog = RoutineCatalog(
        root=Path("routine_packs"),
        routines=(
            _routine(
                routine_id="browser.read-page",
                name="Browser read page",
                tags=["browser", "reading"],
                safety_class="low",
                approval_policy="none",
                schedule_policy="manual",
            ),
            _routine(
                routine_id="social-content.linkedin-approved-publish",
                name="LinkedIn approved publish",
                tags=["social", "linkedin", "publish"],
                required_site="linkedin.com",
                safety_class="high",
                approval_policy="manifest_required",
                schedule_policy="scheduled",
                allowed_time_windows=[
                    {
                        "days": ["mon"],
                        "start": "09:00",
                        "end": "10:00",
                        "timezone": "local",
                    },
                ],
            ),
        ),
    )
    now = datetime(2026, 5, 18, 9, 30, tzinfo=UTC)

    results = search_routine_index_for_goal(
        catalog,
        "linkedin high manifest scheduled",
        now=now,
        require_schedule_eligible=True,
    )

    assert len(results) == 1
    result = results[0]
    assert result.candidate.routine_id == "social-content.linkedin-approved-publish"
    assert result.candidate.safety_class == "high"
    assert result.candidate.approval_policy == "manifest_required"
    assert result.schedule_eligible is True
    assert result.schedule_reason == "inside_allowed_time_window"
    assert "safety_class" in result.candidate.matched_fields
    assert "schedule_policy" in result.candidate.matched_fields


def test_goal_routine_index_search_can_filter_ineligible_schedules() -> None:
    catalog = RoutineCatalog(
        root=Path("routine_packs"),
        routines=(
            _routine(
                routine_id="social-content.linkedin-approved-publish",
                name="LinkedIn approved publish",
                tags=["social", "linkedin", "publish"],
                required_site="linkedin.com",
                safety_class="high",
                approval_policy="manifest_required",
                schedule_policy="scheduled",
                allowed_time_windows=[
                    {
                        "days": ["mon"],
                        "start": "09:00",
                        "end": "10:00",
                        "timezone": "local",
                    },
                ],
            ),
        ),
    )
    now = datetime(2026, 5, 18, 12, 0, tzinfo=UTC)

    results = search_routine_index_for_goal(
        catalog,
        "linkedin high scheduled",
        now=now,
        require_schedule_eligible=True,
    )

    assert results == ()


def test_goal_router_uses_exact_site_tags_inputs_and_confidence_ranking() -> None:
    catalog = RoutineCatalog(
        root=Path("routine_packs"),
        routines=(
            _routine(
                routine_id="browser.read-page",
                name="Browser read page",
                tags=["browser", "reading"],
                required_site="example.com",
                safety_class="low",
                approval_policy="none",
                schedule_policy="manual",
                inputs=["url"],
            ),
            _routine(
                routine_id="social-content.linkedin-approved-publish",
                name="LinkedIn approved publish",
                tags=["social", "linkedin", "publish"],
                required_site="linkedin.com",
                safety_class="high",
                approval_policy="manifest_required",
                schedule_policy="manual",
                inputs=["approval manifest"],
            ),
        ),
    )

    plan = route_goal_to_routine(
        catalog,
        GoalRoutingRequest(
            user_goal="Publish the approved LinkedIn draft",
            normalized_intent="linkedin publish approved manifest",
            required_site="linkedin.com",
            tags=("publish",),
            provided_inputs=("approval manifest",),
            max_safety_class="high",
        ),
    )

    assert plan.selected_routine_id == "social-content.linkedin-approved-publish"
    assert plan.execution_status == "blocked"
    assert plan.approvals[0].policy == "manifest_required"
    assert plan.candidate_routines[0].score > 0


def test_goal_router_filters_above_max_safety_class() -> None:
    catalog = RoutineCatalog(
        root=Path("routine_packs"),
        routines=(
            _routine(
                routine_id="social-content.linkedin-approved-publish",
                name="LinkedIn approved publish",
                tags=["social", "linkedin", "publish"],
                required_site="linkedin.com",
                safety_class="high",
                approval_policy="manifest_required",
                schedule_policy="manual",
            ),
        ),
    )

    plan = route_goal_to_routine(
        catalog,
        GoalRoutingRequest(
            user_goal="Publish the approved LinkedIn draft",
            normalized_intent="linkedin publish",
            required_site="linkedin.com",
            max_safety_class="medium",
        ),
    )

    assert plan.selected_routine_id is None
    assert plan.execution_status == "blocked"
    assert plan.candidate_routines == ()


def test_goal_router_marks_missing_inputs_before_execution_ready() -> None:
    catalog = RoutineCatalog(
        root=Path("routine_packs"),
        routines=(
            _routine(
                routine_id="browser.search-web",
                name="Browser web search",
                tags=["browser", "search"],
                safety_class="low",
                approval_policy="none",
                schedule_policy="manual",
                inputs=["query"],
            ),
        ),
    )

    plan = route_goal_to_routine(
        catalog,
        GoalRoutingRequest(
            user_goal="Search the web",
            normalized_intent="browser search",
            tags=("search",),
            max_safety_class="low",
        ),
    )

    assert plan.selected_routine_id == "browser.search-web"
    assert plan.execution_status == "blocked"
    assert plan.missing_inputs == ("query",)


def _routine(
    *,
    routine_id: str,
    name: str,
    tags: list[str],
    safety_class: str,
    approval_policy: str,
    schedule_policy: str,
    required_site: str | None = None,
    inputs: list[str] | None = None,
    allowed_time_windows: list[dict[str, object]] | None = None,
) -> RoutineDefinition:
    payload: dict[str, object] = {
        "id": routine_id,
        "name": name,
        "description": "Routine for goal-planning search tests.",
        "goal": "Match a user goal to a routine.",
        "tags": tags,
        "inputs": inputs or ["input"],
        "outputs": ["output"],
        "safety_class": safety_class,
        "schedule_policy": schedule_policy,
        "approval_policy": approval_policy,
        "expected_duration_seconds": 30,
        "reference": {
            "type": "task",
            "path": "tasks/test.yaml",
        },
    }
    if required_site is not None:
        payload["required_site"] = required_site
    if allowed_time_windows is not None:
        payload["schedule"] = {"allowed_time_windows": allowed_time_windows}
    return routine_definition_from_mapping(payload)
