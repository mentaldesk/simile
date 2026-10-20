import json

import numpy as np
import pytest
from PIL import Image, ImageFilter

from simile.dolls.build import CONTENT, fingerprint, people
from simile.dolls.colour import RGB, delta_e, rgb
from simile.dolls.doll import atlas, flat_doll, pack
from simile.dolls.look import Look
from simile.dolls.shapes import PIECES

BUDGET = 3 * 1024 * 1024
EVERYONE = people()
FIELDS = {
    "skin": "skin",
    "hair": "hair_colour",
    "top": "top_colour",
    "bottom": "bottom_colour",
    "shoe": "shoe_colour",
}
FROM_LOOK = 4.0
"""How far a painted piece's colour may be from the look it was cut from (CIEDE2000)."""
FROM_APPEARANCE = {"skin": 3.5, "hair": 8.0, "top": 8.0, "bottom": 8.0, "shoe": 8.0}
"""And from the `Appearance`: skin is kept exactly, the rest muted by up to about 6."""


def manifest(who: str) -> dict:
    return json.loads((CONTENT / f"{who}.json").read_text())


def painted_colours(who: str) -> list[tuple[str, str, np.ndarray, RGB]]:
    """(piece, colour name, typical painted colour, look colour) for each named colour each piece
    shows, away from its edges."""
    look = Look.of(EVERYONE[who], who)
    found = manifest(who)
    flat = Image.open(CONTENT / found["flat"]).convert("RGBA")
    painted = np.asarray(Image.open(CONTENT / found["painted"]).convert("RGB"), dtype=np.float64)
    inner = np.asarray(flat.getchannel("A").filter(ImageFilter.MinFilter(7))) == 255
    f = np.asarray(flat)[..., :3]
    out = []
    for piece, spec in found["pieces"].items():
        x, y, w, h = spec["frame"]
        window = np.zeros(inner.shape, dtype=bool)
        window[y : y + h, x : x + w] = True
        for name in FIELDS:
            target = getattr(look, name)
            mask = window & inner & (f == target).all(axis=2)
            if mask.sum() >= 150:
                out.append((piece, name, np.median(painted[mask], axis=0), target))
    return out


def test_content_dolls_stay_within_budget() -> None:
    assert sum(path.stat().st_size for path in CONTENT.rglob("*") if path.is_file()) < BUDGET


@pytest.mark.parametrize("who", EVERYONE)
def test_every_resident_and_the_player_has_a_current_doll(who: str) -> None:
    found = manifest(who)

    assert found["hash"] == fingerprint(who, EVERYONE[who]), "run `uv run simile dolls paint`"
    assert found["appearance"] == EVERYONE[who].model_dump(mode="json")
    assert set(found["pieces"]) == set(PIECES)
    assert (CONTENT / found["flat"]).is_file() and (CONTENT / found["painted"]).is_file()


@pytest.mark.parametrize("who", EVERYONE)
def test_the_flat_atlas_is_what_the_code_draws(who: str) -> None:
    doll = flat_doll(Look.of(EVERYONE[who], who))
    size, frames = pack(doll.flat)
    drawn = np.asarray(atlas(doll.flat, size, frames), dtype=np.int16)

    committed = np.asarray(Image.open(CONTENT / f"{who}-flat.webp").convert("RGBA"), np.int16)

    assert committed.shape == drawn.shape
    visible = drawn[..., 3] > 0
    assert np.abs(committed[visible] - drawn[visible]).max() <= 2
    assert {k: v["frame"] for k, v in manifest(who)["pieces"].items()} == {
        k: list(v) for k, v in frames.items()
    }


@pytest.mark.parametrize("who", EVERYONE)
def test_every_painted_piece_keeps_the_appearances_colours(who: str) -> None:
    appearance = EVERYONE[who]
    shown = painted_colours(who)

    assert {"skin", "top", "bottom", "shoe"} <= {name for _, name, _, _ in shown}
    for piece, name, mean, target in shown:
        wanted = rgb(getattr(appearance, FIELDS[name]))
        assert delta_e(mean, target) < FROM_LOOK, f"{piece} {name}"
        assert delta_e(mean, wanted) < FROM_APPEARANCE[name], f"{piece} {name}"
