from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest
from pytest import CaptureFixture

from desktop_agent.cli import main
from desktop_agent.config import LocalModelConfig
from desktop_agent.goal_planning import (
    GoalMissingInputPrompt,
    GoalModelSuggestion,
    GoalPlan,
    GoalPlanApproval,
    GoalPlanCandidate,
    GoalPlanError,
    GoalRoutingRequest,
    goal_plan_from_mapping,
    missing_input_prompts,
    rank_goal_plan_with_optional_model,
    route_goal_to_routine,
    search_routine_index_for_goal,
    selected_routine_for_goal_execution,
    validate_goal_plan,
    validate_missing_input_prompt,
)
from desktop_agent.routines import (
    RoutineCatalog,
    RoutineDefinition,
    RoutineFailureCounters,
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
        expected_evidence=("visible article text",),
        abort_conditions=("stop if page changes",),
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
    assert metadata["expected_evidence"] == ["visible article text"]
    assert metadata["abort_conditions"] == ["stop if page changes"]


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
    assert plan.selected_candidate is not None
    assert plan.selected_candidate.routine_id == (
        "social-content.linkedin-approved-publish"
    )
    assert plan.missing_inputs == ("approval manifest",)
    assert plan.approvals[0].required is True
    metadata = plan.metadata()
    approvals = cast(list[dict[str, object]], metadata["approvals"])
    assert metadata["selected_routine_id"] == (
        "social-content.linkedin-approved-publish"
    )
    assert metadata["missing_inputs"] == ["approval manifest"]
    assert approvals[0]["reason"] == "Publishing requires reviewed content approval."
    assert metadata["explanation"] == "Publishing is selected but blocked on approval."
    assert metadata["execution_status"] == "blocked"


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
                cooldown_seconds=1800,
                stop_conditions=["stop if approval revoked"],
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
        "linkedin high manifest scheduled revoked",
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
    assert "schedule" in result.candidate.matched_fields


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
                outputs=["published post visible"],
                stop_conditions=["approval revoked"],
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
    assert plan.expected_evidence == ("published post visible",)
    assert plan.abort_conditions == ("approval revoked",)
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


def test_goal_router_uses_historical_success_for_tie_breaking() -> None:
    catalog = RoutineCatalog(
        root=Path("routine_packs"),
        routines=(
            _routine(
                routine_id="browser.alpha-search",
                name="Browser search alpha",
                tags=["browser", "search"],
                safety_class="low",
                approval_policy="none",
                schedule_policy="manual",
            ),
            _routine(
                routine_id="browser.beta-search",
                name="Browser search beta",
                tags=["browser", "search"],
                safety_class="low",
                approval_policy="none",
                schedule_policy="manual",
            ),
        ),
    )

    plan = route_goal_to_routine(
        catalog,
        GoalRoutingRequest(
            user_goal="Search in the browser",
            normalized_intent="browser search",
            tags=("browser", "search"),
            max_safety_class="low",
        ),
        failure_counters={
            "browser.alpha-search": RoutineFailureCounters(
                routine_id="browser.alpha-search",
                total_runs=4,
                passed_runs=1,
                failed_runs=3,
            ),
            "browser.beta-search": RoutineFailureCounters(
                routine_id="browser.beta-search",
                total_runs=4,
                passed_runs=4,
            ),
        },
    )

    assert plan.selected_routine_id == "browser.beta-search"
    assert plan.candidate_routines[0].routine_id == "browser.beta-search"
    assert "historical_success" in plan.candidate_routines[0].matched_fields


def test_goal_router_shows_alternatives_for_ambiguous_goals() -> None:
    catalog = RoutineCatalog(
        root=Path("routine_packs"),
        routines=(
            _routine(
                routine_id="browser.read-article",
                name="Browser read article",
                tags=["browser", "reading"],
                safety_class="low",
                approval_policy="none",
                schedule_policy="manual",
            ),
            _routine(
                routine_id="browser.read-page",
                name="Browser read page",
                tags=["browser", "reading"],
                safety_class="low",
                approval_policy="none",
                schedule_policy="manual",
            ),
        ),
    )

    plan = route_goal_to_routine(
        catalog,
        GoalRoutingRequest(
            user_goal="Read browser content",
            normalized_intent="browser reading",
            max_safety_class="low",
        ),
    )

    assert plan.selected_routine_id is None
    assert plan.execution_status == "blocked"
    assert plan.explanation == (
        "Ambiguous goal matched multiple routines; review alternatives."
    )
    assert [candidate.routine_id for candidate in plan.candidate_routines] == [
        "browser.read-article",
        "browser.read-page",
    ]


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


def test_missing_input_prompts_cover_routine_inputs_and_session_state() -> None:
    plan = GoalPlan(
        user_goal="Search the web",
        normalized_intent="browser search",
        missing_inputs=("query",),
        execution_status="blocked",
    )

    prompts = missing_input_prompts(
        plan,
        required_session_state=("browser signed in",),
    )
    metadata = [prompt.metadata() for prompt in prompts]

    assert [prompt.kind for prompt in prompts] == ["routine_input", "session_state"]
    assert prompts[0].key == "query"
    assert "Provide a value" in prompts[0].prompt
    assert metadata[1]["key"] == "browser signed in"


def test_missing_input_prompt_validation_rejects_blank_prompt() -> None:
    with pytest.raises(GoalPlanError, match="prompt text"):
        validate_missing_input_prompt(
            GoalMissingInputPrompt(
                key="query",
                prompt="",
                kind="routine_input",
            ),
        )


def test_goal_planner_cli_dry_run_reports_plan_without_desktop_input(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    root = tmp_path / "routine_packs"
    _write_routine_file(root / "browser" / "search.routine.yaml")

    status = main(
        [
            "plan-goal",
            "Search the web",
            "--intent",
            "browser search",
            "--input",
            "query",
            "--routine-pack-root",
            str(root),
            "--trace-root",
            str(tmp_path / "traces"),
        ],
    )

    output = capsys.readouterr().out
    assert status == 0
    assert "goal plan:" in output
    assert "selected: browser.search-web" in output
    assert "status: ready" in output
    assert "expected_evidence: search results" in output
    assert "dry-run preview:" not in output
    assert "trace:" in output


def test_optional_model_ranking_is_disabled_by_default() -> None:
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
    request = GoalRoutingRequest(
        user_goal="Search the web",
        normalized_intent="browser search",
        provided_inputs=("query",),
    )
    plan = route_goal_to_routine(catalog, request)

    ranked = rank_goal_plan_with_optional_model(
        catalog,
        request,
        plan,
        LocalModelConfig(),
        ranker=_FailingGoalRanker(),
    )

    assert ranked.selected_routine_id == "browser.search-web"
    assert ranked.model_ranking is not None
    assert ranked.model_ranking.status == "disabled"
    assert ranked.model_ranking.attempted is False


def test_optional_ollama_ranking_can_reorder_valid_candidates() -> None:
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
                inputs=[],
            ),
            _routine(
                routine_id="browser.search-web",
                name="Browser web search",
                tags=["browser", "search"],
                safety_class="low",
                approval_policy="none",
                schedule_policy="manual",
                inputs=[],
                outputs=["search results"],
                stop_conditions=["browser signed out"],
            ),
        ),
    )
    request = GoalRoutingRequest(
        user_goal="Read browser content",
        normalized_intent="browser read",
    )
    plan = route_goal_to_routine(catalog, request)

    ranked = rank_goal_plan_with_optional_model(
        catalog,
        request,
        plan,
        LocalModelConfig(enabled=True, use_for_goal_ranking=True),
        ranker=_StaticGoalRanker(
            GoalModelSuggestion(
                selected_routine_id="browser.search-web",
                candidate_order=("browser.search-web", "browser.read-page"),
                explanation="Search best matches the user's goal.",
                raw_output='{"selected_routine_id":"browser.search-web"}',
            ),
        ),
    )

    assert ranked.selected_routine_id == "browser.search-web"
    assert ranked.execution_status == "ready"
    assert [candidate.routine_id for candidate in ranked.candidate_routines] == [
        "browser.search-web",
        "browser.read-page",
    ]
    assert ranked.model_ranking is not None
    assert ranked.model_ranking.status == "applied"
    assert ranked.model_ranking.affected_selection is True
    assert ranked.model_ranking.output_hash is not None
    assert ranked.expected_evidence == ("search results",)
    assert ranked.abort_conditions == ("browser signed out",)
    assert ranked.metadata()["model_ranking"] is not None


