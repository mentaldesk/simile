import asyncio
import json
import sqlite3
from collections import Counter
from collections.abc import Callable
from contextlib import AsyncExitStack
from datetime import UTC, datetime, timedelta

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from simile.app import create_app
from simile.behaviour import DEFAULT_CONFIG, Activity, GoalChosen, Need, behaviour_of
from simile.behaviour.lifespan import lifespan as behaviour
from simile.behaviour.mind import create_behaviour, make_nothing, no_news, skip_news
from simile.llm import FakeProvider, LLMClient
from simile.llm.provider import Request
from simile.memory import memory_of
from simile.memory.lifespan import lifespan as memory
from simile.news import news_of
from simile.news.bundled import bundled
from simile.news.lifespan import lifespan as news
from simile.news.reactions import NewsReader
from simile.schema import Medium, Memory, MemoryKind
from simile.sim import Clock, FakeWallClock, World, world_of
from simile.works import Maker, works_of
from simile.works.lifespan import lifespan as works
from simile.works.reading import WorksReader
from simile.world.lifespan import lifespan as world_lifespan

from .conftest import reply, work

MakePackage = Callable[[dict[str, str]], str]

START = datetime(2026, 1, 1, 9, tzinfo=UTC)
EAGER = DEFAULT_CONFIG.model_copy(
    update={
        "base": {**DEFAULT_CONFIG.base, Activity.NEWS: 1.0},
        "start_needs": {**DEFAULT_CONFIG.start_needs, Need.INSPIRATION: (0.9, 1.0)},
    }
)
REACTION = json.dumps({"take": "Well, well.", "valence": 0.4, "intensity": 0.6, "topics": ["it"]})


def answer(request: Request) -> str:
    if "Write something new in your craft" in request.messages[-1].content:
        return reply(connection=8.0, freedom=8.0, knowledge=8.0, compassion=8.0)
    return REACTION


def test_the_server_keeps_a_maker_on_its_works_and_closes_them(make_package: MakePackage) -> None:
    package = make_package(
        {
            f"{module}/lifespan.py": f"from simile.{module}.lifespan import lifespan\n"
            for module in ("llm", "memory", "works")
        }
    )
    app = create_app(package)

    with TestClient(app):
        maker = app.state.maker
        assert isinstance(maker, Maker)
        assert maker.works is works_of(app)
        assert maker.memory is memory_of(app)
        assert maker.clock is world_of(app).clock
        assert maker.llm() is app.state.llm
        store = works_of(app)
        store.add(work("a"))

    with pytest.raises(sqlite3.ProgrammingError):
        store.get("a")


def test_wraps_the_news_at_the_terminals_and_puts_it_back(make_package: MakePackage) -> None:
    package = make_package(
        {
            f"{module}/lifespan.py": f"from simile.{module}.lifespan import lifespan\n"
            for module in ("memory", "news", "works")
        }
    )
    app = create_app(package)

    with TestClient(app):
        hooks = behaviour_of(app).hooks
        reader = hooks.read_news.__self__
        assert isinstance(reader, WorksReader)
        assert hooks.news_interest.__self__ is reader
        assert isinstance(reader.read_news.__self__, NewsReader)
        assert reader.news_interest.__self__ is reader.read_news.__self__
        assert hooks.create is not make_nothing

    assert behaviour_of(app).hooks.read_news is skip_news
    assert behaviour_of(app).hooks.news_interest is no_news
    assert behaviour_of(app).hooks.create is make_nothing


async def fast_forward(
    hours: float, *, with_works: bool = True
) -> tuple[dict[str, str], list[Memory], list[Memory], Counter[str]]:
    """Works made, residents' work and news memories, and their visits to the terminals."""
    app = Starlette()
    world = World(Clock(START), FakeWallClock())
    app.state.world = world
    app.state.headless = True
    app.state.llm = LLMClient(FakeProvider(default=answer))
    app.state.behaviour = create_behaviour(app, config=EAGER, seed=0)
    news_of(app).add(bundled())
    visits: Counter[str] = Counter()
    world.bus.subscribe(
        GoalChosen, lambda e: visits.update([e.npc] if e.activity == Activity.NEWS else [])
    )
    lifespans = (behaviour, memory, news, *([works] if with_works else []), world_lifespan)
    async with AsyncExitStack() as stack:
        for lifespan in lifespans:
            await stack.enter_async_context(lifespan(app))
        await world.loop.run(timedelta(hours=hours))
        terminal = behaviour_of(app).hooks.read_news.__self__
        readers = [terminal, terminal.read_news.__self__] if with_works else [terminal]
        await asyncio.gather(
            *(app.state.maker.tasks if with_works else ()),
            *(task for reader in readers for task in reader.tasks),
        )
        store, now = memory_of(app), world.clock.now

        def recalled(kind: MemoryKind) -> list[Memory]:
            npcs = behaviour_of(app).npcs
            return [m for npc in npcs for m in store.recall(npc, now, kind=kind, k=100)]

        made = (
            {w.id: w.artist for w in works_of(app).latest(Medium.WRITING, 100)}
            if with_works
            else {}
        )
        return made, recalled(MemoryKind.WORK), recalled(MemoryKind.NEWS), visits


def test_residents_write_and_read_each_others_work_and_lose_no_news() -> None:
    made, work_memories, news_memories, visits = asyncio.run(fast_forward(3))
    _, _, without_works, _ = asyncio.run(fast_forward(3, with_works=False))

    read = [m for m in work_memories if m.owner != made[m.work_id or ""]]
    assert len(set(made.values())) >= 2
    assert len({m.owner for m in read}) >= 2
    assert all(m.about == [made[m.work_id or ""]] for m in read)
    assert len({(m.owner, m.work_id) for m in read}) == len(read)
    assert len(news_memories) >= len(without_works) > 0
    for reads in (Counter(m.owner for m in read), Counter(m.owner for m in news_memories)):
        assert all(reads[npc] <= visits[npc] for npc in reads)
