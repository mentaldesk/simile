import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from simile.behaviour import Behaviour, Need
from simile.conversation import ConversationEngine
from simile.debug import Village
from simile.llm import FakeProvider, LLMClient, Request
from simile.memory import MemoryStore
from simile.npc import load_npcs
from simile.sim import Clock, ConversationEnded, FakeWallClock, LineSpoken, World
from simile.tools import Recorder, RecordStore, load_run, report
from simile.world import Movement
from simile.world.map import load_maps

pytestmark = pytest.mark.anyio

START = datetime(2026, 1, 1, 10, tzinfo=UTC)
WALKED_UP = re.compile(r"(\w+) has just walked up to (\w+)\.")


def scene(request: Request) -> str:
    """Six lines about the allotments and the goodbyes, between whoever the prompt names."""
    found = WALKED_UP.search(request.messages[-1].content)
    assert found is not None
    a, b = found.groups()
    lines = [f"{name}: Line {n} about the allotments." for n, name in enumerate([a, b] * 3, 1)]
    lines += [f"{a}: Right, I'll let you get on.", f"{b}: Bye then."]
    return "".join(f"{line} [values: connection]\n" for line in lines)


class Town:
    """The real residents at the coffee shop, talking in scripted scenes."""

    def __init__(self, db: Path | str = ":memory:") -> None:
        self.world = World(Clock(START), FakeWallClock())
        self.memory = MemoryStore(db)
        movement = Movement(load_maps(), self.world.bus)
        npcs = load_npcs()
        for npc in npcs:
            movement.place(npc.id, "coffee_shop")
        self.behaviour = Behaviour(
            self.world.clock, self.world.bus, movement, npcs, self.memory, seed=0
        )
        self.behaviour.start()
        self.llm = LLMClient(FakeProvider(default=scene))
        self.engine = ConversationEngine(
            self.world.clock, self.world.bus, self.behaviour, self.memory, lambda: self.llm
        )
        self.world.loop.register(movement)
        self.world.loop.register(self.engine)
        self.spoken: list[LineSpoken] = []
        self.ended: list[ConversationEnded] = []
        self.world.bus.subscribe(LineSpoken, self.spoken.append)
        self.world.bus.subscribe(ConversationEnded, self.ended.append)

    async def run_until(self, done: Callable[[], bool]) -> None:
        stop = self.world.clock.now + timedelta(minutes=5)
        while not done():
            assert self.world.clock.now < stop, "timed out"
            await self.world.loop.run(timedelta(seconds=0.1))


async def test_d1_records_and_reports_scripted_conversations(tmp_path: Path) -> None:
    db = tmp_path / "simile.db"
    town = Town(db)
    store = RecordStore(db)
    recorder = Recorder(store, town.world, town.behaviour, town.memory, town.llm)
    recorder.start()
    town.engine.start("tobias", "desmond")
    town.engine.start("kofi", "henrietta")
    await town.run_until(
        lambda: len([e for e in town.spoken if "kofi" in e.line.conversation_id]) == 3
    )
    town.behaviour.minds["kofi"].needs[Need.REST] = 0.99

    await town.run_until(lambda: len(town.ended) == 2)
    recorder.finish()
    store.close()

    run = load_run(db)
    lengths = {c.participants[0]: len(c.lines) for c in run.conversations}
    assert lengths == {"tobias": 8, "kofi": 4}
    assert [call.purpose for call in run.calls] == ["conversation", "conversation"]
    summary = report(run)
    assert "2 conversations, 12 lines, between 2 pairs" in summary
    assert "Lines per conversation: 4 to 8" in summary
    assert "| conversation | " in summary


async def test_the_overlay_shows_a_scripted_conversation_as_it_plays() -> None:
    town = Town()
    village = Village(town.behaviour, town.engine, town.memory)
    started = town.engine.start("tobias", "desmond")
    await town.run_until(lambda: len(town.spoken) == 2)

    talk = village.npc_state("desmond")["conversation"]  # type: ignore[index]

    assert talk["id"] == started.id
    assert talk["talking_to"] == "tobias"
    assert 0 < talk["engagement"] <= 1
    assert talk["leaving"] is False
    assert [line["text"] for line in talk["lines"]] == [
        "Line 1 about the allotments.",
        "Line 2 about the allotments.",
    ]

    town.engine.cut("desmond", Need.REST)
    assert village.npc_state("desmond")["conversation"]["leaving"] is True  # type: ignore[index]
    assert village.npc_state("tobias")["conversation"]["leaving"] is False  # type: ignore[index]
    await town.run_until(lambda: bool(town.ended))

    assert village.npc_state("desmond")["conversation"] is None  # type: ignore[index]
