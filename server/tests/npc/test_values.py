import itertools
import random
from statistics import correlation

import pytest

from simile.npc.values import (
    LOADINGS,
    distance,
    format_scores,
    ranked,
    sample_profile,
    sample_values,
    spread,
)
from simile.schema import CoreValue as V


@pytest.fixture(scope="module")
def population() -> list[dict[V, float]]:
    rng = random.Random(1)
    return [sample_profile(rng) for _ in range(3000)]


def r(population: list[dict[V, float]], a: V, b: V) -> float:
    return correlation([p[a] for p in population], [p[b] for p in population])


def test_every_value_has_a_loading() -> None:
    assert set(LOADINGS) == set(V)


def test_a_seed_always_gives_the_same_village() -> None:
    assert sample_values(10, random.Random(7)) == sample_values(10, random.Random(7))
    assert sample_values(10, random.Random(7)) != sample_values(10, random.Random(8))


def test_profiles_score_all_24_values_from_0_to_1(population: list[dict[V, float]]) -> None:
    for profile in population:
        assert set(profile) == set(V)
        assert all(0 <= score <= 1 for score in profile.values())


@pytest.mark.parametrize(
    ("a", "b"),
    [
        (V.TRADITION, V.OBEDIENCE),
        (V.TRADITION, V.SECURITY),
        (V.FREEDOM, V.INDEPENDENCE),
        (V.ADVENTURE, V.FREEDOM),
        (V.COMPASSION, V.EQUALITY),
        (V.SUCCESS, V.AMBITION),
    ],
)
def test_related_values_go_together(population: list[dict[V, float]], a: V, b: V) -> None:
    assert r(population, a, b) > 0.5


@pytest.mark.parametrize(
    ("a", "b"),
    [
        (V.FREEDOM, V.OBEDIENCE),
        (V.ADVENTURE, V.SECURITY),
        (V.OPEN_MINDEDNESS, V.TRADITION),
        (V.COMPASSION, V.SUCCESS),
        (V.EQUALITY, V.AMBITION),
        (V.DISCIPLINE, V.PLEASURE),
    ],
)
def test_opposing_values_pull_apart(population: list[dict[V, float]], a: V, b: V) -> None:
    assert r(population, a, b) < -0.4


def test_scores_use_the_whole_range_without_piling_up_at_the_ends(
    population: list[dict[V, float]],
) -> None:
    scores = [score for profile in population for score in profile.values()]
    assert min(scores) < 0.05 and max(scores) > 0.95
    assert sum(1 for s in scores if 0.1 <= s <= 0.9) / len(scores) > 0.8


def min_gap(profiles: list[dict[V, float]]) -> float:
    return min(distance(a, b) for a, b in itertools.combinations(profiles, 2))


@pytest.mark.parametrize("seed", range(5))
def test_the_village_is_more_spread_out_than_any_random_ten(seed: int) -> None:
    rng = random.Random(seed)
    pool = [sample_profile(rng) for _ in range(200)]
    picks = random.Random(seed + 100)

    village = min_gap(spread(pool, 10))

    assert all(village > min_gap(picks.sample(pool, 10)) for _ in range(100))


@pytest.mark.parametrize("seed", range(10))
def test_residents_lead_with_different_values(seed: int) -> None:
    village = sample_values(10, random.Random(seed))

    assert len({ranked(profile)[0][0] for profile in village}) >= 6


def test_spread_starts_from_the_first_and_never_repeats() -> None:
    rng = random.Random(3)
    pool = [sample_profile(rng) for _ in range(50)]

    village = spread(pool, 10)

    assert village[0] is pool[0]
    assert len({id(profile) for profile in village}) == 10


def test_ranked_and_format_scores() -> None:
    profile = {value: 0.5 for value in V} | {V.ADVENTURE: 0.9, V.PEACE_OF_MIND: 0.1}

    order = ranked(profile)

    assert order[0] == (V.ADVENTURE, 0.9)
    assert order[-1] == (V.PEACE_OF_MIND, 0.1)
    assert format_scores([order[0], order[-1]]) == "adventure 0.90, peace of mind 0.10"
