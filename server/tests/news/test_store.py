from datetime import UTC, datetime, timedelta
from pathlib import Path

from simile.memory import MemoryStore
from simile.news import FeedState, NewsStore, parse
from simile.schema import CoreValue, Memory, MemoryKind, NewsItem

NOON = datetime(2026, 3, 14, 12, tzinfo=UTC)


def news(id: str, hours_ago: float = 0) -> NewsItem:
    return NewsItem(
        id=id,
        title=f"Story {id}",
        url=f"https://example.com/{id}",
        summary="Something happened.",
        published=NOON - timedelta(hours=hours_ago),
    )


def test_adds_only_new_items(store: NewsStore) -> None:
    a, b = news("a"), news("b")

    assert store.add([a]) == [a]
    assert store.add([b, a, b.model_copy(update={"title": "Again"})]) == [b]
    assert store.get("b") == b


def test_adds_a_story_once_even_under_another_id(store: NewsStore) -> None:
    a = news("a")
    elsewhere = news("b").model_copy(update={"url": a.url, "source": "Elsewhere"})

    assert store.add([a, elsewhere]) == [a]
    assert store.add([elsewhere]) == []
    assert store.get("b") is None


def test_stores_the_saved_feed_once(store: NewsStore, feed_xml: bytes) -> None:
    items = parse(feed_xml)

    assert store.add(items) == items
    assert store.add(parse(feed_xml)) == []
    assert store.latest(10) == items


def test_lists_the_latest_first(store: NewsStore) -> None:
    store.add([news("old", 5), news("new", 1), news("middle", 3)])

    assert [item.id for item in store.latest(2)] == ["new", "middle"]
    assert [item.id for item in store.latest()] == ["new", "middle", "old"]


def test_lists_the_latest_leaving_out_ids_already_seen(store: NewsStore) -> None:
    store.add([news("old", 5), news("new", 1), news("middle", 3)])

    assert [item.id for item in store.latest(2, exclude={"new"})] == ["middle", "old"]
    assert store.latest(exclude=["new", "middle", "old"]) == []


def test_gets_nothing_for_an_unknown_id(store: NewsStore) -> None:
    assert store.get("nope") is None


def analysed(item: NewsItem) -> NewsItem:
    return NewsItem.model_validate(
        {**item.model_dump(), "values": dict.fromkeys(CoreValue, 0.5), "tags": ["x"]}
    )


def test_writes_an_analysis_back(store: NewsStore) -> None:
    store.add([news("a"), news("b", 1)])

    assert store.update(analysed(news("a")))
    assert not store.update(analysed(news("c")))

    assert store.get("a") == analysed(news("a"))
    assert store.get("c") is None
    assert [item.id for item in store.latest(analysed=True)] == ["a"]
    assert [item.id for item in store.latest(analysed=False)] == ["b"]
    assert [item.id for item in store.latest(analysed=None)] == ["a", "b"]


def test_lists_unanalysed_items_among_the_newest(store: NewsStore) -> None:
    store.add([news("old", 5), news("new", 1), news("middle", 3), news("done", 2)])
    store.update(analysed(news("done", 2)))

    assert [item.id for item in store.unanalysed(4, "claude")] == ["new", "middle", "old"]
    assert [item.id for item in store.unanalysed(3, "claude")] == ["new", "middle"]


def test_leaves_out_what_a_provider_couldnt_analyse(store: NewsStore) -> None:
    store.add([news("a"), news("b", 1)])

    store.unanalysable("a", "canned")
    store.unanalysable("a", "canned")

    assert [item.id for item in store.unanalysed(10, "canned")] == ["b"]
    assert [item.id for item in store.unanalysed(10, "claude-code")] == ["a", "b"]
    assert [item.id for item in store.latest(analysed=False)] == ["a", "b"]


def test_remembers_each_feed(store: NewsStore) -> None:
    assert store.feed("https://example.com/feed") == FeedState()

    state = FeedState(checked=1_700_000_000.5, etag='"v1"', modified="Wed, 15 Sep 2021")
    store.set_feed("https://example.com/feed", state)

    assert store.feed("https://example.com/feed") == state
    assert store.feed("https://example.com/other") == FeedState()


def test_shares_the_memory_stores_file(tmp_path: Path) -> None:
    path = tmp_path / "data" / "simile.db"
    memory = Memory(
        owner="mei", kind=MemoryKind.NEWS, content="hi", salience=1, valence=0, timestamp=NOON
    )

    with MemoryStore(path) as memories, NewsStore(path) as store:
        memories.add(memory)
        store.add([news("a")])

    with MemoryStore(path) as memories, NewsStore(path) as store:
        assert memories.recall("mei", NOON) == [memory]
        assert store.latest() == [news("a")]
