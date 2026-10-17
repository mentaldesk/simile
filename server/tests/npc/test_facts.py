import random
from collections import Counter

import pytest

from simile.npc.facts import MAX_EVENTS, MIN_EVENTS, Facts, sample_facts
from simile.npc.tables import ARRIVALS, EVENTS, OCCUPATIONS, ORIGINS, STUDENTS


def one(age: int, gender: str = "woman", seed: int = 0) -> Facts:
    [facts] = sample_facts([(age, gender)], random.Random(seed))
    return facts


def test_a_seed_samples_the_same_facts() -> None:
    people = [(30, "woman"), (70, "man"), (19, "man")]

    assert sample_facts(people, random.Random(1)) == sample_facts(people, random.Random(1))
    assert sample_facts(people, random.Random(1)) != sample_facts(people, random.Random(2))


@pytest.mark.parametrize("gender", ["woman", "man"])
def test_a_name_is_a_real_one_for_their_origin_and_gender(gender: str) -> None:
    for facts in sample_facts([(40, gender)] * 10, random.Random(3)):
        first, surname = facts.name.split(" ", 1)
        [origin] = [origin for origin in ORIGINS if origin.country == facts.country]
        assert first in (origin.women if gender == "woman" else origin.men)
        assert surname in origin.surnames
        assert "-" not in surname


@pytest.mark.parametrize("seed", range(20))
def test_a_village_uses_no_name_or_job_twice(seed: int) -> None:
    cast = sample_facts([(30, "woman"), (45, "man")] * 5, random.Random(seed))

    names = [part for facts in cast for part in facts.name.split()]
    jobs = [facts.occupation.removeprefix("retired ") for facts in cast]
    assert len(names) == len(set(names))
    assert len(jobs) == len(set(jobs))


@pytest.mark.parametrize("age", [19, 35, 52, 80])
def test_life_events_sit_on_a_timeline_up_to_today(age: int) -> None:
    spans = {event.text: event for event in EVENTS}
    for seed in range(50):
        events = one(age, seed=seed).events

        assert MIN_EVENTS <= len(events) <= MAX_EVENTS
        assert list(events) == sorted(events)
        assert len({text for _, text in events}) == len(events)
        for at, text in events:
            assert spans[text].youngest <= at <= min(spans[text].oldest, age)


def test_older_residents_have_more_room_for_events() -> None:
    assert {len(one(19, seed=seed).events) for seed in range(50)} == {MIN_EVENTS}
    assert max(len(one(70, seed=seed).events) for seed in range(50)) == MAX_EVENTS


@pytest.mark.parametrize("age", [19, 40, 80])
def test_they_came_to_the_village_by_now_or_were_born_there(age: int) -> None:
    reasons = {arrival.text: arrival for arrival in ARRIVALS}
    arrivals = [one(age, seed=seed).arrived for seed in range(100)]

    assert None in arrivals
    for arrived in filter(None, arrivals):
        at, why = arrived
        assert reasons[why].youngest <= at <= min(reasons[why].oldest, age)


def test_origin_says_where_they_were_born_and_when_they_came() -> None:
    came = Facts("Ewa Nowak", "Poland", (31, "for a job"), "baker", ())
    native = Facts("Esi Osei", "Ghana", None, "baker", ())

    assert came.origin == "born in Poland, came to the village at 31 for a job"
    assert native.origin == "born in the village to a family from Ghana"


def test_occupations_follow_the_employment_shares() -> None:
    groups = {title: group.name for group in OCCUPATIONS for title in group.titles}
    drawn = Counter(
        groups[facts.occupation]
        for seed in range(4000)
        if (facts := one(40, seed=seed)).occupation in groups
    )

    total = sum(group.weight for group in OCCUPATIONS)
    for group in OCCUPATIONS:
        assert drawn[group.name] / drawn.total() == pytest.approx(group.weight / total, abs=0.03)


def test_most_older_residents_have_retired_and_some_young_ones_study() -> None:
    old = [one(75, seed=seed).occupation for seed in range(200)]
    young = [one(20, seed=seed).occupation for seed in range(200)]

    assert sum(job.startswith("retired ") for job in old) > 150
    assert any(job in STUDENTS for job in young)
    assert not any(job.startswith("retired ") for job in young)


def test_nobody_young_is_a_manager_or_a_professional() -> None:
    senior = {title for group in OCCUPATIONS if group.youngest > 19 for title in group.titles}

    assert not senior & {one(19, seed=seed).occupation for seed in range(500)}
