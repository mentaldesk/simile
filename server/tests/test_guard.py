import logging
from collections.abc import Callable, Iterable, Iterator

import pytest
from starlette.applications import Starlette
from starlette.routing import BaseRoute, Mount, Route, WebSocketRoute
from starlette.testclient import TestClient
from starlette.types import Message
from starlette.websockets import WebSocketDisconnect

from simile import guard
from simile.app import create_app

MakePackage = Callable[[dict[str, str]], str]

CLIENT = "http://localhost:5173"
FOREIGN = "https://example.com"
JSON = {"Content-Type": "application/json"}
CHANGES = ["POST", "PUT", "PATCH", "DELETE"]
SAFELISTED = ["text/plain", "application/x-www-form-urlencoded", "multipart/form-data; boundary=x"]
REFUSED_ORIGIN = {"error": "Requests from other sites aren't allowed"}
REFUSED_HOST = {"error": "This server only answers to localhost"}

ROUTES = """
from starlette.responses import PlainTextResponse
from starlette.routing import Route, WebSocketRoute

from simile.guard import accepts


async def echo(request):
    return PlainTextResponse(await request.body())


@accepts("audio/wav", "audio/mpeg")
async def upload(request):
    return PlainTextResponse("uploaded")


@accepts(None)
async def cancel(request):
    return PlainTextResponse("cancelled")


async def hello(websocket):
    await websocket.accept()
    await websocket.send_text("hello")
    await websocket.close()


routes = [
    Route("/api/echo", echo, methods=["GET", "POST", "PUT", "PATCH", "DELETE"]),
    Route("/api/upload", upload, methods=["POST"]),
    Route("/api/cancel", cancel, methods=["POST"]),
    WebSocketRoute("/ws", hello),
]
"""


@pytest.fixture
def app(make_package: MakePackage) -> Starlette:
    return create_app(make_package({"echo/routes.py": ROUTES}))


@pytest.fixture
def client(app: Starlette) -> Iterator[TestClient]:
    with TestClient(app) as client:
        yield client


def refused_socket(client: TestClient, path: str, headers: dict[str, str]) -> int:
    with (
        pytest.raises(WebSocketDisconnect) as refused,
        client.websocket_connect(path, headers=dict(headers)),
    ):
        pass
    return refused.value.code


@pytest.mark.parametrize("method", CHANGES)
def test_refuses_a_change_from_another_site(client: TestClient, method: str) -> None:
    response = client.request(method, "/api/echo", content="{}", headers=JSON | {"Origin": FOREIGN})

    assert (response.status_code, response.json()) == (403, REFUSED_ORIGIN)


@pytest.mark.parametrize(
    "origin",
    [
        "null",
        "http://localhost:3000",
        "https://localhost:5173",
        "http://localhost:5173.evil.com",
        "http://127.0.0.1:8000.evil.com",
        "http://localhost:51730",
    ],
)
def test_refuses_a_change_from_any_origin_but_the_clients(client: TestClient, origin: str) -> None:
    response = client.post("/api/echo", content="{}", headers=JSON | {"Origin": origin})

    assert (response.status_code, response.json()) == (403, REFUSED_ORIGIN)


@pytest.mark.parametrize("origin", [*sorted(guard.ORIGINS), "HTTP://LOCALHOST:5173", None])
@pytest.mark.parametrize("method", CHANGES)
def test_takes_a_change_from_the_client_or_with_no_origin(
    client: TestClient, method: str, origin: str | None
) -> None:
    headers = JSON | ({"Origin": origin} if origin else {})

    response = client.request(method, "/api/echo", content='{"a": 1}', headers=headers)

    assert (response.status_code, response.text) == (200, '{"a": 1}')


def test_leaves_reads_from_other_sites_to_the_browser(client: TestClient) -> None:
    assert client.get("/api/echo", headers={"Origin": FOREIGN}).status_code == 200


@pytest.mark.parametrize(
    "host",
    [
        "example.com",
        "example.com:8000",
        "localhost.example.com",
        "127.0.0.1.example.com:8000",
        "evil@localhost",
        "[::1]evil.com",
        "[::1].evil.com",
        "[::1]:8000.evil.com",
        "localhost:evil",
        "localhost:",
        "::1",
        "0.0.0.0:8000",
        "[::2]:8000",
        "testserver.example.com",
    ],
)
@pytest.mark.parametrize("method", ["GET", "HEAD", "POST"])
def test_refuses_a_foreign_host_on_every_request(
    client: TestClient, method: str, host: str
) -> None:
    response = client.request(method, "/api/echo", content="{}", headers=JSON | {"Host": host})

    assert response.status_code == 403
    if method != "HEAD":
        assert response.json() == REFUSED_HOST


