"""Deterministic sampling boundary for bounded runtime randomness."""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class SampleRecord:
    """One sampled value produced by a seeded sampler."""

    index: int
    label: str
    value: float
    lower_bound: float | None = None
    upper_bound: float | None = None

    def metadata(self) -> dict[str, object]:
        return {
            "sample_index": self.index,
            "sample_label": self.label,
            "sample_value": self.value,
            "sample_lower_bound": self.lower_bound,
            "sample_upper_bound": self.upper_bound,
        }


class SeededSampler:
    """Small wrapper that makes every random decision seedable and countable."""

    def __init__(self, seed: int | None) -> None:
        self.seed = seed
        self._random = random.Random(seed)
        self._records: list[SampleRecord] = []

    @property
    def sample_count(self) -> int:
        return len(self._records)

    @property
    def records(self) -> tuple[SampleRecord, ...]:
        return tuple(self._records)

    def records_since(self, sample_count: int) -> tuple[SampleRecord, ...]:
        return tuple(self._records[sample_count:])

    def random(self, label: str) -> float:
        value = self._random.random()
        self._record(label, value)
        return value

    def probability(self, label: str, probability: float) -> bool:
        return self.random(label) < probability

    def uniform(self, label: str, bounds: tuple[float, float]) -> float:
        lower, upper = bounds
        if lower == upper:
            return lower
        value = self._random.uniform(lower, upper)
        self._record(label, value, lower, upper)
        return value

    def fraction(self, label: str, distribution: str) -> float:
        if distribution == "uniform":
            return self.random(label)
        if distribution == "center_weighted":
            first = self.random(f"{label}.center_a")
            second = self.random(f"{label}.center_b")
            return (first + second) / 2
        raise ValueError(f"unsupported sampling distribution: {distribution}")

    def index(self, label: str, count: int, distribution: str) -> int:
        if count <= 0:
            raise ValueError("sample count must be greater than zero")
        if count == 1:
            return 0
        return min(count - 1, int(self.fraction(label, distribution) * count))

    def _record(
        self,
        label: str,
        value: float,
        lower_bound: float | None = None,
        upper_bound: float | None = None,
    ) -> None:
        self._records.append(
            SampleRecord(
                index=len(self._records) + 1,
                label=label,
                value=value,
                lower_bound=lower_bound,
                upper_bound=upper_bound,
            ),
        )
