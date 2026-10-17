import asyncio
import io
from datetime import timedelta

import pytest
from PIL import Image

from simile.llm import FakeProvider, LLMClient, LLMError, Model
from simile.memory import MemoryStore
from simile.schema import CoreValue, Medium, Memory, MemoryKind, Npc, Work
from simile.sim import Clock
from simile.works import DEFAULT_CONFIG, Maker, WorksStore
from simile.works.render import canvas

from .conftest import (
    MEI,
    NOW,
    OTHER_WALL,
    SUKI,
    VIKTOR,
    WALL,
    mural,
    mural_reply,
    reply,
    svg,
    work,
)

CONFIG = DEFAULT_CONFIG.model_copy(update={"memories": 3, "past_works": 2})


def memory_of(kind: MemoryKind, content: str, salience: float, **fields: object) -> Memory:
    return Memory.model_validate(
        {
            "owner": "viktor",
            "kind": kind,
            "content": content,
            "salience": salience,
            "valence": 0.0,
            "timestamp": NOW - timedelta(hours=1),
            **fields,
        }
    )


NEWS = memory_of(
    MemoryKind.NEWS,
    'I read "Council to replace the footbridge" on the news terminal. A disgrace.',
    0.9,
    valence=-0.7,
    news_id="news-1",
)
TALK = memory_of(
    MemoryKind.CONVERSATION,
    "Mei and I talked about the bridge repairs. She wants a new one.",
    0.7,
    valence=-0.3,
    conversation_id="conv-1",
    about=["mei"],
)
MURAL = memory_of(
    MemoryKind.WORK, "I saw Suki's mural of the village from the air.", 0.5, work_id="mural-1"
)
WEAK = memory_of(MemoryKind.NEWS, "I read something about the weather.", 0.1, news_id="news-2")
MADE = memory_of(MemoryKind.WORK, 'I wrote "Old Stones".', 1.0, work_id="old")


async def make(maker: Maker, npc: Npc = VIKTOR) -> Work | None:
    task = maker.make(npc)
    assert task is not None
    return await task


@pytest.fixture
def remembered(memory: MemoryStore, works: WorksStore) -> None:
    memory.add(NEWS, TALK, MURAL, WEAK, MADE)
    works.add(work("old", title="Old Stones", statement="Stone outlasts us.", hours_ago=30))
    works.add(work("older", title="Rust", statement="Rust is neglect.", hours_ago=60))
    works.add(work("oldest", title="First", statement="The first.", hours_ago=90))
    works.add(work("hers", artist="mei", title="Not His", statement="Mei's piece."))


@pytest.mark.usefixtures("remembered")
def test_writes_from_the_strongest_memories_and_the_latest_works(
    memory: MemoryStore, works: WorksStore
) -> None:
    fake = FakeProvider([reply()])
    llm = LLMClient(fake)

    asyncio.run(make(Maker(works, memory, Clock(NOW), lambda: llm, config=CONFIG)))

    [request] = fake.requests
    asked = request.messages[-1].content
    assert asked.index(f"1. {NEWS.content} (It upset you, and you keep coming back to it.)") < (
        asked.index(f"2. {TALK.content} (It bothered you, and you keep coming back to it.)")
    )
    assert f"3. {MURAL.content} (You had mixed feelings about it.)" in asked
    assert WEAK.content not in asked
    assert MADE.content not in asked
    assert '- "Old Stones": Stone outlasts us.\n- "Rust": Rust is neglect.' in asked
    assert '"First"' not in asked
    assert "Not His" not in asked
    assert "Write something new in your craft, plain verse about old bridges." in asked
    assert VIKTOR.persona in request.system
    assert "You care most about: " in request.system
    assert "In your own time you write plain verse about old bridges." in request.system
    assert request.model == Model.SONNET


@pytest.mark.usefixtures("remembered")
def test_stores_the_work_with_what_inspired_it(memory: MemoryStore, works: WorksStore) -> None:
    llm = LLMClient(FakeProvider([reply()]))

    made = asyncio.run(make(Maker(works, memory, Clock(NOW), lambda: llm, config=CONFIG)))

    assert made is not None
    assert works.get(made.id) == made
    assert made.id.startswith("viktor-")
    assert made.artist == "viktor"
    assert made.form == "plain verse about old bridges"
    assert made.title == "The Footbridge"
    assert made.created == NOW
    assert made.inspired_by == ["conv-1", "news-1"]
    assert made.tags == ["repair", "the old footbridge", "boredom", "bridges"]
    assert made.sentiment == pytest.approx(-0.4)
    assert made.values[CoreValue.TRADITION] == pytest.approx(0.8)
    assert made.values[CoreValue.FREEDOM] == 0.0
    assert made.wall is None


