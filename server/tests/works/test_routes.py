from collections.abc import Callable

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from simile.app import create_app
from simile.works import works_of

from .conftest import mural, work

PNG = b"\x89PNG\r\n\x1a\n a picture"


@pytest.fixture
def app(make_package: Callable[[dict[str, str]], str]) -> Starlette:
    package = make_package(
        {
            "memory/lifespan.py": "from simile.memory.lifespan import lifespan\n",
            "works/lifespan.py": "from simile.works.lifespan import lifespan\n",
            "works/routes.py": "from simile.works.routes import routes\n",
        }
    )
    return create_app(package)


def test_serves_a_murals_picture(app: Starlette) -> None:
    with TestClient(app) as client:
        works_of(app).paint(mural("suki-1a2b"), "<svg/>", PNG)
        response = client.get("/api/works/suki-1a2b.png")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content == PNG


@pytest.mark.parametrize(
    "path",
    [
        "/api/works/poem.png",
        "/api/works/nothing.png",
        "/api/works/suki-1a2b",
        "/api/works/suki-1a2b.svg",
        "/api/works/..%2F..%2Fsimile.db.png",
        "/api/works/%2E%2E%2Fsuki-1a2b.png",
    ],
)
def test_serves_nothing_but_a_murals_picture(app: Starlette, path: str) -> None:
    with TestClient(app) as client:
        works_of(app).paint(mural("suki-1a2b"), "<svg/>", PNG)
        works_of(app).add(work("poem"))
        response = client.get(path)

    assert response.status_code == 404
    assert response.content != PNG
