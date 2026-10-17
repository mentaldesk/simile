import asyncio

import pytest

from simile.llm import FakeProvider, LLMClient, LLMError, Model
from simile.memory import MemoryStore
from simile.schema import CoreValue, Memory, MemoryKind, Npc, Relationship
from simile.sim import Clock
from simile.social import meet
from simile.works import DEFAULT_CONFIG, WorksStore
from simile.works.reading import Reaction, WorksReader

from .conftest import MEI, NOW, SUKI, VIKTOR, work

NPCS = {npc.id: npc for npc in (VIKTOR, SUKI, MEI)}
CARING = {
    **{value: 0.0 for value in CoreValue},
    CoreValue.CONNECTION: 0.9,
    CoreValue.COMPASSION: 0.7,
}
REACTION = Reaction(take="It made me want to ring my sister.", valence=0.6, intensity=0.7)


class News:
    def __init__(self, interest: float = 0.0) -> None:
        self.level = interest
        self.read: list[str] = []

    def interest(self, npc: Npc) -> float:
        return self.level

    def read_news(self, npc: Npc) -> None:
        self.read.append(npc.id)


def feeling(owner: Npc, about: str, level: float) -> Relationship:
    return meet(owner, about).model_copy(
        update={"like": level, "trust": level, "respect": level, "familiarity": 0.8}
    )


def reader(
    works: WorksStore,
    memory: MemoryStore,
    news: News | None = None,
    llm: LLMClient | None = None,
) -> WorksReader:
    news = news or News()
    return WorksReader(
        works,
        memory,
        Clock(NOW),
        lambda: llm,
        NPCS,
        news_interest=news.interest,
        read_news=news.read_news,
    )


async def read(reader: WorksReader, npc: Npc) -> None:
    reader.read(npc)
    await asyncio.gather(*reader.tasks)


def read_by(memory: MemoryStore, npc: Npc) -> list[Memory]:
    return memory.recall(npc.id, NOW, kind=MemoryKind.WORK, k=100)


def test_a_friends_work_outranks_a_strangers_and_a_rivals_at_the_same_alignment(
    works: WorksStore, memory: MemoryStore
) -> None:
    works.add(work("friend", artist="viktor", values=CARING, hours_ago=3))
    works.add(work("stranger", artist="desmond", values=CARING, hours_ago=2))
    works.add(work("rival", artist="suki", values=CARING, hours_ago=1))
    memory.add(feeling(MEI, "viktor", 0.9), feeling(MEI, "suki", 0.25))

    ranked = reader(works, memory, llm=LLMClient(FakeProvider())).ranked(MEI)

    assert [w.id for w, _ in ranked] == ["friend", "stranger", "rival"]


def test_nobody_reads_their_own_work(works: WorksStore, memory: MemoryStore) -> None:
    tradition = {**CARING, CoreValue.TRADITION: 0.9, CoreValue.DISCIPLINE: 0.8}
    works.add(work("his", artist="viktor", values=tradition))

    terminal = reader(works, memory, llm=LLMClient(FakeProvider()))

    assert terminal.ranked(VIKTOR) == []
    assert [w.id for w, _ in terminal.ranked(MEI)] == ["his"]


def test_reading_stores_a_memory_about_the_artist_with_the_works_tags(
    works: WorksStore, memory: MemoryStore
) -> None:
    tags = ["the old footbridge", "repair", "family", "boredom"]
    works.add(
        work(
            "a",
            values=CARING,
            title="The Footbridge",
            text="The arch has held for ninety-one.",
            statement="Things last when people look after them.",
            tags=tags,
        )
    )
    memory.add(feeling(MEI, "viktor", 0.9))
    fake, news = FakeProvider([REACTION]), News(0.3)
    terminal = reader(works, memory, news, LLMClient(fake))

    asyncio.run(read(terminal, MEI))

    assert read_by(memory, MEI) == [
        Memory(
            owner="mei",
            kind=MemoryKind.WORK,
            content='I read Viktor Hale\'s "The Footbridge" on the news terminal. '
            "It made me want to ring my sister.",
            salience=0.7,
            valence=0.6,
            timestamp=NOW,
            about=["viktor"],
            topics=tags[:3],
            work_id="a",
        )
    ]
    [request] = fake.requests
    asked = request.messages[-1].content
    assert "It's by Viktor Hale, who writes plain verse about old bridges." in asked
    assert "The Footbridge\n\nThe arch has held for ninety-one." in asked
    assert "Viktor Hale says of it: Things last when people look after them." in asked
    assert "You like Viktor Hale a lot" in asked
    assert "given what you care about and how you feel about Viktor Hale?" in asked
    assert request.system.startswith("You are Mei Lin")
    assert request.model == DEFAULT_CONFIG.reaction_model == Model.HAIKU_5_5