@pytest.mark.usefixtures("remembered")
def test_the_artist_remembers_making_it(memory: MemoryStore, works: WorksStore) -> None:
    llm = LLMClient(FakeProvider([reply()]))

    made = asyncio.run(make(Maker(works, memory, Clock(NOW), lambda: llm, config=CONFIG)))

    assert made is not None
    [remembered] = [m for m in memory.recall("viktor", NOW, k=10) if m.work_id == made.id]
    assert remembered == Memory(
        owner="viktor",
        kind=MemoryKind.WORK,
        content='I wrote "The Footbridge" and put it up on the news terminals. '
        "Things last when people look after them.",
        salience=CONFIG.salience,
        valence=CONFIG.valence,
        timestamp=NOW,
        topics=["repair", "the old footbridge", "boredom"],
        work_id=made.id,
    )


def test_writes_from_their_values_alone_with_nothing_on_their_mind(
    memory: MemoryStore, works: WorksStore
) -> None:
    fake = FakeProvider([reply(inspired_by=[1])])
    llm = LLMClient(fake)

    made = asyncio.run(make(Maker(works, memory, Clock(NOW), lambda: llm)))

    asked = fake.requests[0].messages[-1].content
    assert asked.startswith("Nothing in particular has been on your mind lately.\n\n")
    assert "Your last few pieces" not in asked
    assert made is not None
    assert made.inspired_by == []


def test_makes_nothing_without_a_craft_a_wall_for_a_mural_or_an_llm(
    memory: MemoryStore, works: WorksStore
) -> None:
    fake = FakeProvider([reply()])
    llm = LLMClient(fake)

    async def scenario() -> list[object]:
        maker = Maker(works, memory, Clock(NOW), lambda: llm, walls=[WALL])
        silent = Maker(works, memory, Clock(NOW), lambda: None, walls=[WALL])
        made = [
            maker.make(MEI, "wall_1"),
            maker.make(SUKI),
            maker.make(SUKI, "nowhere"),
            silent.make(VIKTOR),
            silent.make(SUKI, "wall_1"),
        ]
        return made

    assert asyncio.run(scenario()) == [None] * 5
    assert fake.requests == []


def test_writes_without_blocking_and_one_piece_at_a_time(
    memory: MemoryStore, works: WorksStore
) -> None:
    resume = asyncio.Event()
    llm = LLMClient(FakeProvider([[resume, reply()], reply(title="Next")]))
    clock = Clock(NOW)

    async def scenario() -> list[Work | None]:
        maker = Maker(works, memory, clock, lambda: llm)
        task = maker.make(VIKTOR)
        assert task is not None
        await asyncio.sleep(0.01)
        assert not task.done()
        assert maker.make(VIKTOR) is None
        clock.now = NOW + timedelta(hours=1)
        resume.set()
        first = await task
        return [first, await make(maker)]

    first, second = asyncio.run(scenario())

    assert first is not None and first.created == NOW
    assert second is not None and second.title == "Next"
    assert works.by("viktor") == [second, first]


@pytest.mark.parametrize(
    "failure", [[LLMError("usage limit reached")], ["not json", "still not json"]]
)
def test_a_failed_call_makes_nothing(
    failure: list[object], memory: MemoryStore, works: WorksStore
) -> None:
    llm = LLMClient(FakeProvider([*failure, reply()]))

    async def scenario() -> list[Work | None]:
        maker = Maker(works, memory, Clock(NOW), lambda: llm)
        return [await make(maker), await make(maker)]

    failed, then = asyncio.run(scenario())

    assert failed is None
    assert then is not None
    assert works.by("viktor") == [then]
    assert [m.work_id for m in memory.recall("viktor", NOW)] == [then.id]


def test_stopping_cancels_pieces_under_way(memory: MemoryStore, works: WorksStore) -> None:
    llm = LLMClient(FakeProvider([[asyncio.Event(), reply()]]))

    async def scenario() -> asyncio.Task[Work | None]:
        maker = Maker(works, memory, Clock(NOW), lambda: llm)
        task = maker.make(VIKTOR)
        assert task is not None
        await asyncio.sleep(0.01)
        await maker.stop()
        return task

    assert asyncio.run(scenario()).cancelled()
    assert works.by("viktor") == []


NPCS = {npc.id: npc for npc in (VIKTOR, SUKI, MEI)}
SKY = memory_of(
    MemoryKind.NEWS, "I read about drones over the square.", 0.8, owner="suki", news_id="news-9"
)


