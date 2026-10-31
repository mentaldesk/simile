from collections import Counter

import pytest

from simile.npc import load_npcs
from simile.schema import Npc
from simile.story import disappearance
from simile.story.town import FACTS, METRO, PLACES, PREFIX, Knowing, asked_about, known
from simile.street.village import village

from ..conversation.test_player import BEN, make_npc
from .test_journal import Listening

SEEDS = range(100)
AMENITIES = [id for id in FACTS if id not in METRO]
RESIDENTS = load_npcs()


def resident(id: str, age: int, interests: list[str], **values: float) -> Npc:
    npc = make_npc(id, "house_2", **values)
    return npc.model_copy(update={"age": age, "occupation": "Clerk", "interests": interests})


NEWCOMER = resident(
    "newcomer", 19, ["knitting"], adventure=0, open_mindedness=0, connection=0, security=1
)
OLD_HAND = resident("old_hand", 70, ["salvage"], adventure=1, open_mindedness=1, connection=1)


def shares(npcs: list[Npc]) -> dict[str, Counter[Knowing | None]]:
    counts: dict[str, Counter[Knowing | None]] = {id: Counter() for id in FACTS}
    for seed in SEEDS:
        for npc in npcs:
            knows = known(npc, seed)
            for id in FACTS:
                counts[id][knows.get(id)] += 1
    return counts


def test_most_residents_know_the_amenities_and_the_metro_and_fewer_the_way_down() -> None:
    counts, everyone = shares(RESIDENTS), len(SEEDS) * len(RESIDENTS)

    def share(id: str, *knowing: Knowing) -> float:
        return sum(counts[id][each] for each in knowing) / everyone

    heard = (Knowing.KNOWS, Knowing.HEARD)
    for id in AMENITIES:
        assert share(id, Knowing.KNOWS) > 0.85, id
    assert 0.75 < share("town_metro", *heard) < 0.98
    assert share("town_metro", Knowing.HEARD) > 0.05
    for id in ("town_way_down", "town_clinic", "town_scrap_trader"):
        assert share(id, *heard) < 0.4, id
        assert share(id, Knowing.HEARD) > 0.05, id


def test_it_varies_with_time_here_and_curiosity() -> None:
    newcomer, old_hand = shares([NEWCOMER]), shares([OLD_HAND])

    assert newcomer["town_metro"][None] > 50
    assert old_hand["town_metro"][Knowing.KNOWS] > 90
    assert newcomer["town_way_down"][None] == len(SEEDS)
    assert old_hand["town_way_down"][Knowing.KNOWS] > 70


def test_the_same_seed_and_resident_always_know_the_same() -> None:
    assert all(known(npc, 7) == known(npc, 7) for npc in RESIDENTS)
    assert len({tuple(sorted(known(NEWCOMER, seed).items())) for seed in SEEDS}) > 10


def test_anyone_who_knows_whats_down_there_knows_of_the_metro() -> None:
    for seed in SEEDS:
        for npc in [*RESIDENTS, NEWCOMER]:
            knows = known(npc, seed)
            details = [knows[id] for id in METRO[1:] if id in knows]
            if Knowing.KNOWS in details:
                assert knows["town_metro"] is Knowing.KNOWS
            elif details:
                assert "town_metro" in knows


def test_residents_know_where_they_work() -> None:
    mirela = next(npc for npc in RESIDENTS if npc.workplace == "coffee_shop")
    assert all(known(mirela, seed)["town_cafe"] is Knowing.KNOWS for seed in SEEDS)


def test_every_fact_is_about_somewhere_in_the_village_and_none_about_her_disappearance() -> None:
    plans = village()
    places = {plan.id for plan in plans} | {loc.id for plan in plans for loc in plan.locations}
    for fact in FACTS.values():
        assert fact.where in places, fact.id
        assert fact.id.startswith(PREFIX)
        assert "Aris" not in fact.what + fact.rumour
        assert all(lead.fact_id in FACTS for lead in fact.leads)
    ids = [getattr(disappearance, name) for name in dir(disappearance) if name.isupper()]
    assert not any(isinstance(id, str) and id.startswith(PREFIX) for id in ids)


@pytest.mark.parametrize(
    ("said", "names"),
    [
        ("Is there a metro round here?", ["the old metro"]),
        ("How do I get down to the clinic?", ["the clinic"]),
        ("Where can I sell scrap?", ["the scrap trader"]),
        ("Fancy a coffee at the Daily Grind?", ["the café"]),
        ("What's down by the river, past the gallery?", ["the gallery", "the river promenade"]),
        ("Lovely morning, isn't it?", []),
        ("I'm parking that idea.", []),
    ],
)
def test_a_place_is_asked_about_by_name(said: str, names: list[str]) -> None:
    assert [place.name for place in asked_about(said)] == names
    assert len({place.name for place in PLACES}) == len(PLACES)


def seed_where(npc: Npc, **wanted: Knowing | None) -> int:
    return next(
        seed
        for seed in range(1000)
        if all(known(npc, seed).get(id) is knowing for id, knowing in wanted.items())
    )


@pytest.mark.anyio
async def test_what_a_resident_tells_of_the_metro_goes_in_the_journal_with_its_lead() -> None:
    listening = Listening(None, npcs=(OLD_HAND, BEN))
    listening.village.players.town_seed = seed_where(
        OLD_HAND,
        town_metro=Knowing.KNOWS,
        town_way_down=None,
        town_clinic=Knowing.HEARD,
        town_scrap_trader=None,
    )

    await listening.say("Do you know a good café?", "old_hand")
    assert listening.notebook.entries == []

    await listening.say("Is there really a metro under the village?", "old_hand")

    metro, clinic = FACTS["town_metro"], FACTS["town_clinic"]
    assert listening.learned() == [
        ("town_metro", "Old_Hand", metro.what, None),
        ("town_clinic", "Old_Hand", clinic.rumour, None),
    ]
    assert [lead.fact_id for lead in listening.notebook.entries[0].leads] == ["town_way_down"]
    assert listening.notebook.entries[1].leads == []


@pytest.mark.anyio
async def test_the_way_down_closes_the_lead_and_no_idea_writes_nothing() -> None:
    listening = Listening(None, npcs=(NEWCOMER, OLD_HAND))
    listening.village.players.town_seed = next(
        seed
        for seed in range(1000)
        if known(OLD_HAND, seed).get("town_way_down") is Knowing.KNOWS
        and not any(id in known(NEWCOMER, seed) for id in METRO)
    )

    await listening.say("Where's the old metro?", "newcomer")
    assert listening.notebook.entries == []

    listening.village.walk_to("old_hand", 1)
    await listening.say("Where's the old metro?", "old_hand")

    assert [entry.fact_id for entry in listening.notebook.entries][:2] == [
        "town_metro",
        "town_way_down",
    ]
    assert all(entry.leads == [] for entry in listening.notebook.entries)
