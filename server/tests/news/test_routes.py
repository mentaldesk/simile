import json
import socket
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from starlette.testclient import TestClient

from simile.app import create_app
from simile.news import FEEDS, FeedList, FeedState, news_of

MakePackage = Callable[[dict[str, str]], str]
FeedServer = Any
DEFAULT_URLS = [feed.url for feed in FEEDS]


@pytest.fixture
def package(make_package: MakePackage) -> str:
    return make_package(
        {
            "memory/lifespan.py": "from simile.memory.lifespan import lifespan\n",
            "news/lifespan.py": "from simile.news.lifespan import lifespan\n",
            "news/routes.py": "from simile.news.routes import routes\n",
            "sim/lifespan.py": "from simile.sim.lifespan import running\n",
        }
    )


@pytest.fixture(autouse=True)
def no_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SIMILE_NEWS_FEED", raising=False)


@pytest.fixture
def client(package: str) -> Iterator[TestClient]:
    with TestClient(create_app(package)) as client:
        yield client


def urls(listing: dict[str, Any]) -> list[str]:
    return [feed["url"] for feed in listing["feeds"]]


def post(client: TestClient, path: str, body: object) -> Any:
    return client.post(f"/api/news/feeds{path}", json=body)


def test_lists_the_six_feeds_until_the_list_is_changed(
    client: TestClient, feeds_file: Path
) -> None:
    listing = client.get("/api/news/feeds").json()

    assert listing["feeds"][0] == {
        "url": FEEDS[0].url,
        "name": "The Atlantic",
        "on": True,
        "checked": None,
    }
    assert urls(listing) == DEFAULT_URLS
    assert listing["defaults"] is True
    assert listing["override"] is None
    assert listing["fetching"] is False
    assert (listing["max"], listing["calls_per_feed"]) == (12, 10)
    assert not feeds_file.exists()


def test_says_when_each_feed_was_last_checked(client: TestClient) -> None:
    store = news_of(client.app)
    store.set_feed(FEEDS[1].url, FeedState(checked=1760000000.0))

    checked = [feed["checked"] for feed in client.get("/api/news/feeds").json()["feeds"]]

    assert checked == [None, 1760000000.0, None, None, None, None]


def test_checks_a_feed_without_adding_it(
    client: TestClient, feed_server: FeedServer, feeds_file: Path
) -> None:
    reply = post(client, "/check", {"url": f"  {feed_server.url} "})

    assert reply.status_code == 200
    assert reply.json() == {
        "url": feed_server.url,
        "title": "Big Think",
        "latest": {
            "title": "A new window to the early universe (and aliens?)",
            "published": "2021-09-15T16:00:00+00:00",
        },
    }
    assert urls(client.get("/api/news/feeds").json()) == DEFAULT_URLS
    assert not feeds_file.exists()


def test_adds_a_feed_under_its_title(
    client: TestClient, feed_server: FeedServer, feeds_file: Path
) -> None:
    reply = post(client, "", {"url": feed_server.url})

    assert reply.status_code == 201
    listing = reply.json()
    assert listing["feeds"][-1] == {
        "url": feed_server.url,
        "name": "Big Think",
        "on": True,
        "checked": None,
    }
    assert listing["defaults"] is False
    assert json.loads(feeds_file.read_text())["feeds"][-1]["url"] == feed_server.url


def test_adds_a_feed_with_no_stories_yet_under_its_host(
    client: TestClient, feed_server: FeedServer
) -> None:
    empty = feed_server.add("/empty", b'<rss version="2.0"><channel></channel></rss>')

    assert post(client, "/check", {"url": empty}).json()["latest"] is None
    assert post(client, "", {"url": empty}).json()["feeds"][-1]["name"] == "127.0.0.1"


def test_refuses_a_page_that_isnt_a_feed(
    client: TestClient, feed_server: FeedServer, feeds_file: Path
) -> None:
    page = feed_server.add("/page", b"<!doctype html><html><body>Hello</body></html>")

    for path in ("/check", ""):
        reply = post(client, path, {"url": page})
        assert reply.status_code == 422
        assert reply.json() == {
            "error": "That's a web page, not a feed. Look on it for an RSS or Atom link"
        }
    assert not feeds_file.exists()


def test_says_why_a_feed_cant_be_fetched(client: TestClient, feed_server: FeedServer) -> None:
    feed_server.errors["/feed"] = 404
    with socket.socket() as closed:
        closed.bind(("127.0.0.1", 0))
        port = closed.getsockname()[1]

    missing = post(client, "/check", {"url": feed_server.url}).json()["error"]
    unreachable = post(client, "/check", {"url": f"http://127.0.0.1:{port}/feed"}).json()["error"]

    assert missing == "The site answered 404 Not Found"
    assert unreachable.startswith("Couldn't reach it: ")


def test_refuses_a_feed_listed_already(client: TestClient) -> None:
    for path in ("/check", ""):
        reply = post(client, path, {"url": FEEDS[0].url})
        assert reply.status_code == 409
        assert reply.json() == {"error": "That feed is in the list already"}


def test_refuses_a_thirteenth_feed_before_fetching_it(
    client: TestClient, feed_server: FeedServer, feed_xml: bytes
) -> None:
    for n in range(6):
        assert post(client, "", {"url": feed_server.add(f"/{n}", feed_xml)}).status_code == 201
    asked = len(feed_server.paths)

    for path in ("/check", ""):
        reply = post(client, path, {"url": feed_server.add("/more", feed_xml)})
        assert reply.status_code == 409
        assert reply.json()["error"] == "The list takes at most 12 feeds. Remove one to add another"
    assert len(feed_server.paths) == asked


