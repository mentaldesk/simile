import asyncio
import logging
import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from simile.llm import FakeProvider, LLMClient, LLMError, Model, Request
from simile.memory import MemoryStore
from simile.news import NewsStore
from simile.news.reactions import NewsConfig, NewsReader, Reaction, mentioned, topics_to_raise
from simile.schema import CoreValue, Memory, MemoryKind, NewsItem, Npc
from simile.sim import Clock

NOW = datetime(2026, 3, 14, 9, tzinfo=UTC)
MEI = Npc.model_validate_json(
    (Path(__file__).parents[1] / "fixtures" / "npcs" / "mei.json").read_text()
)
SHRUG = Reaction(take="Huh.", valence=0.1, intensity=0.2, topics=["news"]).model_dump_json()


def npc(id: str, **values: float) -> Npc:
    return MEI.model_copy(
        update={"id": id, "values": {value: values.get(value.value, 0.5) for value in CoreValue}}
    )


def analysed(item: NewsItem, **related: float) -> NewsItem:
    values = {value: related.get(value.value, 0.0) for value in CoreValue}
    return NewsItem.model_validate({**item.model_dump(), "values": values})


def article(n: int, **related: float) -> NewsItem:
    item = NewsItem(
        id=f"item-{n}",
        title=f"Article {n}",
        url=f"https://example.com/{n}",
        summary=f"What happened in article {n}.",
        published=NOW - timedelta(hours=n),
    )
    return analysed(item, **(related or {"knowledge": 0.8}))


RULES = analysed(
    NewsItem(
        id="rules",
        title="Why the best rules are made to be broken",
        url="https://example.com/rules",
        summary="A historian argues that progress comes from people who ignore the rules.",
        published=NOW - timedelta(hours=2),
        source="The Atlantic",
        source_url="https://www.theatlantic.com/feed/best-of/",
    ),
    obedience=0.9,
    freedom=0.8,
)
MEI_READS = npc("mei", knowledge=0.95)


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
    return [request.messages[0].content.split("\n")[2] for request in fake.requests]


@pytest.mark.anyio
async def test_an_article_clashing_with_a_high_value_lands_badly(
    news: NewsStore, memory: MemoryStore
) -> None:
    news.add([RULES])
    fake = FakeProvider([judge, judge])
    reader = reader_for(news, memory, fake)
    stickler, rebel = npc("stickler", obedience=0.95), npc("rebel", obedience=0.1, freedom=0.95)

    reader.read(stickler)
    reader.read(rebel)
    await settle(reader)

    [reaction] = news_memories(memory, "stickler")
    assert reaction.valence == pytest.approx(-0.9)
    assert reaction.salience == pytest.approx(0.9)
    assert reaction.news_id == RULES.id
    assert reaction.timestamp == NOW
    assert reaction.content == f'I read "{RULES.title}" in The Atlantic on the news terminal. ' + (
        "Rules are there for a reason."
    )
    assert reaction.topics == ["rules", "civic life", "history"]
    [other] = news_memories(memory, "rebel")
    assert other.valence == pytest.approx(0.8)
    assert all(request.model == Model.HAIKU_5_5 for request in fake.requests)
    assert (
        fake.requests[0]
        .messages[-1]
        .content.startswith("You've just read this in The Atlantic on the village news terminal.")
    )


@pytest.mark.anyio
async def test_an_article_from_an_unnamed_feed_is_read_on_the_terminal(
    news: NewsStore, memory: MemoryStore
) -> None:
    news.add([article(0)])
    fake = FakeProvider(default=SHRUG)
    reader = reader_for(news, memory, fake)

    reader.read(MEI_READS)
    await settle(reader)

    [reaction] = news_memories(memory, "mei")
    assert reaction.content == 'I read "Article 0" on the news terminal. Huh.'
    assert (
        fake.requests[0]
        .messages[-1]
        .content.startswith("You've just read this on the village news terminal.")
    )


