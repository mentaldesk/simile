from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta

import pytest
from starlette.testclient import TestClient

from simile.app import create_app
from simile.memory import MemoryStore, memory_of
from simile.news import NewsStore, news_of
from simile.news.config import NewsConfig
from simile.news.player import PlayerNews
from simile.protocol import NewsArticle
from simile.schema import PLAYER_ID, Memory, MemoryKind, NewsItem
from simile.sim import Clock

MakePackage = Callable[[dict[str, str]], str]

NOW = datetime(2026, 3, 14, 9, tzinfo=UTC)


def article(n: int, **fields: str) -> NewsItem:
    return NewsItem.model_validate(
        {
            "id": f"item-{n}",
            "title": f"Article {n}",
            "url": f"https://example.com/{n}",
            "summary": f"What happened in article {n}.",
            "published": NOW - timedelta(hours=n),
            "source": "The Atlantic",
            **fields,
        }
    )


@pytest.fixture
def news() -> Iterator[NewsStore]:
    with NewsStore(":memory:") as store:
        yield store


@pytest.fixture
def memory() -> Iterator[MemoryStore]:
    with MemoryStore(":memory:") as store:
        yield store


@pytest.fixture
def player(news: NewsStore, memory: MemoryStore) -> PlayerNews:
    news.add(article(n) for n in range(3))
    return PlayerNews(news, memory, Clock(NOW))


def player_news(memory: MemoryStore) -> list[Memory]:
    return memory.recall(PLAYER_ID, NOW, kind=MemoryKind.NEWS, k=100)


def test_lists_an_articles_long_summary_when_it_has_one(
    news: NewsStore, memory: MemoryStore
) -> None:
    long = "The council voted for a barrier.\n\nWork starts in spring."
    news.add([article(0, long_summary=long), article(1)])

    first, second = PlayerNews(news, memory, Clock(NOW)).listing().articles

    assert (first.summary, first.long_summary) == ("What happened in article 0.", long)
    assert second.long_summary is None
    assert "long_summary" not in second.model_dump()


def test_lists_the_newest_articles_unread(news: NewsStore, memory: MemoryStore) -> None:
    news.add(article(n) for n in range(5))
    player = PlayerNews(news, memory, Clock(NOW), config=NewsConfig(articles=2))

    assert player.listing().articles == [
        NewsArticle(
            news_id="item-0",
            title="Article 0",
            source="The Atlantic",
            summary="What happened in article 0.",
            url="https://example.com/0",
            read=False,
        ),
        NewsArticle(
            news_id="item-1",
            title="Article 1",
            source="The Atlantic",
            summary="What happened in article 1.",
            url="https://example.com/1",
            read=False,
        ),
    ]


def test_reading_an_article_stores_the_players_news_memory(
    player: PlayerNews, memory: MemoryStore, news: NewsStore
) -> None:
    news.update(article(1).model_copy(update={"tags": ["drones", "law", "cities", "air"]}))

    reply = player.read("item-1")

    assert [a.read for a in reply.articles] == [False, True, False]
    assert player_news(memory) == [
        Memory(
            owner=PLAYER_ID,
            kind=MemoryKind.NEWS,
            content='I read "Article 1" in The Atlantic on the news terminal.',
            salience=0.5,
            valence=0,
            timestamp=NOW,
            topics=["drones", "law", "cities"],
            news_id="item-1",
        )
    ]
    assert player.listing() == reply


def test_reading_an_article_again_stores_nothing_more(
    player: PlayerNews, memory: MemoryStore
) -> None:
    player.read("item-2")
    player.read("item-2")

    assert [m.news_id for m in player_news(memory)] == ["item-2"]


def test_an_unknown_article_stores_nothing_and_gets_the_list(
    player: PlayerNews, memory: MemoryStore
) -> None:
    reply = player.read("nope")

    assert player_news(memory) == []
    assert [a.news_id for a in reply.articles] == ["item-0", "item-1", "item-2"]


def test_the_terminal_lists_and_reads_over_the_websocket(make_package: MakePackage) -> None:
    package = make_package(
        {
            "memory/lifespan.py": "from simile.memory.lifespan import lifespan\n",
            "news/lifespan.py": "from simile.news.lifespan import lifespan\n",
            "protocol/routes.py": "from simile.protocol.routes import routes\n",
            "sim/lifespan.py": "from simile.sim.lifespan import running\n",
        }
    )
    app = create_app(package)

    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        news_of(app).add([article(0), article(1)])
        assert ws.receive_json()["type"] == "snapshot"

        ws.send_json({"type": "list_news"})
        listed = ws.receive_json()
        ws.send_json({"type": "read_news", "news_id": "item-1"})
        read = ws.receive_json()

        memories = memory_of(app).recall(PLAYER_ID, NOW, kind=MemoryKind.NEWS)

    assert listed["type"] == read["type"] == "news"
    assert [(a["news_id"], a["read"]) for a in listed["articles"]] == [
        ("item-0", False),
        ("item-1", False),
    ]
    assert [(a["news_id"], a["read"]) for a in read["articles"]] == [
        ("item-0", False),
        ("item-1", True),
    ]
    assert [m.news_id for m in memories] == ["item-1"]
