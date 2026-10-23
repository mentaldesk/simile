from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from starlette.applications import Starlette


@asynccontextmanager
async def lifespan(app: Starlette) -> AsyncIterator[None]:
    import os
    from datetime import timedelta

    from simile.behaviour import behaviour_of
    from simile.conversation.engine import conversations_of
    from simile.conversation.flush import flushed
    from simile.conversation.player import SUSPECT_ENV, PlayerConfig, PlayerConversations
    from simile.conversation.temptation import Missed, missed_shifts
    from simile.news import news_of
    from simile.persistence import investigation_of, player_of
    from simile.protocol import PlayerSayMessage, hub_of
    from simile.schema import Id, NewsItem, Work
    from simile.sim import world_of
    from simile.social.sightings import sightings_of
    from simile.works import works_of

    engine, hub, loop = conversations_of(app), hub_of(app), world_of(app).loop

    def article(news_id: str) -> NewsItem | None:
        return news_of(app).get(news_id)

    def work(work_id: str) -> Work | None:
        return works_of(app).get(work_id)

    def missed(npc: Id) -> list[Missed]:
        economy = getattr(app.state, "economy", None)
        if economy is None:
            return []
        grace = timedelta(minutes=economy.config.late)
        return missed_shifts(economy.turns, npc, economy.clock.now, grace)

    suspect = os.environ.get(SUSPECT_ENV)
    config = PlayerConfig(suspect_model=suspect) if suspect else PlayerConfig()
    players = PlayerConversations(
        engine, connected=lambda: bool(hub.connections), article=article, config=config
    )
    engine.player_request, engine.article, engine.work = players.request, article, work
    engine.missed = missed
    engine.incident = lambda: investigation_of(app).incident
    engine.looks = lambda npc: sightings_of(app).looks(npc)
    app.state.players = players
    app.state.flushed = lambda line: flushed(players.talk(), line, player_of(app))
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
        del app.state.flushed
        engine.player_request = None
        del app.state.players
        await engine.close()
