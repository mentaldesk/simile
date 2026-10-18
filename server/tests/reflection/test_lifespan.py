import asyncio
import logging
import re
from collections.abc import AsyncGenerator, Callable
from datetime import UTC, datetime, timedelta

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from simile.app import create_app
from simile.behaviour.mind import create_behaviour
from simile.conversation import create_engine
from simile.llm import FakeProvider, LLMClient, Request, Usage
from simile.llm.fake import scene
from simile.memory import memory_of
from simile.npc import load_npcs
from simile.reflection import SYSTEM, Deed, Extraction, Reflection
from simile.schema import Conversation, Line, Memory, MemoryKind, Relationship
from simile.sim import Clock, ConversationEnded, FakeWallClock, World, world_of

MakePackage = Callable[[dict[str, str]], str]

START = datetime(2026, 1, 1, 8, tzinfo=UTC)
WITHOUT_ORDERS = [npc for npc in load_npcs() if npc.home != "coffee_shop"]
"""Everyone but the barista, whose orders change relationships without B3."""


def reflect_on(request: Request) -> str:
    """Every NPC in the prompt warms a little to the others."""
    ids = re.findall(r"^([a-z][a-z0-9_]*) \(", request.messages[-1].content, re.MULTILINE)
    return Extraction(
        reflections=[
            Reflection(
                npc=npc,
                summary="We had a nice chat.",
                valence=0.3,
                salience=0.3,
                topics=["weather"],
                events=[
                    Deed(by=other, action="chatted", aspects=["like"], valence=0.3, magnitude=0.3)
                    for other in ids
                    if other != npc
                ],
            )
            for npc in ids
        ]
    ).model_dump_json()


class Village:
    """Lines for the conversation engine and a reflection for B3."""

    name = "village"

    def stream(self, request: Request) -> AsyncGenerator[str | Usage, None]:
        if request.system.startswith(SYSTEM):
            return FakeProvider([reflect_on]).stream(request)
        reply = scene(request, ["Lovely weather today."]) or "Lovely weather today."
        return FakeProvider([reply]).stream(request)


def conversation(started: datetime) -> Conversation:
    line = Line(
        id=1, conversation_id="c1", speaker="kofi", text="Hi.", timestamp=started, duration=1
    )
    return Conversation(
        id="c1",
        participants=["kofi", "henrietta"],
        started=started,
        ended=started + timedelta(seconds=5),
        lines=[line],
    )


@pytest.fixture
def app(make_package: MakePackage) -> Starlette:
    package = make_package(
        {
            f"{module}/lifespan.py": f"from simile.{module}.lifespan import lifespan\n"
            for module in ("behaviour", "llm", "memory", "reflection", "world")
        }
    )
    app = create_app(package)
    app.state.world = World(Clock(START))
    return app


def test_reflects_on_every_conversation_until_shutdown(app: Starlette) -> None:
    async def settle() -> None:
        await asyncio.gather(*reflector.tasks)

    async def publish() -> set[object]:
        bus.publish(ConversationEnded(conversation(START)))
        return set(reflector.tasks)

    with TestClient(app) as client:
        app.state.llm = LLMClient(Village())
        bus, reflector = world_of(app).bus, app.state.reflection

        assert client.portal.call(publish)
        client.portal.call(settle)

        store = memory_of(app)
        rel = store.relationship("kofi", "henrietta")
        assert rel is not None and rel.like > rel.baseline.like
        assert [m.conversation_id for m in store.recall("henrietta", START, about="kofi")] == ["c1"]

    assert asyncio.run(publish()) == set()


async def run_village(
    hours: float, llm: LLMClient | None = None
) -> tuple[list[Conversation], list[Memory], list[Relationship]]:
    app = create_app()
    world = World(Clock(START), FakeWallClock())
    app.state.world = world
    app.state.headless = True
    app.state.behaviour = create_behaviour(app, seed=0, npcs=WITHOUT_ORDERS)
    app.state.conversation = create_engine(app, seed=0)
    ended: list[Conversation] = []
    world.bus.subscribe(ConversationEnded, lambda event: ended.append(event.conversation))
    async with app.router.lifespan_context(app):
        if llm is not None:
            app.state.llm = llm
        await world.loop.run(timedelta(hours=hours))
        await asyncio.gather(*app.state.reflection.tasks)
        store, now = memory_of(app), world.clock.now
        npcs = app.state.behaviour.npcs
        memories = [
            m for npc in npcs for m in store.recall(npc, now, kind=MemoryKind.CONVERSATION, k=100)
        ]
        relationships = [rel for npc in npcs for rel in store.relationships(npc)]
    return ended, memories, relationships


@pytest.mark.anyio
async def test_the_village_remembers_its_conversations() -> None:
    ended, memories, relationships = await run_village(hours=1, llm=LLMClient(Village()))

    talked = [talk for talk in ended if talk.lines]
    assert talked
    assert {(m.owner, m.conversation_id) for m in memories} == {
        (npc, talk.id) for talk in talked for npc in talk.participants
    }
    pairs = {(a, b) for talk in talked for a in talk.participants for b in talk.participants}
    assert {(rel.owner, rel.about) for rel in relationships} == {(a, b) for a, b in pairs if a != b}
    assert all(rel.like > rel.baseline.like for rel in relationships)


@pytest.mark.anyio
async def test_the_fake_llm_changes_nothing(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="simile.reflection"):
        ended, memories, relationships = await run_village(hours=1)

    talked = [talk for talk in ended if talk.lines]
    assert talked
    skipped = [r for r in caplog.records if r.getMessage().startswith("Couldn't make sense of")]
    assert len(skipped) == len(talked)
    assert memories == relationships == []
