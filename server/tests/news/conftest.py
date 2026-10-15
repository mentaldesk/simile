import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from simile.news import NewsStore

FIXTURE = Path(__file__).parent / "fixtures" / "bigthink.xml"


class FeedServer(ThreadingHTTPServer):
    """Serves the saved feed on localhost, with an ETag, and records each request's headers."""

    def __init__(self, xml: bytes) -> None:
        super().__init__(("127.0.0.1", 0), FeedHandler)
        self.xml = xml
        self.status = 200
        self.etag = '"v1"'
        self.modified = "Wed, 15 Sep 2021 20:05:26 GMT"
        self.requests: list[dict[str, str]] = []

    @property
    def url(self) -> str:
        host, port = self.server_address[:2]
        return f"http://{host!s}:{port}/feed"


class FeedHandler(BaseHTTPRequestHandler):
    server: FeedServer

    def do_GET(self) -> None:
        self.server.requests.append(dict(self.headers))
        if self.server.status != 200:
            self.send_error(self.server.status)
        elif self.headers.get("If-None-Match") == self.server.etag:
            self.send_response(304)
            self.end_headers()
        else:
            self.send_response(200)
            self.send_header("Content-Type", "application/rss+xml")
            self.send_header("Content-Length", str(len(self.server.xml)))
            self.send_header("ETag", self.server.etag)
            self.send_header("Last-Modified", self.server.modified)
            self.end_headers()
            self.wfile.write(self.server.xml)

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
