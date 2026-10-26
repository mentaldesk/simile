import random
from collections import Counter
from datetime import UTC, datetime, timedelta

import pytest

from simile.npc import load_npcs
from simile.schema import (
    PLAYER_ID,
    Aspect,
    Bionic,
    Body,
    InteractionEvent,
    Item,
    ItemKind,
    Memory,
    MemoryKind,
    Npc,
    Player,
)
from simile.social import apply_events, as_of, meet, tolerance
from simile.social.bionics import level
from simile.social.sightings import Sightings
from simile.story import DEFAULT_CONFIG, StoryConfig
from simile.story.lens import FULL, GIVEN, GIVES, KEPT, LENS, Lens, keeper

from ..conversation.test_player import ANA, Village, feeling, make_npc

pytestmark = pytest.mark.anyio

FAN = make_npc("fan", "house_3", adventure=1.0, ambition=1.0, open_mindedness=1.0)
EASY = make_npc("easy", "house_4")
UNEASY = make_npc("uneasy", "house_5", security=0.65, tradition=0.65)
WARY = make_npc("wary", "house_6", security=0.8, tradition=0.8)


def takes_to_bionics(npc: Npc) -> int:
    return level(tolerance(npc.values))


def test_the_lens_goes_to_someone_who_doesn_t_mind_bionics() -> None:
    village = [FAN, EASY, UNEASY, WARY]

    chosen = {keeper(village, random.Random(seed)).id for seed in range(50)}

    assert chosen == {"fan", "easy"}
    assert [takes_to_bionics(npc) for npc in village] == [2, 0, -1, -2]


def test_any_tolerant_default_resident_may_keep_it_the_same_for_a_seed() -> None:
    npcs = load_npcs()
    tolerant = {npc.id for npc in npcs if takes_to_bionics(npc) >= DEFAULT_CONFIG.tolerates_from}

    drawn = Counter(keeper(npcs, random.Random(f"lens/{seed}")).id for seed in range(200))

    assert set(drawn) == tolerant and len(tolerant) < len(npcs)
    assert keeper(npcs, random.Random("lens/0")).id == "desmond"
    assert keeper(npcs, random.Random("lens/3")) == keeper(npcs, random.Random("lens/3"))


def test_an_attacker_keeps_it_only_if_every_tolerant_resident_is_one() -> None:
    village = [FAN, EASY, UNEASY, WARY]

    for seed in range(20):
        assert keeper(village, random.Random(seed), besides={"fan"}).id == "easy"
        drawn = keeper(village, random.Random(seed))
        assert keeper(village, random.Random(seed), besides={"wary"}) == drawn
    assert keeper(village, random.Random(0), besides={"fan", "easy"}).id in {"fan", "easy"}


def test_with_nobody_tolerant_whoever_minds_least_keeps_it() -> None:
    assert keeper([WARY, UNEASY], random.Random(0)).id == "uneasy"
    assert keeper([WARY, UNEASY], random.Random(0), besides={"uneasy"}).id == "wary"
    assert keeper([UNEASY], random.Random(0), besides={"uneasy"}).id == "uneasy"
    assert keeper([], random.Random(0)) is None


def test_a_few_good_conversations_win_any_tolerant_default_resident_s_trust() -> None:
    def conversations(npc: Npc, trust: float) -> int:
        rel, now = meet(npc, PLAYER_ID), datetime(2026, 1, 1, tzinfo=UTC)
        for had in range(10):
            if as_of(rel, now).trust >= trust:
                return had
            event = InteractionEvent(
                actor=PLAYER_ID,
                target=npc.id,
                action="kept their word",
                aspects=[Aspect.TRUST],
                valence=0.5,
                magnitude=0.5,
                timestamp=now,
            )
            rel = apply_events(as_of(rel, now), [event], now)
            now += timedelta(hours=6)
        return 10

    for npc in load_npcs():
        if takes_to_bionics(npc) >= DEFAULT_CONFIG.tolerates_from:
            assert conversations(npc, DEFAULT_CONFIG.mentions_from) <= 2, npc.id
            assert conversations(npc, DEFAULT_CONFIG.gives_from) <= 4, npc.id


class Keeping:
    """Ana keeps the lens, trusting the player `trust`, on the conversation tests' village."""

    def __init__(
        self,
        trust: float | None = None,
        player: Player | None = None,
        config: StoryConfig = DEFAULT_CONFIG,
    ) -> None:
        trusting = [] if trust is None else [feeling(ANA, PLAYER_ID, trust=trust)]
        self.village = Village(relationships=trusting)
        if trust is not None:
            self.talked()
        self.player = player or Player()
        self.config = config
        self.lens = self.start()

    def talked(self) -> None:
        self.village.store.add(
            Memory(
                owner="ana",
                kind=MemoryKind.CONVERSATION,
                content="I chatted with Visitor about the village.",
                salience=0.3,
                valence=0.2,
                timestamp=self.village.clock.now,
                about=[PLAYER_ID],
            )
        )

    def start(self) -> Lens:
        village = self.village
        now, players = (lambda: village.clock.now), (lambda: village.players)
        lens = Lens(ANA, village.store, now, lambda: self.player, players, self.config)
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


async def test_seeing_the_player_s_bionics_isn_t_talking_so_the_lens_stays_locked() -> None:
    keeping = Keeping(config=StoryConfig(mentions_from=0.0, gives_from=0.0))
    village = keeping.village
    sightings = Sightings(
        village.store,
        village.clock,
        {"ana": ANA},
        village.movement,
        lambda: Body(legs=Bionic.BIONIC_LEGS),
        lambda npc: True,
    )
    sightings.see("ana", [Bionic.BIONIC_LEGS])
    assert village.store.relationship("ana", PLAYER_ID) is not None

    await village.run(DEFAULT_CONFIG.lens_every * 3)
    said = await keeping.talk()

    assert keeping.remembered(KEPT) == [] and GIVES not in said and keeping.lenses() == 0
    keeping.talked()
    await village.run(DEFAULT_CONFIG.lens_every)
    assert keeping.lens.kept
