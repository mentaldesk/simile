from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from starlette.applications import Starlette


@asynccontextmanager
async def running(app: Starlette) -> AsyncIterator[None]:
    from simile.voice import voice_of

    voice = voice_of(app)
    if voice is None:
        yield
        return

    from simile.behaviour import behaviour_of
    from simile.conversation import LineDrafted, conversations_of
    from simile.protocol import hub_of
    from simile.sim import ConversationEnded, ConversationStarted, LineSpoken, world_of
    from simile.voicing.voicing import Voicing, add_voices
    from simile.world import movement_of

    world, hub = world_of(app), hub_of(app)
    voicing = Voicing(
        voice,
        movement_of(app).distance,
        hub.broadcast,
        listening=lambda: bool(hub.connections),
    )
    stops = [
        world.bus.subscribe(ConversationStarted, voicing.on_started),
        world.bus.subscribe(LineDrafted, voicing.on_drafted),
        world.bus.subscribe(LineSpoken, voicing.on_spoken),
        world.bus.subscribe(ConversationEnded, voicing.on_ended),
        world.loop.register(voicing),
    ]
    app.state.voiced = voicing.voiced
    engine = conversations_of(app)
    engine.voiced_duration = voicing.duration
    try:
        await add_voices(voice, behaviour_of(app).npcs.values())
        yield
    finally:
        engine.voiced_duration = None
        del app.state.voiced
        for stop in reversed(stops):
            stop()
        await voicing.close()
