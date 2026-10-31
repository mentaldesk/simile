import random
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import pytest

from simile.conversation.telling import Stance, tellings
from simile.npc import load_npcs
from simile.schema import CoreValue, Disappearance, HowKnown, Npc
from simile.social import meet, tolerance
from simile.social.bionics import level
from simile.story import DEFAULT_CONFIG, NOTES, Made, load_story, make_disappearance
from simile.story.content import HATCH, TERMINAL
from simile.story.disappearance import (
    GONE,
    HATCH_LOG,
    LAST_SEEN,
    LIFT_LOG,
    NOTED,
    PASSED,
    distrust,
    distrusters,
)

from ..schema.test_story import DISAPPEARANCES

NOW = datetime(2026, 1, 9, 8, tzinfo=UTC)
NPCS = load_npcs()
BY_ID = {npc.id: npc for npc in NPCS}
TEXTS = load_story().texts
SEEDS = range(120)


def made(seed: int, npcs: Sequence[Npc] = NPCS) -> Made:
    return make_disappearance(npcs, NOW, rng=random.Random(seed))


def village(seed: int) -> list[Npc]:
    """One to eleven of today's residents, with values drawn at random."""
    rng = random.Random(seed)
    chosen = rng.sample(NPCS, rng.randint(1, len(NPCS)))
    return [
        npc.model_copy(update={"values": {value: rng.random() for value in CoreValue}})
        for npc in chosen
    ]


WORLDS = [made(seed) for seed in SEEDS]
VILLAGES = [village(seed) for seed in SEEDS]
ELSEWHERE = [made(seed, npcs) for seed, npcs in zip(SEEDS, VILLAGES, strict=True)]
EVERYWHERE = [*((w, NPCS) for w in WORLDS), *zip(ELSEWHERE, VILLAGES, strict=True)]


def facts(world: Made) -> dict[str, list[str]]:
    return {fact.id: [lead.fact_id for lead in fact.leads] for fact in world.disappearance.facts}


def test_the_default_villages_distrusters_are_those_against_bionics() -> None:
    expected = ["tobias", "henrietta", "mirela", "raymond"]

    assert [npc.id for npc in distrusters(NPCS)] == expected
    assert {tuple(world.disappearance.distrusted_by) for world in WORLDS} == {tuple(expected)}


@pytest.mark.parametrize(("world", "npcs"), EVERYWHERE)
def test_those_against_bionics_distrusted_her_or_else_the_least_tolerant(
    world: Made, npcs: list[Npc]
) -> None:
    against = {npc.id for npc in npcs if level(tolerance(npc.values)) <= -1}
    least = min(npcs, key=lambda npc: (tolerance(npc.values), npc.id)).id

    assert set(world.disappearance.distrusted_by) == (against or {least})


@pytest.mark.parametrize(("world", "npcs"), EVERYWHERE)
def test_each_fact_has_the_knowers_and_leads_of_the_table(world: Made, npcs: list[Npc]) -> None:
    found = world.disappearance
    ids, by_id = found.distrusted_by, {fact.id: fact for fact in found.facts}
    others = {npc.id for npc in npcs} - set(ids)
    leads = facts(world)
    [passer] = [k.id for k in by_id[PASSED].known_by]

    assert {k.id for k in by_id[GONE].known_by} == {npc.id for npc in npcs}
    assert all(k.tells_from == 0 and k.cover is None for k in by_id[GONE].known_by)
    assert leads[GONE] == ([NOTED, LAST_SEEN] if LAST_SEEN in by_id else [NOTED])
    noted = [lead.removeprefix("distrust_") for lead in leads[NOTED]]
    assert 1 <= len(noted) <= 2 and set(noted) <= set(ids) and passer in noted
    assert by_id[NOTED].found_in == NOTES and not by_id[NOTED].known_by
    for npc in ids:
        fact = by_id[distrust(npc)]
        did, *heard = fact.known_by
        assert (did.id, did.how) == (npc, HowKnown.DID)
        assert [k.how for k in heard] == ([HowKnown.WITNESSED] if others else [])
        assert {k.id for k in heard} <= others
        assert leads[fact.id] == ([PASSED] if npc == passer else [])
    assert passer in ids and by_id[PASSED].known_by[0].how is HowKnown.WITNESSED
    assert leads[PASSED] == [LIFT_LOG]
    if others:
        [seen_by] = by_id[LAST_SEEN].known_by
        assert seen_by.id in others and seen_by.how is HowKnown.WITNESSED
        assert leads[LAST_SEEN] == [LIFT_LOG, PASSED]
        assert set(by_id[LAST_SEEN].about) == {"aris", passer}
    else:
        assert LAST_SEEN not in by_id
    assert (by_id[LIFT_LOG].found_in, by_id[HATCH_LOG].found_in) == (TERMINAL, HATCH)
    assert leads[LIFT_LOG] == [HATCH_LOG]


