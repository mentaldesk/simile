import numpy as np
import pytest
from PIL import Image, ImageFilter

from simile.dolls.build import people
from simile.dolls.colour import delta_e
from simile.dolls.look import Look
from simile.dolls.sheet import (
    BACKGROUND,
    LAYOUTS,
    SIZE,
    cut,
    misplaced,
    paper,
    regions,
    restore,
    sheet,
    strengthen,
)

EVERYONE = people()


def drifted(image: Image.Image, shift: tuple[int, int, int], seed: int = 0) -> Image.Image:
    """`image` as a painter might return it: colours off, and some texture."""
    a = np.asarray(image.convert("RGB"), dtype=np.float64)
    noise = np.random.default_rng(seed).normal(0, 8, a.shape[:2])[..., None]
    return Image.fromarray(np.clip(a + np.array(shift) + noise, 0, 255).astype(np.uint8))


def region_means(painted: Image.Image, flat: Image.Image) -> list[tuple[np.ndarray, np.ndarray]]:
    nearest, main, opaque = regions(flat)
    p = np.asarray(painted.convert("RGB"), dtype=np.float64)
    f = np.asarray(flat.convert("RGB"), dtype=np.float64)
    out = []
    for i, colour in enumerate(main):
        core = opaque & (nearest == i) & (np.abs(f - colour).max(axis=2) < 1)
        if core.sum() > 200:
            out.append((p[core].mean(axis=0), colour))
    return out


@pytest.mark.parametrize("who", EVERYONE)
@pytest.mark.parametrize("layout", LAYOUTS)
def test_every_sheet_fits_with_its_pieces_apart(who: str, layout: str) -> None:
    laid = sheet(layout, Look.of(EVERYONE[who], who))

    boxes = [
        (x, y, x + laid.pieces[n].image.width, y + laid.pieces[n].image.height)
        for n, (x, y) in laid.spots.items()
    ]
    for i, (x0, y0, x1, y1) in enumerate(boxes):
        assert min(x0, y0) >= 0 and x1 <= SIZE[0] and y1 <= SIZE[1]
        for ox0, oy0, ox1, oy1 in boxes[i + 1 :]:
            assert x1 + 8 <= ox0 or ox1 + 8 <= x0 or y1 + 8 <= oy0 or oy1 + 8 <= y0
    assert laid.scale >= 5.0


def test_restore_pulls_a_drifted_painting_back_to_the_flat_colours() -> None:
    laid = sheet("side", Look.of(EVERYONE["desmond"], "desmond"))
    flat = laid.pieces["head"].image

    painted = drifted(flat, (60, 40, 30))
    restored = restore(painted, flat)

    for before, colour in region_means(painted, flat):
        assert delta_e(before, colour) > 8
    for after, colour in region_means(restored, flat):
        assert delta_e(after, colour) < 3


def texture(painted: Image.Image, flat: Image.Image) -> float:
    """The mean spread of each region's colours, away from its edges."""
    nearest, main, opaque = regions(flat)
    p = np.asarray(painted.convert("RGB"), dtype=np.float64)
    inner = np.asarray(flat.getchannel("A").filter(ImageFilter.MinFilter(9))) == 255
    spreads = [
        p[region].std(axis=0).mean()
        for i in range(len(main))
        if (region := inner & opaque & (nearest == i)).sum() > 400
    ]
    return float(np.mean(spreads))


def test_strengthen_adds_texture_without_moving_the_colours() -> None:
    laid = sheet("side", Look.of(EVERYONE["odalys"], "odalys"))
    flat = laid.pieces["torso"].image
    painted = drifted(flat, (0, 0, 0)).filter(ImageFilter.BoxBlur(4))

    strong = strengthen(painted, flat, laid.scale)

    assert texture(strong, flat) > 1.3 * texture(painted, flat)
    pairs = zip(region_means(painted, flat), region_means(strong, flat), strict=True)
    for (before, _), (after, _) in pairs:
        assert delta_e(before, after) < 3


def test_misplaced_finds_a_piece_the_painter_dropped() -> None:
    laid = sheet("front_back", Look.of(EVERYONE["kofi"], "kofi"))
    painting = laid.image()
    x, y = laid.spots["torso_back"]
    w, h = laid.pieces["torso_back"].image.size
    painting.paste(BACKGROUND, (x, y, x + w, y + h))

    found = misplaced(laid, painting)

    assert found["torso_back"] > 0.95
    assert all(share < 0.01 for name, share in found.items() if name != "torso_back")


def test_cut_fills_what_the_painter_left_bare_inside_an_outline() -> None:
    laid = sheet("front_back", Look.of(EVERYONE["ingrid"], "ingrid"))
    painting = drifted(laid.image(), (-30, -20, -10))
    background = tuple(int(v) for v in paper(laid, painting))
    flat = laid.pieces["head_back"].image
    alpha = np.asarray(flat.getchannel("A"))
    core = np.asarray(flat.getchannel("A").filter(ImageFilter.MinFilter(15))) > 0
    rim = Image.fromarray(((alpha > 0) & ~core).astype(np.uint8) * 255)
    painting.paste(background, laid.spots["head_back"], rim)

    pieces = cut(laid, painting)

    head = np.asarray(pieces["head_back"], dtype=np.float64)
    assert misplaced(laid, painting)["head_back"] > 0.05
    assert (delta_e(head[alpha == 255], background) > 12).all()
    for mean, colour in region_means(pieces["head_back"], flat):
        assert delta_e(mean, colour) < 3
