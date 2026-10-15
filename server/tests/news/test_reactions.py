import asyncio
import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from simile.llm import FakeProvider, LLMClient, LLMError, Model, Request
from simile.memory import MemoryStore
from simile.news import NewsStore
from simile.news.reactions import NewsConfig, NewsReader, Reaction, topics_to_raise
from simile.schema import CoreValue, Memory, MemoryKind, NewsItem, Npc
from simile.sim import Clock

NOW = datetime(2026, 3, 14, 9, tzinfo=UTC)
MEI = Npc.model_validate_json(
    (Path(__file__).parents[1] / "fixtures" / "npcs" / "mei.json").read_text()
)
RULES = NewsItem(
    id="rules",
    title="Why the best rules are made to be broken",
    url="https://example.com/rules",
    summary="A historian argues that progress comes from people who ignore the rules.",
    published=NOW - timedelta(hours=2),
)
SHRUG = Reaction(take="Huh.", valence=0.1, intensity=0.2, topics=["news"]).model_dump_json()


def npc(id: str, **values: float) -> Npc:
    return MEI.model_copy(
        update={"id": id, "values": {value: values.get(value.value, 0.5) for value in CoreValue}}
    )


def article(n: int) -> NewsItem:
    return NewsItem(
        id=f"item-{n}",
        title=f"Article {n}",
        url=f"https://example.com/{n}",
        summary=f"What happened in article {n}.",
        published=NOW - timedelta(hours=n),
    )


def judge(request: Request) -> str:
    """Stands in for the model: the more the reader values obedience, the worse rule-breaking
    lands."""
    match = re.search(r"obedience (\d\.\d+)", request.system)
    assert match, "the reader's obedience isn't in the prompt"
    assert RULES.title in request.messages[-1].content
    valence = 1 - 2 * float(match[1])
    return Reaction(
        take="Rules are there for a reason." if valence < 0 else "About time someone said it.",
        valence=valence,
        intensity=abs(valence),
        topics=[" Rules ", "civic life", "", "history", "progress"],
    ).model_dump_json()


@pytest.fixture
def news() -> Iterator[NewsStore]:
    with NewsStore(":memory:") as store:
        yield store


@pytest.fixture
def memory() -> Iterator[MemoryStore]:
    with MemoryStore(":memory:") as store:
        yield store


def reader_for(
    news: NewsStore, memory: MemoryStore, fake: FakeProvider, **config: object
) -> NewsReader:
    client = LLMClient(fake)
    return NewsReader(
        news, memory, Clock(NOW), lambda: client, config=NewsConfig.model_validate(config)
    )


async def settle(reader: NewsReader) -> None:
    await asyncio.gather(*reader.tasks)


def news_memories(memory: MemoryStore, owner: str) -> list[Memory]:
    return memory.recall(owner, NOW, kind=MemoryKind.NEWS, k=100)


def read_titles(fake: FakeProvider) -> list[str]:
    return [request.messages[-1].content.split("\n")[2] for request in fake.requests]


@pytest.mark.anyio
async def test_an_article_clashing_with_a_high_value_lands_badly(
    news: NewsStore, memory: MemoryStore
) -> None:
    news.add([RULES])
    fake = FakeProvider([judge, judge])
    reader = reader_for(news, memory, fake)
    stickler, rebel = npc("stickler", obedience=0.95), npc("rebel", obedience=0.1)

    reader.read(stickler)
    reader.read(rebel)
    await settle(reader)

    [reaction] = news_memories(memory, "stickler")
    assert reaction.valence == pytest.approx(-0.9)
    assert reaction.salience == pytest.approx(0.9)
    assert reaction.news_id == RULES.id
    assert reaction.timestamp == NOW
    assert reaction.content == f'I read "{RULES.title}" on the news terminal. ' + (
        "Rules are there for a reason."
    )
    assert reaction.topics == ["rules", "civic life", "history"]
    [other] = news_memories(memory, "rebel")
    assert other.valence == pytest.approx(0.8)
    assert all(request.model == Model.HAIKU for request in fake.requests)


@pytest.mark.anyio
async def test_reads_the_newest_unread_articles_a_few_at_a_time(
    news: NewsStore, memory: MemoryStore
) -> None:
    news.add(article(n) for n in range(5))
    fake = FakeProvider(default=SHRUG)
    reader = reader_for(news, memory, fake, per_visit=2)
    mei = npc("mei")

    for _ in range(4):
        reader.read(mei)
        await settle(reader)

    assert read_titles(fake) == [f"Article {n}" for n in range(5)]
    assert {m.news_id for m in news_memories(memory, "mei")} == {f"item-{n}" for n in range(5)}


