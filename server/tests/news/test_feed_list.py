import json
import logging
from pathlib import Path

import pytest

from simile.news import FEEDS, Feed, FeedList, SavedFeed, feeds
from simile.news.feed_list import DEFAULTS, Refused

BIG_THINK = SavedFeed(url="https://bigthink.com/feed", name="Big Think")


@pytest.fixture(autouse=True)
def no_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SIMILE_NEWS_FEED", raising=False)


def written(path: Path) -> list[dict[str, object]]:
    return json.loads(path.read_text())["feeds"]


def test_starts_with_the_six_feeds_and_writes_nothing(feeds_file: Path) -> None:
    listed = FeedList()

    assert listed.path == feeds_file
    assert [saved.feed for saved in listed.feeds] == list(FEEDS)
    assert all(saved.on for saved in listed.feeds)
    assert listed.defaults
    assert listed.current() == FEEDS
    assert not feeds_file.exists()


def test_adds_a_feed_and_keeps_it_after_a_restart(feeds_file: Path) -> None:
    FeedList().add(BIG_THINK)

    again = FeedList()
    assert again.feeds == [*DEFAULTS, BIG_THINK]
    assert again.current()[-1] == Feed("https://bigthink.com/feed", "Big Think")
    assert not again.defaults
    assert written(feeds_file)[-1] == {"url": BIG_THINK.url, "name": "Big Think", "on": True}


def test_switches_a_feed_off_and_on(feeds_file: Path) -> None:
    economist = FEEDS[3]
    FeedList().switch(economist.url, False)

    off = FeedList()
    assert economist not in off.current()
    assert len(off.current()) == 5
    assert [saved.on for saved in off.feeds] == [True, True, True, False, True, True]

    off.switch(economist.url, True)
    assert FeedList().current() == FEEDS


def test_removes_a_feed(feeds_file: Path) -> None:
    FeedList().remove(FEEDS[0].url)

    assert FeedList().current() == FEEDS[1:]


def test_removing_every_feed_leaves_none(feeds_file: Path) -> None:
    listed = FeedList()
    for feed in FEEDS:
        listed.remove(feed.url)

    assert FeedList().current() == ()
    assert feeds() == ()
    assert written(feeds_file) == []


def test_resets_to_the_defaults(feeds_file: Path) -> None:
    listed = FeedList()
    listed.add(BIG_THINK)
    listed.remove(FEEDS[0].url)

    listed.reset()

    assert listed.defaults
    assert listed.current() == FEEDS
    assert not feeds_file.exists()
    assert FeedList().current() == FEEDS


def test_refuses_a_feed_listed_already() -> None:
    listed = FeedList()

    with pytest.raises(Refused, match="in the list already") as refused:
        listed.add(SavedFeed(url=FEEDS[0].url))

    assert refused.value.status == 409
    assert listed.defaults


def test_takes_at_most_its_limit(feeds_file: Path) -> None:
    listed = FeedList(limit=7)
    listed.add(BIG_THINK)

    with pytest.raises(Refused, match="at most 7 feeds") as refused:
        listed.add(SavedFeed(url="https://example.com/feed"))

    assert refused.value.status == 409
    assert len(FeedList().feeds) == 7


def test_the_limit_is_twelve_by_default() -> None:
    listed = FeedList()
    for n in range(6):
        listed.add(SavedFeed(url=f"https://example.com/{n}"))

    with pytest.raises(Refused, match="at most 12 feeds"):
        listed.check("https://example.com/more")


@pytest.mark.parametrize("change", ["switch", "remove"])
def test_refuses_to_change_a_feed_not_in_the_list(feeds_file: Path, change: str) -> None:
    listed = FeedList()

    with pytest.raises(Refused, match="isn't in the list") as refused:
        if change == "switch":
            listed.switch("https://example.com/feed", False)
        else:
            listed.remove("https://example.com/feed")

    assert refused.value.status == 404
    assert not feeds_file.exists()


def test_reads_the_defaults_when_the_file_is_broken(
    feeds_file: Path, caplog: pytest.LogCaptureFixture
) -> None:
    feeds_file.parent.mkdir(parents=True)
    feeds_file.write_text('{"feeds": [{"url": 3}]}')

    with caplog.at_level(logging.WARNING):
        assert FeedList().current() == FEEDS

    assert f"since {feeds_file} can't be read" in caplog.text


def test_keeps_the_first_of_a_feed_listed_twice(feeds_file: Path) -> None:
    feeds_file.parent.mkdir(parents=True)
    feeds_file.write_text(
        json.dumps(
            {
                "feeds": [
                    {"url": "https://example.com/a", "name": "A"},
                    {"url": "https://example.com/b", "on": False},
                    {"url": "https://example.com/a", "name": "Again"},
                ]
            }
        )
    )

    assert FeedList().current() == (Feed("https://example.com/a", "A"),)


def test_the_env_overrides_the_saved_list(monkeypatch: pytest.MonkeyPatch) -> None:
    listed = FeedList()
    listed.add(BIG_THINK)
    monkeypatch.setenv("SIMILE_NEWS_FEED", f"https://example.com/feed,{FEEDS[1].url}")

    assert listed.current() == (Feed("https://example.com/feed"), FEEDS[1])
    assert feeds() == listed.current()
    assert listed.feeds[-1] == BIG_THINK


def test_feeds_reads_the_saved_list() -> None:
    FeedList().switch(FEEDS[0].url, False)

    assert feeds() == FEEDS[1:]