def muralist(
    works: WorksStore, memory: MemoryStore, fake: FakeProvider, painted: list[Work] | None = None
) -> Maker:
    llm = LLMClient(fake)
    return Maker(
        works,
        memory,
        Clock(NOW),
        lambda: llm,
        walls=[WALL, OTHER_WALL],
        npcs=NPCS,
        painted=(painted if painted is not None else []).append,
        config=CONFIG,
    )


async def paint(maker: Maker, npc: Npc = SUKI, wall: str = "wall_1") -> Work | None:
    task = maker.make(npc, wall)
    assert task is not None
    return await task


def test_paints_a_mural_at_its_walls_size_and_says_so(
    memory: MemoryStore, works: WorksStore
) -> None:
    memory.add(SKY)
    fake, painted = FakeProvider([mural_reply()]), []

    made = asyncio.run(paint(muralist(works, memory, fake, painted)))

    assert made is not None
    assert painted == [made]
    assert works.showing() == {"wall_1": made}
    assert made.id.startswith("suki-")
    assert (made.medium, made.wall, made.form) == (Medium.MURAL, "wall_1", SUKI.craft.form)
    assert made.title == "Sunrise Over the Square"
    assert made.text == "A red wall with a yellow sun in the middle."
    assert made.inspired_by == ["news-9"]
    assert made.tags == ["mornings", "the square"]
    assert made.values[CoreValue.FREEDOM] == pytest.approx(0.8)
    picture = Image.open(io.BytesIO(works.picture(made.id) or b""))
    assert picture.size == canvas(WALL) == (288, 262)
    [remembered] = memory.recall("suki", NOW, kind=MemoryKind.WORK)
    assert remembered.content == (
        'I painted "Sunrise Over the Square" on the wall 1 wall. Morning belongs to everyone.'
    )
    assert remembered.work_id == made.id
    [request] = fake.requests
    asked = request.messages[-1].content
    assert f"1. {SKY.content}" in asked
    assert "a new mural on the wall 1 wall, 3.3 m wide and 3.0 m high. It's blank." in asked
    assert f"Paint something new in your craft, {SUKI.craft.form}." in asked
    assert 'one SVG document with viewBox="0 0 288 262"' in asked
    assert f"In your own time you paint {SUKI.craft.form} on the village's walls" in request.system
    assert request.model == Model.SONNET


def test_painting_over_a_mural_keeps_it_and_remembers_whose_it_was(
    memory: MemoryStore, works: WorksStore
) -> None:
    works.paint(mural("old", "viktor", hours_ago=50), "<svg/>", b"")
    fake = FakeProvider([mural_reply(), mural_reply(title="Again")])
    maker = muralist(works, memory, fake)

    over_his = asyncio.run(paint(maker))
    over_mine = asyncio.run(paint(maker))

    assert over_his is not None and over_mine is not None
    assert works.covered(over_his.id) == works.get("old")
    assert works.covered(over_mine.id) == over_his
    asked = [request.messages[-1].content for request in fake.requests]
    assert "You're painting over Viktor Hale's \"Piece old\": What old says." in asked[0]
    assert 'You\'re painting over your own "Sunrise Over the Square"' in asked[1]
    said = " ".join(m.content for m in memory.recall("suki", NOW, kind=MemoryKind.WORK))
    assert 'on the wall 1 wall over Viktor Hale\'s "Piece old". Morning' in said
    assert 'I painted "Again" on the wall 1 wall over my "Sunrise Over the Square".' in said


def test_a_bad_svg_is_tried_again_once_with_what_was_wrong(
    memory: MemoryStore, works: WorksStore
) -> None:
    fake = FakeProvider([mural_reply(svg=svg(inside="<script>go()</script>")), mural_reply()])

    made = asyncio.run(paint(muralist(works, memory, fake)))

    assert made is not None
    first, second = (request.messages[-1].content for request in fake.requests)
    assert (
        second
        == f"{first}\n\nYour last try couldn't go up, because <script> isn't allowed. Fix that."
    )


@pytest.mark.parametrize("second", [svg(100, 262), "<svg"])
def test_gives_up_quietly_after_two_bad_svgs(
    second: str, memory: MemoryStore, works: WorksStore
) -> None:
    fake = FakeProvider([mural_reply(svg="<svg/>"), mural_reply(svg=second), mural_reply()])
    painted: list[Work] = []

    async def scenario() -> list[Work | None]:
        maker = muralist(works, memory, fake, painted)
        return [await paint(maker), await paint(maker)]

    failed, then = asyncio.run(scenario())

    assert failed is None
    assert then is not None
    assert len(fake.requests) == 3
    assert painted == [then]
    assert works.latest(Medium.MURAL) == [then]
    assert [m.work_id for m in memory.recall("suki", NOW)] == [then.id]
