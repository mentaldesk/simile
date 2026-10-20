from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from simile.papercraft import cutout


def block_on(backdrop: tuple[int, int, int], fill: tuple[int, int, int]) -> Image.Image:
    image = Image.new("RGB", (240, 200), backdrop)
    ImageDraw.Draw(image).rectangle((60, 40, 180, 170), fill=fill)
    return image


def test_the_backdrop_is_the_colour_round_the_border() -> None:
    assert list(cutout.background(block_on((150, 150, 150), (20, 90, 40)))) == [150, 150, 150]


def test_unmixing_takes_the_backdrop_out_of_a_soft_edge() -> None:
    image = Image.new("RGB", (4, 4), (255, 255, 255))
    image.putpixel((1, 1), (155, 205, 255))
    mask = Image.new("L", (4, 4), 0)
    mask.putpixel((1, 1), 128)

    r, g, b, a = cutout.unmix(image, mask).getpixel((1, 1))

    assert a == 128 and r < 70 and g < 170


def test_a_skyline_is_solid_from_its_top_edge_down() -> None:
    mask = np.zeros((10, 3), dtype=np.uint8)
    mask[2, 0] = mask[8, 0] = 255
    mask[4:6, 1] = 255

    solid = np.asarray(cutout.skyline(Image.fromarray(mask)))

    assert solid[2:9, 0].min() == 255 and solid[:2, 0].max() == 0
    assert solid[4:6, 1].min() == 255 and solid[:, 2].max() == 0


def test_the_key_cuts_away_the_backdrop_touching_the_border() -> None:
    pytest.importorskip("cv2")

    alpha = np.asarray(cutout.key(block_on((255, 255, 255), (200, 60, 50))))

    assert alpha[100, 120] == 255 and alpha[5, 5] == 0


def test_tidying_cuts_away_painted_shadow_and_backdrop_seen_through_an_object() -> None:
    pytest.importorskip("cv2")
    image = block_on((240, 240, 240), (60, 120, 200))
    pen = ImageDraw.Draw(image)
    pen.rectangle((60, 172, 180, 190), fill=(150, 146, 140))
    pen.rectangle((100, 80, 140, 120), fill=(240, 240, 240))
    mask = Image.new("L", image.size, 0)
    ImageDraw.Draw(mask).rectangle((60, 40, 180, 190), fill=255)

    alpha = np.asarray(cutout.tidy(image, mask, ("shadows", "gaps")))

    assert alpha[150, 70] == 255 and alpha[180, 120] == 0 and alpha[100, 120] == 0


def test_small_holes_are_filled_and_big_ones_kept() -> None:
    pytest.importorskip("cv2")
    mask = np.full((100, 100), 255, dtype=np.uint8)
    mask[10:14, 10:14] = 0
    mask[40:80, 40:80] = 0

    filled = np.asarray(cutout.fill_holes(Image.fromarray(mask), largest=100))

    assert filled[12, 12] == 255 and filled[60, 60] == 0


def test_isnet_weights_that_dont_match_the_checksum_are_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    cutout.model_path().parent.mkdir(parents=True)
    cutout.model_path().write_bytes(b"not the model")

    with pytest.raises(RuntimeError, match="checksum"):
        cutout.ensure_model()


@pytest.mark.skipif(not cutout.model_path().exists(), reason="IS-Net's weights aren't cached")
def test_the_hybrid_cut_keeps_a_pale_object_on_white() -> None:
    pytest.importorskip("cv2")
    pytest.importorskip("onnxruntime")
    image = block_on((255, 255, 255), (238, 226, 200))
    ImageDraw.Draw(image).ellipse((90, 70, 150, 130), fill=(60, 120, 90))

    alpha = np.asarray(cutout.hybrid(image))

    assert alpha[100, 120] > 200 and alpha[50, 70] > 200 and alpha[5, 5] < 30