def test_optional_ollama_ranking_rejects_unknown_routine_ids() -> None:
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
                inputs=[],
            ),
        ),
    )
    request = GoalRoutingRequest(
        user_goal="Read the page",
        normalized_intent="browser read",
    )
    plan = route_goal_to_routine(catalog, request)

    ranked = rank_goal_plan_with_optional_model(
        catalog,
        request,
        plan,
        LocalModelConfig(enabled=True, use_for_goal_ranking=True),
        ranker=_StaticGoalRanker(
            GoalModelSuggestion(
                selected_routine_id="invented.raw-action",
                candidate_order=("invented.raw-action",),
                explanation="Invalid model output.",
                raw_output='{"selected_routine_id":"invented.raw-action"}',
            ),
        ),
    )

    assert ranked.selected_routine_id == plan.selected_routine_id
    assert ranked.model_ranking is not None
    assert ranked.model_ranking.status == "rejected"
    assert ranked.model_ranking.affected_selection is False
    assert ranked.model_ranking.error is not None


def test_optional_ollama_ranking_cannot_bypass_safety_filter() -> None:
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
                inputs=[],
            ),
            _routine(
                routine_id="social-content.linkedin-approved-publish",
                name="LinkedIn approved publish",
                tags=["social", "linkedin", "publish"],
                required_site="linkedin.com",
                safety_class="high",
                approval_policy="manifest_required",
                schedule_policy="manual",
                inputs=[],
            ),
        ),
    )
    request = GoalRoutingRequest(
        user_goal="Review browser content",
        normalized_intent="browser linkedin publish",
        max_safety_class="low",
    )
    plan = route_goal_to_routine(catalog, request)

    ranked = rank_goal_plan_with_optional_model(
        catalog,
        request,
        plan,
        LocalModelConfig(enabled=True, use_for_goal_ranking=True),
        ranker=_StaticGoalRanker(
            GoalModelSuggestion(
                selected_routine_id="social-content.linkedin-approved-publish",
                candidate_order=("social-content.linkedin-approved-publish",),
                explanation="Invalidly tries to pick a filtered high-risk routine.",
                raw_output=(
                    '{"selected_routine_id":'
                    '"social-content.linkedin-approved-publish"}'
                ),
            ),
        ),
    )

    assert ranked.selected_routine_id == plan.selected_routine_id
    assert ranked.model_ranking is not None
    assert ranked.model_ranking.status == "rejected"
    assert all(
        candidate.safety_class == "low" for candidate in ranked.candidate_routines
    )


