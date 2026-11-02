"""Landmarks drawn flat in code, as the plan FLUX redraws: the Apex towers' outline, setbacks and
spires, and which of their windows are lit, which is all their glow map may light."""

from dataclasses import asdict, dataclass
from functools import cache

import numpy as np
from PIL import Image, ImageDraw

from simile.papercraft.fronts import BACKDROP, Plan, Rgb

PLAN = 1
"""Bump when a change to the drawing should repaint every landmark."""
MARGIN = 6.0
GLASS: Rgb = (170, 192, 208)
MULLION: Rgb = (112, 130, 146)
WINDOW: Rgb = (96, 116, 138)
LIT: Rgb = (244, 228, 170)
SPIRE: Rgb = (88, 96, 108)
BEACON: Rgb = (236, 92, 76)


@dataclass(frozen=True)
class Tower:
    """One tower, in metres: its middle from the group's middle, its width and its roof's
    height, with a narrower top storey set back and a spire above it."""

    x: float
    width: float
    height: float
    spire: float = 0.0
    setback: float = 0.0
    """How tall the narrower top is."""
    floor: float = 8.0
    bay: float = 4.0
    lit: int = 5
    """Every `lit`th window glows at night."""


APEX = (
    Tower(-32.0, 22.0, 150.0, spire=18.0, setback=16.0),
    Tower(0.0, 30.0, 230.0, spire=60.0, setback=28.0),
    Tower(30.0, 24.0, 185.0, spire=32.0, setback=20.0),
)
PLANS: dict[str, tuple[Tower, ...]] = {"apex": APEX}


def params(name: str) -> list[dict]:
    """What a landmark's plan is drawn from, for its hash."""
    return [asdict(t) for t in PLANS[name]]


def plan_ppm(towers: tuple[Tower, ...], pixels: float = 1.2e6, longest: int = 1536) -> float:
    w, h = _extent(towers)
    return min((pixels / (w * h)) ** 0.5, longest / max(w, h))


def _extent(towers: tuple[Tower, ...]) -> tuple[float, float]:
    half = max(abs(t.x) + t.width / 2 for t in towers)
    return 2 * (half + MARGIN), max(t.height + t.spire for t in towers) + 2 * MARGIN


@cache
def plan(name: str) -> Plan:
    return draw(PLANS[name])


def draw(towers: tuple[Tower, ...], ppm: float | None = None) -> Plan:
    """The towers side by side on one ground line, the middle of the group in the middle of the
    picture. `left` is that middle."""
    ppm = ppm or plan_ppm(towers)
    w, h = _extent(towers)
    size = (round(w * ppm / 16) * 16, round(h * ppm / 16) * 16)
    image = Image.new("RGB", size, BACKDROP)
    glow = Image.new("L", size, 0)
    shape = Image.new("L", size, 0)
    pen, light, outline = ImageDraw.Draw(image), ImageDraw.Draw(glow), ImageDraw.Draw(shape)
    middle, ground = size[0] / 2, size[1] - MARGIN * ppm

    def px(x0: float, y0: float, x1: float, y1: float) -> tuple[float, float, float, float]:
        return (middle + x0 * ppm, ground - y1 * ppm, middle + x1 * ppm, ground - y0 * ppm)

    for n, t in enumerate(sorted(towers, key=lambda t: t.height)):
        top = t.height - t.setback
        inset = t.width * 0.18 if t.setback else 0.0
        blocks = [(t.x - t.width / 2, 0.0, t.x + t.width / 2, top)]
        if t.setback:
            blocks.append((t.x - t.width / 2 + inset, top, t.x + t.width / 2 - inset, t.height))
        for x0, y0, x1, y1 in blocks:
            pen.rectangle(px(x0, y0, x1, y1), fill=GLASS, outline=MULLION, width=2)
            outline.rectangle(px(x0, y0, x1, y1), fill=255)
            bays = max(1, round((x1 - x0) / t.bay))
            floors = int((y1 - y0 - 1.0) // t.floor)
            for i in range(bays):
                for j in range(floors):
                    a = x0 + (x1 - x0) * i / bays + 0.6
                    b = x0 + (x1 - x0) * (i + 1) / bays - 0.6
                    c, d = y0 + j * t.floor + 2.0, y0 + (j + 1) * t.floor - 1.0
                    lit = (i * 7 + j * 3 + n) % t.lit == 0
                    pen.rectangle(px(a, c, b, d), fill=LIT if lit else WINDOW)
                    if lit:
                        light.rectangle(px(a, c, b, d), fill=255)
        if t.spire:
            base = t.width * 0.12
            points = [(t.x - base, t.height), (t.x, t.height + t.spire), (t.x + base, t.height)]
            corners = [px(x, y, x, y)[:2] for x, y in points]
            pen.polygon(corners, fill=SPIRE)
            outline.polygon(corners, fill=255)
            tip = px(t.x - 0.9, t.height + t.spire - 1.8, t.x + 0.9, t.height + t.spire)
            pen.ellipse(tip, fill=BEACON)
            light.ellipse(tip, fill=255)
    a = np.asarray(image, dtype=np.int16)
    drawn = (np.abs(a - np.array(BACKDROP)).max(axis=2) > 6).astype(np.uint8) * 255
    shape = Image.fromarray(np.maximum(drawn, np.asarray(shape)))
    return Plan(image, glow, ppm, middle, ground, shape)
