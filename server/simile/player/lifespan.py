from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from starlette.applications import Starlette


@asynccontextmanager
async def running(app: Starlette) -> AsyncIterator[None]:
    from simile.behaviour import behaviour_of
    from simile.economy.economy import economy_of
    from simile.persistence import investigation_of, player_of
    from simile.player.clients import InGame
    from simile.player.finds import Finds
    from simile.player.health import Health
    from simile.player.hunger import Hunger
    from simile.player.lamp import Lamp
    from simile.player.machines import Machines
    from simile.player.pickups import Pickups, claimers_of
    from simile.player.power import Power
    from simile.player.sync import PlayerSync, recipes_of
    from simile.player.trade import Trade, keepers_of
    from simile.protocol import (
        BuyMessage,
        EatMessage,
        JournalMessage,
        LampMessage,
        PickUpMessage,
        PlayerCollapsedMessage,
        PlayerMoveMessage,
        Position,
        RestMessage,
        SellMessage,
        Vital,
        hub_of,
    )
    from simile.schema import Interactable, MapTile
    from simile.sim import world_of
    from simile.story import Journal
    from simile.world import movement_of

    world, hub, behaviour = world_of(app), hub_of(app), behaviour_of(app)
    player, movement, economy = player_of(app), movement_of(app), economy_of(app)
    economy.player = player
    in_game = InGame()

    def collapsed(home: MapTile, cause: Vital) -> None:
        lamp.switch(False)
        position = Position(x=home.x, y=home.y, map=home.map)
        hub.broadcast(PlayerCollapsedMessage(position=position, cause=cause))

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
    trade = Trade(player, movement, economy, world.clock, keepers_of(app))
    health = app.state.health = Health(
        player,
        movement,
        world.clock,
        playing=lambda: bool(in_game),
        collapse=lambda: hunger.collapse(Vital.HEALTH),
    )

    def bed() -> MapTile | None:
        spot = health.bed()
        return None if spot is None else MapTile(map=spot.map, x=spot.x, y=spot.y)

    book = recipes_of(app)
    sync = PlayerSync(
        player,
        hunger.meal,
        hub.broadcast,
        shut=hunger.shut,
        buyer=trade.buyer,
        piles=pickups.piles,
        recipes=lambda: [book[bionic] for bionic in player.mind.recipes],
        bed=bed,
        resting=health.resting,
    )
    lamp = Lamp(player, movement, world.clock, playing=lambda: bool(in_game))
    power = Power(
        player,
        world.clock,
        charging=lamp.charging,
        playing=lambda: bool(in_game),
        collapse=lambda: hunger.collapse(Vital.POWER),
    )
    investigation = investigation_of(app)
    journal = Journal(investigation, lambda: world.clock.now, lambda: player)

    def found(jack: Interactable) -> None:
        if journal.found(jack.id, jack.label):
            hub.broadcast(JournalMessage(entries=investigation.journal))

    def clues() -> set[str]:
        story = investigation.disappearance
        return {fact.found_in for fact in story.facts if fact.found_in} if story else set()

    machines = Machines(player, movement, found, clues)
    finds = Finds(player, movement, known=lambda: book, find=economy.find)
    claimers_of(app).extend((machines.claim, finds.claim))

    def on_lamp(message: LampMessage) -> None:
        if lamp.switch(message.on):
            sync.update()

    def on_eat(message: EatMessage) -> None:
        if hunger.eat(message.item):
            sync.update()

    def on_pick_up(message: PickUpMessage) -> None:
        pickups.pick_up(claimers_of(app))
        sync.update()

    def on_sell(message: SellMessage) -> None:
        if trade.sell(message.item):
            sync.update()

    def on_rest(message: RestMessage) -> None:
        if health.rest(message.on):
            sync.update()

    def on_buy(message: BuyMessage) -> None:
        if trade.buy(message.item):
            sync.update()

    stops = [
        world.loop.register(hunger),
        world.loop.register(lamp),
        world.loop.register(power),
        world.loop.register(health),
        world.loop.register(finds),
        world.loop.register(sync),
        hub.subscribe(PlayerMoveMessage, in_game.moved),
        hub.subscribe(EatMessage, on_eat),
        hub.subscribe(PickUpMessage, on_pick_up),
        hub.subscribe(SellMessage, on_sell),
        hub.subscribe(BuyMessage, on_buy),
        hub.subscribe(LampMessage, on_lamp),
        hub.subscribe(RestMessage, on_rest),
        hub.greet(sync.message),
    ]
    yield
    for stop in reversed(stops):
        stop()
    claimers_of(app).remove(finds.claim)
    claimers_of(app).remove(machines.claim)
    del app.state.health
    economy.player = None