@pytest.mark.anyio
async def test_reads_one_article_a_visit_the_most_interesting_first(
    news: NewsStore, memory: MemoryStore
) -> None:
    news.add([article(0, knowledge=0.6), article(1, knowledge=0.9), article(2, knowledge=0.75)])
    fake = FakeProvider(default=SHRUG)
    reader = reader_for(news, memory, fake)

    for visits in range(1, 5):
        reader.read(MEI_READS)
        await settle(reader)
        assert len(fake.requests) == min(visits, 3)

    assert read_titles(fake) == ["Article 1", "Article 2", "Article 0"]
    assert {m.news_id for m in news_memories(memory, "mei")} == {"item-0", "item-1", "item-2"}


@pytest.mark.anyio
async def test_different_residents_read_different_articles(
    news: NewsStore, memory: MemoryStore
) -> None:
    news.add([article(0, justice=0.9, equality=0.4), article(1, pleasure=0.9, adventure=0.5)])
    fake = FakeProvider(default=SHRUG)
    reader = reader_for(news, memory, fake)

    reader.read(npc("fair", justice=0.95))
    reader.read(npc("fun", pleasure=0.95))
    reader.read(npc("neither"))
    await settle(reader)

    assert [m.news_id for m in news_memories(memory, "fair")] == ["item-0"]
    assert [m.news_id for m in news_memories(memory, "fun")] == ["item-1"]
    assert news_memories(memory, "neither") == []
    assert len(fake.requests) == 2


@pytest.mark.anyio
async def test_nothing_below_the_threshold_is_read(news: NewsStore, memory: MemoryStore) -> None:
    news.add([article(0, knowledge=0.4), article(1, knowledge=0.9)])
    fake = FakeProvider(default=SHRUG)
    reader = reader_for(news, memory, fake, min_interest=0.5)

    assert reader.interest(MEI_READS) == pytest.approx((0.95 * 2 - 1) * 0.9)
    reader.read(MEI_READS)
    await settle(reader)
    assert reader.interest(MEI_READS) == 0.0
    reader.read(MEI_READS)
    await settle(reader)

    assert read_titles(fake) == ["Article 1"]
    assert [item for item, _ in reader.ranked(MEI_READS)] == []


@pytest.mark.anyio
async def test_skips_articles_not_yet_analysed(news: NewsStore, memory: MemoryStore) -> None:
    fresh = article(0).model_copy(update={"values": {}})
    news.add([fresh, article(1)])
    fake = FakeProvider(default=SHRUG)
    reader = reader_for(news, memory, fake)

    reader.read(MEI_READS)
    reader.read(MEI_READS)
    await settle(reader)

    assert read_titles(fake) == ["Article 1"]


def test_interest_is_capped_at_one(news: NewsStore, memory: MemoryStore) -> None:
    news.add([article(0, knowledge=1.0, honesty=1.0, justice=1.0)])
    reader = reader_for(news, memory, FakeProvider())
    keen = npc("keen", knowledge=1.0, honesty=1.0, justice=1.0)

    assert reader.ranked(keen)[0][1] > 1
    assert reader.interest(keen) == 1.0


@pytest.mark.anyio
async def test_reading_doesnt_block_the_tick(news: NewsStore, memory: MemoryStore) -> None:
    news.add([article(0, knowledge=0.9), article(1, knowledge=0.7)])
    replied = asyncio.Event()
    fake = FakeProvider([[replied, SHRUG]], default=SHRUG)
    reader = reader_for(news, memory, fake)

    reader.read(MEI_READS)
    reader.read(MEI_READS)
    await asyncio.wait(reader.tasks, return_when=asyncio.FIRST_COMPLETED)

    assert [m.news_id for m in news_memories(memory, "mei")] == ["item-1"]
    replied.set()
    await settle(reader)
    assert {m.news_id for m in news_memories(memory, "mei")} == {"item-0", "item-1"}


