from pathlib import Path

import pytest
from starlette.testclient import TestClient

from simile.app import create_app


def test_health() -> None:
    response = TestClient(create_app()).get("/api/health")

    assert response.json() == {"status": "ok"}


def test_mounts_routes_from_modules(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "fakesrv" / "gamma").mkdir(parents=True)
    (tmp_path / "fakesrv" / "__init__.py").write_text("")
    (tmp_path / "fakesrv" / "gamma" / "__init__.py").write_text("")
    (tmp_path / "fakesrv" / "gamma" / "routes.py").write_text(
        "from starlette.responses import PlainTextResponse\n"
        "from starlette.routing import Route\n"
        "async def ping(request):\n"
        "    return PlainTextResponse('pong')\n"
        "routes = [Route('/api/gamma/ping', ping)]\n"
    )
    monkeypatch.syspath_prepend(tmp_path)

    response = TestClient(create_app("fakesrv")).get("/api/gamma/ping")

    assert response.text == "pong"
