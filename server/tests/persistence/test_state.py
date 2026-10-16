import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from simile.behaviour import Behaviour, GoalChosen, Need
from simile.npc import load_npcs
from simile.persistence import SavedWorld, Saver, WorldStore, capture, restore
from simile.sim import STEP, Clock, FakeWallClock, World
from simile.world import Movement
from simile.world.map import load_map

TOWN = load_map()
NPCS = load_npcs()
MORNING = datetime(2026, 1, 1, 8, tzinfo=UTC)


class Village:
    def __init__(self, start: datetime = MORNING, seed: int = 0) -> None:
        self.world = World(Clock(start), FakeWallClock())
        self.movement = Movement(TOWN, self.world.bus)
        self.behaviour = Behaviour(self.world.clock, self.world.bus, self.movement, NPCS, seed=seed)
        self.goals: list[GoalChosen] = []
        self.world.bus.subscribe(GoalChosen, self.goals.append)
        self.world.loop.register(self.behaviour)
        self.world.loop.register(self.movement)
        self.behaviour.start()

    def run(self, duration: timedelta) -> None:
        asyncio.run(self.world.loop.run(duration))

    def run_until_someone_walks(self, duration: timedelta) -> None:
        self.run(duration)
        while all(mind.walk is None for mind in self.behaviour.minds.values()):
            self.world.loop.tick()

    def think(self) -> None:
        for _ in range(round(self.behaviour.config.think_every / STEP)):
            self.world.loop.tick()


def resumed(saved: SavedWorld) -> SavedWorld:
    """`saved` as it comes back: anyone walking or talking decides again straight away."""
    npcs = {
        npc: state.model_copy(update={"until": state.until or saved.now})
        for npc, state in saved.npcs.items()
    }
    return saved.model_copy(update={"npcs": npcs})


def test_a_village_comes_back_as_it_was_saved(tmp_path: Path) -> None:
    before = Village()
    before.run_until_someone_walks(timedelta(hours=3))
    saved = capture(before.behaviour)
    with WorldStore(tmp_path / "simile.db") as store:
        store.save(saved)
        loaded = store.load()
    assert loaded == saved

    after = Village(start=MORNING + timedelta(days=3), seed=1)
    restore(loaded, after.behaviour)

    assert after.world.clock.now == saved.now
    assert capture(after.behaviour) == resumed(saved)
    assert any(state.until is None for state in saved.npcs.values())
    assert any(state.cooldowns for state in saved.npcs.values())
    assert after.goals[-len(NPCS) :] == [
        GoalChosen(npc, state.activity, state.target) for npc, state in saved.npcs.items()
    ]


def test_nobody_moves_until_they_decide_again() -> None:
    before = Village()
    before.run_until_someone_walks(timedelta(hours=2))
    saved = capture(before.behaviour)

    after = Village(seed=1)
    restore(saved, after.behaviour)
    after.world.loop.tick()

    assert all(mind.walk is None for mind in after.behaviour.minds.values())
    assert capture(after.behaviour).npcs.keys() == saved.npcs.keys()
    assert {npc: state.position for npc, state in capture(after.behaviour).npcs.items()} == {
        npc: state.position for npc, state in saved.npcs.items()
    }


def test_needs_rise_from_the_restored_time_not_the_first_start() -> None:
    before = Village()
    before.run(timedelta(hours=1))
    saved = capture(before.behaviour).model_copy(update={"now": MORNING + timedelta(days=2)})

    after = Village()
    restore(saved, after.behaviour)
    after.think()

    for npc, state in saved.npcs.items():
        needs = after.behaviour.needs(npc)
        assert all(abs(needs[need] - state.needs[need]) < 0.01 for need in Need), npc


def test_walkers_and_talkers_decide_again_on_the_first_think() -> None:
    before = Village()
    before.run_until_someone_walks(timedelta(hours=1))
    saved = capture(before.behaviour)
    walking = {npc for npc, state in saved.npcs.items() if state.until is None}
    assert walking

    after = Village(seed=1)
    restore(saved, after.behaviour)
    after.goals.clear()
    after.think()

    assert walking <= {goal.npc for goal in after.goals}


def test_npcs_missing_from_the_save_start_afresh_and_strangers_are_ignored() -> None:
    before = Village()
    before.run(timedelta(hours=1))
    saved = capture(before.behaviour)
    kofi = saved.npcs.pop("kofi")
    saved.npcs["stranger"] = kofi

    after = Village(seed=1)
    home = after.movement.position("kofi")
    restore(saved, after.behaviour)

    assert "stranger" not in after.movement.entities()
    assert after.movement.position("kofi") == home
    assert after.behaviour.minds["kofi"].until is not None


def test_cooldowns_that_have_run_out_are_not_saved() -> None:
    village = Village()
    mind = village.behaviour.minds["kofi"]
    mind.cooldowns = {
        "henrietta": MORNING + timedelta(minutes=1),
        "tobias": MORNING - timedelta(minutes=1),
    }

    assert capture(village.behaviour).npcs["kofi"].cooldowns == {
        "henrietta": MORNING + timedelta(minutes=1)
    }


@pytest.mark.anyio
async def test_saves_every_so_often_until_stopped(tmp_path: Path) -> None:
    village = Village()
    with WorldStore(tmp_path / "simile.db") as store:
        saver = Saver(store, village.behaviour)
        autosave = asyncio.create_task(saver.autosave(0.01))
        await asyncio.sleep(0.05)
        assert store.load() == capture(village.behaviour)

        village.world.loop.tick()
        await asyncio.sleep(0.05)
        saver.stop()
        await autosave
        assert store.load() == capture(village.behaviour)

        village.world.loop.tick()
        await asyncio.sleep(0.05)
        assert store.load() != capture(village.behaviour)
