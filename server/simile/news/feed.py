import contextlib
import functools
import io
import ipaddress
import os
import re
import socket
import textwrap
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.message import Message
from html.parser import HTMLParser
from http.client import HTTPConnection, HTTPResponse, HTTPSConnection
from types import TracebackType
from typing import IO, Any, Self
from urllib.error import HTTPError
from urllib.parse import urljoin, urlsplit
from urllib.request import (
    HTTPHandler,
    HTTPRedirectHandler,
    HTTPSHandler,
    Request,
    build_opener,
)

from simile.schema import NewsItem

USER_AGENT = "Simile/0.1 (village news reader; +https://github.com/mentaldesk/simile)"
TIMEOUT = 10.0
DEADLINE = 30.0
MAX_BYTES = 4 * 1024 * 1024
MAX_REDIRECTS = 5
SCHEMES = ("http", "https")
SUMMARY_LENGTH = 600

SKIPPED = {"script", "style", "noscript", "template"}
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
    def __init__(self, gap: str = " ") -> None:
        super().__init__(convert_charrefs=True)
        self.gap = gap
        self.parts: list[str] = []
        self.skipping = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in BREAKS:
            self.parts.append(self.gap)
        self.skipping += tag in SKIPPED

    def handle_endtag(self, tag: str) -> None:
        if tag in BREAKS:
            self.parts.append(self.gap)
        if tag in SKIPPED and self.skipping:
            self.skipping -= 1

    def handle_data(self, data: str) -> None:
        if not self.skipping:
            self.parts.append(data)


def text_of(html: str, gap: str) -> str:
    extractor = TextExtractor(gap)
    extractor.feed(html)
    extractor.close()
    return "".join(extractor.parts)


def plain(html: str) -> str:
    """The text of an HTML fragment, on one line."""
    return " ".join(text_of(html, " ").split())


def paragraphs(html: str) -> str:
    """The text of an HTML fragment, a paragraph a line."""
    blocks = (" ".join(block.split()) for block in text_of(html, "\x1e").split("\x1e"))
    return "\n".join(block for block in blocks if block)


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
    texts: dict[str, str] = field(default_factory=dict)
    """The full text some feeds carry for an item, by its id, a paragraph a line."""


def read(xml: bytes, feed: Feed | None = None) -> Parsed:
    """The feed's title, and its entries as news items from `feed`, in feed order, without
    repeated guids, with the text of those whose entries carry their content. Entries with no
    link, title or date are skipped. Refuses anything but RSS or Atom, and bytes that declare an
    XML entity."""
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
    texts: dict[str, str] = {}
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
        contents = (paragraphs(part.get("value", "")) for part in entry.get("content", []))
        if text := max(contents, key=len, default=""):
            texts[guid] = text
    return Parsed(feed_title, list(items.values()), texts)


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
    texts: Mapping[str, str] = field(default_factory=dict)


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


class Deadline:
    """Shuts every socket a fetch opens once `seconds` have passed, so nothing it waits for, from
    connecting to the last byte, outlasts them. Leaving it raises `TimeoutError` if they did."""

    def __init__(self, seconds: float) -> None:
        self.seconds = seconds
        self.end = time.monotonic() + seconds
        self.passed = False
        self._sockets: list[socket.socket] = []
        self._lock = threading.Lock()
        self._timer = threading.Timer(seconds, self._expire)
        self._timer.daemon = True

    def __enter__(self) -> Self:
        self._timer.start()
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._timer.cancel()
        if self.passed:
            raise TimeoutError(f"It took over {self.seconds:g} seconds") from error

    def left(self) -> float:
        left = self.end - time.monotonic()
        if left <= 0:
            raise TimeoutError(f"It took over {self.seconds:g} seconds")
        return left

    def track(self, sock: socket.socket) -> None:
        with self._lock:
            self._sockets.append(sock)
            if self.passed:
                _shut(sock)

    def connect(
        self, address: tuple[str, int], timeout: float, source_address: Any = None
    ) -> socket.socket:
        sock = socket.create_connection(address, timeout, source_address)
        self.track(sock)
        return sock

    def _expire(self) -> None:
        with self._lock:
            self.passed = True
            for sock in self._sockets:
                _shut(sock)


