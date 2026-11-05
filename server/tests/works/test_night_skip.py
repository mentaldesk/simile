import asyncio
import random
from datetime import UTC, datetime, timedelta

import pytest

from simile.llm import LLMClient
from simile.llm.client import CallRecord
from simile.player.health import DEFAULT_HEALTH
from simile.sim import Clock, FakeWallClock, World

EVENING = datetime(2026, 1, 1, 21, 1, tzinfo=UTC)
QUIET = {
    "notice",
    "work",
    "mural",
    "painting",
    "work-reaction",
    "mural-reaction",
    "painting-reaction",
    "news-reaction",
    "news-analysis",
}
"""What works, the gallery and the news call the LLM for."""


async def skip_the_night() -> tuple[list[tuple[datetime, str]], datetime]:
    """A headless rest from 21:01 in a village with works, paintings and news to react to, until
    a minute and a half after they're up: each call's sim time and purpose, and when they got up."""
    from simile.app import create_app
    from simile.behaviour.mind import create_behaviour
    from simile.conversation import create_engine
    from simile.loop.player import LoopPlayer
    from simile.loop.playthrough import Canned
    from simile.memory import MemoryStore, memory_of
    from simile.news.bundled import fall_back
    from simile.news.store import news_of
    from simile.persistence import player_of
    from simile.protocol import RestMessage
    from simile.story.begin import begin
    from simile.works.starters import seed
    from simile.works.store import works_of

    world = World(Clock(EVENING), FakeWallClock())
    app = create_app()
    app.state.world, app.state.headless = world, True
    app.state.memory = MemoryStore(":memory:")
    app.state.behaviour = create_behaviour(app, seed=0)
    app.state.conversation = create_engine(app, seed=0)
    await begin(app, rng=random.Random("story/0"))
    calls: list[tuple[datetime, str]] = []

    def heard(record: CallRecord) -> None:
        calls.append((world.clock.now, record.purpose))

    async with app.router.lifespan_context(app):
        npcs = app.state.behaviour.npcs
        seed(works_of(app), memory_of(app), npcs, world.clock.now, hang=app.state.gallery.hang)
        fall_back(news_of(app))
        app.state.llm = LLMClient(Canned(), listeners=[heard])
        player = LoopPlayer(app, [])
        player.join(app.state.health.home_bed())
        await player.wait(1)
        player_of(app).health = 0.4
        player.send(RestMessage(on=True))
        wall = world.loop.wall.now()
        while world.loop.wall.now() - wall < DEFAULT_HEALTH.lie_down + 0.1:
            await world.loop.run(timedelta(seconds=world.loop.dt()))
        assert world.clock.skipping
        while world.clock.time_of_day < 7 or world.clock.skipping:
            await world.loop.run(timedelta(seconds=world.loop.dt()))
        up = world.clock.now
        await world.loop.run(timedelta(minutes=1.5))
    return calls, up


def test_a_night_skipped_from_nine_makes_no_works_gallery_or_news_calls_until_morning() -> None:
    with pytest.MonkeyPatch.context() as env:
        env.setenv("SIMILE_LLM", "fake")
        env.setenv("SIMILE_NEWS", "0")
        env.setenv("SIMILE_DB", ":memory:")
        calls, up = asyncio.run(skip_the_night())

    assert up.hour == 7
    assert [call for call in calls if call[0] < up and call[1] in QUIET] == []
    assert "notice" in {purpose for when, purpose in calls if when >= up}
