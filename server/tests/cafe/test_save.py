from datetime import timedelta
from pathlib import Path

import pytest

from simile.behaviour import Activity, Goal
from simile.cafe.events import Ordered
from simile.memory import MemoryStore
from simile.npc import load_npcs
from simile.persistence import WorldStore, capture, restore
from simile.schema import MapTile
from simile.world import Point

from .conftest import DAY, Village

TILL = Point(5, 4, "coffee_shop")
COFFEE = Goal(Activity.COFFEE_SHOP, "coffee_shop")

pytestmark = pytest.mark.anyio

NPCS = load_npcs()
BARISTA = next(npc for npc in NPCS if npc.home == "coffee_shop")
BEFORE = [npc for npc in NPCS if npc is not BARISTA]


async def test_a_save_from_before_the_barista_loads_with_them_at_the_cafe(tmp_path: Path) -> None:
    before = Village(BEFORE, start=DAY.replace(hour=9))
    await before.run(minutes=20)
    with MemoryStore(tmp_path / "simile.db") as memory, WorldStore(memory) as store:
        store.save(capture(before.behaviour))
        saved = store.load()
    assert saved is not None and BARISTA.id not in saved.npcs

    after = Village(NPCS, start=DAY.replace(hour=7, minute=30))
    restore(saved, after.behaviour)
    await after.run(seconds=1)

    assert after.now >= saved.now
    for npc, state in saved.npcs.items():
        assert after.behaviour.goal(npc) == Goal(state.activity, state.target)
    assert after.at(BARISTA.id).map == "coffee_shop"
    await after.run(minutes=1)
    assert after.cafe.on_shift
    assert after.behaviour.goal(BARISTA.id) == COFFEE
    await after.run_until(lambda: after.at(BARISTA.id) == TILL, minutes=2)
    assert after.now - saved.now < timedelta(minutes=5)


async def test_someone_restored_mid_stay_in_the_cafe_sits_rather_than_queuing_again() -> None:
    npc = BEFORE[0].id
    village = Village((BARISTA, BEFORE[0]), start=DAY.replace(hour=9))
    village.movement.place(npc, MapTile(map="coffee_shop", x=13, y=9))
    now, needs = village.now, village.behaviour.needs(npc)
    since, until = now - timedelta(minutes=20), now + timedelta(minutes=10)
    village.behaviour.restore(npc, COFFEE, needs, since, until, {})

    await village.run(minutes=2)

    assert village.cafe.queue == [] and village.of(Ordered) == []
    assert village.behaviour.goal(npc) == COFFEE
    assert village.at(npc).map == "coffee_shop"
