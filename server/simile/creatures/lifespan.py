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
