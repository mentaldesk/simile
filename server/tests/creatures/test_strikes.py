from datetime import UTC, datetime

import pytest

from simile.creatures.engine import Creatures, Sight
from simile.creatures.kind import Kind
from simile.creatures.kinds import RAT
from simile.player.corpses import Death
from simile.player.health import DEFAULT_HEALTH, Health
from simile.schema import PLAYER_ID, Item, ItemKind, MapTile, Player, lamp
from simile.sim import Clock, EventBus
from simile.world import Movement, Point
from simile.world.map import load_maps
from simile.world.paths import Spot

MAPS = load_maps()
TUNNEL = Point(65, 15, "metro")
BED = Spot("maker_space_floor_2", 5, 2)
RATION = Item(id="ration_pack", kind=ItemKind.FOOD, name="Ration pack", weight=0.5)


@pytest.mark.parametrize("rats", [2, 5])
def test_rats_striking_in_the_tick_of_a_death_leave_the_new_body_alone(rats: int) -> None:
    player = Player(health=0.1, items=[lamp(), RATION])
    movement = Movement(MAPS, EventBus())
    movement.track(PLAYER_ID, TUNNEL)
    clock = Clock(datetime(2026, 1, 1, tzinfo=UTC))
    death = Death(player, movement, clock, bed=lambda: BED)
    health = Health(player, movement, clock, die=death.die, beds=[BED])

    def harm(kind: Kind) -> None:
        health.bite(kind.damage)

    creatures = Creatures(
        {TUNNEL.map: MAPS[TUNNEL.map]},
        sense=lambda: Sight(player, movement.entities().get(PLAYER_ID)),
        harm=harm,
    )
    at = MapTile(map=TUNNEL.map, x=65, y=15)
    biting = [creatures.spawn(RAT, at, route=()) for _ in range(rats)]
    for _ in range(100):
        creatures.tick(0.1)

    assert len({rat.rested for rat in biting}) == 1, "they must strike in the same tick"
    assert biting[0].rested > 0
    assert len(player.corpses) == 1
    assert player.health == DEFAULT_HEALTH.waking
    assert player.effects == []
