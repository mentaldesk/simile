from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError

import pytest

from simile.news import FEEDS, Feed, feeds, fetch, parse
from simile.news.feed import SUMMARY_LENGTH, USER_AGENT, plain, shorten

FeedServer = Any

FIXTURES = Path(__file__).parent / "fixtures"
OPENAI = Feed("https://openai.com/news/rss.xml", "OpenAI")
RNZ = Feed("https://www.rnz.co.nz/rss/sport.xml", "RNZ Sport")


def rss(*items: str) -> bytes:
    return (
        '<?xml version="1.0"?><rss version="2.0"><channel><title>Test</title>'
        f"{''.join(items)}</channel></rss>"
    ).encode()


def item(
    guid: str | None, title: str = "Title", date: str | None = "Mon, 13 Sep 2021 17:00:01 +0000"
) -> str:
    return (
        f"<item><title>{title}</title><link>https://example.com/{title}</link>"
        + (f"<guid>{guid}</guid>" if guid else "")
        + (f"<pubDate>{date}</pubDate>" if date else "")
        + "<description>&lt;p&gt;Hello.&lt;/p&gt;</description></item>"
    )


def test_parses_the_saved_feed(feed_xml: bytes) -> None:
    items = parse(feed_xml)

    assert len(items) == 5
    first = items[0]
    assert first.id == "https://bigthink.com/13-8/james-webb-telescope"
    assert first.url == "https://bigthink.com/13-8/james-webb-telescope"
    assert first.title == "A new window to the early universe (and aliens?)"
    assert first.published == datetime(2021, 9, 15, 16, tzinfo=UTC)
    assert first.summary.startswith("Astrophysicists anxiously await the upcoming launch")
    assert [item.published for item in items] == sorted(
        (item.published for item in items), reverse=True
    )


def test_credits_each_item_to_its_feed() -> None:
    openai = parse((FIXTURES / "openai.xml").read_bytes(), OPENAI)
    rnz = parse((FIXTURES / "rnz.xml").read_bytes(), RNZ)

    assert (len(openai), len(rnz)) == (40, 14)
    assert {(item.source, item.source_url) for item in openai} == {("OpenAI", OPENAI.url)}
    assert {(item.source, item.source_url) for item in rnz} == {("RNZ Sport", RNZ.url)}
    assert rnz[0].title == (
        "All Blacks coach Dave Rennie expresses his dismay at 'crazy' World Cup draw"
    )
    assert rnz[0].published == datetime(2026, 10, 16, 1, 49, 41, tzinfo=UTC)


def test_credits_an_unnamed_feed_to_its_title(feed_xml: bytes) -> None:
    [first, *_] = parse(feed_xml, Feed("https://example.com/feed"))

    assert (first.source, first.source_url) == ("Big Think", "https://example.com/feed")
    assert parse(feed_xml)[0].source_url == ""


def test_summaries_are_short_plain_text(feed_xml: bytes) -> None:
    for item in parse(feed_xml):
        assert "<" not in item.summary
        assert "&amp;" not in item.summary
        assert 0 < len(item.summary) <= SUMMARY_LENGTH
        assert item.summary == " ".join(item.summary.split())


def test_dedupes_entries_by_guid() -> None:
    items = parse(rss(item("a", "First"), item("b", "Second"), item("a", "Repeat")))

    assert [(item.id, item.title) for item in items] == [("a", "First"), ("b", "Second")]


def test_falls_back_to_the_link_without_a_guid() -> None:
    [only] = parse(rss(item(None, "Unguided")))

    assert only.id == "https://example.com/Unguided"


def test_skips_entries_without_a_date() -> None:
    assert [item.id for item in parse(rss(item("a", date=None), item("b")))] == ["b"]


def test_reads_atom_feeds_by_their_updated_date() -> None:
    atom = (
        b'<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><title>T</title>'
        b"<entry><id>urn:a</id><title>Atom</title><link href='https://example.com/a'/>"
        b"<updated>2026-03-14T06:30:00+13:00</updated><summary>Hi</summary></entry></feed>"
    )

    [only] = parse(atom)

    assert only.id == "urn:a"
    assert only.published == datetime(2026, 3, 13, 17, 30, tzinfo=UTC)


def test_rejects_something_that_isnt_a_feed() -> None:
    with pytest.raises(ValueError, match="not a feed"):
        parse(b"<html><body>Just a moment...")


def test_plain_text_keeps_words_whole_and_blocks_apart() -> None:
    html = "<ul><li>Fish &amp; chips</li><li>are <em>un</em>beatable.</li></ul><p>\n Yes</p>"

    assert plain(html) == "Fish & chips are unbeatable. Yes"


def test_shortens_at_a_sentence_end_past_halfway() -> None:
    text = "One two three. Four five six seven eight nine."

    assert shorten(text, 24) == "One two three."
    assert shorten(text, 20) == "One two three."


def test_shortens_at_a_word_without_a_late_sentence_end() -> None:
    assert shorten("Hi. A long sentence that keeps going on and on", 30) == (
        "Hi. A long sentence that…"
    )
    assert shorten("Short.", 30) == "Short."


def test_reads_the_six_feeds_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SIMILE_NEWS_FEED", raising=False)

    assert feeds() == FEEDS
    assert [feed.name for feed in FEEDS] == [
        "The Atlantic",
        "OpenAI",
        "Scientific American",
        "The Economist",
        "RNZ Sport",
        "IGN",
    ]


def test_feeds_can_be_overridden_with_a_list(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "SIMILE_NEWS_FEED",
        f" https://example.com/feed,{OPENAI.url},, https://example.com/feed ",
    )

    assert feeds() == (Feed("https://example.com/feed"), OPENAI)


def test_fetch_identifies_itself_and_keeps_the_validators(feed_server: FeedServer) -> None:
    fetched = fetch(Feed(feed_server.url))

    assert fetched.items is not None and len(fetched.items) == 5
    assert (fetched.etag, fetched.modified) == (feed_server.etag, feed_server.modified)
    [request] = feed_server.requests
    assert request["User-Agent"] == USER_AGENT
    assert "If-None-Match" not in request


def test_fetch_asks_only_for_changes(feed_server: FeedServer) -> None:
    etag, modified = feed_server.etag, feed_server.modified

    fetched = fetch(Feed(feed_server.url), etag, modified)

    assert fetched.items is None
    assert (fetched.etag, fetched.modified) == (etag, modified)
    [request] = feed_server.requests
    assert request["If-None-Match"] == etag
    assert request["If-Modified-Since"] == modified


def test_fetch_raises_on_a_server_error(feed_server: FeedServer) -> None:
    feed_server.errors["/feed"] = 503

    with pytest.raises(HTTPError):
        fetch(Feed(feed_server.url))
