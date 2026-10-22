from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from starlette.applications import Starlette


@asynccontextmanager
async def running(app: Starlette) -> AsyncIterator[None]:
    from simile.behaviour import behaviour_of
    from simile.economy.economy import economy_of
    from simile.persistence import player_of
    from simile.player.clients import InGame
    from simile.player.hunger import Hunger
    from simile.player.pickups import Pickups, claimers_of
    from simile.player.sync import PlayerSync
    from simile.player.trade import Trade
    from simile.protocol import (
        EatMessage,
        PickUpMessage,
        PlayerCollapsedMessage,
        PlayerMoveMessage,
        Position,
        SellMessage,
        hub_of,
    )
    from simile.schema import MapTile
    from simile.sim import world_of
    from simile.world import movement_of

    world, hub, behaviour = world_of(app), hub_of(app), behaviour_of(app)
    player, movement, economy = player_of(app), movement_of(app), economy_of(app)
    economy.player = player
    in_game = InGame()

    def collapsed(home: MapTile) -> None:
        hub.broadcast(PlayerCollapsedMessage(position=Position(x=home.x, y=home.y, map=home.map)))

    hunger = Hunger(
        player,
        movement,
        world.clock,
        supply=lambda goal, need: behaviour.hooks.supply(goal, need),
        economy=economy,
        playing=lambda: bool(in_game),
        collapsed=collapsed,
    )
    pickups = Pickups(player, movement, economy, world.clock)
    trade = Trade(player, movement, economy, world.clock)
    sync = PlayerSync(player, hunger.meal, hub.broadcast, buyer=trade.buyer, piles=pickups.piles)

    def on_eat(message: EatMessage) -> None:
        if hunger.eat(message.item):
            sync.update()

    def on_pick_up(message: PickUpMessage) -> None:
        if pickups.pick_up(claimers_of(app)):
            sync.update()

    def on_sell(message: SellMessage) -> None:
        if trade.sell(message.item):
            sync.update()

    stops = [
        world.loop.register(hunger),
        world.loop.register(sync),
        hub.subscribe(PlayerMoveMessage, in_game.moved),
        hub.subscribe(EatMessage, on_eat),
        hub.subscribe(PickUpMessage, on_pick_up),
        hub.subscribe(SellMessage, on_sell),
        hub.greet(sync.message),
    ]
    yield
    for stop in reversed(stops):
        stop()
    economy.player = None
