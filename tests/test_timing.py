from typing import cast

from desktop_agent.config import ExecutionProfile
from desktop_agent.perception import ElementCandidate
from desktop_agent.screen import Bounds, ScreenObservation
from desktop_agent.task_dsl import TaskStep
from desktop_agent.timing import (
    ExecutionTimingController,
    build_action_timing_context,
    estimate_step_timing_budget,
)


def test_execution_timing_samples_stay_inside_configured_bounds() -> None:
    controller = ExecutionTimingController(
        ExecutionProfile(
            enabled=True,
            action_delay_seconds=(0.2, 0.4),
            retry_delay_seconds=(1.0, 2.0),
            hesitation_probability=1.0,
            movement_smoothness=0.75,
            random_seed=123,
        )
    )

    action_decisions = [controller.before_action() for _ in range(20)]
    retry_decisions = [controller.before_retry() for _ in range(20)]

    assert all(0.2 <= decision.delay_seconds <= 0.4 for decision in action_decisions)
    assert all(decision.hesitation_applied for decision in action_decisions)
    assert all(1.0 <= decision.delay_seconds <= 2.0 for decision in retry_decisions)
    assert all(decision.movement_smoothness == 0.75 for decision in action_decisions)


def test_execution_timing_is_zero_when_profile_is_disabled() -> None:
    controller = ExecutionTimingController(ExecutionProfile())

    decision = controller.before_action()

    assert decision.delay_seconds == 0
    assert decision.reason == "execution profile disabled"


def test_target_aware_timing_biases_harder_targets_later_inside_bounds() -> None:
    profile = ExecutionProfile(
        enabled=True,
        action_delay_seconds=(0.1, 0.5),
        hesitation_probability=0.0,
        random_seed=123,
    )
    observation = ScreenObservation(size=(1000, 1000))
    easy_context = build_action_timing_context(
        TaskStep(id="near-large", action="click_text", target="Submit"),
        ElementCandidate(
            id="easy",
            source="uia",
            label="Submit",
            bounds=Bounds(x=420, y=420, width=200, height=200),
            confidence=0.95,
        ),
        observation,
    )
    hard_context = build_action_timing_context(
        TaskStep(id="far-small", action="click_text", target="Submit"),
        ElementCandidate(
            id="hard",
            source="uia",
            label="Submit",
            bounds=Bounds(x=900, y=900, width=10, height=10),
            confidence=0.95,
        ),
        observation,
    )

    easy_decision = ExecutionTimingController(profile).before_action(easy_context)
    hard_decision = ExecutionTimingController(profile).before_action(hard_context)

    assert easy_context.target_complexity < hard_context.target_complexity
    assert 0.1 <= easy_decision.delay_seconds <= 0.5
    assert 0.1 <= hard_decision.delay_seconds <= 0.5
    assert hard_decision.delay_seconds > easy_decision.delay_seconds
    assert hard_decision.metadata()["timing_model"] == "target_aware"
    assert hard_decision.metadata()["target_id"] == "hard"


def test_action_type_contributes_to_timing_complexity() -> None:
    observation = ScreenObservation(size=(1000, 1000))
    target = ElementCandidate(
        id="tile",
        source="uia",
        label="Tile",
        bounds=Bounds(x=500, y=500, width=40, height=40),
        confidence=0.95,
    )

    click_context = build_action_timing_context(
        TaskStep(id="click-tile", action="click_text", target="Tile"),
        target,
        observation,
    )
    drag_context = build_action_timing_context(
        TaskStep(id="drag-tile", action="drag", target="Tile"),
        target,
        observation,
    )

    assert drag_context.action_complexity > click_context.action_complexity
    assert drag_context.target_complexity > click_context.target_complexity


