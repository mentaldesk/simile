import random
from collections.abc import Callable

import pytest

from simile.characters.tables import Skeleton, Tables, load_tables, sample_skeleton

type Skeletons = Callable[..., Skeleton]


@pytest.fixture(scope="session")
def tables() -> Tables:
    return load_tables()


@pytest.fixture
def skeleton() -> Skeletons:
    def make(age: int = 50, seed: int = 0, **fixed: object) -> Skeleton:
        return sample_skeleton(random.Random(seed), age, **fixed)

    return make


def flat(score: float, **overrides: float) -> dict[str, float]:
    """Every core value at `score`, with some set otherwise."""
    from simile.schema import CoreValue

    return {value.value: overrides.get(value.value, score) for value in CoreValue}


@pytest.fixture
def values() -> Callable[..., dict[str, float]]:
    return flat
