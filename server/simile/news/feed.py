import io
import ipaddress
import os
import re
import socket
import textwrap
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import Message
from html.parser import HTMLParser
from http.client import HTTPResponse
from typing import IO
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from simile.schema import NewsItem

USER_AGENT = "Simile/0.1 (village news reader; +https://github.com/mentaldesk/simile)"
TIMEOUT = 10.0
DEADLINE = 30.0
MAX_BYTES = 4 * 1024 * 1024
MAX_REDIRECTS = 5
SCHEMES = ("http", "https")
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


class FeedRefused(ValueError):
    """Why Simile won't read a URL as a feed, in words for the player."""


def override() -> tuple[Feed, ...]:
    """The feeds at the comma-separated URLs in `$SIMILE_NEWS_FEED`, if it's set. A URL from
    `FEEDS` keeps its name."""
    urls = [url.strip() for url in os.environ.get("SIMILE_NEWS_FEED", "").split(",")]
    named = {feed.url: feed for feed in FEEDS}
    return tuple(named.get(url, Feed(url)) for url in dict.fromkeys(urls) if url)


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


@dataclass(frozen=True)
class Parsed:
    title: str
    items: list[NewsItem]


def read(xml: bytes, feed: Feed | None = None) -> Parsed:
    """The feed's title, and its entries as news items from `feed`, in feed order, without
    repeated guids. Entries with no link, title or date are skipped. Refuses anything but RSS or
    Atom, and XML that declares entities."""
    import feedparser

    if re.search(rb"<!ENTITY", xml, re.IGNORECASE):
        raise FeedRefused("It declares XML entities, which Simile doesn't read")
    parsed = feedparser.parse(io.BytesIO(xml))
    if not (parsed.get("version") or "").startswith(("rss", "atom")):
        if re.search(rb"<html", xml[:4096], re.IGNORECASE):
            raise FeedRefused("That's a web page, not a feed. Look on it for an RSS or Atom link")
        raise FeedRefused("That isn't an RSS or Atom feed")
    if parsed.bozo and not parsed.entries:
        raise FeedRefused(f"It looks like a feed but can't be read: {parsed.bozo_exception}")
    feed_title = plain(parsed.feed.get("title", ""))
    source = feed.name if feed and feed.name else feed_title
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
    return Parsed(feed_title, list(items.values()))


def parse(xml: bytes, feed: Feed | None = None) -> list[NewsItem]:
    """`read`'s items."""
    return read(xml, feed).items


@dataclass(frozen=True)
class Fetched:
    """A feed download. `items` is None when the feed hasn't changed since `etag`/`modified`."""

    items: list[NewsItem] | None
    etag: str | None = None
    modified: str | None = None
    title: str = ""


def is_private(host: str) -> bool:
    """Whether `host` is, or resolves to, an address off the public internet."""
    try:
        addresses = {str(info[4][0]) for info in socket.getaddrinfo(host, None)}
    except (OSError, UnicodeError):
        return False
    try:
        return not all(ipaddress.ip_address(address).is_global for address in addresses)
    except ValueError:
        return True


class Redirects(HTTPRedirectHandler):
    """Follows redirects over http(s) only, and from the internet only to the internet."""

    max_redirections = MAX_REDIRECTS

    def __init__(self, origin: str) -> None:
        self.origin = origin

    def http_error_302(
        self, req: Request, fp: IO[bytes], code: int, msg: str, headers: Message
    ) -> object:
        if location := headers.get("location") or headers.get("uri"):
            target = urljoin(req.full_url, location)
            parts = urlsplit(target)
            if parts.scheme.lower() not in SCHEMES or (
                is_private(parts.hostname or "")
                and not is_private(urlsplit(self.origin).hostname or "")
            ):
                fp.close()
                raise FeedRefused(f"It redirects to {target}, which Simile won't follow")
        return super().http_error_302(req, fp, code, msg, headers)

    http_error_301 = http_error_303 = http_error_307 = http_error_308 = http_error_302


def download(response: HTTPResponse, deadline: float) -> bytes:
    """The response's body, refused past `MAX_BYTES` or `deadline`."""
    too_big = FeedRefused(f"It's over {MAX_BYTES / 2**20:g} MB, too big for a news feed")
    length = response.headers.get("Content-Length", "")
    if length.isdigit() and int(length) > MAX_BYTES:
        raise too_big
    data = bytearray()
    while chunk := response.read1(64 * 1024):
        data += chunk
        if len(data) > MAX_BYTES:
            raise too_big
        if time.monotonic() > deadline:
            raise TimeoutError(f"It took over {DEADLINE:g} seconds to download")
    return bytes(data)


def fetch(
    feed: Feed, etag: str | None = None, modified: str | None = None, timeout: float = TIMEOUT
) -> Fetched:
    """Download and parse `feed`, asking only for changes since `etag`/`modified`. Blocks.
    Only over http(s), and within `MAX_BYTES` and `DEADLINE`."""
    if urlsplit(feed.url).scheme.lower() not in SCHEMES:
        raise FeedRefused("Simile reads feeds only over http or https")
    headers = {"User-Agent": USER_AGENT}
    if etag:
        headers["If-None-Match"] = etag
    if modified:
        headers["If-Modified-Since"] = modified
    deadline = time.monotonic() + DEADLINE
    opener = build_opener(Redirects(feed.url))
    try:
        with opener.open(Request(feed.url, headers=headers), timeout=timeout) as response:
            xml = download(response, deadline)
            parsed = read(xml, feed)
            return Fetched(
                parsed.items,
                response.headers.get("ETag"),
                response.headers.get("Last-Modified"),
                parsed.title,
            )
    except HTTPError as error:
        if error.code == 304:
            return Fetched(None, etag, modified)
        raise
