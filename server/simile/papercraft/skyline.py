"""Landmarks drawn flat in code, as the plan FLUX redraws: the Apex towers' outline, setbacks,
spires and sky-bridge, and which of their windows are lit, which is all their glow map may light."""

import zlib
from dataclasses import asdict, dataclass
from functools import cache

import numpy as np
from PIL import Image, ImageDraw

from simile.papercraft.fronts import BACKDROP, Plan, Rgb

PLAN = 2
"""Bump when a change to the drawing should repaint every landmark."""
MARGIN = 6.0
GLASS: Rgb = (64, 112, 132)
MULLION: Rgb = (226, 232, 234)
WINDOW: Rgb = (120, 170, 186)
SPIRE: Rgb = (214, 220, 224)
BEACON: Rgb = (236, 92, 76)


@dataclass(frozen=True)
class Tower:
    """One tower, in metres: its middle from the group's middle, its width and its roof's
    height, with narrower tiers set back at its top and a spire above them."""

    x: float
    width: float
    height: float
    spire: float = 0.0
    setback: float = 0.0
    """How tall each narrower tier at the top is."""
    tiers: int = 1
    floor: float = 8.0
    bay: float = 4.0
    lit: int = 5
    """About one window in `lit` glows at night, scattered."""


@dataclass(frozen=True)
class Bridge:
    """A sky-bridge, in metres: its ends from the group's middle, and its floor's height."""

    x0: float
    x1: float
    y: float
    depth: float = 9.0


@dataclass(frozen=True)
class Skyline:
    towers: tuple[Tower, ...]
    bridges: tuple[Bridge, ...] = ()


APEX = Skyline(
    (
        Tower(-23.0, 30.0, 250.0, spire=46.0, setback=22.0, tiers=2),
        Tower(23.0, 30.0, 232.0, spire=38.0, setback=22.0, tiers=2),
    ),
    (Bridge(-8.0, 8.0, 150.0),),
)
"""Twin towers joined by a sky-bridge, the left a little taller, as #554's study drew them."""
PLANS: dict[str, Skyline] = {"apex": APEX}


def params(name: str) -> dict:
    """What a landmark's plan is drawn from, for its hash."""
    return asdict(PLANS[name])


def plan_ppm(skyline: Skyline, pixels: float = 1.2e6, longest: int = 1536) -> float:
    w, h = _extent(skyline.towers)
    return min((pixels / (w * h)) ** 0.5, longest / max(w, h))


def _extent(towers: tuple[Tower, ...]) -> tuple[float, float]:
    half = max(abs(t.x) + t.width / 2 for t in towers)
    return 2 * (half + MARGIN), max(t.height + t.spire for t in towers) + 2 * MARGIN


@cache
def plan(name: str) -> Plan:
    return draw(PLANS[name])


def draw(skyline: Skyline, ppm: float | None = None) -> Plan:
    """The towers side by side on one ground line, the middle of the group in the middle of the
    picture, and their bridges between them. `left` is that middle."""
    towers = skyline.towers
    ppm = ppm or plan_ppm(skyline)
    w, h = _extent(towers)
    size = (round(w * ppm / 16) * 16, round(h * ppm / 16) * 16)
    image = Image.new("RGB", size, BACKDROP)
    glow = Image.new("L", size, 0)
    shape = Image.new("L", size, 0)
    pen, light, outline = ImageDraw.Draw(image), ImageDraw.Draw(glow), ImageDraw.Draw(shape)
    middle, ground = size[0] / 2, size[1] - MARGIN * ppm

    def px(x0: float, y0: float, x1: float, y1: float) -> tuple[float, float, float, float]:
        return (middle + x0 * ppm, ground - y1 * ppm, middle + x1 * ppm, ground - y0 * ppm)

    def glazed(
        x0: float, y0: float, x1: float, y1: float, bay: float, floor: float, lit: int, n: int
    ):
        pen.rectangle(px(x0, y0, x1, y1), fill=GLASS, outline=MULLION, width=2)
        outline.rectangle(px(x0, y0, x1, y1), fill=255)
        bays = max(1, round((x1 - x0) / bay))
        floors = max(1, int((y1 - y0 - 1.0) // floor))
        step = (y1 - y0) / floors
        for i in range(bays):
            for j in range(floors):
                a = x0 + (x1 - x0) * i / bays + 0.6
                b = x0 + (x1 - x0) * (i + 1) / bays - 0.6
                c, d = y0 + j * step + step * 0.25, y0 + (j + 1) * step - step * 0.12
                pen.rectangle(px(a, c, b, d), fill=WINDOW)
                if zlib.crc32(f"{n},{i},{j},{y0}".encode()) % lit == 0:
                    light.rectangle(px(a, c, b, d), fill=255)

    for n, t in enumerate(sorted(towers, key=lambda t: t.height)):
        tiers = t.tiers if t.setback else 0
        top = t.height - tiers * t.setback
        glazed(t.x - t.width / 2, 0.0, t.x + t.width / 2, top, t.bay, t.floor, t.lit, n)
        half = t.width / 2
        for k in range(tiers):
            half *= 0.78
            y0 = top + k * t.setback
            glazed(t.x - half, y0, t.x + half, y0 + t.setback, t.bay, t.floor, t.lit, n + k)
        if t.spire:
            base = max(0.8, half * 0.12)
            points = [(t.x - base, t.height), (t.x, t.height + t.spire), (t.x + base, t.height)]
            corners = [px(x, y, x, y)[:2] for x, y in points]
            pen.polygon(corners, fill=SPIRE)
            outline.polygon(corners, fill=255)
            tip = px(t.x - 1.2, t.height + t.spire - 2.4, t.x + 1.2, t.height + t.spire)
            pen.ellipse(tip, fill=BEACON)
            light.ellipse(tip, fill=255)
    for b in skyline.bridges:
        glazed(b.x0, b.y, b.x1, b.y + b.depth, 4.0, b.depth, 2, 0)
    a = np.asarray(image, dtype=np.int16)
    drawn = (np.abs(a - np.array(BACKDROP)).max(axis=2) > 6).astype(np.uint8) * 255
    shape = Image.fromarray(np.maximum(drawn, np.asarray(shape)))
    return Plan(image, glow, ppm, middle, ground, shape)
