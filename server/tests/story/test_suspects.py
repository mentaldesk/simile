import random
from collections import Counter

from simile.npc import load_npcs
from simile.schema import CoreValue, Npc
from simile.story import DEFAULT_CONFIG, load_story
from simile.story.suspects import attackers, fit, hostility, suspect

GRIEVANCES = load_story().grievances
TEMPLATE = load_npcs()[0]


def resident(id: str, **values: float) -> Npc:
    scores = {value: values.get(value.value, 0.5) for value in CoreValue}
    return TEMPLATE.model_copy(update={"id": id, "name": f"{id.title()} Test", "values": scores})


STERN = resident("stern", obedience=1.0, discipline=1.0, compassion=0.0, freedom=0.0)
KIND = resident("kind", compassion=1.0, open_mindedness=1.0, obedience=0.0, success=0.0)


def test_rules_rankle_with_the_obedient_and_a_hard_heart_makes_them_hostile() -> None:
    assert fit(STERN, GRIEVANCES["rules"]) > 0.4
    assert hostility(STERN, GRIEVANCES) > 0.9
    assert hostility(KIND, GRIEVANCES) < 0


def test_a_suspects_grievance_is_among_those_that_fit_them_best() -> None:
    fits = {kind: fit(STERN, grievance) for kind, grievance in GRIEVANCES.items()}

    drawn = {suspect(STERN, GRIEVANCES, random.Random(seed)).grievance for seed in range(50)}

    assert drawn
    assert all(fits[kind] >= max(fits.values()) - DEFAULT_CONFIG.grievance_spread for kind in drawn)


def test_one_to_three_hostile_residents_attack_in_every_world() -> None:
    npcs = load_npcs()
    counts: Counter[int] = Counter()
    who: Counter[str] = Counter()

    for seed in range(300):
        found = attackers(npcs, GRIEVANCES, random.Random(seed))
        counts[len(found)] += 1
        who.update(attacker.npc.id for attacker in found)
        assert len({attacker.npc.id for attacker in found}) == len(found)
        assert all(attacker.hostility >= DEFAULT_CONFIG.hostile_from for attacker in found)

    assert set(counts) == {1, 2, 3}
    assert len(who) >= 3
    assert not {"desmond", "kofi", "mirela", "odalys", "tobias"} & set(who)


def test_with_nobody_hostile_the_most_hostile_attacks_alone() -> None:
    gentle = [KIND, resident("mild", compassion=0.8), resident("calm", compassion=0.9)]

    found = attackers(gentle, GRIEVANCES, random.Random(1))

    assert [attacker.npc.id for attacker in found] == ["mild"]


def test_there_are_never_more_attackers_than_hostile_residents() -> None:
    village = [STERN, KIND, resident("mild", compassion=0.8)]

    for seed in range(40):
        assert [a.npc.id for a in attackers(village, GRIEVANCES, random.Random(seed))] == ["stern"]
