from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast

from simile.combat.shooting import Shooting
from simile.creatures.engine import Creatures
from simile.machines.materials import plastic
from simile.machines.printer import PISTOL, ROUNDS
from simile.machines.workshop import Workshop, register_offers
from simile.schema import PLAYER_ID, Player, SideFacing
from simile.sim import Clock, FakeWallClock, World
from simile.world import Movement, Point
from simile.world.map import load_maps

MAPS = load_maps()
AT_THE_PRINTER = Point(9, 2, "maker_space_floor_0")


def test_what_the_spool_prints_loads_fires_and_wears_out() -> None:
    world = World(Clock(datetime(2026, 1, 1, 12, tzinfo=UTC)), FakeWallClock())
    movement = Movement(MAPS, world.bus)
    movement.track(PLAYER_ID, AT_THE_PRINTER)
    player = Player(items=[plastic(8.0)], repaired=["printer_3d"])
    shop = Workshop(player, movement)
    register_offers(shop)
    assert shop.make("printer_3d", PISTOL.id) and shop.make("printer_3d", ROUNDS.id)
    nobody = cast(Creatures, SimpleNamespace(maps={}, all={}))
    shooting = Shooting(player, movement, nobody)

    assert not shooting.fire(SideFacing.EAST)
    assert shooting.reload()
    assert [item.id for item in player.items] == [PISTOL.id]
    assert player.items[0].rounds == 6

    fired = 0
    while shooting.fire(SideFacing.EAST):
        fired += 1
        if not player.items[0].rounds and player.items[0].condition:
            player.items = [player.items[0].model_copy(update={"rounds": 6})]
    assert fired == 30
    assert player.items[0].condition == 0
