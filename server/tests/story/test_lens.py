import random
from collections import Counter

import pytest

from simile.npc import load_npcs
from simile.schema import PLAYER_ID, Item, ItemKind, Player
from simile.story import DEFAULT_CONFIG
from simile.story.lens import FULL, GIVEN, GIVES, KEPT, LENS, Lens, keeper
from simile.story.suspects import lean

from ..conversation.test_player import ANA, BEN, Village, feeling, make_npc

pytestmark = pytest.mark.anyio

KEEPER = make_npc("keeper", "house_3", security=1.0, tradition=1.0, knowledge=0.9, adventure=0.8)
CAREFREE = make_npc("carefree", "house_4", security=0.0, tradition=0.0, knowledge=0.2)


def test_the_lens_goes_to_someone_who_d_keep_an_old_thermal_camera() -> None:
    village = [KEEPER, CAREFREE, ANA, BEN]

    chosen = {keeper(village, random.Random(seed)).id for seed in range(50)}

    assert chosen == {"keeper"}
    assert lean(KEEPER, DEFAULT_CONFIG.keeps) > 0.3 > DEFAULT_CONFIG.keeps_from
    assert lean(CAREFREE, DEFAULT_CONFIG.keeps) < 0


def test_the_keeper_is_drawn_from_those_who_lean_that_way_the_same_for_a_seed() -> None:
    npcs = load_npcs()
    keen = {npc.id for npc in npcs if lean(npc, DEFAULT_CONFIG.keeps) >= DEFAULT_CONFIG.keeps_from}

    drawn = Counter(keeper(npcs, random.Random(f"lens/{seed}")).id for seed in range(200))

    assert set(drawn) == keen and len(keen) > 1
    assert keeper(npcs, random.Random("lens/3")) == keeper(npcs, random.Random("lens/3"))


def test_an_attacker_never_keeps_it_and_with_nobody_keen_the_keenest_does() -> None:
    village = [KEEPER, CAREFREE, ANA]

    assert keeper(village, random.Random(0), besides={"keeper"}).id == "ana"
    assert keeper([KEEPER], random.Random(0), besides={"keeper"}).id == "keeper"
    assert keeper([], random.Random(0)) is None


class Keeping:
    """Ana keeps the lens, trusting the player `trust`, on the conversation tests' village."""

    def __init__(self, trust: float | None = None, player: Player | None = None) -> None:
        trusting = [] if trust is None else [feeling(ANA, PLAYER_ID, trust=trust)]
        self.village = Village(relationships=trusting)
        self.player = player or Player()
        self.lens = self.start()

    def start(self) -> Lens:
        village = self.village
        now, players = (lambda: village.clock.now), (lambda: village.players)
        lens = Lens(ANA, village.store, now, lambda: self.player, players)
        village.world.loop.register(lens)
        return lens

    async def talk(self) -> list[str]:
        self.village.players.say("Hi, I'm new here.", "ana")
        await self.village.run()
        return self.village.said("ana")

    def remembered(self, topic: str) -> list[str]:
        memories = self.village.store.recall("ana", self.village.clock.now, about=PLAYER_ID, k=50)
        return [memory.content for memory in memories if topic in memory.topics]

    def lenses(self) -> int:
        return sum(item.id == LENS.id for item in self.player.items)


async def test_below_the_trust_they_need_the_keeper_keeps_the_lens() -> None:
    keeping = Keeping(trust=DEFAULT_CONFIG.gives_from - 0.01)

    said = await keeping.talk()

    assert GIVES not in said and FULL not in said
    assert keeping.lenses() == 0 and not keeping.remembered(GIVEN)


async def test_trusted_enough_they_hand_it_over_after_their_reply_and_remember_it() -> None:
    keeping = Keeping(trust=DEFAULT_CONFIG.gives_from)

    said = await keeping.talk()

    assert said == ["Lovely to meet you.", "Settling in?", GIVES]
    assert keeping.lenses() == 1
    [lens] = [item for item in keeping.player.items if item.id == LENS.id]
    assert (lens.kind, lens.name, lens.weight) == (ItemKind.PART, "Infrared lens", 0.2)
    assert keeping.remembered(GIVEN) == [
        "I gave Visitor the infrared lens out of my old thermal camera, for an infrared eye."
    ]


async def test_it_is_given_once_even_after_a_restart() -> None:
    keeping = Keeping(trust=0.9)
    await keeping.talk()
    keeping.village.engine.end(keeping.village.engine.live()[0].id)
    keeping.player.items = [item for item in keeping.player.items if item.id != LENS.id]

    keeping.lens = keeping.start()
    assert keeping.lens.given
    await keeping.village.run(60)
    said = await keeping.talk()

    assert said.count(GIVES) == 1 and keeping.lenses() == 0


async def test_with_full_hands_they_say_so_and_give_it_once_there_s_room() -> None:
    heavy = Item(id="scrap_steel", kind=ItemKind.SALVAGE, name="Scrap steel", weight=9.0)
    player = Player()
    player.items = [*player.items, heavy]
    keeping = Keeping(trust=0.9, player=player)

    said = await keeping.talk()

    assert said[-1] == FULL and keeping.lenses() == 0
    keeping.village.engine.end(keeping.village.engine.live()[0].id)
    player.items = [item for item in player.items if item.id != heavy.id]
    await keeping.village.run(60)
    assert keeping.lenses() == 0
    assert (await keeping.talk())[-1] == GIVES and keeping.lenses() == 1


async def test_trusting_the_player_enough_they_remember_having_it_and_so_can_say() -> None:
    wary = Keeping(trust=DEFAULT_CONFIG.mentions_from - 0.01)
    trusting = Keeping(trust=DEFAULT_CONFIG.mentions_from)

    for keeping in (wary, trusting):
        await keeping.village.run(DEFAULT_CONFIG.lens_every * 3)

    assert wary.remembered(KEPT) == []
    assert trusting.remembered(KEPT) == [
        "I've still got my old thermal camera at home. Its infrared lens is the part an infrared "
        "eye needs, and I'd give it to Visitor once I trust them a little more."
    ]
    assert trusting.lens.kept and not trusting.lens.given
    assert trusting.lenses() == 0


async def test_another_resident_never_hands_it_over() -> None:
    keeping = Keeping(trust=0.9)
    keeping.village.walk_to("ben", 1)

    keeping.village.players.say("Hi, I'm new here.", "ben")
    await keeping.village.run()

    assert GIVES not in keeping.village.said("ben") and keeping.lenses() == 0
