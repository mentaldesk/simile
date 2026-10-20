import io
from typing import Any

import pytest
from PIL import Image
from starlette.testclient import TestClient

from simile.app import create_app
from simile.behaviour import MuralSpot, behaviour_of
from simile.gallery import Gallery
from simile.llm import FakeProvider, LLMClient
from simile.schema import MapTile, Medium, Npc, Work
from simile.works import Maker, works_of
from simile.works.render import painting_canvas

from .conftest import KOFI, TOBIAS, painter, painting, painting_reply


async def make(maker: Maker, npc: Npc, wall: str | None = None) -> Work | None:
    task = maker.make(npc, wall)
    assert task is not None
    return await task


def until_paintings(ws: Any) -> dict[str, Any]:
    for _ in range(500):
        if (message := ws.receive_json())["type"] == "paintings":
            return message
    raise AssertionError("no paintings message")


@pytest.mark.usefixtures("database")
def test_paintings_made_in_the_server_hang_and_everyone_hears(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("simile.works.lifespan.shopkeepers", list)
    app = create_app()

    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        greeted = [ws.receive_json() for _ in range(4)]
        maker, gallery = app.state.maker, app.state.gallery
        assert isinstance(gallery, Gallery)
        assert maker.hang == gallery.hang
        app.state.llm = LLMClient(FakeProvider([painting_reply(), painting_reply(title="Two")]))

        made = client.portal.call(make, maker, painter(TOBIAS))
        hung = until_paintings(ws)
        by_kofi = client.portal.call(make, maker, KOFI, "house_6")
        hung_again = until_paintings(ws)
        picture = client.get(f"/api/gallery/{made.id}.png" if made else "")

    assert [message["type"] for message in greeted] == ["snapshot", "clock", "paintings", "murals"]
    assert len(greeted[2]["frames"]) == 13
    starters = [frame["painting"] is not None for frame in greeted[2]["frames"]]
    assert starters == [True] * 5 + [False] * 8
    assert made is not None and by_kofi is not None
    assert (made.medium, made.form) == (Medium.PAINTING, "small oil studies of the harbour")
    assert (by_kofi.medium, by_kofi.form, by_kofi.wall) == (
        Medium.PAINTING,
        KOFI.craft.form if KOFI.craft else "",
        None,
    )
    first = hung["frames"][5]
    assert (first["id"], first["painting"]["work_id"]) == (gallery.frames[5].id, made.id)
    assert hung_again["frames"][6]["painting"]["title"] == "Two"
    assert picture.status_code == 200
    assert Image.open(io.BytesIO(picture.content)).size == painting_canvas()
    assert maker.hang is None


@pytest.mark.usefixtures("database")
def test_muralists_take_turns_painting_for_the_gallery() -> None:
    app = create_app()

    with TestClient(app):
        works_of(app).add(painting("m1", "kofi", medium=Medium.MURAL, wall="tower"))
        turn = behaviour_of(app).hooks.mural_wall(KOFI)

    assert turn == MuralSpot("house_6", MapTile(map="house_6_floor_0", x=3, y=2))
