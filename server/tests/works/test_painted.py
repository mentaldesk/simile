import asyncio
import io

import numpy as np
import pytest
from PIL import Image

from simile.llm import FakeProvider, LLMClient, LLMError
from simile.memory import MemoryStore
from simile.schema import CoreValue, Craft, Medium, MemoryKind, Npc, Work
from simile.sim import Clock
from simile.works import DEFAULT_CONFIG, Maker, WorksStore
from simile.works.maker import MuralPictureReply, PaintingPictureReply
from simile.works.painter import FakeImageModel, Painter
from simile.works.render import canvas, painting_canvas

from .conftest import NOW, SUKI, VIKTOR, WALL, mural_reply, svg

NPCS = {npc.id: npc for npc in (VIKTOR, SUKI)}
PAINTER = VIKTOR.model_copy(
    update={"craft": Craft(medium=Medium.PAINTING, form="small oil studies of the harbour")}
)
PICTURE = "A yellow sun over a red wall, with a blue door below it, in thick flat brushstrokes."
TONE = (
    "Keep it fit for every neighbour who sees it, children too: no violence, weapons or blood, "
    "nothing frightening or gruesome, and nothing adult or suggestive."
)


def picture_reply(medium: Medium = Medium.MURAL, **fields: object) -> str:
    model = MuralPictureReply if medium is Medium.MURAL else PaintingPictureReply
    return model.model_validate(
        {
            "title": "Sunrise Over the Square",
            "description": "A red wall with a yellow sun in the middle.",
            "statement": "Morning belongs to everyone.",
            "picture": f" {PICTURE} ",
            "inspired_by": [],
            "tags": ["Mornings"],
            "sentiment": 7.0,
            **{value.value: 0.0 for value in CoreValue},
            "freedom": 8.0,
            **fields,
        }
    ).model_dump_json()


async def make(
    fake: FakeProvider,
    model: FakeImageModel,
    memory: MemoryStore,
    works: WorksStore,
    npc: Npc = SUKI,
    wall: str | None = "wall_1",
) -> tuple[Work | None, list[tuple[Work, str, bytes]]]:
    llm, hung = LLMClient(fake), []

    def hang(work: Work, svg: str, png: bytes) -> None:
        hung.append((work, svg, png))

    async with Painter(model, timeout=10) as painter:
        maker = Maker(
            works,
            memory,
            Clock(NOW),
            lambda: llm,
            walls=[WALL],
            npcs=NPCS,
            hang=hang,
            painter=painter,
            config=DEFAULT_CONFIG,
        )
        task = maker.make(npc, wall)
        assert task is not None
        return await task, hung


def test_a_painter_paints_a_mural_from_a_description_of_it(
    memory: MemoryStore, works: WorksStore
) -> None:
    fake, model = FakeProvider([picture_reply()]), FakeImageModel()

    made, _ = asyncio.run(make(fake, model, memory, works))

    assert made is not None
    assert works.showing() == {"wall_1": made}
    assert made.text == "A red wall with a yellow sun in the middle."
    assert works.svg(made.id) == ""
    png = Image.open(io.BytesIO(works.picture(made.id) or b""))
    assert png.size == canvas(WALL)
    [prompt] = model.prompts
    assert prompt.startswith(f"{PICTURE} Hand-painted street mural, ")
    assert prompt.endswith("No text, no lettering, no logos.")
    [request] = fake.requests
    asked = request.messages[-1].content
    assert "Describe the picture you'll paint, filling the whole wall." in asked
    assert "Put no words, letters, numbers, signs or logos in it" in asked
    assert TONE in asked
    assert "SVG" not in asked
    [remembered] = memory.recall("suki", NOW, kind=MemoryKind.WORK)
    assert remembered.work_id == made.id


def test_a_painted_mural_goes_on_weathered_plaster(memory: MemoryStore, works: WorksStore) -> None:
    made, _ = asyncio.run(make(FakeProvider([picture_reply()]), FakeImageModel(), memory, works))

    assert made is not None
    painted = np.asarray(Image.open(io.BytesIO(works.picture(made.id) or b"")), dtype=float)
    top = painted[: painted.shape[0] // 2]
    assert top.std(axis=(0, 1)).max() > 1


def test_a_painting_is_painted_on_canvas_and_hung_with_no_svg(
    memory: MemoryStore, works: WorksStore
) -> None:
    fake, model = FakeProvider([picture_reply(Medium.PAINTING)]), FakeImageModel()

    made, hung = asyncio.run(make(fake, model, memory, works, PAINTER, None))

    assert made is not None and made.medium is Medium.PAINTING
    [(work, drawn, png)] = hung
    assert work == made and drawn == ""
    assert Image.open(io.BytesIO(png)).size == painting_canvas()
    [prompt] = model.prompts
    assert prompt.startswith(f"{PICTURE} Hand-painted acrylic painting on canvas")
    assert prompt.endswith("No text, no lettering, no logos.")
    asked = fake.requests[0].messages[-1].content
    assert "Describe the picture you'll paint, filling the whole canvas" in asked
    assert TONE in asked


@pytest.mark.parametrize(
    ("medium", "npc", "wall", "fallback"),
    [
        (Medium.MURAL, SUKI, "wall_1", mural_reply()),
        (Medium.PAINTING, PAINTER, None, mural_reply(svg=svg(*painting_canvas()))),
    ],
    ids=str,
)
def test_draws_it_as_svg_when_painting_it_fails(
    medium: Medium,
    npc: Npc,
    wall: str | None,
    fallback: str,
    memory: MemoryStore,
    works: WorksStore,
) -> None:
    fake = FakeProvider([picture_reply(medium), fallback])

    made, hung = asyncio.run(make(fake, FakeImageModel(failing=True), memory, works, npc, wall))

    assert made is not None and made.medium is medium
    painted, drawn = (request.messages[-1].content for request in fake.requests)
    assert "Describe the picture you'll paint" in painted
    assert "Draw it as one SVG document" in drawn
    svg_of = works.svg(made.id) if medium is Medium.MURAL else hung[0][1]
    assert svg_of and svg_of.startswith("<svg")


def test_a_failed_description_makes_nothing_and_paints_nothing(
    memory: MemoryStore, works: WorksStore
) -> None:
    fake, model = FakeProvider([LLMError("down")]), FakeImageModel()

    made, _ = asyncio.run(make(fake, model, memory, works))

    assert made is None
    assert len(fake.requests) == 1
    assert model.prompts == []
    assert works.showing() == {}
