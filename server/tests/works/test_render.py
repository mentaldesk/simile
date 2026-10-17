import io

import pytest
from PIL import Image, ImageStat

from simile.art.iso.camera import TILE_W
from simile.works.render import canvas, render
from simile.works.svg import BadSvg, checked
from simile.world.map import load_map

from .conftest import WALL, svg


def test_a_mural_is_an_iso_tile_wide_per_tile_and_as_tall_at_that_scale() -> None:
    assert canvas(WALL) == (3 * TILE_W, 262)
    for wall in load_map().murals:
        width, height = canvas(wall)
        assert width == wall.width * TILE_W
        metres = (wall.width * 1.1, (wall.top - wall.bottom) * 3.0)
        assert width / height == pytest.approx(metres[0] / metres[1], rel=0.01)


@pytest.mark.parametrize("bricks", [False, True])
def test_paints_the_svg_onto_a_wall_at_its_size(bricks: bool) -> None:
    width, height = canvas(WALL)
    clean = checked(svg(width, height), width, height, chars=9999, elements=99, tolerance=0.1)

    png = render(clean, width, height, seed=1, bricks=bricks)

    image = Image.open(io.BytesIO(png))
    assert image.format == "PNG"
    assert image.size == (width, height)
    assert image.mode == "RGB"
    middle = (width // 2 - 20, height // 2 - 20, width // 2 + 20, height // 2 + 20)
    sun = ImageStat.Stat(image.crop(middle)).mean
    corner = ImageStat.Stat(image.crop((0, 0, 20, 20))).mean
    assert sun[2] < 140 < sun[1] < sun[0]
    assert corner[1] < 120 < corner[0]
    assert render(clean, width, height, seed=1, bricks=bricks) == png
    assert render(clean, width, height, seed=2, bricks=bricks) != png


def test_something_resvg_cant_draw_is_bad_svg() -> None:
    with pytest.raises(BadSvg, match="couldn't be drawn"):
        render("not an svg", 10, 10, seed=0)
