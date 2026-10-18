import threading
from datetime import UTC, datetime
from email.message import Message
from pathlib import Path
from typing import Any
from urllib.error import HTTPError

import pytest

from simile.news import FeedRefused, NewsStore
from simile.news.article import NoText, article_text, capped, main_text, page, read_page
from simile.news.config import NewsConfig
from simile.news.feed import USER_AGENT
from simile.schema import NewsItem

FeedServer = Any
Pages = Any

PAGE = (Path(__file__).parent / "fixtures" / "article.html").read_bytes()
NOW = datetime(2026, 10, 18, 9, tzinfo=UTC)
URL = "https://example.com/barrier"
FEED_URL = "https://example.com/feed"


def barrier() -> NewsItem:
    return NewsItem(
        id="barrier",
        title="River town votes for a tidal barrier",
        url=URL,
        summary="Councillors vote for a barrier across the estuary.",
        published=NOW,
        source="The Valley Courier",
        source_url=FEED_URL,
    )


def words(n: int) -> str:
    return " ".join(f"word{i}" for i in range(n))


def test_finds_the_article_on_a_page_without_its_furniture() -> None:
    found = main_text(PAGE, URL)

    assert found.startswith(
        "River town votes for a tidal barrier\nCouncillors in the river town of Wexley voted"
    )
    assert found.endswith("how the oyster beds will be monitored once the work begins.")
    for furniture in ["Subscribe", "Most read", "Bakery", "newsletter", "rights", "dataLayer"]:
        assert furniture not in found


def test_finds_nothing_on_a_page_without_an_article() -> None:
    with pytest.raises(NoText, match="No article text found on the page"):
        main_text(
            b"<html><head><title>Home</title></head><body><script>go()</script></body></html>"
        )


def flagged(marking: bytes) -> bytes:
    return PAGE.replace(b"</head>", marking + b"</head>")


@pytest.mark.parametrize(
    "marking",
    [
        b'<script type="application/ld+json">{"@type":"NewsArticle","isAccessibleForFree":false}'
        b"</script>",
        b'<script type="application/ld+json">{"isAccessibleForFree": "False"}</script>',
        b'<meta itemprop="isAccessibleForFree" content="false">',
        b'<meta content="False" itemprop="isAccessibleForFree">',
    ],
    ids=["json-ld", "json-ld-string", "microdata", "microdata-content-first"],
)
def test_wont_summarise_a_page_that_says_it_isnt_free_to_read(marking: bytes) -> None:
    with pytest.raises(NoText, match="Paywalled: the page says it isn't free to read"):
        main_text(flagged(marking), URL)


def test_summarises_a_page_that_says_it_is_free_to_read() -> None:
    marking = b'<script type="application/ld+json">{"isAccessibleForFree": true}</script>'

    assert main_text(flagged(marking), URL) == main_text(PAGE, URL)


@pytest.mark.anyio
async def test_keeps_the_feeds_summary_of_paid_content_but_summarises_what_a_feed_carries(
    store: NewsStore, feed_server: FeedServer
) -> None:
    marking = b'<script type="application/ld+json">{"isAccessibleForFree":false}</script>'
    paid = barrier().model_copy(
        update={
            "url": feed_server.add("/paid", flagged(marking), "text/html"),
            "source_url": feed_server.url,
        }
    )
    carried = paid.model_copy(update={"id": "carried", "url": feed_server.url_of("/carried")})
    store.add([paid, carried])
    store.keep_text("carried", words(300))

    assert await article_text(store, paid, page) is None
    assert await article_text(store, carried, page) == words(300)

    assert store.why_no_text("barrier") == "Paywalled: the page says it isn't free to read"
    assert feed_server.paths == ["/paid"]


def test_reads_a_page_with_one_request_saying_who_it_is(feed_server: FeedServer) -> None:
    url = feed_server.add("/barrier", PAGE, "text/html; charset=utf-8")

    assert page(url, feed_server.url) == main_text(PAGE, url)
    [request] = feed_server.requests
    assert request["User-Agent"] == USER_AGENT
    assert feed_server.paths == ["/barrier"]


def test_reads_only_web_pages(feed_server: FeedServer) -> None:
    url = feed_server.add("/barrier.pdf", b"%PDF-1.7", "application/pdf")

    with pytest.raises(NoText, match="The page is application/pdf, not HTML"):
        page(url, feed_server.url)


def test_raises_on_an_error_status(feed_server: FeedServer) -> None:
    url = feed_server.add("/barrier", PAGE, "text/html")
    feed_server.errors["/barrier"] = 403

    with pytest.raises(HTTPError, match="Forbidden"):
        page(url, feed_server.url)


def test_follows_a_feeds_link_on_the_same_machine(feed_server: FeedServer) -> None:
    url = feed_server.add("/barrier", PAGE, "text/html")

    assert "tidal barrier" in page(url, feed_server.url)