def test_optional_ollama_ranking_cannot_bypass_required_approvals() -> None:
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
                inputs=[],
            ),
            _routine(
                routine_id="social-content.linkedin-approved-publish",
                name="LinkedIn approved publish",
                tags=["browser", "publish"],
                safety_class="high",
                approval_policy="manifest_required",
                schedule_policy="manual",
                inputs=[],
            ),
        ),
    )
    request = GoalRoutingRequest(
        user_goal="Handle browser publishing",
        normalized_intent="browser",
        max_safety_class="high",
    )
    plan = route_goal_to_routine(catalog, request)

    ranked = rank_goal_plan_with_optional_model(
        catalog,
        request,
        plan,
        LocalModelConfig(enabled=True, use_for_goal_ranking=True),
        ranker=_StaticGoalRanker(
            GoalModelSuggestion(
                selected_routine_id="social-content.linkedin-approved-publish",
                candidate_order=(
                    "social-content.linkedin-approved-publish",
                    "browser.read-page",
                ),
                explanation="Publishing is preferred.",
                raw_output=(
                    '{"selected_routine_id":'
                    '"social-content.linkedin-approved-publish"}'
                ),
            ),
        ),
    )

    assert ranked.selected_routine_id == "social-content.linkedin-approved-publish"
    assert ranked.execution_status == "blocked"
    assert ranked.execution_ready is False
    assert ranked.approvals[0].required is True
    assert ranked.explanation == "Selected routine is blocked by required approvals."


