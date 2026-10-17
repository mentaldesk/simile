import io
import json
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from PIL import Image
from starlette.applications import Starlette
from starlette.testclient import TestClient

from simile.app import create_app
from simile.art import characters
from simile.jobs.runner import CONTENT
from simile.schema import Appearance

LOOK = Appearance.model_validate(
    {
        "skin": "#c28569",
        "hair_style": "curly",
        "hair_colour": "#733e39",
        "top_colour": "#3e8948",
        "bottom_colour": "#262b44",
        "shoe_colour": "#181425",
        "build": "broad",
        "accessories": ["glasses", "scarf"],
    }
)


@pytest.fixture
def client(make_package: Callable[[dict[str, str]], str], root: Path) -> Iterator[TestClient]:
    package = make_package(
        {
            "jobs/lifespan.py": "from simile.jobs.lifespan import lifespan\n",
            "jobs/routes.py": "from simile.jobs.routes import routes\n",
        }
    )
    app: Starlette = create_app(package)
    with TestClient(app) as client:
        yield client


def content_files() -> dict[Path, int]:
    return {path: path.stat().st_mtime_ns for path in CONTENT.rglob("*") if path.is_file()}


def test_draws_a_sprite_the_client_can_load(client: TestClient, root: Path) -> None:
    before = content_files()
    params = {"character": "new_face", "appearance": LOOK.model_dump(mode="json")}

    job_id = client.post("/api/jobs", json={"kind": "sprite", "params": params}).json()["id"]
    with client.websocket_connect(f"/ws/jobs/{job_id}") as ws:
        while (job := ws.receive_json())["state"] in ("queued", "running"):
            pass
    image = client.get(job["result"]["image"])
    atlas = client.get(job["result"]["atlas"])

    assert job["state"] == "succeeded", job["error"]
    assert job["result"] == {
        "image": "/api/jobs/files/sprite/new_face.png",
        "atlas": "/api/jobs/files/sprite/new_face.json",
    }
    assert image.headers["content-type"] == "image/png"
    assert atlas.json() == characters.atlas("new_face.png")
    drawn = Image.open(io.BytesIO(image.content))
    expected = characters.sprite_sheet(LOOK, seed="new_face").to_image()
    assert drawn.mode == "RGBA" and drawn.size == (48, 192)
    assert drawn.tobytes() == expected.tobytes()
    assert sorted(path.name for path in (root / "sprite").iterdir()) == [
        "new_face.json",
        "new_face.png",
    ]
    assert content_files() == before


@pytest.mark.parametrize("character", ["kofi", "player", "sample_coder"])
def test_never_draws_a_character_from_content(client: TestClient, character: str) -> None:
    params = {"character": character, "appearance": LOOK.model_dump(mode="json")}

    response = client.post("/api/jobs", json={"kind": "sprite", "params": params})

    assert response.status_code == 422
    assert response.json() == {
        "error": f"character: {character} has a sprite in content/, which jobs never change"
    }


def test_drawing_again_replaces_the_sprite(client: TestClient, root: Path) -> None:
    for look in (LOOK, Appearance.model_validate({**LOOK.model_dump(), "hair_style": "bald"})):
        params = {"character": "new_face", "appearance": look.model_dump(mode="json")}
        job_id = client.post("/api/jobs", json={"kind": "sprite", "params": params}).json()["id"]
        with client.websocket_connect(f"/ws/jobs/{job_id}") as ws:
            while ws.receive_json()["state"] in ("queued", "running"):
                pass

    drawn = Image.open(root / "sprite" / "new_face.png")
    bald = characters.sprite_sheet(look, seed="new_face").to_image()
    assert drawn.tobytes() == bald.tobytes()
    assert json.loads((root / "sprite" / "new_face.json").read_text())["meta"]["image"] == (
        "new_face.png"
    )
