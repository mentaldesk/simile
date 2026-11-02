"""The Apex towers as one landmark: three silhouettes drawn in code as plans FLUX redraws, each
with the lights it shows at night."""

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from simile.papercraft.sketches import SKETCHES, Sheet

GLASS = (46, 96, 112)
PALE = (120, 176, 184)
STEEL = (228, 232, 230)
SPIRE = (128, 140, 148)
BAND = (156, 214, 210)
HEIGHT = 13.0
"""How tall the landmark is drawn, in the metres the client draws a parallax layer in."""
WINDOWS = (190, 240, 236)
CROWN = (120, 255, 236)
BEACON = (255, 96, 80)
PPM = 110


class Tower:
    """One tower's outline, its window bands and its crown, in metres, y up."""

    def __init__(self, sheet: Sheet) -> None:
        self.sheet = sheet
        self.lights: list[tuple[str, list[tuple[float, float]], tuple[int, int, int]]] = []

    def body(self, points, fill=GLASS):
        self.sheet.polygon(points, fill, STEEL)

    def light(self, kind: str, points, colour) -> None:
        self.lights.append((kind, points, colour))


def _taper(x: float, w0: float, w1: float, y0: float, y1: float) -> list[tuple[float, float]]:
    return [(x - w0 / 2, y0), (x + w0 / 2, y0), (x + w1 / 2, y1), (x - w1 / 2, y1)]


def _bands(t: Tower, x: float, w0: float, w1: float, y0: float, y1: float, step: float) -> None:
    """Pale window bands across a tapering shaft, every `step` metres, and a mullion down it."""
    y = y0 + step
    while y < y1 - step / 2:
        f = (y - y0) / (y1 - y0)
        w = w0 + (w1 - w0) * f
        band = _taper(x, w - 0.04, w - 0.04, y, y + step * 0.32)
        t.sheet.polygon(band, BAND)
        t.light("window", band, WINDOWS)
        y += step
    t.sheet.polygon(_taper(x, 0.05, 0.05, y0, y1), STEEL)


def twin() -> Image.Image:
    """Two slim tapering towers with needle spires, joined high up by a sky-bridge."""
    width = 5.6
    s = Sheet(width, HEIGHT, PPM)
    t = Tower(s)
    for x, top, w in ((1.7, 11.2, 1.7), (3.9, 10.0, 1.5)):
        t.body(_taper(x, w, w * 0.62, 0, top))
        _bands(t, x, w, w * 0.62, 0, top - 0.3, 0.42)
        s.polygon([(x - w * 0.31, top), (x + w * 0.31, top), (x, top + 0.9)], PALE, STEEL)
        t.light("crown", [(x - w * 0.31, top), (x + w * 0.31, top), (x, top + 0.9)], CROWN)
        spire = top + 0.9 + (1.0 if top > 10.5 else 0.6)
        s.rect(x - 0.04, top + 0.8, x + 0.04, spire, SPIRE)
        t.light(
            "beacon",
            [
                (x - 0.09, spire - 0.12),
                (x + 0.09, spire - 0.12),
                (x + 0.09, spire),
                (x - 0.09, spire),
            ],
            BEACON,
        )
    bridge = [(2.4, 8.0), (3.25, 8.0), (3.25, 8.45), (2.4, 8.45)]
    s.polygon(bridge, PALE, STEEL)
    t.light("crown", bridge, CROWN)
    return _finish(t, "twin")


def trio() -> Image.Image:
    """Three stepped towers, the middle one tallest, with a lit ring round its crown."""
    width = 6.6
    s = Sheet(width, HEIGHT, PPM)
    t = Tower(s)
    for x, top, w in ((1.2, 7.6, 1.5), (5.4, 8.6, 1.5), (3.3, 11.4, 2.0)):
        t.body(_taper(x, w, w * 0.8, 0, top - 1.2))
        t.body(_taper(x, w * 0.8, w * 0.55, top - 1.2, top), PALE)
        _bands(t, x, w, w * 0.8, 0, top - 1.2, 0.5)
        s.rect(x - 0.04, top, x + 0.04, top + 0.6, SPIRE)
        t.light("beacon", _taper(x, 0.16, 0.16, top + 0.5, top + 0.62), BEACON)
    ring = _taper(3.3, 2.3, 2.3, 9.7, 9.95)
    s.polygon(ring, STEEL, GLASS)
    t.light("crown", ring, CROWN)
    return _finish(t, "trio")


def helix() -> Image.Image:
    """One very tall tower that twists as it rises, like a strand of DNA, with a spire."""
    width = 3.6
    s = Sheet(width, HEIGHT, PPM)
    t = Tower(s)
    x, top = width / 2, 11.6
    t.body(_taper(x, 2.2, 1.0, 0, top))
    for i, y in enumerate(np.arange(0.5, top - 0.4, 0.7)):
        f = y / top
        half = (2.2 + (1.0 - 2.2) * f) / 2
        a, b = (-half, half) if i % 2 else (half, -half)
        strand = [(x + a, y), (x + a, y + 0.16), (x + b, y + 0.56), (x + b, y + 0.4)]
        s.polygon(strand, BAND)
        t.light("window", strand, WINDOWS)
    s.polygon(_taper(x, 0.05, 0.05, 0, top), STEEL)
    s.polygon([(x - 0.5, top), (x + 0.5, top), (x, top + 1.3)], PALE, STEEL)
    t.light("crown", [(x - 0.5, top), (x + 0.5, top), (x, top + 1.3)], CROWN)
    t.light("beacon", _taper(x, 0.16, 0.16, top + 1.15, top + 1.3), BEACON)
    return _finish(t, "helix")


_LIGHTS: dict[str, Image.Image] = {}


def _finish(t: Tower, name: str) -> Image.Image:
    glow = Image.new("RGB", t.sheet.image.size, (0, 0, 0))
    pen = ImageDraw.Draw(glow)
    for _, points, colour in t.lights:
        pen.polygon([t.sheet.at(x, y) for x, y in points], fill=colour)
    _LIGHTS[name] = glow
    return t.sheet.image


SILHOUETTES = {"twin": twin, "trio": trio, "helix": helix}
SUBJECTS = {
    "twin": "two slim, tapering glass skyscrapers with needle spires, joined high up by a "
    "glass sky-bridge",
    "trio": "three stepped glass skyscrapers, the middle one the tallest, with a white steel "
    "ring around its crown",
    "helix": "one very tall glass skyscraper that twists as it rises, like a strand of DNA, "
    "with a needle spire",
}
for _name, _draw in SILHOUETTES.items():
    SKETCHES[f"apex_{_name}"] = _draw


def lights(name: str) -> Image.Image:
    """The plan's night lights, RGB on black, the size of its plan."""
    if name not in _LIGHTS:
        SILHOUETTES[name]()
    return _LIGHTS[name]


def glow(name: str, painted: Image.Image) -> Image.Image:
    """The tower's lights at night, on the painting's own light and shade."""
    light = np.asarray(lights(name).filter(ImageFilter.GaussianBlur(1.5)), dtype=np.float32)
    lum = np.asarray(painted.convert("L").resize(lights(name).size), dtype=np.float32)[..., None]
    out = light * (0.55 + 0.45 * lum / 255)
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))