def test_goal_execution_resolves_only_validated_routine_ids() -> None:
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
                inputs=[],
            ),
        ),
    )
    plan = GoalPlan(
        user_goal="Read page",
        normalized_intent="browser read",
        candidate_routines=(
            GoalPlanCandidate(
                routine_id="browser.read-page",
                routine_name="Browser read page",
                score=10,
            ),
        ),
        selected_routine_id="browser.read-page",
        execution_status="ready",
    )

    routine = selected_routine_for_goal_execution(catalog, plan)

    assert routine.id == "browser.read-page"


def test_goal_execution_rejects_candidate_ids_missing_from_catalog() -> None:
    catalog = RoutineCatalog(root=Path("routine_packs"), routines=())
    plan = GoalPlan(
        user_goal="Invent an action",
        normalized_intent="invented",
        candidate_routines=(
            GoalPlanCandidate(
                routine_id="invented.raw-action",
                routine_name="Invented raw action",
                score=1,
            ),
        ),
        selected_routine_id="invented.raw-action",
        execution_status="ready",
    )

    with pytest.raises(GoalPlanError, match="unknown_routine_id"):
        selected_routine_for_goal_execution(catalog, plan)


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
    cooldown_seconds: float | None = None,
    stop_conditions: list[str] | None = None,
    outputs: list[str] | None = None,
) -> RoutineDefinition:
    payload: dict[str, object] = {
        "id": routine_id,
        "name": name,
        "description": "Routine for goal-planning search tests.",
        "goal": "Match a user goal to a routine.",
        "tags": tags,
        "inputs": inputs if inputs is not None else ["input"],
        "outputs": outputs if outputs is not None else ["output"],
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
    schedule: dict[str, object] = {}
    if allowed_time_windows is not None:
        schedule["allowed_time_windows"] = allowed_time_windows
    if cooldown_seconds is not None:
        schedule["cooldown_seconds"] = cooldown_seconds
    if stop_conditions is not None:
        schedule["stop_conditions"] = stop_conditions
    if schedule:
        payload["schedule"] = schedule
    return routine_definition_from_mapping(payload)


class _StaticGoalRanker:
    def __init__(self, suggestion: GoalModelSuggestion) -> None:
        self._suggestion = suggestion

    def rank_goal_candidates(self, plan: GoalPlan) -> GoalModelSuggestion:
        _ = plan
        return self._suggestion


class _FailingGoalRanker:
    def rank_goal_candidates(self, plan: GoalPlan) -> GoalModelSuggestion:
        _ = plan
        raise AssertionError("ranker should not be called while disabled")


def _write_routine_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "id: browser.search-web",
                "name: Browser web search",
                "description: Search from a browser input.",
                "goal: Find web results for a query.",
                "required_app: Microsoft Edge",
                "tags:",
                "  - browser",
                "  - search",
                "inputs:",
                "  - query",
                "outputs:",
                "  - search results",
                "safety_class: low",
                "schedule_policy: manual",
                "approval_policy: none",
                "expected_duration_seconds: 30",
                "reference:",
                "  type: task",
                "  path: tasks/search-web.yaml",
                "",
            ],
        ),
        encoding="utf-8",
    )
