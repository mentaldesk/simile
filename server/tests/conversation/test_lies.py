import itertools
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import pytest

from simile.behaviour import Behaviour
from simile.conversation import ConversationConfig, ConversationEngine
from simile.conversation.temptation import Kind, Lie, Temptation, chance, lies
from simile.llm import FakeProvider, LLMClient
from simile.memory import MemoryStore
from simile.schema import Flag, FlagKind, MapTile, Npc, Relationship
from simile.sim import Clock, ConversationStarted, FakeWallClock, World
from simile.social import meet, open_flag
from simile.world import Movement
from simile.world.map import load_maps

from .test_player import Village, make_npc

pytestmark = pytest.mark.anyio

START = datetime(2026, 1, 1, 10, tzinfo=UTC)
ALWAYS = ConversationConfig(lie_most=1.0, leave_below=0.0)
SHORT = (
    "You are short of money this week. If it comes up, say you're doing fine. Use that cover story "
    "and nothing else: no days, times, places or other people."
)


def liar(id: str = "ana", home: str = "house_1") -> Npc:
    return make_npc(id, home, honesty=0.05)


def honest(id: str = "ana", home: str = "house_1") -> Npc:
    return make_npc(id, home, honesty=0.9)


def talking(npc: Npc) -> Village:
    """`npc` and Ben at the café, where `npc` is down to 10 and the player is next to them."""
    village = Village(["Oh, fine, fine. [values: honesty]"], npcs=(npc, make_npc("ben", "house_2")))
    village.engine.config = ALWAYS
    village.behaviour.hooks.set(money=lambda resident: 10.0)
    return village


def started(village: Village) -> str:
    return village.of(ConversationStarted)[0].conversation.id


async def test_the_player_touching_a_temptation_directs_a_dishonest_npc_to_lie() -> None:
    village = talking(liar())

    village.players.say("You're not struggling for money, are you?", "ana")
    await village.run()

    assert SHORT in village.script.prompts[-1]
    [told] = village.engine.lies(started(village))
    assert (told.liar, told.listener, told.known) == ("ana", "player", False)
    assert told.admits == "I lied to Visitor about being short of money."
    assert village.engine.lies(started(village)) == []


async def test_an_honest_npc_gets_no_direction() -> None:
    village = talking(honest())

    village.players.say("You're not struggling for money, are you?", "ana")
    await village.run()

    assert "short of money" not in village.script.prompts[-1]
    assert village.engine.lies(started(village)) == []


async def test_the_direction_waits_for_the_player_to_touch_it_and_then_stays() -> None:
    village = talking(liar())

    village.players.say("Lovely morning, isn't it?", "ana")
    await village.run()
    village.players.say("Is the rent round here steep?", "ana")
    await village.run()
    village.players.say("What do you do for fun?", "ana")
    await village.run()

    first, second, third = village.script.prompts
    assert SHORT not in first
    assert SHORT in second and SHORT in third
    assert len(village.engine.lies(started(village))) == 1


async def test_being_asked_to_cover_is_a_temptation_without_any_state() -> None:
    village = talking(liar())
    village.behaviour.hooks.set(money=lambda resident: 900.0)

    village.players.say("If Sandra asks, can you say I was with you on Thursday?", "ana")
    await village.run()

    assert (
        "Visitor is asking you to cover for them. Say you'll do it." in (village.script.prompts[-1])
    )


CHAT = "Ana: Morning, Ben! [values: connection]\nBen: Bye then. [values: connection]\n"


class Scenes:
    """Ana and Ben at the café, each with what they hold, and a scene engine."""

    def __init__(
        self,
        ana: Npc,
        relationships: Sequence[Relationship] = (),
        money: dict[str, float] | None = None,
    ) -> None:
        self.world = World(Clock(START), FakeWallClock())
        ben = make_npc("ben", "house_2")
        store = MemoryStore(":memory:")
        store.add(*relationships)
        movement = Movement(load_maps(), self.world.bus)
        for npc in (ana, ben):
            movement.place(npc.id, MapTile(map="coffee_shop", x=13, y=8))
        behaviour = Behaviour(self.world.clock, self.world.bus, movement, [ana, ben], store)
        behaviour.start()
        if money is not None:
            behaviour.hooks.set(money=lambda npc: money[npc.id])
        self.provider = FakeProvider(itertools.repeat(CHAT, 10))
        llm = LLMClient(self.provider)
        self.engine = ConversationEngine(
            self.world.clock, self.world.bus, behaviour, store, lambda: llm, config=ALWAYS
        )
        self.world.loop.register(movement)
        self.world.loop.register(self.engine)

    async def scene(self) -> tuple[str, list[Lie]]:
        """The prompt of a scene Ana starts with Ben, and the lies B3 gets for it."""
        conversation = self.engine.start("ana", "ben")
        await self.world.loop.run(timedelta(minutes=1))
        return self.provider.requests[-1].messages[-1].content, self.engine.lies(conversation.id)


def test_the_engines_roll_is_seeded_by_the_conversation() -> None:
    engine = Scenes(make_npc("ana", "house_1", honesty=0.35)).engine
    short = Temptation(Kind.SHORT, "ana", "short", "", "", "")
    odds = chance(0.35, config=ALWAYS)

    rolls = [engine.lies_about(short, f"talk_{n}") for n in range(40)]

    assert set(rolls) == {True, False}
    assert rolls == [lies(short, f"talk_{n}", odds) for n in range(40)]


def bens_secret() -> Relationship:
    """Ben once saw Ana do something she wants kept quiet."""
    flag = Flag(
        id="hook/secret",
        kind=FlagKind.SECRET,
        owner="ben",
        about="ana",
        description="something best kept quiet",
        created=START - timedelta(days=30),
    )
    return open_flag(meet(make_npc("ben", "house_2"), "ana"), flag)


async def test_a_scene_with_someone_who_knows_the_secret_directs_the_lie_in_the_plan() -> None:
    prompt, [told] = await Scenes(liar(), [bens_secret()]).scene()

    direction = prompt.split("## Direction\n", 1)[1].splitlines()
    assert (
        "- Ana has a secret to keep: something best kept quiet. If anyone gets near it, Ana says "
        "there's nothing to tell. Ana uses that cover story and nothing else: no days, times, "
        "places or other people."
    ) in direction
    assert (told.liar, told.listener, told.known) == ("ana", "ben", True)


async def test_no_lie_roll_leaves_the_plan_as_it_was() -> None:
    prompt, told = await Scenes(honest(), [bens_secret()]).scene()

    assert "secret to keep" not in prompt
    assert told == []


async def test_what_the_other_doesnt_bring_up_isnt_touched() -> None:
    prompt, told = await Scenes(liar(), money={"ana": 10.0, "ben": 10.0}).scene()

    assert "short of money" not in prompt.split("## Direction\n", 1)[1]
    assert told == []


async def test_nobody_hides_being_short_while_asking_for_a_loan() -> None:
    friends = [
        meet(liar(), "ben").model_copy(update={"like": 0.9}),
        meet(make_npc("ben", "house_2"), "ana").model_copy(update={"like": 0.9, "trust": 0.9}),
    ]
    debt = Flag(
        id="hook/debt",
        kind=FlagKind.DEBT,
        owner="ben",
        about="ana",
        description="an old loan",
        created=START - timedelta(days=30),
    )
    friends[1] = open_flag(friends[1], debt)

    prompt, told = await Scenes(liar(), friends, {"ana": 10.0, "ben": 900.0}).scene()

    assert "Ana is short of money and asks Ben" in prompt
    assert "doing fine" not in prompt and "owe anyone" not in prompt
    assert told == []
