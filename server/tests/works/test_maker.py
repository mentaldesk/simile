import asyncio
import io
import random
from datetime import timedelta
from typing import Any

import pytest
from PIL import Image

from simile.llm import FakeProvider, LLMClient, LLMError, Model
from simile.memory import MemoryStore
from simile.schema import (
    CoreValue,
    Craft,
    Intention,
    IntentionKind,
    Medium,
    Memory,
    MemoryKind,
    Npc,
    Work,
)
from simile.sim import Clock
from simile.works import DEFAULT_CONFIG, Maker, WorksConfig, WorksStore
from simile.works.maker import PaintingReply, draw_seed
from simile.works.render import canvas, draw, painting_canvas
from simile.works.svg import BadSvg

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
    assert "- \"Not His\", Mei's writing: Mei's piece." in asked
    assert (
        "Write something new in your craft, plain verse about old bridges: a piece of fiction or "
        "poetry, not an opinion piece"
    ) in asked
    assert "You know what someone with your life and job would know." in asked
    assert VIKTOR.persona in request.system
    assert "You care most about: " in request.system
    assert "In your own time you write plain verse about old bridges." in request.system
    assert "have your say" not in request.system
    assert request.model == Model.SONNET


def test_others_works_weigh_less_among_what_is_on_their_mind(
    memory: MemoryStore, works: WorksStore
) -> None:
    seen = MURAL.model_copy(update={"salience": 0.8})
    memory.add(seen, TALK, WEAK)
    fake = FakeProvider([reply()])
    llm = LLMClient(fake)
    config = CONFIG.model_copy(update={"memories": 2, "others_works": 0.5})

    asyncio.run(make(Maker(works, memory, Clock(NOW), lambda: llm, config=config)))

    asked = fake.requests[0].messages[-1].content
    assert f"1. {TALK.content}" in asked
    assert f"2. {seen.content}" in asked
    assert WEAK.content not in asked


def test_the_prompt_carries_the_villages_latest_works_and_a_random_seed(
    memory: MemoryStore, works: WorksStore
) -> None:
    works.add(work("mine", title="My Own", hours_ago=1))
    works.add(
        mural("chair", artist="suki", hours_ago=2).model_copy(
            update={"title": "Save a Seat", "tags": ["empty chair", "belonging", "supper", "x"]}
        )
    )
    works.add(work("older", artist="mei", title="Too Old", hours_ago=30))
    fake = FakeProvider([reply(), reply()])
    llm = LLMClient(fake)
    config = CONFIG.model_copy(update={"village_works": 1})
    maker = Maker(
        works, memory, Clock(NOW), lambda: llm, npcs=NPCS, rng=random.Random(1), config=config
    )
    expected = draw_seed(Medium.WRITING, random.Random(1), config)

    asyncio.run(make(maker))
    asyncio.run(make(maker))

    first, second = (request.messages[-1].content for request in fake.requests)
    assert (
        "Your neighbours' latest works, newest first. Make yours unlike them, in its subject, its "
        f'images and its feeling:\n- "Save a Seat", {SUKI.name}\'s mural: empty chair, '
        "belonging, supper\n\n"
    ) in first
    assert "Too Old" not in first
    assert '- "My Own"' in first and '"My Own",' not in first
    assert f"For a spark this time, try {expected}." in first
    assert str(expected) not in second
    assert expected.genre in CONFIG.writing_genres


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
    works: WorksStore,
    memory: MemoryStore,
    fake: FakeProvider,
    painted: list[Work] | None = None,
    config: WorksConfig = CONFIG,
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
        config=config,
    )


async def paint(maker: Maker, npc: Npc = SUKI, wall: str | None = "wall_1") -> Work | None:
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
    assert (
        "m high. You're painting over Viktor Hale's \"Piece old\", of which Viktor Hale said: "
        '"What old says."\n\n'
    ) in asked[0]
    assert (
        'You\'re painting over your own "Sunrise Over the Square", of which you said: "Morning'
    ) in asked[1]
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


