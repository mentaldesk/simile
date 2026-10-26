from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from starlette.applications import Starlette


@asynccontextmanager
async def lifespan(app: Starlette) -> AsyncIterator[None]:
    from simile.creatures.engine import Sight, creatures_of
    from simile.creatures.kind import Kind
    from simile.persistence import player_of
    from simile.player.clients import InGame
    from simile.player.kick import kickables_of
    from simile.protocol import PlayerMoveMessage, hub_of
    from simile.schema import PLAYER_ID
    from simile.sim import world_of
    from simile.world import movement_of

    world, hub, movement = world_of(app), hub_of(app), movement_of(app)
    creatures = creatures_of(app)
    in_game = InGame()

    def sense() -> Sight:
        if not in_game:
            return Sight()
        return Sight(player_of(app), movement.entities().get(PLAYER_ID))

    def harm(kind: Kind) -> None:
        from simile.player.health import health_of

        try:
            health = health_of(app)
        except AttributeError:
            return
        if kind.bites:
            health.bite()
        else:
            health.hurt(kind.damage)

    creatures.clock, creatures.sense, creatures.harm = world.clock, sense, harm
    creatures.send = hub.broadcast
    snapshot = hub.snapshot
    hub.snapshot = lambda: snapshot().model_copy(update={"creatures": creatures.shown()})
    kickables_of(app).append(creatures.kickable)
    stops = [world.loop.register(creatures), hub.subscribe(PlayerMoveMessage, in_game.moved)]
    yield
    for stop in reversed(stops):
        stop()
    kickables_of(app).remove(creatures.kickable)
    hub.snapshot = snapshot


@asynccontextmanager
async def running(app: Starlette) -> AsyncIterator[None]:
    from simile.creatures.engine import creatures_of
    from simile.creatures.placing import populate, spawns
    from simile.economy.economy import economy_of
    from simile.persistence import player_of
    from simile.player.pickups import Pickups
    from simile.sim import world_of
    from simile.world import movement_of
    from simile.world.map import PickupKind, TownMap, world_level

    clock, player, movement = world_of(app).clock, player_of(app), movement_of(app)
    creatures = creatures_of(app)
    pickups = Pickups(player, movement, economy_of(app), clock)

    def salvage(town: TownMap) -> dict[tuple[int, int], str]:
        lying = {(pile.at.x, pile.at.y) for pile in pickups.piles() if pile.at.map == town.id}
        return {
            (pickup.x, pickup.y): pickup.id
            for pickup in town.pickups
            if pickup.kind is PickupKind.SALVAGE and (pickup.x, pickup.y) in lying
        }

    def collect(pickup: str) -> None:
        player.taken = {**player.taken, pickup: clock.now}

    kept = creatures.salvage, creatures.collect
    creatures.salvage, creatures.collect = salvage, collect
    placed = populate(creatures, spawns(level=world_level()))
    yield
    for creature in placed:
        creatures.remove(creature.id)
    creatures.salvage, creatures.collect = kept