@pytest.mark.anyio
async def test_wont_follow_a_link_from_an_unknown_feed_to_a_private_address(
    store: NewsStore, feed_server: FeedServer
) -> None:
    url = feed_server.add("/barrier", PAGE, "text/html")
    unknown = barrier().model_copy(update={"url": url, "source_url": ""})
    store.add([unknown])

    with pytest.raises(FeedRefused, match=f"It links to {url}"):
        page(url, "")
    assert await article_text(store, unknown, page) is None

    assert store.why_no_text("barrier") == f"It links to {url}, which Simile won't follow"
    assert feed_server.paths == []


def test_wont_follow_a_feeds_link_from_the_internet_to_a_private_address(
    feed_server: FeedServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("simile.news.feed.is_private", lambda host: host == "127.0.0.1")
    url = feed_server.add("/barrier", PAGE, "text/html")

    with pytest.raises(FeedRefused, match=f"It links to {url}"):
        page(url, FEED_URL)
    assert feed_server.paths == []


def test_holds_a_page_to_the_feeds_deadline_and_size(
    feed_server: FeedServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = feed_server.add("/barrier", PAGE, "text/html")
    monkeypatch.setattr("simile.news.feed.MAX_BYTES", len(PAGE) - 1)

    with pytest.raises(FeedRefused, match="too big for an article"):
        page(url, feed_server.url)

    monkeypatch.setattr("simile.news.feed.MAX_BYTES", 4 * 2**20)
    monkeypatch.setattr("simile.news.feed.DEADLINE", 0.2)
    feed_server.drips["/barrier"] = 0.05
    with pytest.raises(TimeoutError, match="took over 0.2 seconds"):
        page(url, feed_server.url)


@pytest.mark.anyio
async def test_gives_up_on_a_page_whose_read_never_returns() -> None:
    release = threading.Event()

    def stuck(url: str, origin: str) -> str:
        release.wait(5)
        return ""

    try:
        with pytest.raises(TimeoutError, match="It took over 0.05 seconds"):
            await read_page(URL, FEED_URL, page=stuck, give_up=0.05)
    finally:
        release.set()


def test_caps_text_at_a_number_of_words_keeping_its_lines() -> None:
    assert capped("one two\nthree four five\nsix", 4) == "one two\nthree four"
    assert capped("one two\n\n three ", 10) == "one two\nthree"


@pytest.mark.anyio
async def test_summarises_from_the_feeds_text_without_reading_the_page(
    store: NewsStore, pages: Pages
) -> None:
    store.add([barrier()])
    store.keep_text("barrier", words(150))
    reader = pages(words(500))

    assert await article_text(store, barrier(), reader) == words(150)
    assert reader.asked == []


@pytest.mark.anyio
async def test_reads_the_page_once_when_the_feed_has_only_a_teaser(
    store: NewsStore, pages: Pages
) -> None:
    store.add([barrier()])
    store.keep_text("barrier", words(149))
    reader = pages(words(500))

    first = await article_text(store, barrier(), reader)
    again = await article_text(store, barrier(), reader)

    assert first == again == words(500)
    assert reader.asked == [(URL, FEED_URL)]
    assert store.text("barrier") == words(500)


@pytest.mark.anyio
async def test_reads_no_more_of_a_page_than_the_analysis_does(
    store: NewsStore, pages: Pages
) -> None:
    store.add([barrier()])

    text = await article_text(store, barrier(), pages(words(500)), NewsConfig(article_words=300))

    assert text == store.text("barrier") == words(300)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("answer", "reason"),
    [
        (words(149), "Only 149 words: a teaser or a paywall"),
        (NoText("No article text found on the page"), "No article text found on the page"),
        (HTTPError(URL, 403, "Forbidden", Message(), None), "The site answered 403 Forbidden"),
        (TimeoutError("It took over 30 seconds"), "It took over 30 seconds"),
        (FeedRefused("It's over 4 MB, too big for an article"), "It's over 4 MB"),
        (ValueError("A parser broke"), "A parser broke"),
    ],
    ids=["teaser", "no-article", "forbidden", "slow", "too-big", "broken"],
)
async def test_keeps_the_feeds_summary_when_theres_no_text_and_says_why_once(
    store: NewsStore, pages: Pages, answer: str | Exception, reason: str
) -> None:
    store.add([barrier()])
    reader = pages(answer)

    assert await article_text(store, barrier(), reader) is None
    assert await article_text(store, barrier(), reader) is None

    assert (store.why_no_text("barrier") or "").startswith(reason)
    assert len(reader.asked) == 1
    assert store.text("barrier") is None


@pytest.mark.anyio
async def test_reads_no_page_without_a_reader(store: NewsStore) -> None:
    store.add([barrier()])
    store.keep_text("barrier", words(40))

    assert await article_text(store, barrier(), None) is None
    assert store.why_no_text("barrier") is None
