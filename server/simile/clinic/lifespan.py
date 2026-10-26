from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from starlette.applications import Starlette


@asynccontextmanager
async def running(app: Starlette) -> AsyncIterator[None]:
    from simile.clinic.clinic import Clinic
    from simile.clinic.doctor import load_doctor
    from simile.clinic.standing import standing
    from simile.clinic.talk import DoctorTalk
    from simile.conversation import line_ids
    from simile.economy.economy import economy_of
    from simile.persistence import player_of
    from simile.player.sync import recipes_of
    from simile.player.trade import keepers_of
    from simile.protocol import (
        FitMessage,
        PlayerSayMessage,
        SellPartMessage,
        SellRecipeMessage,
        hub_of,
    )
    from simile.sim import world_of
    from simile.world import movement_of

    world, hub, economy, movement = world_of(app), hub_of(app), economy_of(app), movement_of(app)
    doctor = load_doctor()
    clinic = Clinic(player_of(app), movement, economy, world.clock)
    talk = DoctorTalk(
        doctor,
        clinic,
        world.clock,
        world.bus,
        llm=lambda: getattr(app.state, "llm", None),
        line_ids=line_ids(app),
        salvage=economy.config.salvage,
    )
    keepers = keepers_of(app)
    keepers[clinic.config.place] = clinic.keep
    recipes_of(app).update(clinic.config.recipes)
    snapshot = hub.snapshot
    hub.snapshot = lambda: standing(snapshot(), doctor, movement, talk.live())
    stops = [
        hub.subscribe(SellPartMessage, lambda message: clinic.sell_part(message.part)),
        hub.subscribe(FitMessage, lambda message: clinic.fit(message.bionic, message.part)),
        hub.subscribe(SellRecipeMessage, lambda message: clinic.sell_recipe(message.recipe)),
        hub.subscribe(PlayerSayMessage, lambda message: talk.say(message.text, message.target)),
        world.loop.register(talk),
    ]
    try:
        yield
    finally:
        for stop in reversed(stops):
            stop()
        hub.snapshot = snapshot
        keepers.pop(clinic.config.place, None)
        await talk.close()
