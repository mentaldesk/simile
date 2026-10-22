import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from starlette.applications import Starlette

from simile.app import create_app
from simile.behaviour import behaviour_of
from simile.behaviour.mind import create_behaviour
from simile.conversation import conversations_of, create_engine
from simile.conversation.player import PlayerConversations
from simile.economy.economy import economy_of
from simile.llm import FakeProvider, LLMClient, Request, Usage
from simile.llm.fake import scene
from simile.memory import MemoryStore, memory_of
from simile.news import news_of
from simile.persistence import SavedWorld, WorldStore, capture, investigation_of
from simile.persistence.lifespan import FRESH_ENV
from simile.reflection import SYSTEM, Deed, Extraction, Reflection
from simile.schema import (
    PLAYER_ID,
    Conversation,
    Line,
    MapTile,
    Memory,
    MemoryKind,
    NewsItem,
    Relationship,
)
from simile.sim import Clock, ConversationEnded, FakeWallClock, World, world_of
from simile.world import Point, movement_of

START = datetime(2026, 1, 1, 8, tzinfo=UTC)

type Step = Callable[[Starlette], Awaitable[None]]


async def nothing(app: Starlette) -> None:
    pass


async def run_village(
    duration: timedelta,
    *,
    before: Step = nothing,
    after: Step = nothing,
    app: Starlette | None = None,
) -> Starlette:
    """Start every module on the database in `SIMILE_DB`, run the village for `duration` from
    wherever it resumes, and shut down."""
    app = app or create_app()
    world = World(Clock(START), FakeWallClock())
    app.state.world = world
    app.state.headless = True
    app.state.behaviour = create_behaviour(app, seed=0)
    app.state.conversation = create_engine(app, seed=0)
    async with app.router.lifespan_context(app):
        await before(app)
        await world.loop.run(duration)
        await after(app)
    return app


def saved(database: Path) -> SavedWorld:
    with MemoryStore(database) as memory, WorldStore(memory) as store:
        world = store.load()
    assert world is not None
    return world


def whereabouts(world: SavedWorld) -> dict[str, tuple[object, ...]]:
    return {
        npc: (state.position, state.map, state.activity, state.target, state.needs, state.since)
        for npc, state in world.npcs.items()
    }


def recall(app: Starlette, npc: str) -> list[Memory]:
    return memory_of(app).recall(npc, world_of(app).clock.now, k=100)


@pytest.mark.anyio
async def test_restarting_keeps_the_clock_positions_goals_relationships_and_memories(
    database: Path, relationships: list[Relationship], memories: list[Memory]
) -> None:
    async def remember(app: Starlette) -> None:
        memory_of(app).add(*relationships, *memories)

    first = await run_village(timedelta(hours=1, minutes=10), after=remember)
    stopped = saved(database)
    assert stopped.now == START + timedelta(hours=1, minutes=10)
    assert stopped == capture(
        behaviour_of(first), economy_of(first), investigation=investigation_of(first)
    )

    async def resumed(app: Starlette) -> None:
        assert world_of(app).clock.now == stopped.now
        assert whereabouts(capture(behaviour_of(app))) == whereabouts(stopped)
        store = memory_of(app)
        assert [rel for npc in ("mei", "suki", "viktor") for rel in store.relationships(npc)] == (
            sorted(relationships, key=lambda rel: (rel.owner, rel.about))
        )
        assert sorted(m.content for npc in ("mei", "suki", "viktor") for m in recall(app, npc)) == (
            sorted(m.content for m in memories)
        )

    await run_village(timedelta(minutes=30), before=resumed)
    assert saved(database).now == stopped.now + timedelta(minutes=30)


@pytest.mark.anyio
async def test_a_resident_inside_at_shutdown_is_inside_after_restarting(database: Path) -> None:
    async def go_in(app: Starlette) -> None:
        movement_of(app).place("kofi", MapTile(map="coffee_shop_floor_1", x=11, y=2))

    await run_village(timedelta(minutes=10), after=go_in)
    assert saved(database).npcs["kofi"].map == "coffee_shop_floor_1"

    async def still_inside(app: Starlette) -> None:
        assert movement_of(app).position("kofi") == Point(11, 2, "coffee_shop_floor_1")

    await run_village(timedelta(minutes=1), before=still_inside)


def reflection() -> str:
    """Kofi and Henrietta warm to each other."""
    pair = ("kofi", "henrietta")
    return Extraction(
        reflections=[
            Reflection(
                npc=npc,
                summary="We chatted about the weather.",
                valence=0.4,
                salience=0.5,
                events=[
                    Deed(by=other, action="chatted", aspects=["like"], valence=0.4, magnitude=0.4)
                ],
            )
            for npc, other in (pair, pair[::-1])
        ]
    ).model_dump_json()


