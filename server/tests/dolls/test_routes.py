import base64
import io

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from PIL import Image
from starlette.applications import Starlette
from starlette.testclient import TestClient

from simile.art.palette import PALETTE
from simile.dolls.routes import MAX_BODY, routes
from simile.dolls.shapes import PIECES
from simile.schema import Accessory, Build, HairStyle

COLOURS = st.sampled_from(sorted(PALETTE.values()))
APPEARANCES = st.fixed_dictionaries(
    {
        "skin": COLOURS,
        "hair_style": st.sampled_from([s.value for s in HairStyle]),
        "hair_colour": COLOURS,
        "top_colour": COLOURS,
        "bottom_colour": COLOURS,
        "shoe_colour": COLOURS,
        "build": st.sampled_from([b.value for b in Build]),
        "accessories": st.lists(st.sampled_from([a.value for a in Accessory]), unique=True),
    }
)


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(Starlette(routes=routes))


def atlas(data_url: str) -> Image.Image:
    head, _, data = data_url.partition(",")
    assert head == "data:image/webp;base64"
    return Image.open(io.BytesIO(base64.b64decode(data)))


@settings(
    max_examples=15, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(appearance=APPEARANCES)
def test_draws_a_flat_doll_for_any_appearance(client: TestClient, appearance: dict) -> None:
    response = client.post("/api/dolls/flat", json={"appearance": appearance})

    assert response.status_code == 200
    doll = response.json()
    assert "painted" not in doll
    image = atlas(doll["flat"])
    assert set(doll["pieces"]) == set(PIECES)
    for name, piece in doll["pieces"].items():
        x, y, w, h = piece["frame"]
        assert x + w <= image.width and y + h <= image.height, name
        assert image.crop((x, y, x + w, y + h)).getchannel("A").getbbox() is not None, name


def test_a_characters_id_picks_their_accent(client: TestClient) -> None:
    from simile.art.characters import PLAYER

    look = PLAYER.model_dump(mode="json")

    ingrid = client.post("/api/dolls/flat", json={"character": "ingrid", "appearance": look})
    odalys = client.post("/api/dolls/flat", json={"character": "odalys", "appearance": look})

    assert atlas(ingrid.json()["flat"]).tobytes() != atlas(odalys.json()["flat"]).tobytes()


def test_refuses_a_bad_appearance(client: TestClient) -> None:
    response = client.post("/api/dolls/flat", json={"appearance": {"skin": "pink"}})

    assert response.status_code == 422
    assert "appearance.skin" in response.json()["error"]


def test_refuses_a_huge_request(client: TestClient) -> None:
    response = client.post("/api/dolls/flat", content=b"x" * (MAX_BODY + 1))

    assert response.status_code == 413
