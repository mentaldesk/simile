import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta

import pytest

from simile.llm import FakeProvider, LLMClient, LLMError, Model
from simile.news import NewsStore
from simile.news.analysis import NewsAnalyser, analyse
from simile.news.config import NewsConfig
from simile.schema import CoreValue, NewsItem

NOW = datetime(2026, 3, 14, 9, tzinfo=UTC)


def article(n: int) -> NewsItem:
    return NewsItem(
        id=f"item-{n}",
        title=f"Article {n}",
        url=f"https://example.com/{n}",
        summary=f"What happened in article {n}.",
        published=NOW - timedelta(hours=n),
        source="The Atlantic",
    )


def reply(**changes: object) -> str:
    scores: dict[str, object] = {value.value: 0 for value in CoreValue}
    scores.update(justice=9, compassion=6.5)
    return json.dumps({"tags": ["Courts", "law"], "sentiment": 2.5, **scores, **changes})


def without(value: CoreValue) -> str:
    data = json.loads(reply())
    del data[value.value]
    return json.dumps(data)


def analyser_for(
    store: NewsStore, fake: FakeProvider, **config: object
) -> tuple[NewsAnalyser, LLMClient]:
    client = LLMClient(fake)
    return NewsAnalyser(store, lambda: client, config=NewsConfig.model_validate(config)), client


@pytest.mark.anyio
async def test_an_article_is_analysed_against_every_value_in_one_call() -> None:
    fake = FakeProvider([reply()])

    item = await analyse(LLMClient(fake), article(0))

    assert item.analysed
    assert item.values[CoreValue.JUSTICE] == pytest.approx(0.9)
    assert item.values[CoreValue.COMPASSION] == pytest.approx(0.65)
    assert item.values[CoreValue.OPTIMISM] == 0.0
    assert item.tags == ["courts", "law"]
    assert item.sentiment == pytest.approx(-0.5)
    assert item.model_copy(update={"values": {}, "tags": [], "sentiment": None}) == article(0)
    [request] = fake.requests
    assert request.model == Model.HAIKU_5_5
    assert request.messages[-1].content == (
        "Article 0 (The Atlantic)\n\nWhat happened in article 0."
    )
    assert all(f"- {value.value}: " in request.system for value in CoreValue)
    assert all(f'"{value.value}"' in request.system for value in CoreValue)


@pytest.mark.anyio
async def test_tags_are_tidied_to_fit() -> None:
    tags = ["Drones", "  drone   law ", "drones", "", "x" * 41, *(f"tag {n}" for n in range(12))]
    fake = FakeProvider([reply(tags=tags)])

    item = await analyse(LLMClient(fake), article(0))

    assert item.tags == ["drones", "drone law", *(f"tag {n}" for n in range(8))]


@pytest.mark.anyio
async def test_a_reply_leaving_out_a_value_is_asked_again() -> None:
    fake = FakeProvider([without(CoreValue.OPTIMISM), reply()])

    item = await analyse(LLMClient(fake), article(0))

    assert item.analysed
    assert len(fake.requests) == 2
    assert "optimism" in fake.requests[1].messages[-1].content


@pytest.mark.anyio
async def test_analyses_each_waiting_article_once_newest_first(store: NewsStore) -> None:
    store.add(article(n) for n in range(3))
    fake = FakeProvider(default=reply())
    analyser, _ = analyser_for(store, fake)

    analysed = await analyser.analyse_pending()
    again = await analyser.analyse_pending()

    assert [item.id for item in analysed] == ["item-0", "item-1", "item-2"]
    assert again == []
    assert len(fake.requests) == 3
    assert all(item.analysed for item in store.latest())


@pytest.mark.anyio
async def test_only_the_newest_are_analysed(store: NewsStore) -> None:
    store.add(article(n) for n in range(3))
    fake = FakeProvider(default=reply())
    analyser, _ = analyser_for(store, fake, candidates=2)

    await analyser.analyse_pending()

    assert [item.id for item in store.latest(analysed=False)] == ["item-2"]


@pytest.mark.anyio
async def test_an_article_that_cant_be_analysed_is_left_out_and_not_asked_again(
    store: NewsStore, caplog: pytest.LogCaptureFixture
) -> None:
    store.add(article(n) for n in range(3))
    fake = FakeProvider(["Gibberish", "More gibberish", "Nonsense", "Rubbish"], default=reply())
    analyser, _ = analyser_for(store, fake)

    with caplog.at_level(logging.DEBUG, logger="simile.news.analysis"):
        analysed = await analyser.analyse_pending()
        await analyser.analyse_pending()

    assert [item.id for item in analysed] == ["item-2"]
    assert len(fake.requests) == 5
    assert [item.id for item in store.latest(analysed=False)] == ["item-0", "item-1"]
    failures = [r for r in caplog.records if "couldn't analyse" in r.getMessage()]
    assert [r.levelno for r in failures] == [logging.WARNING, logging.DEBUG]
    assert failures[0].getMessage() == "fake couldn't analyse 'Article 0', so left it out"


@pytest.mark.anyio
async def test_another_provider_tries_what_one_couldnt_analyse(store: NewsStore) -> None:
    store.add([article(0)])
    canned = FakeProvider(default="Can't complain.")
    await analyser_for(store, canned)[0].analyse_pending()

    claude = FakeProvider(default=reply())
    claude.name = "claude-code"
    await analyser_for(store, claude)[0].analyse_pending()

    assert len(claude.requests) == 1
    assert store.latest(analysed=True) != []


@pytest.mark.anyio
async def test_a_failed_call_stops_until_next_time(store: NewsStore) -> None:
    store.add(article(n) for n in range(2))
    fake = FakeProvider([LLMError("usage limit reached")], default=reply())
    analyser, _ = analyser_for(store, fake)

    assert await analyser.analyse_pending() == []
    assert len(fake.requests) == 1
    assert len(await analyser.analyse_pending()) == 2


@pytest.mark.anyio
async def test_checks_for_new_articles_on_the_sim_loop_without_blocking_it(
    store: NewsStore,
) -> None:
    store.add([article(0)])
    answer = asyncio.Event()
    fake = FakeProvider([[answer, reply()]], default=reply())
    analyser, _ = analyser_for(store, fake, analyse_every=timedelta(minutes=1))

    analyser.tick(0.1)
    first = analyser.task
    analyser.tick(0.1)
    assert first is not None and analyser.task is first
    answer.set()
    await first
    store.add([article(-1)])
    analyser.tick(30)
    assert analyser.task is None
    analyser.tick(30)
    assert analyser.task is not None
    await analyser.task

    assert len(fake.requests) == 2
    assert all(item.analysed for item in store.latest())


@pytest.mark.anyio
async def test_does_nothing_without_an_llm(store: NewsStore) -> None:
    store.add([article(0)])
    analyser = NewsAnalyser(store, lambda: None)

    analyser.tick(0.1)
    assert analyser.task is not None
    assert await analyser.task == []
    assert store.latest(analysed=True) == []


@pytest.mark.anyio
async def test_stop_abandons_analysis(store: NewsStore) -> None:
    store.add([article(0)])
    analyser, _ = analyser_for(store, FakeProvider([[asyncio.Event(), reply()]]))

    analyser.tick(60)
    await asyncio.sleep(0)
    await analyser.stop()

    assert store.latest(analysed=True) == []