class Chat:
    name = "chat"

    def stream(self, request: Request) -> AsyncGenerator[str | Usage, None]:
        if request.system.startswith(SYSTEM):
            return FakeProvider([reflection()]).stream(request)
        reply = scene(request, ["Lovely weather today."]) or "Lovely weather today."
        return FakeProvider([reply]).stream(request)


@pytest.mark.anyio
async def test_a_conversation_going_on_at_shutdown_is_ended_and_reflected_on(
    database: Path,
) -> None:
    ended: list[Conversation] = []

    async def start_talking(app: Starlette) -> None:
        app.state.llm = LLMClient(Chat())
        world_of(app).bus.subscribe(
            ConversationEnded, lambda event: ended.append(event.conversation)
        )
        conversations_of(app).start("kofi", "henrietta")

    await run_village(timedelta(seconds=3), before=start_talking)

    stop = START + timedelta(seconds=3)
    [conversation] = ended
    assert conversation.participants == ["kofi", "henrietta"]
    assert conversation.ended == stop
    assert conversation.lines
    with MemoryStore(database) as store:
        talks = store.recall("kofi", stop, kind=MemoryKind.CONVERSATION)
        assert [m.about for m in talks] == [["henrietta"]]
        rel = store.relationship("henrietta", "kofi")
        assert rel is not None and rel.like > rel.baseline.like
    world = saved(database)
    assert world.npcs["kofi"].cooldowns.keys() == {"henrietta"}
    assert world.npcs["henrietta"].cooldowns.keys() == {"kofi"}
    assert world.npcs["kofi"].until == world.npcs["henrietta"].until == stop


@pytest.mark.anyio
async def test_a_conversation_with_the_player_is_ended_too(database: Path) -> None:
    ended: list[Conversation] = []

    async def greet_the_player(app: Starlette) -> None:
        app.state.llm = LLMClient(Chat())
        world_of(app).bus.subscribe(
            ConversationEnded, lambda event: ended.append(event.conversation)
        )
        PlayerConversations(conversations_of(app)).start("kofi", opener="kofi")

    await run_village(timedelta(0), before=greet_the_player)

    [conversation] = ended
    assert conversation.participants == ["kofi", PLAYER_ID]
    assert conversation.ended == START
    kofi = saved(database).npcs["kofi"]
    assert kofi.cooldowns.keys() == {PLAYER_ID}
    assert kofi.until == conversation.ended


@pytest.mark.anyio
async def test_waits_for_reflections_still_going_on(database: Path) -> None:
    async def finish_talking(app: Starlette) -> None:
        reply = asyncio.Event()
        app.state.llm = LLMClient(FakeProvider([[reply, reflection()]]))
        line = Line(
            id=1, conversation_id="c1", speaker="kofi", text="Morning!", timestamp=START, duration=1
        )
        talk = Conversation(
            id="c1", participants=["kofi", "henrietta"], started=START, ended=START, lines=[line]
        )
        world_of(app).bus.publish(ConversationEnded(talk))
        asyncio.get_running_loop().call_later(0.05, reply.set)

    await run_village(timedelta(0), after=finish_talking)

    with MemoryStore(database) as store:
        talks = store.recall("henrietta", START, kind=MemoryKind.CONVERSATION)
        assert [m.conversation_id for m in talks] == ["c1"]


@pytest.mark.anyio
async def test_fresh_starts_a_new_village_but_keeps_the_news(
    database: Path,
    monkeypatch: pytest.MonkeyPatch,
    relationships: list[Relationship],
    news: list[NewsItem],
) -> None:
    async def remember(app: Starlette) -> None:
        memory_of(app).add(*relationships)
        news_of(app).add(news)

    await run_village(timedelta(hours=1), after=remember)
    monkeypatch.setenv(FRESH_ENV, "1")

    async def fresh(app: Starlette) -> None:
        assert world_of(app).clock.now == START
        assert memory_of(app).relationships("mei") == []
        assert {item.id for item in news_of(app).latest(10)} == {item.id for item in news}

    await run_village(timedelta(minutes=5), before=fresh)
    assert saved(database).now == START + timedelta(minutes=5)


@pytest.mark.anyio
async def test_does_nothing_with_an_in_memory_database() -> None:
    async def check(app: Starlette) -> None:
        assert not hasattr(app.state, "persistence")

    await run_village(timedelta(minutes=5), before=check)
