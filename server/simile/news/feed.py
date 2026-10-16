import io
import os
import textwrap
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from simile.schema import NewsItem

USER_AGENT = "Simile/0.1 (village news reader; +https://github.com/mentaldesk/simile)"
TIMEOUT = 10.0
SUMMARY_LENGTH = 600

BREAKS = {
    *("address", "article", "aside", "blockquote", "br", "dd", "div", "dl", "dt", "figcaption"),
    *("figure", "footer", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr", "img", "li", "ol"),
    *("p", "pre", "section", "table", "td", "th", "tr", "ul"),
}


@dataclass(frozen=True)
class Feed:
    """A news feed, and the name its stories are credited to. Unnamed, they take the feed's own
    title."""

    url: str
    name: str = ""


FEEDS = (
    Feed("https://www.theatlantic.com/feed/best-of/", "The Atlantic"),
    Feed("https://openai.com/news/rss.xml", "OpenAI"),
    Feed("http://rss.sciam.com/ScientificAmerican-Global", "Scientific American"),
    Feed("https://www.economist.com/the-world-this-week/rss.xml", "The Economist"),
    Feed("https://www.rnz.co.nz/rss/sport.xml", "RNZ Sport"),
    Feed("https://feeds.feedburner.com/ign/pc-reviews", "IGN"),
)


def feeds() -> tuple[Feed, ...]:
    """The feeds at the comma-separated URLs in `$SIMILE_NEWS_FEED`, or `FEEDS`. A URL from
    `FEEDS` keeps its name."""
    urls = [url.strip() for url in os.environ.get("SIMILE_NEWS_FEED", "").split(",")]
    named = {feed.url: feed for feed in FEEDS}
    chosen = tuple(named.get(url, Feed(url)) for url in dict.fromkeys(urls) if url)
    return chosen or FEEDS


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


def parse(xml: bytes, feed: Feed | None = None) -> list[NewsItem]:
    """The feed's entries as news items from `feed`, in feed order, without repeated guids.
    Entries with no link, title or date are skipped."""
    import feedparser

    parsed = feedparser.parse(io.BytesIO(xml))
    if parsed.bozo and not parsed.entries:
        raise ValueError(f"not a feed: {parsed.bozo_exception}")
    source = feed.name if feed and feed.name else plain(parsed.feed.get("title", ""))
    items: dict[str, NewsItem] = {}
    for entry in parsed.entries:
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
            source=source,
            source_url=feed.url if feed else "",
        )
    return list(items.values())


@dataclass(frozen=True)
class Fetched:
    """A feed download. `items` is None when the feed hasn't changed since `etag`/`modified`."""

    items: list[NewsItem] | None
    etag: str | None = None
    modified: str | None = None


def fetch(
    feed: Feed, etag: str | None = None, modified: str | None = None, timeout: float = TIMEOUT
) -> Fetched:
    """Download and parse `feed`, asking only for changes since `etag`/`modified`. Blocks."""
    headers = {"User-Agent": USER_AGENT}
    if etag:
        headers["If-None-Match"] = etag
    if modified:
        headers["If-Modified-Since"] = modified
    try:
        with urlopen(Request(feed.url, headers=headers), timeout=timeout) as response:
            return Fetched(
                parse(response.read(), feed),
                response.headers.get("ETag"),
                response.headers.get("Last-Modified"),
            )
    except HTTPError as error:
        if error.code == 304:
            return Fetched(None, etag, modified)
        raise
