import random
from collections import Counter
from collections.abc import Callable

import pytest

from simile.characters.tables import (
    Happening,
    Skeleton,
    Tables,
    Village,
    sample_events,
    sample_skeleton,
)
from simile.characters.tables.events import MAX_EVENTS, MIN_EVENTS

type Skeletons = Callable[..., Skeleton]


def draws(skeleton: Skeleton, scores: dict[str, float], times: int, **options: object) -> Counter:
    counts = Counter()
    for seed in range(times):
        counts.update(e.id for e in sample_events(random.Random(seed), skeleton, scores, **options))
    return counts


@pytest.mark.parametrize("age", [18, 30, 55, 85])
def test_every_event_happens_at_an_age_it_allows(
    tables: Tables, skeleton: Skeletons, values: Callable, age: int
) -> None:
    for seed in range(150):
        s = skeleton(age, seed=seed)
        events = sample_events(random.Random(seed), s, values(random.Random(seed).random()))
        ages = {e.id: e.age for e in events}

        assert MIN_EVENTS <= len(events) <= MAX_EVENTS
        assert events == sorted(events, key=lambda e: (e.age, e.id))
        assert len(ages) == len(events)
        for e in events:
            event = tables.event[e.id]
            assert event.ages[0] <= e.age <= min(event.ages[1], age)
            if event.years:
                assert event.years[0] <= s.birth_year + e.age <= event.years[1]
            if event.after:
                assert any(ages.get(id, 99) < e.age for id in event.after)
            assert not set(event.not_with) & set(ages)


def test_high_and_low_values_draw_different_events(skeleton: Skeletons, values: Callable) -> None:
    s = skeleton(50, seed=1)
    bold = draws(s, values(0.5, adventure=0.95, freedom=0.95, security=0.05), 400)
    timid = draws(s, values(0.5, adventure=0.05, freedom=0.05, security=0.95), 400)
    upright = draws(s, values(0.5, justice=0.95, honesty=0.95, obedience=0.05), 1500)
    pliant = draws(s, values(0.5, justice=0.05, honesty=0.05, obedience=0.95), 1500)
    young = skeleton(30, seed=1)
    rebel = draws(young, values(0.5, honesty=0.05, obedience=0.05), 1000)
    dutiful = draws(young, values(0.5, honesty=0.95, obedience=0.95), 1000)

    assert bold["travelled_broke"] > 4 * timid["travelled_broke"]
    assert upright["whistleblower"] > 4 * pliant["whistleblower"]
    assert rebel["shoplifting"] > 4 * dutiful["shoplifting"]


def test_temperament_shifts_events_too(skeleton: Skeletons, values: Callable) -> None:
    s = skeleton(45, seed=2)
    reckless = draws(s, {**values(0.5), "prudence": 0.05}, 600)
    careful = draws(s, {**values(0.5), "prudence": 0.95}, 600)

    assert reckless["drink_driving"] > 3 * careful["drink_driving"]


def test_the_skeleton_decides_what_can_happen(skeleton: Skeletons, values: Callable) -> None:
    childless = draws(skeleton(70, seed=3, children=0), values(0.5), 300)
    privileged = draws(
        skeleton(40, seed=3, background="professional", education="degree"), values(0.5), 300
    )

    assert not {"grandparent", "first_child", "child_estranged"} & set(childless)
    assert "first_in_family_university" not in privileged


def test_events_the_skeleton_implies_always_happen(skeleton: Skeletons, values: Callable) -> None:
    for seed in range(30):
        widowed = skeleton(70, seed=seed, partnership="widowed")
        in_care = skeleton(30, seed=seed, upbringing="care")

        rng = random.Random(seed)
        assert "widowed" in {e.id for e in sample_events(rng, widowed, values(0.5))}
        assert "went_into_care" in {e.id for e in sample_events(rng, in_care, values(0.5))}


def test_a_rare_event_happens_to_one_resident_at_most(tables: Tables, values: Callable) -> None:
    rare = {event.id for event in tables.events if event.rare}
    rng, village = random.Random(4), Village()
    counts = Counter()
    for _ in range(80):
        s = sample_skeleton(rng, rng.randint(18, 90), village=village)
        counts.update(e.id for e in sample_events(rng, s, values(rng.random()), village=village))

    assert rare & set(counts)
    assert all(counts[id] <= 1 for id in rare)
    assert all(village.drawn[id] == n for id, n in counts.items())


def test_a_common_event_gets_less_likely_once_a_neighbour_has_it(
    skeleton: Skeletons, values: Callable
) -> None:
    s = skeleton(60, seed=5)
    neighbours = 0
    for seed in range(300):
        village = Village()
        village.drawn["parent_died"] = 2
        events = sample_events(random.Random(seed), s, values(0.5), village=village)
        neighbours += any(e.id == "parent_died" for e in events)

    assert neighbours < draws(s, values(0.5), 300)["parent_died"] / 4


def test_fixed_events_are_kept_and_shape_the_rest(skeleton: Skeletons, values: Callable) -> None:
    s = skeleton(40, seed=6)
    champion = [Happening(17, "sport_champion", "won", 28, 0.8)]
    divorce = [Happening(35, "divorced", "divorced", 73, -0.6)]
    married = skeleton(60, seed=6, partnership="married")

    with_title = draws(s, values(0.5), 300, fixed=champion)
    without = draws(s, values(0.5), 300)
    assert with_title["sport_champion"] == 300
    assert with_title["knee_injury"] > 3 * without["knee_injury"]
    for seed in range(100):
        events = sample_events(random.Random(seed), married, values(0.5), fixed=divorce)
        assert all(e.age > 35 for e in events if e.id == "remarried")


def test_count_overrides_how_many(skeleton: Skeletons, values: Callable) -> None:
    s = skeleton(60, upbringing="two_parents", partnership="married")

    assert len(sample_events(random.Random(0), s, values(0.5), count=1)) == 1
