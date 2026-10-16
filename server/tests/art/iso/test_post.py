import io

import numpy as np
import pytest
from PIL import Image

from simile.art.iso import formats
from simile.art.iso.post import chunks, glow, light_map


def test_glow_spreads_from_neon_but_not_from_dull_colours() -> None:
    image = Image.new("RGB", (41, 41), (60, 60, 70))
    image.paste((255, 40, 200), (18, 18, 23, 23))
    out = np.asarray(glow(image, 4, 0.85)).astype(int)
    assert (out[20, 26] > np.asarray(image)[20, 26]).any()
    assert (out[0, 0] == (60, 60, 70)).all()


def test_glow_keeps_the_silhouette() -> None:
    image = Image.new("RGBA", (30, 30), (0, 0, 0, 0))
    image.paste((255, 40, 200, 255), (10, 10, 20, 20))
    out = glow(image, 4, 1.0)
    assert out.getchannel("A").tobytes() == image.getchannel("A").tobytes()
    rgb = np.asarray(out)
    assert (rgb[rgb[..., 3] == 0][:, :3] == 0).all()


def test_no_glow_by_day_leaves_the_image_alone() -> None:
    image = Image.new("RGB", (4, 4), (255, 0, 0))
    assert glow(image, 10, 0.0) is image


def test_chunks_tile_the_ground_within_the_size_limit() -> None:
    pieces = chunks(5136, 2592, 2048)
    assert len(pieces) == 6
    assert sum(w * h for *_, w, h in pieces) == 5136 * 2592
    assert all(w <= 2048 and h <= 2048 for *_, w, h in pieces)
    assert {(c, r) for c, r, *_ in pieces} == {(c, r) for c in range(3) for r in range(2)}


def lit_ground(shape=(40, 64)) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    sun = np.full((*shape, 3), 1.0, np.float32)
    sun[:20, :16] = 0.0
    sky = np.full((*shape, 3), 0.3, np.float32)
    lights = np.zeros((*shape, 3), np.float32)
    lights[30:, 48:] = 4.0
    return sun + sky, sun, lights


def test_light_map_is_one_in_the_open_and_shows_where_the_sun_is() -> None:
    image, scale = light_map(*lit_ground(), elevation=40, px_per_tile=8)
    rgba = np.asarray(image).astype(float)
    assert image.size == (64, 40)
    assert rgba[10, 40, :3] / 255 * scale == pytest.approx([1, 1, 1], abs=0.01)
    assert rgba[10, 40, 3] == 255
    assert rgba[5, 5, 3] == 0
    assert (rgba[5, 5, :3] < rgba[10, 40, :3]).all()


def test_lamps_push_the_light_map_past_one() -> None:
    image, scale = light_map(*lit_ground(), elevation=40, px_per_tile=8)
    rgba = np.asarray(image).astype(float)
    assert scale > 1
    assert (rgba[36, 60, :3] / 255 * scale > 1.2).all()
    assert rgba[..., :3].max() == 255


@pytest.mark.parametrize("fmt", [formats.PNG, formats.LOSSLESS_WEBP])
def test_lossless_formats_keep_every_visible_pixel(fmt: formats.Format) -> None:
    rng = np.random.default_rng(0)
    pixels = rng.integers(0, 256, (20, 30, 4), dtype=np.uint8)
    pixels[..., 3] = 255
    image = Image.fromarray(pixels, "RGBA")
    with Image.open(io.BytesIO(fmt.encode(image))) as back:
        assert back.convert("RGBA").tobytes() == image.tobytes()


def test_the_light_map_format_keeps_colour_where_there_is_no_sun() -> None:
    image = Image.new("RGBA", (8, 8), (120, 90, 200, 0))
    with Image.open(io.BytesIO(formats.LIGHT_MAP.encode(image))) as back:
        assert back.convert("RGBA").tobytes() == image.tobytes()


def test_sizes_measures_every_format() -> None:
    image = Image.new("RGBA", (16, 16), (10, 20, 30, 255))
    totals = formats.sizes([image, image])
    assert set(totals) == {"lossy-webp", "png", "lossless-webp"}
    assert all(n > 0 for n in totals.values())