@pytest.mark.parametrize(
    "host",
    ["localhost", "localhost:8000", "LocalHost:5173", "127.0.0.1", "127.0.0.1:9999", "[::1]:8000"],
)
def test_takes_a_local_host_on_any_port(client: TestClient, host: str) -> None:
    assert client.get("/api/echo", headers={"Host": host}).status_code == 200


@pytest.mark.anyio
async def test_refuses_a_request_with_no_host(app: Starlette) -> None:
    sent: list[Message] = []

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.0",
        "method": "GET",
        "scheme": "http",
        "path": "/api/echo",
        "raw_path": b"/api/echo",
        "query_string": b"",
        "root_path": "",
        "headers": [],
    }
    await app(scope, receive, send)

    assert sent[0]["status"] == 403


def test_the_test_client_host_is_allowed_only_in_tests(
    app: Starlette, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SIMILE_HOSTS")

    response = TestClient(app).get("/api/echo")

    assert "testserver" not in guard.HOSTS
    assert (response.status_code, response.json()) == (403, REFUSED_HOST)


def test_takes_the_hosts_and_origins_its_told_to(
    make_package: MakePackage, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SIMILE_HOSTS", " testserver, Simile.lan:9000 ,[fd00::1], fd00::2")
    monkeypatch.setenv("SIMILE_ORIGINS", "http://Simile.lan:5173/")
    client = TestClient(create_app(make_package({"echo/routes.py": ROUTES})))

    def post(host: str, origin: str) -> int:
        headers = JSON | {"Host": host, "Origin": origin}
        return client.post("/api/echo", content="{}", headers=headers).status_code

    assert post("simile.lan:5173", "http://simile.lan:5173") == 200
    assert post("[fd00::1]:8000", CLIENT) == 200
    assert post("[fd00::2]", CLIENT) == 200
    assert post("localhost:5173", CLIENT) == 200
    assert post("simile.lan:5173", "http://simile.lan:8000") == 403
    assert post("other.lan", "http://simile.lan:5173") == 403


@pytest.mark.parametrize(
    "content_type", ["application/json", "application/json; charset=utf-8", "Application/JSON;"]
)
def test_takes_json_with_or_without_a_charset(client: TestClient, content_type: str) -> None:
    response = client.post("/api/echo", content="{}", headers={"Content-Type": content_type})

    assert response.status_code == 200


@pytest.mark.parametrize("content_type", [*SAFELISTED, "application/jsonp", "", None])
@pytest.mark.parametrize("origin", [CLIENT, None])
def test_refuses_anything_but_json_by_default(
    client: TestClient, content_type: str | None, origin: str | None
) -> None:
    headers = {"Content-Type": content_type} if content_type is not None else {}
    headers |= {"Origin": origin} if origin else {}

    response = client.post("/api/echo", content="{}", headers=headers)

    assert response.status_code == 415
    assert response.json()["error"].startswith("Send the request as application/json")


def test_says_what_it_wanted_and_what_it_got(client: TestClient) -> None:
    def error(path: str, content_type: str | None) -> str:
        headers = {"Content-Type": content_type} if content_type else {}
        return client.post(path, content="x", headers=headers).json()["error"]

    assert error("/api/echo", None) == "Send the request as application/json"
    assert error("/api/echo", "text/plain; charset=utf-8") == (
        "Send the request as application/json, not text/plain"
    )
    assert error("/api/upload", "audio/ogg") == (
        "Send the request as audio/mpeg or audio/wav, not audio/ogg"
    )
    assert error("/api/cancel", "application/json") == (
        "This request takes no body, not application/json"
    )


def test_an_upload_takes_only_the_types_it_declares(client: TestClient) -> None:
    def status(content_type: str | None) -> int:
        headers = {"Content-Type": content_type} if content_type else {}
        return client.post("/api/upload", content=b"RIFF", headers=headers).status_code

    assert [status("audio/wav"), status("audio/mpeg"), status("Audio/WAV; rate=24000")] == [200] * 3
    assert [status(None), status(JSON["Content-Type"]), status("audio/ogg")] == [415] * 3
    assert [status(media) for media in SAFELISTED] == [415] * 3


def test_a_route_with_no_body_takes_no_content_type(client: TestClient) -> None:
    def status(content_type: str | None) -> int:
        headers = {"Content-Type": content_type} if content_type else {}
        return client.post("/api/cancel", headers=headers).status_code

    assert status(None) == 200
    assert [status(media) for media in [*SAFELISTED, JSON["Content-Type"]]] == [415] * 4


def test_leaves_unknown_routes_and_methods_to_the_router(client: TestClient) -> None:
    headers = {"Content-Type": "text/plain"}

    assert client.post("/api/nowhere", content="x", headers=headers).status_code == 404
    assert client.put("/api/cancel", content="x", headers=headers).status_code == 405


@pytest.mark.parametrize("origin", [CLIENT, None])
def test_the_client_can_open_a_websocket(client: TestClient, origin: str | None) -> None:
    with client.websocket_connect("/ws", headers={"Origin": origin} if origin else {}) as ws:
        assert ws.receive_text() == "hello"


@pytest.mark.parametrize(
    "headers", [{"Origin": FOREIGN}, {"Origin": "null"}, {"Host": "example.com:8000"}]
)
def test_refuses_a_websocket_from_another_site(client: TestClient, headers: dict[str, str]) -> None:
    assert refused_socket(client, "/ws", headers) == 1008


def test_logs_each_refusal_once_per_origin(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger="simile.guard"):
        for origin in (FOREIGN, FOREIGN, "https://example.org", FOREIGN):
            client.post("/api/echo", content="{}", headers=JSON | {"Origin": origin})
        refused_socket(client, "/ws", {"Origin": FOREIGN})
        for _ in range(2):
            client.post("/api/echo", content="{}", headers={"Content-Type": "text/plain"})
            client.get("/api/echo", headers={"Host": "example.com"})

    assert caplog.messages == [
        f"Refused POST /api/echo from {FOREIGN}: Requests from other sites aren't allowed",
        "Refused POST /api/echo from https://example.org: Requests from other sites aren't allowed",
        "Refused POST /api/echo from testserver: "
        "Send the request as application/json, not text/plain",
        "Refused GET /api/echo from example.com: This server only answers to localhost",
    ]


def walk(routes: Iterable[BaseRoute], prefix: str = "") -> Iterator[tuple[str, BaseRoute]]:
    """Every route in `routes` with its path, failing on any kind of route this test can't call."""
    for route in routes:
        if isinstance(route, Mount) and route.routes:
            yield from walk(route.routes, prefix + route.path)
        elif isinstance(route, Route | WebSocketRoute):
            path = route.path_format.format(**dict.fromkeys(route.param_convertors, "1"))
            yield prefix + path, route
        else:
            raise AssertionError(f"Teach the guard and this test about {route!r}")


SERVER = list(walk(create_app().routes))
CHANGING = [
    pytest.param(path, method, id=f"{method} {path}")
    for path, route in SERVER
    if isinstance(route, Route)
    for method in sorted(set(CHANGES) if route.methods is None else route.methods)
    if method not in ("GET", "HEAD")
]
SOCKETS = [path for path, route in SERVER if isinstance(route, WebSocketRoute)]


def test_finds_the_servers_routes() -> None:
    found = {param.values for param in CHANGING}

    assert found >= {
        ("/api/art/preview", "POST"),
        ("/api/characters/1", "DELETE"),
        ("/api/characters/1", "PUT"),
        ("/api/characters/1/voice/recording", "POST"),
        ("/api/characters/generate", "POST"),
        ("/api/characters/import", "POST"),
        ("/api/characters/reroll", "POST"),
        ("/api/jobs", "POST"),
        ("/api/news/feeds", "POST"),
        ("/api/news/feeds/check", "POST"),
        ("/api/player", "PUT"),
        ("/api/worlds", "POST"),
    }
    assert set(SOCKETS) >= {"/ws", "/ws/jobs/1"}


@pytest.fixture
def server() -> TestClient:
    return TestClient(create_app())


@pytest.mark.parametrize(("path", "method"), CHANGING)
def test_every_change_the_server_takes_is_guarded(
    server: TestClient, path: str, method: str
) -> None:
    def call(headers: dict[str, str]) -> int:
        return server.request(method, path, content=b"{}", headers=headers).status_code

    assert call(JSON | {"Origin": FOREIGN}) == 403
    assert call(JSON | {"Origin": "null"}) == 403
    assert call(JSON | {"Host": "example.com:8000"}) == 403
    assert [call({"Content-Type": media}) for media in SAFELISTED] == [415] * 3


@pytest.mark.parametrize("path", SOCKETS)
def test_every_websocket_the_server_takes_is_guarded(server: TestClient, path: str) -> None:
    assert refused_socket(server, path, {"Origin": FOREIGN}) == 1008
    assert refused_socket(server, path, {"Origin": "null"}) == 1008
    assert refused_socket(server, path, {"Host": "example.com:8000"}) == 1008


def test_stops_logging_when_too_many_sites_have_been_refused(
    client: TestClient, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(guard, "MAX_LOGGED", 3)

    with caplog.at_level(logging.WARNING, logger="simile.guard"):
        statuses = [
            client.get("/api/echo", headers={"Host": f"r{n}.attacker.example:8000"}).status_code
            for n in range(5)
        ]

    assert statuses == [403] * 5
    assert [message.split(":")[0] for message in caplog.messages] == [
        f"Refused GET /api/echo from r{n}.attacker.example" for n in range(3)
    ]
