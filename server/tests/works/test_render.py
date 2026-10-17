import io

import pytest
from PIL import Image, ImageStat

from simile.art.iso.camera import TILE_W
from simile.works.render import canvas, draw
from simile.works.svg import BadSvg, checked
from simile.world.map import load_map

from .conftest import WALL, svg

WIDTH, HEIGHT = canvas(WALL)


def picture(drawing: str, seed: int = 1, timeout: float = 30, memory: int = 2**30) -> Image.Image:
    png = draw(drawing, WIDTH, HEIGHT, seed=seed, timeout=timeout, memory=memory)
    return Image.open(io.BytesIO(png))


def test_a_mural_is_an_iso_tile_wide_per_tile_and_as_tall_at_that_scale() -> None:
    assert canvas(WALL) == (3 * TILE_W, 262)
    for wall in load_map().murals:
        width, height = canvas(wall)
        assert width == wall.width * TILE_W
        metres = (wall.width * 1.1, (wall.top - wall.bottom) * 3.0)
        assert width / height == pytest.approx(metres[0] / metres[1], rel=0.01)


def test_paints_the_svg_onto_plaster_at_the_walls_size() -> None:
    clean = checked(svg(WIDTH, HEIGHT), WIDTH, HEIGHT, chars=9999, elements=99, tolerance=0.1)

    image = picture(clean)

    assert (image.format, image.size, image.mode) == ("PNG", (WIDTH, HEIGHT), "RGB")
    middle = (WIDTH // 2 - 20, HEIGHT // 2 - 20, WIDTH // 2 + 20, HEIGHT // 2 + 20)
    sun = ImageStat.Stat(image.crop(middle)).mean
    corner = ImageStat.Stat(image.crop((0, 0, 20, 20))).mean
    assert sun[2] < 140 < sun[1] < sun[0]
    assert corner[1] < 120 < corner[0]
    assert picture(clean).tobytes() == image.tobytes()
    assert picture(clean, seed=2).tobytes() != image.tobytes()


def test_weathering_never_takes_more_than_about_half_the_paint() -> None:
    black = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}">'
    black += f'<rect width="{WIDTH}" height="{HEIGHT}" fill="#000"/></svg>'

    for seed in range(3):
        assert max(channel for _, channel in picture(black, seed).getextrema()) < 120


@pytest.mark.parametrize(
    ("drawing", "reason"),
    [
        ("not an svg", "couldn't be drawn"),
        (svg(inside='<g transform="scale(1e30)"><circle r="1"/></g>'), "couldn't be drawn"),
        (svg(inside="<g>" * 1000 + "<rect/>" + "</g>" * 1000), "crashed the renderer"),
    ],
    ids=["not svg", "panics", "overflows the stack"],
)
def test_an_svg_that_fails_or_crashes_resvg_is_bad(drawing: str, reason: str) -> None:
    with pytest.raises(BadSvg, match=reason):
        picture(drawing)


def test_an_svg_that_takes_too_long_to_draw_is_bad() -> None:
    noise = '<filter id="f"><feTurbulence numOctaves="100000000"/></filter>'
    slow = svg(inside=f'{noise}<rect width="288" height="262" filter="url(#f)"/>')

    with pytest.raises(BadSvg, match="took more than 2 s to draw"):
        picture(slow, timeout=2)


def test_an_svg_that_takes_too_much_memory_to_draw_is_bad() -> None:
    tile = '<pattern id="p" width="1" height="1" patternUnits="userSpaceOnUse">'
    tile += '<rect width="1" height="1"/></pattern>'
    fill = '<rect width="0.003" height="0.003" fill="url(#p)"/>'
    huge = svg(inside=f'{tile}<g transform="scale(100000)">{fill}</g>')

    with pytest.raises(BadSvg, match="took more than 200 MB to draw"):
        picture(huge, memory=200 * 2**20)
