import json
from datetime import UTC, datetime, timedelta

import pytest

from simile.llm import FakeProvider, LLMClient
from simile.news import Feed, Fetched, NewsStore, refresh
from simile.news.analysis import NewsAnalyser
from simile.news.bundled import bundled, fall_back
from simile.news.config import DEFAULT_CONFIG
from simile.news.refresh import too_short
from simile.schema import CoreValue, NewsItem

NOW = datetime(2026, 10, 17, 9, tzinfo=UTC)


def live(n: int) -> NewsItem:
    return NewsItem(
        id=f"live-{n}",
        title=f"Live article {n}",
        url=f"https://example.com/live/{n}",
        summary=f"What happened in live article {n}.",
        published=NOW - timedelta(hours=n),
        source="The Atlantic",
    )


def newest_first(items: list[NewsItem]) -> list[NewsItem]:
    return sorted(items, key=lambda item: item.published, reverse=True)


def test_the_bundled_articles_are_analysed_and_all_fit_on_a_terminal() -> None:
    articles = bundled()

    assert 0 < len(articles) <= DEFAULT_CONFIG.articles
    assert all(set(item.values) == set(CoreValue) for item in articles)
    assert all(item.tags and item.sentiment is not None for item in articles)
    assert not any(too_short(item) for item in articles)
    assert len({item.id for item in articles}) == len(articles)
    assert len({item.url for item in articles}) == len(articles)


def test_falls_back_on_the_bundled_articles_while_no_news_is_stored(store: NewsStore) -> None:
    assert newest_first(fall_back(store)) == newest_first(bundled())
    assert fall_back(store) == []
    assert store.latest(100) == newest_first(bundled())


def test_doesnt_fall_back_once_any_news_is_stored(store: NewsStore) -> None:
    store.add([live(0)])

    assert fall_back(store) == []
    assert store.latest(100) == [live(0)]


@pytest.mark.anyio
async def test_a_feeds_copy_of_a_bundled_article_isnt_stored_again(store: NewsStore) -> None:
    fall_back(store)
    original = bundled()[0]
    copy = original.model_copy(update={"values": {}, "tags": [], "sentiment": None})

    refreshed = await refresh(
        store, Feed("https://example.com/feed"), fetch=lambda *_: Fetched([copy, live(0)])
    )

    assert refreshed.added == [live(0)]
    assert store.get(original.id) == original


@pytest.mark.anyio
async def test_only_the_live_articles_are_analysed(store: NewsStore) -> None:
    fall_back(store)
    store.add([live(0), live(1)])
    scores = {value.value: 0 for value in CoreValue}
    fake = FakeProvider(default=json.dumps({"tags": ["news"], "sentiment": 5, **scores}))
    client = LLMClient(fake)

    analysed = await NewsAnalyser(store, lambda: client).analyse_pending()

    assert [item.id for item in analysed] == ["live-0", "live-1"]
    assert len(fake.requests) == 2
    assert all(store.get(item.id) == item for item in bundled())
