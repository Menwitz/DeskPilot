from desktop_agent.sampling import SeededSampler


def test_seeded_sampler_replays_random_and_uniform_sequence() -> None:
    first = SeededSampler(42)
    second = SeededSampler(42)

    first_values = (
        first.random("unit.random"),
        first.uniform("unit.uniform", (0.1, 0.9)),
        first.probability("unit.probability", 0.5),
    )
    second_values = (
        second.random("unit.random"),
        second.uniform("unit.uniform", (0.1, 0.9)),
        second.probability("unit.probability", 0.5),
    )

    assert first_values == second_values
    assert first.sample_count == 3
    assert [record.index for record in first.records] == [1, 2, 3]
    assert [record.index for record in first.records_since(1)] == [2, 3]
    assert first.records[0].metadata()["sample_lower_bound"] == 0.0
    assert first.records[0].metadata()["sample_upper_bound"] == 1.0
    assert first.records[1].metadata()["sample_label"] == "unit.uniform"
    assert first.records[1].metadata()["sample_lower_bound"] == 0.1
