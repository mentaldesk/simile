import numpy as np
from PIL import Image, ImageDraw

from simile.characters.palette import PLAYER
from simile.dolls.colour import delta_e, rgb
from simile.dolls.flux import figure
from simile.dolls.measure import (
    CLOSE,
    MARKS,
    anchors,
    face_marks,
    hidden,
    matched,
    pulled,
    swatches,
    worst,
)
from simile.schema import Appearance

from .keyed import keyed

COLOURS = {
    "skin": PLAYER.skin,
    "hair": PLAYER.hair_colour,
    "top": PLAYER.top_colour,
    "bottom": PLAYER.bottom_colour,
    "shoe": PLAYER.shoe_colour,
}


def painted(**off: str) -> Image.Image:
    return keyed(figure((300, 400), COLOURS | off))


def test_finds_each_colour_in_its_band() -> None:
    found = swatches(painted(), PLAYER)

    assert worst(found) < 1
    assert {name: s.got for name, s in found.items()} == COLOURS


def test_a_colour_painted_off_is_measured_and_pulled_back_keeping_the_rest() -> None:
    skin = "#e09b47"
    off = painted(skin=skin)
    before = swatches(off, PLAYER)

    fixed = matched(off, anchors(off, PLAYER))

    after = swatches(fixed, PLAYER)
    assert before["skin"].delta_e > CLOSE
    assert after["skin"].delta_e < 1
    pixels = np.asarray(fixed.convert("RGB"))
    for name in ("top", "bottom", "hair"):
        assert after[name].delta_e < 1, name
    top = pixels[np.all(np.asarray(off.convert("RGB")) == rgb(PLAYER.top_colour), axis=2)]
    assert delta_e(top, rgb(PLAYER.top_colour)).max() < 0.5


def test_another_colour_altogether_isnt_pulled_back() -> None:
    blue = painted(top="#a22633")

    fixed = matched(blue, anchors(blue, PLAYER))

    assert swatches(fixed, PLAYER)["top"].delta_e > CLOSE


def test_hair_under_a_cap_may_not_show() -> None:
    capped = Appearance.model_validate(PLAYER.model_dump() | {"accessories": ["cap"]})

    assert hidden(capped) == {"hair"}
    assert hidden(PLAYER) == frozenset()


def test_hair_a_cap_hides_isnt_pulled_onto_the_face() -> None:
    capped = Appearance.model_validate(
        PLAYER.model_dump() | {"accessories": ["cap"], "skin": "#ead4aa", "hair_colour": "#c0cbdc"}
    )
    face = keyed(figure((300, 400), COLOURS | {"skin": "#ead4aa", "hair": "#7a3cc0"}))

    assert "hair" not in anchors(face, capped)
    assert face_marks(pulled(face, capped), capped) == 0


def test_a_clean_face_has_no_marks_and_a_patch_painted_on_it_does() -> None:
    marked = figure((300, 400), COLOURS)
    ImageDraw.Draw(marked).ellipse((160, 75, 195, 105), "#8b9bb4")

    assert face_marks(painted(), PLAYER) == 0
    assert face_marks(keyed(marked), PLAYER) > MARKS