@pytest.mark.anyio
async def test_an_article_that_failed_is_read_on_the_next_visit(
    news: NewsStore, memory: MemoryStore
) -> None:
    news.add([article(0, knowledge=0.9), article(1, knowledge=0.7)])
    fake = FakeProvider([LLMError("usage limit reached")], default=SHRUG)
    reader = reader_for(news, memory, fake)

    reader.read(MEI_READS)
    await settle(reader)
    assert news_memories(memory, "mei") == []

    reader.read(MEI_READS)
    await settle(reader)
    reader.read(MEI_READS)
    await settle(reader)
    assert read_titles(fake) == ["Article 0", "Article 0", "Article 1"]
    assert len(news_memories(memory, "mei")) == 2


@pytest.mark.anyio
async def test_an_article_that_cant_be_rated_is_skipped(
    news: NewsStore, memory: MemoryStore, caplog: pytest.LogCaptureFixture
) -> None:
    news.add([article(0, knowledge=0.9), article(1, knowledge=0.7)])
    fake = FakeProvider(["Interesting!", "Very interesting!"], default=SHRUG)
    reader = reader_for(news, memory, fake)

    reader.read(MEI_READS)
    await settle(reader)
    reader.read(MEI_READS)
    await settle(reader)

    assert read_titles(fake) == ["Article 0", "Article 0", "Article 1"]
    assert [m.news_id for m in news_memories(memory, "mei")] == ["item-1"]
    [warning] = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert warning.getMessage() == "mei couldn't rate 'Article 0', so skipped it"
    assert warning.exc_info is None


@pytest.mark.anyio
async def test_conversations_go_ahead_of_reading(news: NewsStore, memory: MemoryStore) -> None:
    news.add([article(0)])
    busy = asyncio.Event()

    def answer(request: Request) -> str:
        return SHRUG if request.messages[-1].content.startswith("You've just read") else "Hi."

    fake = FakeProvider([[busy, "Done."], answer, answer])
    client = LLMClient(fake, max_concurrency=1)
    reader = NewsReader(news, memory, Clock(NOW), lambda: client)

    first = asyncio.create_task(client.complete("Busy"))
    await asyncio.sleep(0)
    reader.read(MEI_READS)
    await asyncio.sleep(0)
    line = asyncio.create_task(client.complete("Hello"))
    await asyncio.sleep(0)
    busy.set()
    await asyncio.gather(first, line, *reader.tasks)

    prompts = [request.messages[-1].content for request in fake.requests]
    assert prompts[:2] == ["Busy", "Hello"]
    assert len(news_memories(memory, "mei")) == 1


@pytest.mark.anyio
async def test_remembers_what_was_read_before_a_restart(
    news: NewsStore, memory: MemoryStore
) -> None:
    news.add(article(n, knowledge=0.9 - n / 10) for n in range(3))
    first = FakeProvider(default=SHRUG)
    reader = reader_for(news, memory, first)
    reader.read(MEI_READS)
    await settle(reader)
    reader.read(MEI_READS)
    await settle(reader)

    second = FakeProvider(default=SHRUG)
    restarted = reader_for(news, memory, second)
    restarted.read(MEI_READS)
    await settle(restarted)
    restarted.read(MEI_READS)
    await settle(restarted)

    assert read_titles(first) == ["Article 0", "Article 1"]
    assert read_titles(second) == ["Article 2"]


def test_reads_nothing_without_an_llm(news: NewsStore, memory: MemoryStore) -> None:
    news.add([RULES])
    reader = NewsReader(news, memory, Clock(NOW), lambda: None)
    stickler = npc("stickler", obedience=0.95)

    reader.read(stickler)

    assert reader.interest(stickler) == 0.0
    assert reader.tasks == set()
    assert reader.seen == {}


@pytest.mark.anyio
async def test_stop_abandons_reading(news: NewsStore, memory: MemoryStore) -> None:
    news.add([RULES])
    reader = reader_for(news, memory, FakeProvider([[asyncio.Event(), SHRUG]]))

    reader.read(npc("stickler", obedience=0.95))
    await reader.stop()

    assert reader.tasks == set()
    assert news_memories(memory, "stickler") == []


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