@pytest.mark.parametrize(
    ("body", "reason"),
    [
        ({"url": "file:///etc/passwd"}, "Paste a URL that starts with http or https"),
        ({"url": "javascript:alert(1)"}, "Paste a URL that starts with http or https"),
        ({"url": "bigthink.com/feed"}, "Paste a URL that starts with http or https"),
        ({"url": "https://"}, "The URL needs a site's name after the //"),
        ({"url": "https://example.com/a feed"}, "A URL can't have spaces in it"),
        ({"url": "https://me:secret@example.com/feed"}, "Leave the user name and password out"),
        ({"url": "https://example.com:99999/feed"}, "That URL's port isn't a valid one"),
        ({"url": "https://example.com/" + "a" * 2048}, "url: String should have at most 2048"),
        ({"url": 3}, "url: Input should be a valid string"),
        ({}, "url: Field required"),
        ({"url": "https://example.com/feed", "name": "Mine"}, "name: Extra inputs"),
    ],
)
def test_refuses_a_bad_url_without_fetching(
    client: TestClient, feed_server: FeedServer, body: object, reason: str
) -> None:
    for path in ("/check", ""):
        reply = post(client, path, body)
        assert reply.status_code == 422
        assert reply.json()["error"].startswith(reason)
    assert feed_server.paths == []


@pytest.mark.parametrize("path", ["", "/check", "/switch", "/remove", "/reset"])
def test_takes_only_json(client: TestClient, path: str) -> None:
    reply = client.post(
        f"/api/news/feeds{path}",
        content=json.dumps({"url": FEEDS[0].url, "on": False}),
        headers={"Content-Type": "text/plain"},
    )

    assert reply.status_code == 415
    assert reply.json() == {"error": "Send the request as JSON"}
    assert client.get("/api/news/feeds").json()["defaults"] is True


def test_refuses_a_body_too_large(client: TestClient) -> None:
    reply = post(client, "/check", {"url": "https://example.com/", "pad": "x" * 5000})

    assert reply.status_code == 413


def test_switches_a_feed_off_and_on(client: TestClient) -> None:
    off = post(client, "/switch", {"url": FEEDS[2].url, "on": False}).json()

    assert [feed["on"] for feed in off["feeds"]] == [True, True, False, True, True, True]
    assert FEEDS[2] not in FeedList().current()

    on = post(client, "/switch", {"url": FEEDS[2].url, "on": True}).json()
    assert on["defaults"] is True


def test_refuses_a_switch_that_isnt_one(client: TestClient) -> None:
    reply = post(client, "/switch", {"url": FEEDS[2].url, "on": "no"})

    assert reply.status_code == 422
    assert reply.json() == {"error": "on: Input should be a valid boolean"}


def test_removes_a_feed(client: TestClient) -> None:
    listing = post(client, "/remove", {"url": FEEDS[0].url}).json()

    assert urls(listing) == DEFAULT_URLS[1:]
    assert FeedList().current() == FEEDS[1:]


@pytest.mark.parametrize(
    ("path", "body"), [("/switch", {"on": False}), ("/remove", {})], ids=["switch", "remove"]
)
def test_refuses_to_change_a_feed_not_in_the_list(
    client: TestClient, path: str, body: dict[str, object]
) -> None:
    reply = post(client, path, {"url": "https://example.com/feed", **body})

    assert reply.status_code == 404
    assert reply.json() == {"error": "That feed isn't in the list"}


def test_resets_to_the_defaults(
    client: TestClient, feed_server: FeedServer, feeds_file: Path
) -> None:
    post(client, "", {"url": feed_server.url})
    post(client, "/remove", {"url": FEEDS[0].url})

    listing = post(client, "/reset", {}).json()

    assert urls(listing) == DEFAULT_URLS
    assert listing["defaults"] is True
    assert not feeds_file.exists()


def test_the_list_survives_a_restart(package: str, feed_server: FeedServer) -> None:
    with TestClient(create_app(package)) as first:
        post(first, "", {"url": feed_server.url})
        post(first, "/switch", {"url": FEEDS[0].url, "on": False})

    with TestClient(create_app(package)) as second:
        listing = second.get("/api/news/feeds").json()

    assert urls(listing) == [*DEFAULT_URLS, feed_server.url]
    assert listing["feeds"][0]["on"] is False


def test_says_when_the_env_overrides_the_list(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SIMILE_NEWS_FEED", "https://example.com/a, https://example.com/b")

    listing = client.get("/api/news/feeds").json()

    assert listing["override"] == ["https://example.com/a", "https://example.com/b"]
    assert urls(listing) == DEFAULT_URLS


def test_a_running_server_fetches_a_feed_added_without_a_restart(
    package: str, feed_server: FeedServer, feed_xml: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SIMILE_NEWS")
    first = feed_server.add("/first", feed_xml)
    saved = FeedList()
    for feed in FEEDS:
        saved.remove(feed.url)
    with TestClient(create_app(package)) as client:
        post(client, "", {"url": first})
        added = feed_server.add("/added", feed_xml.replace(b"Big Think", b"Small Think"))
        post(client, "", {"url": added})
        post(client, "/switch", {"url": first, "on": False})

        deadline = time.monotonic() + 5
        while feed_server.paths.count("/added") < 2 and time.monotonic() < deadline:
            time.sleep(0.01)
        checked = {
            feed["url"]: feed["checked"] for feed in client.get("/api/news/feeds").json()["feeds"]
        }

    assert feed_server.paths.count("/added") == 2
    assert checked[added] is not None
