from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError

import pytest

from simile.news import FEEDS, Feed, FeedRefused, feeds, fetch, parse
from simile.news.feed import SUMMARY_LENGTH, USER_AGENT, is_private, plain, read, shorten

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
    with pytest.raises(FeedRefused, match="That's a web page, not a feed"):
        parse(b"<html><body>Just a moment...")
    with pytest.raises(FeedRefused, match="That isn't an RSS or Atom feed"):
        parse(b'<?xml version="1.0"?><svg/>')
    with pytest.raises(FeedRefused, match="That isn't an RSS or Atom feed"):
        parse(b"")


def test_reads_the_feeds_title(feed_xml: bytes) -> None:
    assert read(feed_xml).title == "Big Think"
    assert read(rss()).items == []


def test_refuses_xml_that_declares_entities() -> None:
    laughs = (
        b'<?xml version="1.0"?><!DOCTYPE rss [<!ENTITY a "ha"><!ENTITY b "&a;&a;&a;&a;">]>'
        b'<rss version="2.0"><channel><title>&b;</title></channel></rss>'
    )

    with pytest.raises(FeedRefused, match="declares XML entities"):
        parse(laughs)


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


def test_reads_the_six_feeds_by_default(monkeypatch: pytest.MonkeyPatch, feeds_file: Path) -> None:
    monkeypatch.delenv("SIMILE_NEWS_FEED", raising=False)

    assert feeds() == FEEDS
    assert not feeds_file.exists()
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


def test_fetch_keeps_the_feeds_title(feed_server: FeedServer) -> None:
    assert fetch(Feed(feed_server.url)).title == "Big Think"


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://example.com/feed", "data:,x"])
def test_fetch_reads_only_http_and_https(url: str) -> None:
    with pytest.raises(FeedRefused, match="only over http or https"):
        fetch(Feed(url))


def test_fetch_refuses_a_web_page(feed_server: FeedServer) -> None:
    page = feed_server.add("/page", b"<!doctype html><html><head><title>Hi</title></head></html>")

    with pytest.raises(FeedRefused, match="web page"):
        fetch(Feed(page))


def test_fetch_refuses_a_feed_too_big_by_its_length(
    feed_server: FeedServer, feed_xml: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("simile.news.feed.MAX_BYTES", len(feed_xml) - 1)

    with pytest.raises(FeedRefused, match="too big for a news feed"):
        fetch(Feed(feed_server.url))


def test_fetch_stops_reading_a_feed_too_big_without_a_length(
    feed_server: FeedServer, feed_xml: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    feed_server.drips["/feed"] = 0
    monkeypatch.setattr("simile.news.feed.MAX_BYTES", len(feed_xml) // 2)

    with pytest.raises(FeedRefused, match="too big for a news feed"):
        fetch(Feed(feed_server.url))


def test_fetch_gives_up_on_a_feed_that_trickles_in(
    feed_server: FeedServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    feed_server.drips["/feed"] = 0.05
    monkeypatch.setattr("simile.news.feed.DEADLINE", 0.2)

    with pytest.raises(TimeoutError, match="took over 0.2 seconds"):
        fetch(Feed(feed_server.url))


def test_fetch_follows_a_redirect_on_the_same_machine(feed_server: FeedServer) -> None:
    feed_server.redirects["/moved"] = "/feed"

    fetched = fetch(Feed(feed_server.url_of("/moved")))

    assert fetched.items is not None and len(fetched.items) == 5
    assert feed_server.paths == ["/moved", "/feed"]


def test_fetch_wont_be_redirected_to_a_file(feed_server: FeedServer) -> None:
    feed_server.redirects["/moved"] = "file:///etc/passwd"

    with pytest.raises(FeedRefused, match="redirects to file:///etc/passwd"):
        fetch(Feed(feed_server.url_of("/moved")))


def test_fetch_wont_be_redirected_from_the_internet_to_a_private_address(
    feed_server: FeedServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("simile.news.feed.is_private", lambda host: host.startswith("10."))
    feed_server.redirects["/moved"] = "http://10.0.0.1/admin"

    with pytest.raises(FeedRefused, match="redirects to http://10.0.0.1/admin"):
        fetch(Feed(feed_server.url_of("/moved")))
    assert feed_server.paths == ["/moved"]


def test_fetch_follows_only_a_few_redirects(feed_server: FeedServer) -> None:
    for hop in range(6):
        feed_server.redirects[f"/hop{hop}"] = f"/hop{hop + 1}"
    feed_server.redirects["/hop6"] = "/feed"

    with pytest.raises(HTTPError, match="infinite loop"):
        fetch(Feed(feed_server.url_of("/hop0")))


@pytest.mark.parametrize(
    ("host", "private"),
    [("127.0.0.1", True), ("10.1.2.3", True), ("192.168.0.1", True), ("169.254.169.254", True)]
    + [("::1", True), ("8.8.8.8", False), ("2606:4700:4700::1111", False)],
)
def test_knows_a_private_address(host: str, private: bool) -> None:
    assert is_private(host) is private