def took_in(owner: str, title: str, *topics: str) -> Memory:
    return Memory(
        owner=owner,
        kind=MemoryKind.NEWS,
        content=f'I read "{title}" in BBC News on the news terminal. Wow.',
        salience=0.5,
        valence=0.3,
        timestamp=NOW - timedelta(hours=1),
        topics=list(topics),
        news_id=title,
    )


def test_a_line_naming_an_article_brings_back_the_take_on_it(memory: MemoryStore) -> None:
    memory.add(
        took_in("mei", "Colonising Mars by 2050", "space travel"),
        took_in("mei", "Tidal barrier for the river", "flooding"),
        took_in("suki", "Bees in decline", "pollinators"),
    )

    def recalled(said: str) -> list[str | None]:
        return [m.news_id for m in mentioned(memory, "mei", said, NOW)]

    assert recalled("Did you hear about the tidal barrier?") == ["Tidal barrier for the river"]
    assert recalled("They want to colonise Mars!") == ["Colonising Mars by 2050"]
    assert recalled("More floods by the river") == ["Tidal barrier for the river"]
    assert recalled("Is space travel worth it?") == ["Colonising Mars by 2050"]
    assert recalled("Bees are in decline, you know.") == []
    assert recalled("Mars is so bright tonight.") == []
    assert recalled("I read the BBC News on the terminal.") == []
    assert recalled("") == []


def test_the_article_sharing_most_words_comes_first(memory: MemoryStore) -> None:
    memory.add(
        took_in("mei", "River barrier plans"),
        took_in("mei", "Tidal barrier for the river"),
    )

    def recalled(said: str, **config: int) -> list[str | None]:
        found = mentioned(memory, "mei", said, NOW, config=NewsConfig(**config))
        return [m.news_id for m in found]

    said = "That tidal barrier on the river!"
    assert recalled(said) == ["Tidal barrier for the river", "River barrier plans"]
    assert recalled(said, mentions=1) == ["Tidal barrier for the river"]
    assert recalled(said, mentions=0) == []
    assert recalled("The river!") == []
    assert len(recalled("The river!", mention_words=1)) == 2


def stored(title: str, tags: list[str], summary: str) -> NewsItem:
    return NewsItem(
        id=title,
        title=title,
        url=f"https://example.com/{len(title)}",
        summary=summary,
        published=NOW - timedelta(hours=2),
        tags=tags,
    )


ROVER = stored(
    "Mission to the red planet",
    ["space exploration", "robots"],
    "Engineers test a new rover in the desert.",
)
OUTAGE = stored(
    "Internet outage hits millions",
    ["broadband"],
    "Homes lost their connection for hours.",
)


def test_the_stored_articles_tags_and_summary_count_too(memory: MemoryStore) -> None:
    memory.add(took_in("mei", ROVER.title), took_in("mei", "Tidal barrier for the river"))

    def recalled(said: str, store: dict[str, NewsItem]) -> list[str | None]:
        return [m.news_id for m in mentioned(memory, "mei", said, NOW, article=store.get)]

    assert recalled("Those robots out in the desert!", {ROVER.id: ROVER}) == [ROVER.title]
    assert recalled("Those robots out in the desert!", {}) == []
    assert recalled("A mission to another planet.", {}) == [ROVER.title]
    assert recalled("That tidal barrier!", {ROVER.id: ROVER}) == ["Tidal barrier for the river"]


@pytest.mark.parametrize(
    ("said", "recalled"),
    [
        ("Did you see the Mars piece?", ["Colonising Mars by 2050"]),
        ("That broadband story, wow.", [OUTAGE.title]),
        ("Mars is so bright tonight.", []),
        ("Did you read about the colonies?", []),
        ("Tell me the story of your life.", []),
        ("I read about the international summit.", []),
    ],
)
def test_naming_the_news_lets_one_exact_word_do(
    memory: MemoryStore, said: str, recalled: list[str]
) -> None:
    memory.add(
        took_in("mei", "Colonising Mars by 2050", "space travel"),
        took_in("mei", OUTAGE.title),
    )

    found = mentioned(memory, "mei", said, NOW, article={OUTAGE.id: OUTAGE}.get)

    assert [m.news_id for m in found] == recalled
