from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from starlette.applications import Starlette


@asynccontextmanager
async def lifespan(app: Starlette) -> AsyncIterator[None]:
    from simile.behaviour import behaviour_of
    from simile.conversation.engine import conversations_of
    from simile.conversation.player import PlayerConversations
    from simile.news import news_of
    from simile.protocol import PlayerSayMessage, hub_of
    from simile.sim import world_of

    engine, hub, loop = conversations_of(app), hub_of(app), world_of(app).loop
    players = PlayerConversations(
        engine,
        connected=lambda: bool(hub.connections),
        article=lambda news_id: news_of(app).get(news_id),
    )
    engine.player_request = players.request
    stops = [
        behaviour_of(app).hooks.set(request_conversation=engine.request, conversations=engine.live),
        hub.subscribe(PlayerSayMessage, lambda message: players.say(message.text, message.target)),
        loop.register(engine),
        loop.register(players),
    ]
    try:
        yield
    finally:
        for stop in reversed(stops):
            stop()
        engine.player_request = None
        await engine.close()
