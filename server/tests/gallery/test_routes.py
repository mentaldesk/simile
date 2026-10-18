import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from simile.gallery import GalleryStore
from simile.gallery.routes import routes

from .conftest import NOW


@pytest.fixture
def client(store: GalleryStore) -> TestClient:
    app = Starlette(routes=routes)
    app.state.gallery_store = store
    return TestClient(app)


def test_serves_a_paintings_picture(client: TestClient, store: GalleryStore) -> None:
    store.hang("kofi-1", "<svg/>", b"\x89PNG", [("gallery", "painting_1")], NOW)

    response = client.get("/api/gallery/kofi-1.png")

    assert response.status_code == 200
    assert response.content == b"\x89PNG"
    assert response.headers["content-type"] == "image/png"
    assert "max-age" in response.headers["cache-control"]


@pytest.mark.parametrize("path", ["nobody-1.png", "..%2Fsimile.db.png", "kofi-1.svg", "%00.png"])
def test_serves_nothing_but_the_pictures_the_gallery_stored(
    path: str, client: TestClient, store: GalleryStore
) -> None:
    store.hang("kofi-1", "<svg/>", b"\x89PNG", [("gallery", "painting_1")], NOW)

    assert client.get(f"/api/gallery/{path}").status_code == 404