@pytest.mark.parametrize("by", [0.01, 0.1])
def test_the_terminal_falls_through_to_the_news_when_an_article_is_better(
    works: WorksStore, memory: MemoryStore, by: float
) -> None:
    works.add(work("a", values={**CARING, CoreValue.CONNECTION: 0.8, CoreValue.COMPASSION: 0.3}))
    fake, news = FakeProvider(), News()
    terminal = reader(works, memory, news, LLMClient(fake))
    [(_, interest)] = terminal.ranked(MEI)
    news.level = interest + by

    asyncio.run(read(terminal, MEI))

    assert 0.5 < interest < 0.9
    assert terminal.interest(MEI) == news.level
    assert news.read == ["mei"]
    assert fake.requests == []
    assert read_by(memory, MEI) == []


@pytest.mark.parametrize("article", [0.2, 1.0])
def test_a_work_as_interesting_as_any_article_is_read_beside_the_news(
    works: WorksStore, memory: MemoryStore, article: float
) -> None:
    works.add(work("a", values=CARING))
    news = News(article)
    terminal = reader(works, memory, news, LLMClient(FakeProvider([REACTION])))
    [(_, interest)] = terminal.ranked(MEI)

    assert interest > 1.0
    assert terminal.interest(MEI) == 1.0
    asyncio.run(read(terminal, MEI))
    assert [m.work_id for m in read_by(memory, MEI)] == ["a"]
    assert news.read == ["mei"]


def test_with_no_work_worth_reading_the_terminal_is_the_news(
    works: WorksStore, memory: MemoryStore
) -> None:
    works.add(work("dull"))
    news = News(0.4)
    terminal = reader(works, memory, news, LLMClient(FakeProvider()))

    assert terminal.ranked(MEI) == []
    assert terminal.interest(MEI) == 0.4
    asyncio.run(read(terminal, MEI))
    assert news.read == ["mei"]


def test_reads_a_work_once_even_after_a_restart(works: WorksStore, memory: MemoryStore) -> None:
    works.add(work("a", values=CARING))
    first, news = reader(works, memory, News(), LLMClient(FakeProvider([REACTION]))), News()
    asyncio.run(read(first, MEI))
    again = reader(works, memory, news, LLMClient(FakeProvider()))

    asyncio.run(read(first, MEI))
    asyncio.run(read(again, MEI))

    assert first.ranked(MEI) == again.ranked(MEI) == []
    assert [m.work_id for m in read_by(memory, MEI)] == ["a"]
    assert news.read == ["mei"]


def test_a_read_that_fails_can_be_tried_again(works: WorksStore, memory: MemoryStore) -> None:
    works.add(work("a", values=CARING))
    terminal = reader(works, memory, llm=LLMClient(FakeProvider([LLMError("limit")])))

    asyncio.run(read(terminal, MEI))

    assert read_by(memory, MEI) == []
    assert [w.id for w, _ in terminal.ranked(MEI)] == ["a"]


def test_without_an_llm_the_terminal_is_the_news(works: WorksStore, memory: MemoryStore) -> None:
    works.add(work("a", values=CARING))
    news = News(0.3)
    terminal = reader(works, memory, news)

    assert terminal.interest(MEI) == 0.3
    terminal.read(MEI)
    assert news.read == ["mei"]
