import asyncio
import random
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime

import pytest

from simile.conversation.telling import Stance, tellings
from simile.npc import load_npcs
from simile.schema import CoreValue, HowKnown, Npc
from simile.social import meet
from simile.story import DEFAULT_CONFIG, DOOR, NOTES, Made, load_story, make_incident
from simile.story.incident import ATTACK, CLOTH, GONE, MEETING, NOTED, SEEN, SHOUTING
from simile.story.suspects import hostility

NOW = datetime(2026, 1, 9, 8, tzinfo=UTC)
NPCS = load_npcs()
GRIEVANCES = load_story().grievances
SEEDS = range(120)


def made(seed: int, npcs: Sequence[Npc] = NPCS) -> Made:
    return asyncio.run(make_incident(npcs, NOW, None, rng=random.Random(seed)))


def village(seed: int) -> list[Npc]:
    """Two to eleven of today's residents, with values drawn at random."""
    rng = random.Random(seed)
    chosen = rng.sample(NPCS, rng.randint(2, len(NPCS)))
    return [
        npc.model_copy(update={"values": {value: rng.random() for value in CoreValue}})
        for npc in chosen
    ]


WORLDS = [made(seed) for seed in SEEDS]
VILLAGES = [village(seed) for seed in SEEDS]
ELSEWHERE = [made(seed, npcs) for seed, npcs in zip(SEEDS, VILLAGES, strict=True)]


@pytest.mark.parametrize(
    ("world", "npcs"), [*((w, NPCS) for w in WORLDS), *zip(ELSEWHERE, VILLAGES, strict=True)]
)
def test_one_to_three_attackers_whose_values_fit(world: Made, npcs: list[Npc]) -> None:
    incident = world.incident
    scores = {npc.id: hostility(npc, GRIEVANCES) for npc in npcs}

    assert 1 <= len(incident.attackers) <= 3
    fit = [scores[npc] >= DEFAULT_CONFIG.hostile_from for npc in incident.attackers]
    most = max(scores, key=lambda npc: scores[npc])
    assert all(fit) or incident.attackers == [most]


def test_todays_village_gets_one_two_and_three_attackers_and_varied_ones() -> None:
    counts = Counter(len(world.incident.attackers) for world in WORLDS)
    who = Counter(npc for world in WORLDS for npc in world.incident.attackers)

    assert set(counts) == {1, 2, 3}
    assert {"henrietta", "raymond", "marguerite", "priya"} <= set(who)


@pytest.mark.parametrize("world", [*WORLDS, *ELSEWHERE])
def test_the_attackers_know_what_they_did_and_have_a_cover_story_for_it(world: Made) -> None:
    incident = world.incident
    by_id = {fact.id: fact for fact in incident.facts}

    for npc in incident.attackers:
        for fact_id in (ATTACK, f"there_{npc}", f"grudge_{npc}"):
            [knower] = [k for k in by_id[fact_id].known_by if k.id == npc]
            assert knower.how is HowKnown.DID
            assert knower.cover


@pytest.mark.parametrize("world", [*WORLDS, *ELSEWHERE])
def test_every_fact_known_is_in_its_knowers_memories(world: Made) -> None:
    remembered = Counter((memory.owner, memory.fact_id) for memory in world.memories)
    known = Counter(
        (knower.id, fact.id) for fact in world.incident.facts for knower in fact.known_by
    )

    assert remembered == known
    for npc in world.incident.attackers:
        assert (npc, ATTACK) in remembered
    assert all(memory.timestamp < NOW for memory in world.memories)


@pytest.mark.parametrize("world", WORLDS)
def test_witnesses_saw_parts_of_the_night(world: Made) -> None:
    incident = world.incident
    by_id = {fact.id: fact for fact in incident.facts}
    attackers = set(incident.attackers)

    for fact_id in (SHOUTING, SEEN, *(f"grudge_{npc}" for npc in attackers)):
        witnesses = [k for k in by_id[fact_id].known_by if k.how is HowKnown.WITNESSED]
        assert witnesses and not {k.id for k in witnesses} & attackers, fact_id
    assert (MEETING in by_id) == (len(attackers) > 1)
    assert by_id[NOTED].found_in == NOTES and by_id[CLOTH].found_in == DOOR
    assert {k.id for k in by_id[GONE].known_by} == {npc.id for npc in NPCS}


@pytest.mark.parametrize("world", [*WORLDS, *ELSEWHERE])
def test_the_trail_leads_from_the_clues_to_every_attacker(world: Made) -> None:
    incident = world.incident
    leads = {fact.id: [lead.fact_id for lead in fact.leads] for fact in incident.facts}
    reached, frontier = set(), [NOTED, CLOTH, GONE]
    while frontier:
        fact_id = frontier.pop()
        if fact_id not in reached:
            reached.add(fact_id)
            frontier += leads[fact_id]

    assert {f"there_{npc}" for npc in incident.attackers} <= reached


@pytest.mark.parametrize("world", WORLDS)
def test_the_night_is_a_week_before_the_world_starts(world: Made) -> None:
    incident = world.incident
    by_id = {fact.id: fact for fact in incident.facts}

    assert incident.night.date() == (NOW - DEFAULT_CONFIG.night_before).date()
    assert incident.night.hour == 23
    assert incident.night < by_id[GONE].when < NOW
    assert all(fact.when < NOW for fact in incident.facts)


def test_lies_are_decided_for_the_attackers_by_their_trust_in_whoever_asks() -> None:
    npcs = {npc.id: npc for npc in NPCS}
    for world in WORLDS:
        incident = world.incident
        memories = {npc: [m for m in world.memories if m.owner == npc] for npc in npcs}
        for npc in incident.attackers:
            stranger = meet(npcs[npc], "player").trust
            told = {t.fact.id: t for t in tellings(incident, npc, stranger, memories[npc])}
            for fact_id in (ATTACK, f"there_{npc}", f"grudge_{npc}"):
                assert told[fact_id].stance is Stance.LIE
                lie = told[fact_id].temptation()
                assert lie.fact_id == fact_id
                assert told[fact_id].knower.cover in lie.direction()
            assert told[GONE].stance is Stance.TELL
            trusted = {t.fact.id: t.stance for t in tellings(incident, npc, 0.8)}
            assert trusted[f"grudge_{npc}"] is Stance.TELL
            assert trusted[ATTACK] is Stance.LIE


def test_the_same_seed_makes_the_same_incident() -> None:
    assert made(7).incident == made(7).incident
    assert made(7).memories == made(7).memories
    assert made(7).incident != made(8).incident
