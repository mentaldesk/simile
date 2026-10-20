import io
from dataclasses import replace

import pytest
from PIL import Image, ImageStat

from simile.works.render import PAINTING_M, canvas, draw, metres, painting_canvas
from simile.works.svg import BadSvg, checked
from simile.world.map import load_maps, with_every_location

from .conftest import WALL, svg

WIDTH, HEIGHT = canvas(WALL)


def picture(drawing: str, seed: int = 1, timeout: float = 30, memory: int = 2**30) -> Image.Image:
    png = draw(drawing, WIDTH, HEIGHT, seed=seed, timeout=timeout, memory=memory)
    return Image.open(io.BytesIO(png))


def test_a_mural_is_96_px_a_tile_wide_and_as_tall_at_that_scale() -> None:
    assert metres(WALL) == pytest.approx((3 * 1.1, 4.4))
    assert canvas(WALL) == (3 * 96, 384)
    for wall in with_every_location(load_maps()).murals:
        width, height = canvas(wall)
        across, up = metres(wall)
        assert width == wall.width * 96
        assert width / height == pytest.approx(across / up, rel=0.01)


def test_a_mural_goes_no_higher_than_its_buildings_eaves() -> None:
    walls = {wall.id: wall for wall in with_every_location(load_maps()).murals}
    house_10 = walls["banyan_row"]

    assert metres(house_10)[1] == pytest.approx(7 * 1.1 - house_10.bottom * 4.4)
    assert metres(replace(WALL, top=5))[1] == pytest.approx(11 * 1.1 - WALL.bottom * 4.4)


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


def test_a_painting_is_the_frames_opening_960_px_across() -> None:
    width, height = painting_canvas()
    across, up = PAINTING_M
    assert (width, height) == (960, 602)
    assert (across, up) == pytest.approx((1.34, 0.84))
    assert width / height == pytest.approx(across / up, rel=0.01)


def test_paints_a_painting_onto_a_primed_canvas_without_weathering() -> None:
    width, height = painting_canvas()
    clean = checked(svg(width, height), width, height, chars=9999, elements=99, tolerance=0.1)

    def painted(seed: int) -> Image.Image:
        png = draw(clean, width, height, seed=seed, timeout=30, memory=2**30, on_canvas=True)
        return Image.open(io.BytesIO(png))

    image = painted(1)

    assert (image.format, image.size, image.mode) == ("PNG", (width, height), "RGB")
    red = ImageStat.Stat(image.crop((0, 0, 40, 40))).mean
    assert red[0] > 200 and red[1] < 70
    assert painted(2).tobytes() == image.tobytes()


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


NOISE = '<filter id="f"><feTurbulence numOctaves="100000000"/></filter>'
SLOW = svg(inside=f'{NOISE}<rect width="288" height="262" filter="url(#f)"/>')


def test_an_svg_that_takes_too_long_to_draw_is_bad() -> None:
    with pytest.raises(BadSvg, match="took more than 2 s to draw"):
        picture(SLOW, timeout=2)


def test_the_renderer_is_killed_once_it_uses_more_memory_than_it_may() -> None:
    with pytest.raises(BadSvg, match="took more than 1 MB to draw"):
        picture(SLOW, memory=2**20)


def test_an_svg_that_takes_too_much_memory_to_draw_is_bad() -> None:
    tile = '<pattern id="p" width="1" height="1" patternUnits="userSpaceOnUse">'
    tile += '<rect width="1" height="1"/></pattern>'
    fill = '<rect width="0.003" height="0.003" fill="url(#p)"/>'
    huge = svg(inside=f'{tile}<g transform="scale(100000)">{fill}</g>')

    with pytest.raises(BadSvg, match="took more than 200 MB to draw|crashed the renderer"):
        picture(huge, memory=200 * 2**20)
