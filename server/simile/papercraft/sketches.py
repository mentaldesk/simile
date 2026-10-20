"""Flat side views drawn in code for the pieces whose shape matters more than FLUX keeps to
from words: stairs and ladders that fit their cells, the lift, and the white fittings that
otherwise come out looking photographed rather than cut from card."""

from collections.abc import Callable

import numpy as np
from PIL import Image, ImageDraw

from simile.papercraft.fronts import GREY, Rgb

WOOD: Rgb = (184, 136, 92)
DARK_WOOD: Rgb = (130, 90, 58)
IRON: Rgb = (52, 56, 60)
BRASS: Rgb = (200, 164, 84)
WHITE: Rgb = (244, 242, 236)
MINT: Rgb = (186, 226, 204)
STONE: Rgb = (196, 188, 172)
MARGIN = 0.25


class Sheet:
    """A drawing `width` by `height` metres plus a margin, at `ppm` px a metre, y up."""

    def __init__(
        self, width: float, height: float, ppm: float, backdrop: Rgb = (255, 255, 255)
    ) -> None:
        self.ppm = ppm
        size = (
            round((width + 2 * MARGIN) * ppm / 16) * 16,
            round((height + 2 * MARGIN) * ppm / 16) * 16,
        )
        self.image = Image.new("RGB", size, backdrop)
        self.pen = ImageDraw.Draw(self.image)
        self.x0 = (size[0] - width * ppm) / 2
        self.y0 = size[1] - (size[1] - height * ppm) / 2

    def at(self, x: float, y: float) -> tuple[float, float]:
        return (self.x0 + x * self.ppm, self.y0 - y * self.ppm)

    def rect(self, x0: float, y0: float, x1: float, y1: float, fill: Rgb, line: Rgb | None = None):
        (a, b), (c, d) = self.at(x0, y1), self.at(x1, y0)
        self.pen.rectangle((a, b, c, d), fill=fill, outline=line, width=2 if line else 0)

    def polygon(self, points: list[tuple[float, float]], fill: Rgb, line: Rgb | None = None):
        self.pen.polygon([self.at(x, y) for x, y in points], fill=fill, outline=line)

    def ellipse(self, x0: float, y0: float, x1: float, y1: float, fill: Rgb):
        (a, b), (c, d) = self.at(x0, y1), self.at(x1, y0)
        self.pen.ellipse((a, b, c, d), fill=fill)


def stairs(rise: float = 4.4, run: float = 4.4, steps: int = 16) -> Image.Image:
    """A flight rising to the right, its treads on the line from the bottom left corner to the
    top right."""
    s = Sheet(run, rise + 1.0, 150)
    h, d = rise / steps, run / steps
    profile = [(0.0, 0.0)]
    for i in range(steps):
        profile += [(i * d, (i + 1) * h), ((i + 1) * d, (i + 1) * h)]
    s.polygon([*profile, (run, rise - 0.45), (0.45, 0.0)], WOOD, DARK_WOOD)
    for i in range(steps):
        s.rect(i * d, (i + 1) * h - 0.05, (i + 1) * d + 0.03, (i + 1) * h, DARK_WOOD)
    for i in range(0, steps + 1, 3):
        x = min(i * d + d / 2, run - 0.05)
        s.rect(x - 0.03, (i + 1) * h, x + 0.03, (i + 1) * h + 0.9, DARK_WOOD)
    s.polygon([(0, h + 0.9), (run, rise + 0.9), (run, rise + 0.98), (0, h + 0.98)], DARK_WOOD)
    return s.image


def ladder(height: float = 3.6) -> Image.Image:
    s = Sheet(0.6, height, 200)
    s.rect(0.0, 0.0, 0.08, height, WOOD, DARK_WOOD)
    s.rect(0.52, 0.0, 0.6, height, WOOD, DARK_WOOD)
    for y in np.arange(0.3, height - 0.1, 0.3):
        s.rect(0.05, y - 0.035, 0.55, y + 0.035, WOOD, DARK_WOOD)
    return s.image