def test_everyone_who_distrusted_her_has_their_own_distrust_fact() -> None:
    for found in [Disappearance.model_validate(d) for d in DISAPPEARANCES] + [
        world.disappearance for world in WORLDS + ELSEWHERE
    ]:
        ids = {fact.id for fact in found.facts}
        assert {distrust(npc) for npc in found.distrusted_by} <= ids


@pytest.mark.parametrize("world", WORLDS)
def test_the_trail_reaches_the_logs_and_every_distruster_s_fact(world: Made) -> None:
    leads = facts(world)
    reached, frontier = set(), [GONE, NOTED]
    while frontier:
        fact_id = frontier.pop()
        if fact_id not in reached:
            reached.add(fact_id)
            frontier += leads[fact_id]

    assert {LAST_SEEN, PASSED, LIFT_LOG, HATCH_LOG} <= reached
    assert set(leads) - reached <= {distrust(npc) for npc in world.disappearance.distrusted_by}


def test_willingness_follows_values_in_the_default_village() -> None:
    world = made(1)
    knowers = {(fact.id, k.id): k for fact in world.disappearance.facts for k in fact.known_by}

    for npc, tells_from, cover in [
        ("tobias", 0.0, None),
        ("henrietta", 0.75, TEXTS.denial),
        ("mirela", 0.75, None),
        ("raymond", 0.75, TEXTS.denial),
    ]:
        knower = knowers[(distrust(npc), npc)]
        assert (knower.tells_from, knower.cover) == (tells_from, cover), npc
    for world in WORLDS:
        [passer] = next(f for f in world.disappearance.facts if f.id == PASSED).known_by
        lies = BY_ID[passer.id].values[CoreValue.HONESTY] < DEFAULT_CONFIG.distruster_lies_below
        assert passer.cover == (TEXTS.not_seen if lies else None)


@pytest.mark.parametrize(("world", "npcs"), EVERYWHERE)
def test_every_fact_known_is_in_its_knowers_memories(world: Made, npcs: list[Npc]) -> None:
    remembered = Counter((memory.owner, memory.fact_id) for memory in world.memories)
    known = Counter(
        (knower.id, fact.id) for fact in world.disappearance.facts for knower in fact.known_by
    )

    assert remembered == known
    assert all(memory.timestamp < NOW for memory in world.memories)
    for memory in world.memories:
        if memory.fact_id == GONE:
            glad = memory.owner in world.disappearance.distrusted_by
            assert memory.content.endswith(TEXTS.relieved) == glad


@pytest.mark.parametrize("world", WORLDS)
def test_she_was_last_seen_the_evening_before_and_the_logs_follow(world: Made) -> None:
    by_id = {fact.id: fact for fact in world.disappearance.facts}
    seen, gone = by_id[PASSED].when, by_id[GONE].when

    assert seen.date() == (gone - timedelta(days=1)).date()
    start, end = DEFAULT_CONFIG.seen_between
    assert start <= seen.time() <= end and seen.minute % 5 == 0
    assert by_id[LAST_SEEN].when == seen and f"{seen:%H:%M}" in by_id[LAST_SEEN].what
    assert seen < by_id[LIFT_LOG].when < by_id[HATCH_LOG].when < gone < NOW
    assert all(fact.when < NOW for fact in world.disappearance.facts)


def test_lies_are_decided_for_the_distrusters_by_their_trust_in_whoever_asks() -> None:
    for world in WORLDS:
        found = world.disappearance
        for npc in found.distrusted_by:
            mine = [m for m in world.memories if m.owner == npc]
            stranger = meet(BY_ID[npc], "player").trust
            told = {t.fact.id: t for t in tellings(found, npc, stranger, mine)}
            lying = BY_ID[npc].values[CoreValue.HONESTY] < DEFAULT_CONFIG.distruster_lies_below
            expected = Stance.LIE if lying else Stance.TELL if npc == "tobias" else Stance.KEEP
            assert told[distrust(npc)].stance is expected, npc
            if lying:
                lie = told[distrust(npc)].temptation()
                assert lie.fact_id == distrust(npc)
                assert TEXTS.denial in lie.direction()
                assert "how you got on with Aris" in lie.direction()
                assert told[distrust(npc)].remembers not in lie.direction()
            assert told[GONE].stance is Stance.TELL
            trusted = {t.fact.id: t.stance for t in tellings(found, npc, 0.8)}
            assert trusted[distrust(npc)] is Stance.TELL


def test_the_same_seed_makes_the_same_disappearance() -> None:
    assert made(7) == made(7)
    assert made(7).disappearance != made(8).disappearance
