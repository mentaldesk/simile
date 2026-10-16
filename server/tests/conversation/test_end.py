import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from simile.behaviour import Behaviour
from simile.conversation import DEFAULT_CONFIG, ConversationEngine
from simile.llm import CallRecord, FakeProvider, LLMClient
from simile.memory import MemoryStore
from simile.npc import load_npcs
from simile.sim import Clock, ConversationEnded, FakeWallClock, World
from simile.world import Movement
from simile.world.map import load_map

pytestmark = pytest.mark.anyio

START = datetime(2026, 1, 1, 10, tzinfo=UTC)
KOFI, HENRIETTA = "kofi", "henrietta"


class Village:
    """Kofi and Henrietta at the coffee shop, with a conversation engine."""

    def __init__(self, provider: FakeProvider) -> None:
        self.world = World(Clock(START), FakeWallClock())
        self.movement = Movement(load_map(), self.world.bus)
        npcs = [npc for npc in load_npcs() if npc.id in (KOFI, HENRIETTA)]
        for npc in npcs:
            self.movement.place(npc.id, "coffee_shop")
        self.behaviour = Behaviour(
            self.world.clock, self.world.bus, self.movement, npcs, MemoryStore(":memory:")
        )
        self.behaviour.start()
        self.records: list[CallRecord] = []
        llm = LLMClient(provider, listeners=[self.records.append])
        self.engine = ConversationEngine(
            self.world.clock, self.world.bus, self.behaviour, MemoryStore(":memory:"), lambda: llm
        )
        self.ended: list[ConversationEnded] = []
        self.world.bus.subscribe(ConversationEnded, self.ended.append)
        self.world.loop.register(self.movement)
        self.world.loop.register(self.engine)

    async def run(self, seconds: float) -> None:
        await self.world.loop.run(timedelta(seconds=seconds))


async def test_ending_a_conversation_now_ends_it_as_if_it_had_run_its_course() -> None:
    hang = asyncio.Event()
    village = Village(FakeProvider(["Morning! [values: connection]", ["Well", hang]]))
    started = village.engine.start(KOFI, HENRIETTA)
    await village.run(seconds=1)
    assert [record.error for record in village.records] == [None]

    ended = village.engine.end(started.id)

    now = START + timedelta(seconds=1)
    assert ended is not None
    assert ended.ended == now
    assert [line.text for line in ended.lines] == ["Morning!"]
    assert [event.conversation for event in village.ended] == [ended]
    assert village.engine.live() == []
    assert not village.engine.talking(KOFI) and not village.engine.talking(HENRIETTA)
    assert list(village.engine.finished) == [ended]
    cooldown = now + timedelta(minutes=DEFAULT_CONFIG.cooldown)
    for npc, other in ((KOFI, HENRIETTA), (HENRIETTA, KOFI)):
        mind = village.behaviour.minds[npc]
        assert not mind.paused
        assert mind.cooldowns == {other: cooldown}
    await asyncio.sleep(0)
    assert [record.error for record in village.records] == [None, "cancelled"]


async def test_ending_a_conversation_that_is_not_live_does_nothing() -> None:
    village = Village(FakeProvider(default="Morning! [values: connection]"))
    started = village.engine.start(KOFI, HENRIETTA)
    first = village.engine.end(started.id)

    assert village.engine.end(started.id) is None
    assert village.engine.end("nope") is None
    assert [event.conversation for event in village.ended] == [first]