def _shut(sock: socket.socket) -> None:
    with contextlib.suppress(OSError):
        socket.socket.shutdown(sock, socket.SHUT_RDWR)


class CutOff:
    """A connection its deadline can cut off. It connects within what's left of it, and its
    sockets are shut when it passes: the plain one at once, and a TLS one once it's set up."""

    def __init__(self, *args: Any, deadline: Deadline, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.deadline = deadline
        self._create_connection = deadline.connect

    def connect(self) -> None:
        self.timeout = min(self.timeout, self.deadline.left())
        super().connect()
        self.deadline.track(self.sock)


class CutOffHTTPConnection(CutOff, HTTPConnection):
    pass


class CutOffHTTPSConnection(CutOff, HTTPSConnection):
    pass


class DeadlineHTTPHandler(HTTPHandler):
    def __init__(self, deadline: Deadline) -> None:
        super().__init__()
        self.deadline = deadline

    def http_open(self, req: Request) -> HTTPResponse:
        return self.do_open(functools.partial(CutOffHTTPConnection, deadline=self.deadline), req)


class DeadlineHTTPSHandler(HTTPSHandler):
    def __init__(self, deadline: Deadline) -> None:
        super().__init__()
        self.deadline = deadline

    def https_open(self, req: Request) -> HTTPResponse:
        connection = functools.partial(CutOffHTTPSConnection, deadline=self.deadline)
        return self.do_open(connection, req, context=self._context)


def download(response: HTTPResponse, what: str = "a news feed") -> bytes:
    """The response's body, refused past `MAX_BYTES`."""
    too_big = FeedRefused(f"It's over {MAX_BYTES / 2**20:g} MB, too big for {what}")
    length = response.headers.get("Content-Length", "")
    if length.isdigit() and int(length) > MAX_BYTES:
        raise too_big
    data = bytearray()
    while chunk := response.read1(64 * 1024):
        data += chunk
        if len(data) > MAX_BYTES:
            raise too_big
    return bytes(data)


@dataclass(frozen=True)
class Download:
    body: bytes
    headers: Message


def get(
    url: str,
    headers: Mapping[str, str] | None = None,
    timeout: float = TIMEOUT,
    *,
    origin: str | None = None,
    what: str = "a news feed",
) -> Download:
    """`url`'s body and headers. Blocks. Only over http(s), within `MAX_BYTES`, and all of it,
    redirects included, within `DEADLINE`. From the internet it goes only to the internet. A URL
    found at `origin` counts as from there, and one found somewhere unknown (`origin=""`) as from
    the internet. Raises `HTTPError` for an error status."""
    if urlsplit(url).scheme.lower() not in SCHEMES:
        raise FeedRefused("Simile fetches only over http or https")
    start = origin or url
    if (
        origin is not None
        and is_private(urlsplit(url).hostname or "")
        and not (origin and is_private(urlsplit(origin).hostname or ""))
    ):
        raise FeedRefused(f"It links to {url}, which Simile won't follow")
    with Deadline(DEADLINE) as deadline:
        opener = build_opener(
            Redirects(start), DeadlineHTTPHandler(deadline), DeadlineHTTPSHandler(deadline)
        )
        request = Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
        with opener.open(request, timeout=timeout) as response:
            return Download(download(response, what), response.headers)


def fetch(
    feed: Feed, etag: str | None = None, modified: str | None = None, timeout: float = TIMEOUT
) -> Fetched:
    """Download and parse `feed` with `get`, asking only for changes since `etag`/`modified`.
    Blocks."""
    headers = {}
    if etag:
        headers["If-None-Match"] = etag
    if modified:
        headers["If-Modified-Since"] = modified
    try:
        got = get(feed.url, headers, timeout)
    except HTTPError as error:
        if error.code == 304:
            return Fetched(None, etag, modified)
        raise
    parsed = read(got.body, feed)
    etag, modified = got.headers.get("ETag"), got.headers.get("Last-Modified")
    return Fetched(parsed.items, etag, modified, parsed.title, parsed.texts)