def test_execution_persona_biases_timing_inside_configured_bounds() -> None:
    observation = ScreenObservation(size=(1000, 1000))
    target = ElementCandidate(
        id="submit",
        source="uia",
        label="Submit",
        bounds=Bounds(x=500, y=500, width=120, height=40),
        confidence=0.95,
    )
    context = build_action_timing_context(
        TaskStep(id="click-submit", action="click_text", target="Submit"),
        target,
        observation,
    )

    fast = ExecutionTimingController(
        ExecutionProfile(
            persona="fast",
            enabled=True,
            action_delay_seconds=(0.1, 0.9),
            hesitation_probability=0.0,
            random_seed=123,
        ),
    ).before_action(context)
    normal = ExecutionTimingController(
        ExecutionProfile(
            persona="normal",
            enabled=True,
            action_delay_seconds=(0.1, 0.9),
            hesitation_probability=0.0,
            random_seed=123,
        ),
    ).before_action(context)
    careful = ExecutionTimingController(
        ExecutionProfile(
            persona="careful",
            enabled=True,
            action_delay_seconds=(0.1, 0.9),
            hesitation_probability=0.0,
            random_seed=123,
        ),
    ).before_action(context)

    assert 0.1 <= fast.delay_seconds <= 0.9
    assert 0.1 <= normal.delay_seconds <= 0.9
    assert 0.1 <= careful.delay_seconds <= 0.9
    assert fast.delay_seconds < normal.delay_seconds < careful.delay_seconds
    assert fast.metadata()["execution_persona"] == "fast"
    assert cast(float, careful.metadata()["persona_timing_bias"]) > 0


def test_klm_operators_capture_keying_pointing_and_homing() -> None:
    profile = ExecutionProfile(
        enabled=True,
        action_delay_seconds=(0.1, 0.5),
        hesitation_probability=0.0,
        random_seed=123,
    )
    controller = ExecutionTimingController(profile)
    observation = ScreenObservation(size=(1000, 1000))
    type_context = build_action_timing_context(
        TaskStep(id="type-email", action="type_text", text="abc"),
        None,
        observation,
    )
    click_context = build_action_timing_context(
        TaskStep(id="click-submit", action="click_text", target="Submit"),
        ElementCandidate(
            id="submit",
            source="uia",
            label="Submit",
            bounds=Bounds(x=500, y=500, width=120, height=40),
            confidence=0.95,
        ),
        observation,
    )

    type_metadata = controller.before_action(type_context).metadata()
    click_metadata = controller.before_action(click_context).metadata()

    type_counts = cast(dict[str, int], type_metadata["klm_operator_counts"])
    click_counts = cast(dict[str, int], click_metadata["klm_operator_counts"])
    assert type_metadata["input_mode"] == "keyboard"
    assert type_metadata["keypress_count"] == 3
    assert type_counts["mental"] == 1
    assert type_counts["keying"] == 3
    assert "pointing" not in type_counts
    assert click_metadata["input_mode"] == "pointer"
    assert click_counts["mental"] == 1
    assert click_counts["pointing"] == 1
    assert click_counts["homing"] == 1
    assert cast(float, click_metadata["klm_total_seconds"]) > cast(
        float,
        type_metadata["klm_total_seconds"],
    )


def test_retry_timing_reports_system_wait_operator() -> None:
    controller = ExecutionTimingController(
        ExecutionProfile(
            enabled=True,
            retry_delay_seconds=(0.3, 0.4),
            random_seed=123,
        ),
    )

    metadata = controller.before_retry().metadata()

    counts = cast(dict[str, int], metadata["klm_operator_counts"])
    assert metadata["timing_model"] == "profile_bounds"
    assert counts == {"system_wait": 1}
    assert 0.3 <= cast(float, metadata["delay_seconds"]) <= 0.4


def test_step_timing_budget_accounts_for_action_and_retry_waits() -> None:
    budget = estimate_step_timing_budget(
        TaskStep(
            id="click-submit",
            action="click_text",
            target="Submit",
            retry=2,
            timeout_seconds=2.0,
        ),
        ExecutionProfile(
            enabled=True,
            action_delay_seconds=(0.1, 0.2),
            retry_delay_seconds=(0.3, 0.4),
        ),
        default_timeout_seconds=30.0,
        max_retries_per_step=1,
    )

    assert budget.attempt_count == 3
    assert budget.action_timing_slots == 3
    assert budget.retry_timing_slots == 2
    assert round(budget.planned_action_wait_seconds, 2) == 0.6
    assert budget.planned_retry_wait_seconds == 0.8
    assert budget.fits_timeout is True
    remaining_timeout = cast(float, budget.metadata()["remaining_timeout_seconds"])
    assert round(remaining_timeout, 2) == 0.6