@pytest.mark.anyio
async def test_reading_doesnt_block_the_tick(news: NewsStore, memory: MemoryStore) -> None:
    news.add(article(n) for n in range(3))
    replied = asyncio.Event()
    fake = FakeProvider([[replied, SHRUG]], default=SHRUG)
    reader = reader_for(news, memory, fake, per_visit=1)
    mei = npc("mei")

    reader.read(mei)
    reader.read(mei)
    await asyncio.wait(reader.tasks, return_when=asyncio.FIRST_COMPLETED)

    assert [m.news_id for m in news_memories(memory, "mei")] == ["item-1"]
    replied.set()
    await settle(reader)
    assert {m.news_id for m in news_memories(memory, "mei")} == {"item-0", "item-1"}


@pytest.mark.anyio
async def test_an_article_that_failed_is_read_on_the_next_visit(
    news: NewsStore, memory: MemoryStore
) -> None:
    news.add(article(n) for n in range(2))
    fake = FakeProvider([LLMError("usage limit reached")], default=SHRUG)
    reader = reader_for(news, memory, fake)
    mei = npc("mei")

    reader.read(mei)
    await settle(reader)
    assert news_memories(memory, "mei") == []

    reader.read(mei)
    await settle(reader)
    assert read_titles(fake) == ["Article 0", "Article 0", "Article 1"]
    assert len(news_memories(memory, "mei")) == 2


@pytest.mark.anyio
async def test_remembers_what_was_read_before_a_restart(
    news: NewsStore, memory: MemoryStore
) -> None:
    news.add(article(n) for n in range(3))
    first = FakeProvider(default=SHRUG)
    reader = reader_for(news, memory, first)
    reader.read(npc("mei"))
    await settle(reader)

    second = FakeProvider(default=SHRUG)
    restarted = reader_for(news, memory, second)
    restarted.read(npc("mei"))
    restarted.read(npc("mei"))
    await settle(restarted)

    assert read_titles(first) == ["Article 0", "Article 1"]
    assert read_titles(second) == ["Article 2"]


def test_reads_nothing_without_an_llm(news: NewsStore, memory: MemoryStore) -> None:
    news.add([RULES])
    reader = NewsReader(news, memory, Clock(NOW), lambda: None)

    reader.read(npc("mei"))

    assert reader.tasks == set()
    assert reader.seen == {}


@pytest.mark.anyio
async def test_stop_abandons_reading(news: NewsStore, memory: MemoryStore) -> None:
    news.add([RULES])
    reader = reader_for(news, memory, FakeProvider([[asyncio.Event(), SHRUG]]))

    reader.read(npc("mei"))
    await reader.stop()

    assert reader.tasks == set()
    assert news_memories(memory, "mei") == []


def reaction(owner: str, content: str, intensity: float, hours_ago: float) -> Memory:
    return Memory(
        owner=owner,
        kind=MemoryKind.NEWS,
        content=content,
        salience=intensity,
        valence=-0.5,
        timestamp=NOW - timedelta(hours=hours_ago),
        news_id=content,
    )


def test_ranking_favours_recent_and_intense_reactions(memory: MemoryStore) -> None:
    memory.add(
        reaction("mei", "strong, old", 0.9, 72),
        reaction("mei", "weak, recent", 0.2, 1),
        reaction("mei", "faded", 0.2, 72),
        reaction("mei", "strong, recent", 0.9, 1),
        reaction("mei", "middling, this morning", 0.5, 12),
        reaction("suki", "someone else's", 1.0, 0),
        reaction("mei", "a chat", 1.0, 0).model_copy(update={"kind": MemoryKind.CONVERSATION}),
    )

    def raised(k: int) -> list[str]:
        return [m.content for m in topics_to_raise(memory, "mei", NOW, k)]

    assert raised(10) == ["strong, recent", "middling, this morning", "weak, recent", "strong, old"]
    assert raised(3) == ["strong, recent", "middling, this morning", "weak, recent"]


def test_nothing_to_raise_without_news(memory: MemoryStore) -> None:
    assert topics_to_raise(memory, "mei", NOW) == []
