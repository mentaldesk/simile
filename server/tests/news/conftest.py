import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from simile.news import NewsStore

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "bigthink.xml"


class FeedServer(ThreadingHTTPServer):
    """Serves saved feeds on localhost, with an ETag, and records each request's path and
    headers. `url` is the saved Big Think feed's."""

    def __init__(self, xml: bytes) -> None:
        super().__init__(("127.0.0.1", 0), FeedHandler)
        self.feeds = {"/feed": xml}
        self.errors: dict[str, int] = {}
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

    def add(self, path: str, xml: bytes) -> str:
        self.feeds[path] = xml
        return self.url_of(path)


class FeedHandler(BaseHTTPRequestHandler):
    server: FeedServer

    def do_GET(self) -> None:
        self.server.requests.append(dict(self.headers))
        self.server.paths.append(self.path)
        self.server.gate.wait(5)
        xml = self.server.feeds.get(self.path)
        if xml is None:
            self.send_error(404)
        elif self.path in self.server.errors:
            self.send_error(self.server.errors[self.path])
        elif self.headers.get("If-None-Match") == self.server.etag:
            self.send_response(304)
            self.end_headers()
        else:
            self.send_response(200)
            self.send_header("Content-Type", "application/rss+xml")
            self.send_header("Content-Length", str(len(xml)))
            self.send_header("ETag", self.server.etag)
            self.send_header("Last-Modified", self.server.modified)
            self.end_headers()
            self.wfile.write(xml)

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


@pytest.fixture
def store() -> Iterator[NewsStore]:
    with NewsStore(":memory:") as store:
        yield store
