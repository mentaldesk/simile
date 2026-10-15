from collections.abc import Callable

from starlette.testclient import TestClient

from simile.app import create_app

MakePackage = Callable[[dict[str, str]], str]


def test_health() -> None:
    response = TestClient(create_app()).get("/api/health")

    assert response.json() == {"status": "ok"}


def test_mounts_routes_from_modules(make_package: MakePackage) -> None:
    package = make_package(
        {
            "gamma/routes.py": (
                "from starlette.responses import PlainTextResponse\n"
                "from starlette.routing import Route\n"
                "async def ping(request):\n"
                "    return PlainTextResponse('pong')\n"
                "routes = [Route('/api/gamma/ping', ping)]\n"
            ),
        }
    )

    response = TestClient(create_app(package)).get("/api/gamma/ping")

    assert response.text == "pong"


def lifespan_source(module: str) -> str:
    return (
        "from contextlib import asynccontextmanager\n"
        "@asynccontextmanager\n"
        "async def lifespan(app):\n"
        "    app.state.events = getattr(app.state, 'events', [])\n"
        f"    app.state.events.append('{module} up')\n"
        "    yield\n"
        f"    app.state.events.append('{module} down')\n"
    )


def test_runs_module_lifespans_in_order(make_package: MakePackage) -> None:
    package = make_package(
        {
            "beta/lifespan.py": lifespan_source("beta"),
            "alpha/lifespan.py": lifespan_source("alpha"),
            "gamma/__init__.py": "",
        }
    )
    app = create_app(package)

    with TestClient(app):
        assert app.state.events == ["alpha up", "beta up"]

    assert app.state.events == ["alpha up", "beta up", "beta down", "alpha down"]
