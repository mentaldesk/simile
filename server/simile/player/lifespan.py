from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from starlette.applications import Starlette


@asynccontextmanager
async def running(app: Starlette) -> AsyncIterator[None]:
    from simile.behaviour import behaviour_of
    from simile.economy.economy import economy_of
    from simile.persistence import player_of
    from simile.player.hunger import Hunger
    from simile.player.sync import PlayerSync
    from simile.protocol import (
        EatMessage,
        PickUpMessage,
        PlayerCollapsedMessage,
        Position,
        hub_of,
    )
    from simile.schema import MapTile
    from simile.sim import world_of
    from simile.world import movement_of

    world, hub, behaviour = world_of(app), hub_of(app), behaviour_of(app)

    def collapsed(home: MapTile) -> None:
        hub.broadcast(PlayerCollapsedMessage(position=Position(x=home.x, y=home.y, map=home.map)))

    hunger = Hunger(
        player_of(app),
        movement_of(app),
        world.clock,
        supply=lambda goal, need: behaviour.hooks.supply(goal, need),
        economy=economy_of(app),
        playing=lambda: bool(hub.connections),
        collapsed=collapsed,
    )
    sync = PlayerSync(hunger.player, hunger.meal, hub.broadcast)

    def on_eat(message: EatMessage) -> None:
        if hunger.eat(message.item):
            sync.update()

    def on_pick_up(message: PickUpMessage) -> None:
        if hunger.pick_up():
            sync.update()

    stops = [
        world.loop.register(hunger),
        world.loop.register(sync),
        hub.subscribe(EatMessage, on_eat),
        hub.subscribe(PickUpMessage, on_pick_up),
        hub.greet(sync.message),
    ]
    yield
    for stop in reversed(stops):
        stop()
