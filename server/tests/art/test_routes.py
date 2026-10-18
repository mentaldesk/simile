import io
import json
from pathlib import Path

import pytest
from PIL import Image
from starlette.applications import Starlette
from starlette.testclient import TestClient

from simile.art.characters import (
    FRAME_HEIGHT,
    FRAME_WIDTH,
    FRAMES,
    PLAYER,
    THREE_QUARTER,
    sprite_sheet,
)
from simile.art.routes import MAX_BODY, routes
from simile.jobs import sprite
from simile.schema import Appearance

LOOK = PLAYER.model_dump(mode="json") | {"accessories": ["cap", "scarf", "backpack"]}


@pytest.fixture
def client() -> TestClient:
    return TestClient(Starlette(routes=routes))


def frame(image: Image.Image, x: int, y: int) -> bytes:
    return image.crop((x, y, x + FRAME_WIDTH, y + FRAME_HEIGHT)).tobytes()


def png(content: bytes) -> Image.Image:
    return Image.open(io.BytesIO(content)).convert("RGBA")


@pytest.mark.parametrize("character", ["new_face", "player"])
def test_the_preview_is_the_saved_sprite_pixel_for_pixel(
    client: TestClient, tmp_path: Path, character: str
) -> None:
    params = {"character": character, "appearance": LOOK}
    (tmp_path / "params.json").write_text(json.dumps(params))
    sprite.main(tmp_path)
    saved = Image.open(tmp_path / f"{character}.png").convert("RGBA")
    atlas = json.loads((tmp_path / f"{character}.json").read_text())["frames"]

    response = client.post("/api/art/preview", json=params)

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    preview = png(response.content)
    assert preview.size == (FRAME_WIDTH * FRAMES, FRAME_HEIGHT * len(THREE_QUARTER))
    for row, direction in enumerate(THREE_QUARTER):
        for column in range(FRAMES):
            rect = atlas[f"{direction}-{column}"]["frame"]
            shown = frame(preview, column * FRAME_WIDTH, row * FRAME_HEIGHT)
            assert shown == frame(saved, rect["x"], rect["y"]), f"{direction}-{column}"


def test_draws_a_character_that_has_no_id_yet(client: TestClient) -> None:
    response = client.post("/api/art/preview", json={"appearance": LOOK})

    expected = sprite_sheet(Appearance.model_validate(LOOK), None, THREE_QUARTER).to_image()
    assert png(response.content).tobytes() == expected.tobytes()


@pytest.mark.parametrize(
    ("body", "reason"),
    [
        ({"appearance": LOOK | {"hair_style": "mohawk"}}, "appearance.hair_style:"),
        ({"appearance": LOOK | {"skin": "pink"}}, "appearance.skin:"),
        ({"character": "Not An Id", "appearance": LOOK}, "character:"),
        ({"character": "new_face"}, "appearance: Field required"),
    ],
)
def test_refuses_what_the_schema_refuses(client: TestClient, body: dict, reason: str) -> None:
    response = client.post("/api/art/preview", json=body)

    assert response.status_code == 422
    assert reason in response.json()["error"]


def test_refuses_a_large_request(client: TestClient) -> None:
    response = client.post(
        "/api/art/preview",
        content=b" " * (MAX_BODY + 1),
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 413
