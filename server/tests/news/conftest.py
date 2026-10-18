import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from simile.news import NewsStore, article

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "bigthink.xml"
PAGE = FIXTURES / "article.html"


class FeedServer(ThreadingHTTPServer):
    """Serves saved feeds on localhost, with an ETag, and records each request's path and
    headers. `url` is the saved Big Think feed's. A path in `redirects` redirects, and one in
    `drips` sends its feed 256 bytes at a time, that many seconds apart, with no length. One in
    `trickles` sends its "headers", or the size line of its first of some "chunks", a byte every
    50 ms, for as long as the client listens. A path in `types` is served as that content type
    rather than as RSS."""

    def __init__(self, xml: bytes) -> None:
        super().__init__(("127.0.0.1", 0), FeedHandler)
        self.feeds = {"/feed": xml}
        self.types: dict[str, str] = {}
        self.errors: dict[str, int] = {}
        self.redirects: dict[str, str] = {}
        self.drips: dict[str, float] = {}
        self.trickles: dict[str, str] = {}
        self.etag = '"v1"'
        self.modified = "Wed, 15 Sep 2021 20:05:26 GMT"
        self.requests: list[dict[str, str]] = []
        self.paths: list[str] = []
        self.gate = threading.Event()
        self.gate.set()

    @property
    def url(self) -> str:
        return self.url_of("/feed")

    def url_of(self, path: str) -> str:
        host, port = self.server_address[:2]
        return f"http://{host!s}:{port}{path}"

    def add(self, path: str, xml: bytes, kind: str | None = None) -> str:
        self.feeds[path] = xml
        if kind:
            self.types[path] = kind
        return self.url_of(path)


class FeedHandler(BaseHTTPRequestHandler):
    server: FeedServer

    def do_GET(self) -> None:
        self.server.requests.append(dict(self.headers))
        self.server.paths.append(self.path)
        self.server.gate.wait(5)
        xml = self.server.feeds.get(self.path)
        if self.path in self.server.redirects:
            self.send_response(302)
            self.send_header("Location", self.server.redirects[self.path])
            self.end_headers()
        elif self.path in self.server.drips and xml is not None:
            self.send_response(200)
            self.end_headers()
            pieces = [xml[start : start + 256] for start in range(0, len(xml), 256)]
            self.send_slowly(pieces, self.server.drips[self.path])
        elif self.path in self.server.trickles:
            head = b"HTTP/1.1 200 OK\r\nContent-Type: application/rss+xml\r\n"
            if self.server.trickles[self.path] == "headers":
                self.wfile.write(head)
                slow = b"X-Slow: " + b"." * 2000
            else:
                self.wfile.write(head + b"Transfer-Encoding: chunked\r\n\r\n")
                slow = b"f" * 2000
            self.send_slowly([bytes([byte]) for byte in slow], 0.05)
        elif xml is None:
            self.send_error(404)
        elif self.path in self.server.errors:
            self.send_error(self.server.errors[self.path])
        elif self.headers.get("If-None-Match") == self.server.etag:
            self.send_response(304)
            self.end_headers()
        else:
            self.send_response(200)
            self.send_header(
                "Content-Type", self.server.types.get(self.path, "application/rss+xml")
            )
            self.send_header("Content-Length", str(len(xml)))
            self.send_header("ETag", self.server.etag)
            self.send_header("Last-Modified", self.server.modified)
            self.end_headers()
            self.wfile.write(xml)

    def send_slowly(self, pieces: list[bytes], pause: float) -> None:
        for piece in pieces:
            try:
                self.wfile.write(piece)
                self.wfile.flush()
            except OSError:
                return
            time.sleep(pause)

    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture
def feed_xml() -> bytes:
    return FIXTURE.read_bytes()


@pytest.fixture
def feed_server(feed_xml: bytes) -> Iterator[FeedServer]:
    server = FeedServer(feed_xml)
    thread = threading.Thread(target=server.serve_forever, args=(0.01,), daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


@pytest.fixture(autouse=True)
def feeds_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "data" / "feeds.json"
    monkeypatch.setenv("SIMILE_FEEDS_FILE", str(path))
    return path


class Pages:
    """Stands in for `article.page`: answers a URL from `answers`, or else with `default`, raising
    the answer if it's an exception, and keeps each request."""

    def __init__(
        self, default: str | Exception = "", answers: dict[str, str | Exception] | None = None
    ) -> None:
        self.default = default
        self.answers = answers or {}
        self.asked: list[tuple[str, str | None]] = []

    def __call__(self, url: str, origin: str | None = None) -> str:
        self.asked.append((url, origin))
        answer = self.answers.get(url, self.default)
        if isinstance(answer, Exception):
            raise answer
        return answer


@pytest.fixture
def pages() -> type[Pages]:
    return Pages


@pytest.fixture(autouse=True)
def no_article_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(url: str, origin: str | None = None) -> str:
        raise article.NoText("Tests don't read article pages")

    monkeypatch.setattr(article, "page", refuse)


@pytest.fixture
def store() -> Iterator[NewsStore]:
    with NewsStore(":memory:") as store:
        yield store
