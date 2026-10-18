import asyncio
import logging
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from simile.behaviour import Behaviour, GoalChosen, Need
from simile.economy import Entry
from simile.memory import MemoryStore
from simile.npc import load_npcs
from simile.persistence import (
    PersistenceConfig,
    SavedWorld,
    Saver,
    WorldStore,
    capture,
    restore,
)
from simile.reflection import Reflector
from simile.schema import PLAYER_ID, VILLAGE_MAP, Intention, IntentionKind, MapTile
from simile.sim import STEP, Clock, FakeWallClock, World
from simile.world import Movement, Point
from simile.world.map import load_maps

MAPS = load_maps()
NPCS = load_npcs()
MORNING = datetime(2026, 1, 1, 8, tzinfo=UTC)


class Village:
    def __init__(self, start: datetime = MORNING, seed: int = 0) -> None:
        self.world = World(Clock(start), FakeWallClock())
        self.movement = Movement(MAPS, self.world.bus)
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
    with MemoryStore(tmp_path / "simile.db") as memory, WorldStore(memory) as store:
        store.save(saved)
        loaded = store.load()
    assert loaded == saved

    after = Village(start=MORNING + timedelta(days=3), seed=1)
    after.goals.clear()
    restore(loaded, after.behaviour)

    assert after.world.clock.now == saved.now
    assert capture(after.behaviour) == resumed(saved)
    assert any(state.until is None for state in saved.npcs.values())
    assert any(state.cooldowns for state in saved.npcs.values())
    assert after.goals == [
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


def test_a_resident_inside_saves_and_reloads_inside() -> None:
    before = Village()
    before.movement.place("kofi", MapTile(map="coffee_shop", x=13, y=9))
    saved = capture(before.behaviour)
    assert (saved.npcs["kofi"].map, saved.npcs["henrietta"].map) == ("coffee_shop", VILLAGE_MAP)

    after = Village(seed=1)
    restore(saved, after.behaviour)

    assert after.movement.position("kofi") == Point(13, 9, "coffee_shop")


def test_residents_saved_where_someone_starts_get_their_tiles_back() -> None:
    before = Village()
    barista = next(npc.id for npc in NPCS if npc.home == "coffee_shop")
    saved_at = {
        barista: MapTile(map="coffee_shop", x=13, y=9),
        "ingrid": MapTile(map="coffee_shop", x=5, y=6),
        "kofi": MapTile(map="coffee_shop", x=7, y=6),
        "lachlan": MapTile(map="coffee_shop", x=6, y=7),
        "raymond": MapTile(map="coffee_shop", x=6, y=6),
    }
    for npc, tile in saved_at.items():
        before.movement.place(npc, tile)
    saved = capture(before.behaviour)

    after = Village(seed=1)
    assert after.movement.position(barista) == Point(5, 6, "coffee_shop")
    restore(saved, after.behaviour)

    for npc, tile in saved_at.items():
        assert after.movement.position(npc) == Point(tile.x, tile.y, tile.map), npc


def test_a_save_from_before_interiors_loads_onto_the_village() -> None:
    saved = capture(Village().behaviour).model_dump(mode="json")
    for state in saved["npcs"].values():
        del state["map"]

    old = SavedWorld.model_validate(saved)

    assert {state.map for state in old.npcs.values()} == {VILLAGE_MAP}


def intention(owner: str, target: str, hours: float) -> Intention:
    return Intention(
        id=f"talk/{owner}/1",
        owner=owner,
        kind=IntentionKind.GO,
        target=target,
        description=f"go to the {target}",
        promised_to=[PLAYER_ID],
        created=MORNING,
        due=MORNING + timedelta(hours=hours),
        expires=MORNING + timedelta(hours=hours + 24),
        conversation_id="talk",
    )


def test_what_they_said_theyd_do_is_saved_with_the_world(tmp_path: Path) -> None:
    before = Village()
    said = [intention("kofi", "park", 2), intention("tobias", "gallery", 1)]
    assert all(before.behaviour.intend(one) for one in said)
    with MemoryStore(tmp_path / "simile.db") as memory, WorldStore(memory) as store:
        store.save(capture(before.behaviour))
        loaded = store.load()
    assert loaded is not None and loaded.intentions == sorted(said, key=lambda i: i.due)

    after = Village(start=MORNING + timedelta(days=3), seed=1)
    restore(loaded, after.behaviour)

    assert after.behaviour.intentions() == loaded.intentions


def test_a_save_from_before_intentions_has_none() -> None:
    saved = capture(Village().behaviour).model_dump(mode="json")
    del saved["intentions"]

    assert SavedWorld.model_validate(saved).intentions == []


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


class Recorder(WorldStore):
    """Keeps every world saved in a list."""

    def __init__(self) -> None:
        super().__init__(MemoryStore(":memory:"))
        self.saved: list[SavedWorld] = []

    def save(self, world: SavedWorld, entries: Sequence[Entry] = ()) -> None:
        self.saved.append(world)


async def until(condition: Callable[[], bool]) -> None:
    async with asyncio.timeout(5):
        while not condition():
            await asyncio.sleep(0)


@pytest.mark.anyio
async def test_saves_every_so_often_until_stopped() -> None:
    village, store = Village(), Recorder()
    saver = Saver(store, village.behaviour, PersistenceConfig(save_every=1e-6))
    autosave = asyncio.create_task(saver.autosave())

    await until(lambda: len(store.saved) > 0)
    assert store.saved[-1] == capture(village.behaviour)
    village.world.loop.tick()
    await until(lambda: store.saved[-1].now == village.world.clock.now)
    assert store.saved[-1] == capture(village.behaviour)

    saver.stop()
    await asyncio.wait_for(autosave, 5)


@pytest.mark.anyio
async def test_shutdown_saves_without_reflections_that_take_too_long(
    caplog: pytest.LogCaptureFixture,
) -> None:
    village, store = Village(), Recorder()
    saver = Saver(store, village.behaviour, PersistenceConfig(reflection_wait=0))
    reflector = Reflector(MemoryStore(":memory:"), dict, lambda: None)
    stuck = asyncio.create_task(asyncio.Event().wait())
    reflector.tasks.add(stuck)

    with caplog.at_level(logging.WARNING):
        await saver.shut_down(None, reflector)

    assert store.saved == [capture(village.behaviour)]
    assert "Gave up on 1 reflections" in caplog.text
    stuck.cancel()