def test_a_mural_the_renderer_fails_on_is_tried_again(
    memory: MemoryStore, works: WorksStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    drawn: list[str] = []

    def crashing_once(svg: str, *args: Any, **kwargs: Any) -> bytes:
        drawn.append(svg)
        if len(drawn) == 1:
            raise BadSvg("it crashed the renderer")
        return draw(svg, *args, **kwargs)

    monkeypatch.setattr("simile.works.maker.draw", crashing_once)
    fake = FakeProvider([mural_reply(), mural_reply()])

    made = asyncio.run(paint(muralist(works, memory, fake)))

    assert made is not None
    assert len(drawn) == 2
    assert (
        fake.requests[1]
        .messages[-1]
        .content.endswith(
            "Your last try couldn't go up, because it crashed the renderer. Fix that."
        )
    )


def test_gives_up_quietly_on_murals_that_take_too_long_to_draw(
    memory: MemoryStore, works: WorksStore
) -> None:
    fake = FakeProvider([mural_reply(), mural_reply()])
    hasty = CONFIG.model_copy(update={"render_timeout": 0.001})

    made = asyncio.run(paint(muralist(works, memory, fake, config=hasty)))

    assert made is None
    assert "it took more than 0.001 s to draw" in fake.requests[1].messages[-1].content
    assert works.showing() == {}


def test_anything_else_that_goes_wrong_makes_nothing_and_raises_nothing(
    memory: MemoryStore, works: WorksStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*args: object, **kwargs: object) -> bytes:
        raise RuntimeError("the disk is full")

    monkeypatch.setattr("simile.works.maker.draw", broken)
    maker = muralist(works, memory, FakeProvider([mural_reply()]))

    async def scenario() -> asyncio.Task[Work | None]:
        task = maker.make(SUKI, "wall_1")
        assert task is not None
        await asyncio.wait([task])
        return task

    task = asyncio.run(scenario())

    assert task.exception() is None
    assert task.result() is None
    assert maker.making == set()
    assert works.showing() == {}


def painting_reply(**fields: object) -> str:
    return PaintingReply.model_validate(
        {
            "title": "Harbour at Dusk",
            "description": "A yellow sun over a blue harbour.",
            "statement": "Every boat comes home eventually.",
            "svg": svg(*painting_canvas()),
            "inspired_by": [1],
            "tags": ["Harbour", "dusk"],
            "sentiment": 6.0,
            **{value.value: 0.0 for value in CoreValue},
            "peace_of_mind": 7.0,
            **fields,
        }
    ).model_dump_json()


PAINTER = VIKTOR.model_copy(
    update={"craft": Craft(medium=Medium.PAINTING, form="small oil studies of the harbour")}
)


def gallery_painter(
    works: WorksStore, memory: MemoryStore, fake: FakeProvider, hung: list[tuple[Work, str, bytes]]
) -> Maker:
    llm = LLMClient(fake)

    def hang(work: Work, svg: str, png: bytes) -> None:
        hung.append((work, svg, png))

    return Maker(
        works, memory, Clock(NOW), lambda: llm, walls=[WALL], npcs=NPCS, hang=hang, config=CONFIG
    )


def test_a_painter_paints_a_canvas_and_hangs_it(memory: MemoryStore, works: WorksStore) -> None:
    memory.add(NEWS)
    fake, hung = FakeProvider([painting_reply()]), []

    made = asyncio.run(paint(gallery_painter(works, memory, fake, hung), PAINTER, None))

    assert made is not None
    [(work, drawn, png)] = hung
    assert work == made == works.get(made.id)
    assert (made.medium, made.wall, made.form) == (Medium.PAINTING, None, PAINTER.craft.form)
    assert made.text == "A yellow sun over a blue harbour."
    assert made.inspired_by == ["news-1"]
    assert 'viewBox="0 0 960 602"' in drawn
    assert Image.open(io.BytesIO(png)).size == painting_canvas() == (960, 602)
    [remembered] = memory.recall("viktor", NOW, kind=MemoryKind.WORK)
    assert remembered.content == (
        'I painted "Harbour at Dusk" for the gallery. Every boat comes home eventually.'
    )
    [request] = fake.requests
    asked = request.messages[-1].content
    assert "You're painting a canvas for the village gallery, 1.34 m wide and 0.84 m high" in asked
    assert "Paint something new in your craft, small oil studies of the harbour." in asked
    assert 'one SVG document with viewBox="0 0 960 602"' in asked
    assert "In your own time you paint small oil studies of the harbour. They hang in the " in (
        request.system
    )
    assert request.model == Model.SONNET


@pytest.mark.parametrize("medium", [Medium.MURAL, Medium.PAINTING], ids=str)
def test_murals_and_paintings_carry_a_random_seed_and_the_knowledge_limit(
    memory: MemoryStore, works: WorksStore, medium: Medium
) -> None:
    if medium is Medium.MURAL:
        fake = FakeProvider([mural_reply()])
        maker, npc, wall = muralist(works, memory, fake), SUKI, "wall_1"
    else:
        fake = FakeProvider([painting_reply()])
        maker, npc, wall = gallery_painter(works, memory, fake, []), PAINTER, None
    maker.rng = random.Random(3)
    expected = draw_seed(medium, random.Random(3), CONFIG)

    asyncio.run(paint(maker, npc, wall))

    asked = fake.requests[0].messages[-1].content
    assert expected.genre in CONFIG.picture_genres
    assert f"For a spark this time, try {expected}." in asked
    assert (
        "You know what someone with your life and job would know. Stay within it: paint from "
        "your own life, work and village, never as an expert on what you don't know."
    ) in asked


def test_a_muralist_given_anything_but_a_wall_paints_for_the_gallery(
    memory: MemoryStore, works: WorksStore
) -> None:
    fake, hung = FakeProvider([painting_reply()]), []

    made = asyncio.run(paint(gallery_painter(works, memory, fake, hung), SUKI, "house_2"))

    assert made is not None and made.medium is Medium.PAINTING
    assert [work for work, _, _ in hung] == [made]
    assert works.showing() == {}
    asked = fake.requests[0].messages[-1].content
    assert f"in the spirit of your craft, {SUKI.craft.form}, but on canvas this time" in asked
    assert "on the village's walls" in fake.requests[0].system


def test_a_bad_painting_is_tried_again_once(memory: MemoryStore, works: WorksStore) -> None:
    fake, hung = FakeProvider([painting_reply(svg=svg()), painting_reply()]), []

    made = asyncio.run(paint(gallery_painter(works, memory, fake, hung), PAINTER, None))

    assert made is not None and len(hung) == 1
    again = fake.requests[1].messages[-1].content
    assert again.endswith(
        "Your last try couldn't be hung, because its viewBox is 288 × 262, not the wall's "
        'shape: use viewBox="0 0 960 602". Fix that.'
    )


def test_nobody_paints_for_the_gallery_without_one(memory: MemoryStore, works: WorksStore) -> None:
    fake = FakeProvider([painting_reply()])
    llm = LLMClient(fake)

    async def scenario() -> list[object]:
        maker = Maker(works, memory, Clock(NOW), lambda: llm, walls=[WALL])
        return [maker.make(PAINTER), maker.make(SUKI, "house_2")]

    assert asyncio.run(scenario()) == [None, None]
    assert fake.requests == []


def promised(owner: str, description: str, *promised_to: str) -> Intention:
    return Intention(
        id=f"chat-1/{owner}/1",
        owner=owner,
        kind=IntentionKind.CREATE,
        description=description,
        promised_to=list(promised_to),
        created=NOW,
        due=NOW,
        expires=NOW + timedelta(hours=2),
        conversation_id="chat-1",
    )


def test_a_mural_they_promised_leads_with_the_idea(memory: MemoryStore, works: WorksStore) -> None:
    memory.add(SKY)
    fake = FakeProvider([mural_reply()])
    idea = promised("suki", "an ocean of coffee with cups half-sunk in it", "player", "mei")

    async def scenario() -> Work | None:
        task = muralist(works, memory, fake).make(SUKI, "wall_1", idea)
        assert task is not None
        return await task

    made = asyncio.run(scenario())

    assert made is not None
    assert made.inspired_by == ["chat-1", "news-9"]
    asked = fake.requests[0].messages[-1].content
    assert asked.startswith(
        f"You told Visitor, {MEI.name} you'd make this, and you're making it now: an ocean of "
        "coffee with cups half-sunk in it\n\nWhat's been on your mind lately"
    )
    assert "Make that idea, in your own way, drawing on what's on your mind, and say" in asked


@pytest.mark.usefixtures("remembered")
def test_a_piece_or_a_painting_they_meant_to_make_leads_with_the_idea(
    memory: MemoryStore, works: WorksStore
) -> None:
    writing, painting = FakeProvider([reply()]), FakeProvider([painting_reply()])
    llm = LLMClient(writing)

    async def scenario() -> None:
        maker = Maker(works, memory, Clock(NOW), lambda: llm, config=CONFIG)
        task = maker.make(VIKTOR, None, promised("viktor", "lines on the footbridge"))
        assert task is not None and await task is not None
        painter = gallery_painter(works, memory, painting, [])
        task = painter.make(PAINTER, None, promised("viktor", "the harbour at night", "mei"))
        assert task is not None and await task is not None

    asyncio.run(scenario())

    wrote, painted = (fake.requests[0].messages[-1].content for fake in (writing, painting))
    assert wrote.startswith(
        "You meant to make this, and you're making it now: lines on the footbridge\n\n"
    )
    assert painted.startswith(
        f"You told {MEI.name} you'd make this, and you're making it now: the harbour at night"
    )
