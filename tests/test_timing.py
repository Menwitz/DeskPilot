from desktop_agent.config import ExecutionProfile
from desktop_agent.timing import ExecutionTimingController


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
