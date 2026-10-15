import io
import os
import textwrap
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from simile.schema import NewsItem

FEED_URL = "https://feeds.feedburner.com/bigthink/main"
USER_AGENT = "Simile/0.1 (village news reader; +https://github.com/mentaldesk/simile)"
TIMEOUT = 10.0
SUMMARY_LENGTH = 600

BREAKS = {
    *("address", "article", "aside", "blockquote", "br", "dd", "div", "dl", "dt", "figcaption"),
    *("figure", "footer", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr", "img", "li", "ol"),
    *("p", "pre", "section", "table", "td", "th", "tr", "ul"),
}


def feed_url() -> str:
    """`$SIMILE_NEWS_FEED`, or Big Think's feed."""
    return os.environ.get("SIMILE_NEWS_FEED") or FEED_URL


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in BREAKS:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in BREAKS:
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def plain(html: str) -> str:
    """The text of an HTML fragment, on one line."""
    extractor = TextExtractor()
    extractor.feed(html)
    extractor.close()
    return " ".join("".join(extractor.parts).split())


def shorten(text: str, limit: int = SUMMARY_LENGTH) -> str:
    """`text` cut to at most `limit` characters, at the end of a sentence if one ends past
    halfway, else at a word."""
    if len(text) <= limit:
        return text
    end = max(text.rfind(mark, 0, limit) for mark in (". ", "? ", "! "))
    return text[: end + 1] if end > limit // 2 else textwrap.shorten(text, limit, placeholder="…")


def parse(xml: bytes) -> list[NewsItem]:
    """The feed's entries as news items, in feed order, without repeated guids. Entries with no
    link, title or date are skipped."""
    import feedparser

    feed = feedparser.parse(io.BytesIO(xml))
    if feed.bozo and not feed.entries:
        raise ValueError(f"not a feed: {feed.bozo_exception}")
    items: dict[str, NewsItem] = {}
    for entry in feed.entries:
        guid = entry.get("id") or entry.get("link")
        published = entry.get("published_parsed") or entry.get("updated_parsed")
        title = plain(entry.get("title", ""))
        if not (guid and entry.get("link") and title and published) or guid in items:
            continue
        items[guid] = NewsItem(
            id=guid,
            title=title,
            url=entry.link,
            summary=shorten(plain(entry.get("summary", ""))),
            published=datetime(*published[:6], tzinfo=UTC),
        )
    return list(items.values())


@dataclass(frozen=True)
class Fetched:
    """A feed download. `items` is None when the feed hasn't changed since `etag`/`modified`."""

    items: list[NewsItem] | None
    etag: str | None = None
    modified: str | None = None


def fetch(
    url: str, etag: str | None = None, modified: str | None = None, timeout: float = TIMEOUT
) -> Fetched:
    """Download and parse the feed, asking only for changes since `etag`/`modified`. Blocks."""
    headers = {"User-Agent": USER_AGENT}
    if etag:
        headers["If-None-Match"] = etag
    if modified:
        headers["If-Modified-Since"] = modified
    try:
        with urlopen(Request(url, headers=headers), timeout=timeout) as response:
            return Fetched(
                parse(response.read()),
                response.headers.get("ETag"),
                response.headers.get("Last-Modified"),
            )
    except HTTPError as error:
        if error.code == 304:
            return Fetched(None, etag, modified)
        raise
