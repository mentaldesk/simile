import asyncio
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from simile.behaviour import Behaviour
from simile.economy import OUTSIDE, Kind
from simile.economy.economy import Economy
from simile.memory import MemoryStore
from simile.npc import load_npcs
from simile.persistence import SavedWorld, Saver, WorldStore, capture, restore
from simile.sim import Clock, FakeWallClock, World
from simile.world import Movement
from simile.world.map import load_maps

MAPS = load_maps()
NPCS = load_npcs()
MORNING = datetime(2026, 1, 1, 8, tzinfo=UTC)


class Village:
    def __init__(self, start: datetime = MORNING) -> None:
        self.world = World(Clock(start), FakeWallClock())
        self.movement = Movement(MAPS, self.world.bus)
        self.behaviour = Behaviour(self.world.clock, self.world.bus, self.movement, NPCS, seed=0)
        self.economy = Economy(self.world.clock, self.behaviour)
        for system in (self.behaviour, self.movement, self.economy):
            self.world.loop.register(system)
        self.behaviour.start()

    def run(self, duration: timedelta) -> None:
        asyncio.run(self.world.loop.run(duration))


def test_money_and_the_day_settled_come_back_as_they_were_saved() -> None:
    before = Village(MORNING + timedelta(hours=14))
    before.run(timedelta(hours=11))
    saved = capture(before.behaviour, before.economy)
    assert saved.economy is not None
    assert saved.economy.settled == date(2026, 1, 2)
    assert saved.economy.money != {npc.id: npc.money for npc in NPCS}

    after = Village(MORNING + timedelta(days=3))
    restore(SavedWorld.model_validate_json(saved.model_dump_json()), after.behaviour, after.economy)

    assert after.economy.money == saved.economy.money
    assert after.economy.settled == saved.economy.settled
    assert after.economy.ledger.opening == saved.economy.money
    assert after.economy.ledger.entries == []


def test_a_save_from_before_money_starts_everyone_with_their_own() -> None:
    before = Village()
    old = capture(before.behaviour).model_dump(mode="json")
    del old["economy"]
    saved = SavedWorld.model_validate(old)

    after = Village(MORNING + timedelta(days=5))
    after.economy.pay("kofi", OUTSIDE, 50, Kind.RENT)
    restore(saved, after.behaviour, after.economy)

    assert after.economy.money == {npc.id: npc.money for npc in NPCS}
    assert after.economy.settled == MORNING.date()
    assert after.economy.ledger.entries == []
    after.run(timedelta(hours=16.1))
    rent = [e for e in after.economy.ledger.entries if e.kind is Kind.RENT]
    assert len(rent) == len(NPCS)


def test_the_ledger_is_saved_as_it_grows_and_cleared_with_the_village(tmp_path: Path) -> None:
    village = Village(MORNING + timedelta(hours=14))
    with MemoryStore(tmp_path / "simile.db") as memory, WorldStore(memory) as store:
        saver = Saver(store, village.behaviour, economy=village.economy)
        village.run(timedelta(hours=11))
        asyncio.run(saver.save())
        first = len(village.economy.ledger.entries)
        village.run(timedelta(hours=2))
        asyncio.run(saver.save())

        saved = store.ledger()
        assert first > 0
        assert saved == village.economy.ledger.entries
        loaded = store.load()
        assert loaded is not None and loaded.economy is not None
        assert loaded.economy.money == pytest.approx(village.economy.money)

        store.clear()
        assert store.ledger() == [] and store.load() is None