def lift(width: float = 2.0, height: float = 2.9) -> Image.Image:
    """The car: an iron cage with a wooden floor, a brass trim and a lamp on top."""
    s = Sheet(width, height, 220)
    s.rect(0, 0, width, 0.18, DARK_WOOD)
    s.rect(0, height - 0.5, width, height - 0.32, BRASS)
    s.rect(0, 0.18, 0.06, height - 0.32, IRON)
    s.rect(width - 0.06, 0.18, width, height - 0.32, IRON)
    for x in np.arange(0.18, width - 0.1, 0.16):
        s.rect(x - 0.015, 0.18, x + 0.015, height - 0.5, IRON)
    s.rect(0, 1.0, width, 1.06, IRON)
    s.polygon(
        [(0.1, height - 0.32), (width / 2, height - 0.08), (width - 0.1, height - 0.32)], IRON
    )
    s.ellipse(width / 2 - 0.1, height - 0.1, width / 2 + 0.1, height + 0.1, (250, 226, 160))
    return s.image


def lift_shaft(width: float = 2.2, height: float = 4.4) -> Image.Image:
    """One storey of the shaft's iron frame, to stack."""
    s = Sheet(width, height, 180)
    s.rect(0, 0, 0.1, height, IRON)
    s.rect(width - 0.1, 0, width, height, IRON)
    for y in (0.0, height - 0.1):
        s.rect(0, y, width, y + 0.1, IRON)
    for y0 in np.arange(0, height - 0.1, 1.1):
        s.polygon(
            [(0.1, y0), (width - 0.1, y0 + 1.1), (width - 0.1, y0 + 1.04), (0.1, y0 - 0.06)], IRON
        )
    s.rect(width / 2 - 0.02, 0, width / 2 + 0.02, height, (90, 90, 90))
    return s.image


def steps(rise: float = 2.2, run: float = 2.2, count: int = 8) -> Image.Image:
    """Stone steps rising to the right, from the river path up to the street."""
    s = Sheet(run + 0.3, rise, 200)
    h, d = rise / count, run / count
    profile = [(0.0, 0.0)]
    for i in range(count):
        profile += [(i * d, (i + 1) * h), ((i + 1) * d, (i + 1) * h)]
    s.polygon([*profile, (run + 0.3, rise), (run + 0.3, 0.0)], STONE, (150, 142, 128))
    return s.image


def bathtub() -> Image.Image:
    s = Sheet(1.7, 0.75, 400, GREY)
    s.polygon([(0.0, 0.62), (1.7, 0.62), (1.6, 0.2), (0.1, 0.2)], WHITE, (200, 196, 188))
    s.rect(-0.04, 0.6, 1.74, 0.68, WHITE, (200, 196, 188))
    for x in (0.25, 1.4):
        s.polygon([(x - 0.06, 0.22), (x + 0.06, 0.22), (x + 0.1, 0.0), (x - 0.1, 0.0)], BRASS)
    s.rect(1.45, 0.68, 1.5, 0.75, BRASS)
    return s.image


def washbasin() -> Image.Image:
    s = Sheet(0.7, 1.8, 300, GREY)
    s.rect(0.28, 0.0, 0.42, 0.72, WHITE, (200, 196, 188))
    s.polygon([(0.0, 0.86), (0.7, 0.86), (0.6, 0.7), (0.1, 0.7)], WHITE, (200, 196, 188))
    s.rect(0.32, 0.86, 0.38, 0.98, BRASS)
    s.ellipse(0.12, 1.25, 0.58, 1.75, DARK_WOOD)
    s.ellipse(0.16, 1.29, 0.54, 1.71, (210, 222, 226))
    return s.image


def fridge() -> Image.Image:
    s = Sheet(0.75, 1.7, 300)
    s.rect(0.0, 0.08, 0.75, 1.7, MINT, (150, 190, 170))
    s.rect(0.02, 1.08, 0.73, 1.12, (150, 190, 170))
    s.rect(0.06, 1.25, 0.1, 1.5, (210, 210, 200))
    s.rect(0.06, 0.7, 0.1, 0.95, (210, 210, 200))
    for x in (0.08, 0.6):
        s.rect(x, 0.0, x + 0.07, 0.08, IRON)
    return s.image


SKETCHES: dict[str, Callable[[], Image.Image]] = {
    "stairs": stairs,
    "ladder": ladder,
    "lift": lift,
    "lift_shaft": lift_shaft,
    "steps": steps,
    "bathtub": bathtub,
    "washbasin": washbasin,
    "fridge": fridge,
}
