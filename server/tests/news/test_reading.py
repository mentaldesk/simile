import asyncio
from collections import Counter
from collections.abc import Callable
from contextlib import AsyncExitStack
from datetime import UTC, datetime, timedelta

from starlette.applications import Starlette
from starlette.testclient import TestClient

from simile.app import create_app
from simile.behaviour import DEFAULT_CONFIG, Activity, GoalChosen, behaviour_of
from simile.behaviour.lifespan import lifespan as behaviour
from simile.behaviour.mind import create_behaviour, no_news, skip_news
from simile.llm import FakeProvider, LLMClient
from simile.memory import memory_of
from simile.memory.lifespan import lifespan as memory
from simile.news import news_of, parse
from simile.news.lifespan import lifespan as news
from simile.news.reactions import NewsReader, Reaction, topics_to_raise
from simile.schema import CoreValue, Memory, MemoryKind, NewsItem
from simile.sim import Clock, FakeWallClock, World
from simile.world.lifespan import lifespan as world_lifespan

MakePackage = Callable[[dict[str, str]], str]

START = datetime(2026, 1, 1, 9, tzinfo=UTC)
CURIOUS = DEFAULT_CONFIG.model_copy(update={"base": {**DEFAULT_CONFIG.base, Activity.NEWS: 1.0}})
REACTION = Reaction(take="Well, well.", valence=0.4, intensity=0.6, topics=["news"])
V = CoreValue
ANALYSES = {
    "A new window to the early universe": {V.KNOWLEDGE: 0.9, V.ADVENTURE: 0.6},
    "The cruelest people in Russian history": {V.JUSTICE: 0.8, V.COMPASSION: 0.7},
    "Mindfulness": {V.PEACE_OF_MIND: 0.9, V.SELF_ACTUALIZATION: 0.5},
    "Big Tech and privacy": {V.FREEDOM: 0.8, V.SECURITY: 0.7, V.HONESTY: 0.6},
    "What happens when two different respiratory viruses": {V.KNOWLEDGE: 0.8, V.SECURITY: 0.5},
}


def analysed(item: NewsItem) -> NewsItem:
    [related] = [values for title, values in ANALYSES.items() if item.title.startswith(title)]
    values = {value: related.get(value, 0.0) for value in CoreValue}
    return NewsItem.model_validate({**item.model_dump(), "values": values})


async def fast_forward(
    feed_xml: bytes, hours: float
) -> tuple[Counter[str], list[Memory], dict[str, list[Memory]]]:
    """NPCs who go to the terminals whenever there's something they'd like to read, and a fake
    provider that rates every article."""
    app = Starlette()
    world = World(Clock(START), FakeWallClock())
    app.state.world = world
    app.state.headless = True
    app.state.llm = LLMClient(FakeProvider(default=REACTION.model_dump_json()))
    app.state.behaviour = create_behaviour(app, config=CURIOUS, seed=0)
    news_of(app).add(analysed(item) for item in parse(feed_xml))
    visits: Counter[str] = Counter()
    world.bus.subscribe(
        GoalChosen, lambda e: visits.update([e.npc] if e.activity == Activity.NEWS else [])
    )
    async with AsyncExitStack() as stack:
        for lifespan in (behaviour, memory, news, world_lifespan):
            await stack.enter_async_context(lifespan(app))
        await world.loop.run(timedelta(hours=hours))
        await asyncio.gather(*behaviour_of(app).hooks.read_news.__self__.tasks)
        now, store = world.clock.now, memory_of(app)
        npcs = behaviour_of(app).npcs
        memories = [m for npc in npcs for m in store.recall(npc, now, kind=MemoryKind.NEWS, k=100)]
        raised = {npc: topics_to_raise(store, npc, now) for npc in npcs}
    return visits, memories, raised


def test_npcs_at_terminals_read_one_article_they_care_about_a_visit(feed_xml: bytes) -> None:
    visits, memories, raised = asyncio.run(fast_forward(feed_xml, 2))

    stored = {item.id for item in parse(feed_xml)}
    reads = Counter(m.owner for m in memories)
    assert len(reads) >= 3
    assert all(reads[npc] <= visits[npc] for npc in reads)
    assert all(m.news_id in stored for m in memories)
    assert all(m.salience == REACTION.intensity for m in memories)
    assert len({(m.owner, m.news_id) for m in memories}) == len(memories)
    assert {npc for npc, topics in raised.items() if topics} == set(reads)
    assert all(" in Big Think on the news terminal. " in m.content for m in memories)
    first = {
        owner: min((m for m in memories if m.owner == owner), key=lambda m: m.timestamp).news_id
        for owner in reads
    }
    assert len(set(first.values())) >= 2
    assert len(reads) < len(raised)


def test_reads_the_news_for_behaviour_while_running(make_package: MakePackage) -> None:
    package = make_package(
        {
            f"{module}/lifespan.py": f"from simile.{module}.lifespan import lifespan\n"
            for module in ("memory", "news")
        }
    )
    app = create_app(package)

    with TestClient(app):
        hooks = behaviour_of(app).hooks
        assert isinstance(getattr(hooks.read_news, "__self__", None), NewsReader)
        assert hooks.news_interest.__self__ is hooks.read_news.__self__

    assert behaviour_of(app).hooks.read_news is skip_news
    assert behaviour_of(app).hooks.news_interest is no_news
