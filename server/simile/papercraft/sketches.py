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
ROPE: Rgb = (176, 148, 104)
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


def ledge(length: float = 3.0, height: float = 0.6) -> Image.Image:
    """A deck of planks on two brackets, seen from the side."""
    s = Sheet(length, height, 300)
    deck = 0.12
    s.rect(0, height - deck, length, height, WOOD, DARK_WOOD)
    for x in np.arange(0.25, length, 0.25):
        s.rect(x - 0.01, height - deck, x + 0.01, height, DARK_WOOD)
    for x in (0.45, length - 0.45):
        s.polygon(
            [(x - 0.3, height - deck), (x + 0.3, height - deck), (x + 0.05, 0), (x - 0.05, 0)],
            WOOD,
            DARK_WOOD,
        )
    return s.image


def rope_bridge(length: float = 3.3, height: float = 1.25) -> Image.Image:
    """A plank deck under a rope handrail, netted, with a post at each end, to stretch."""
    s = Sheet(length, height, 200)
    deck, rail, mesh, thread = 0.12, 1.0, 0.42, 0.028
    for x in np.arange(0.0, length - 0.01, 0.2):
        s.rect(x + 0.01, 0.0, min(x + 0.19, length), deck, WOOD, DARK_WOOD)
    rise = rail - deck
    for x in np.arange(-rise, length, mesh):
        for a, b in ((x, x + rise), (x + rise, x)):
            s.polygon(
                [(a - thread, deck), (a + thread, deck), (b + thread, rail), (b - thread, rail)],
                ROPE,
            )
    s.rect(0.0, rail - 0.045, length, rail + 0.045, ROPE)
    for x in (0.0, length - 0.1):
        s.rect(x, 0.0, x + 0.1, height, DARK_WOOD)
    s.image.paste((255, 255, 255), (0, 0, round(s.x0), s.image.height))
    s.image.paste((255, 255, 255), (round(s.x0 + length * s.ppm), 0, s.image.width, s.image.height))
    return s.image


def steps(rise: float = 2.2, run: float = 2.2, count: int = 8) -> Image.Image:
    """Stone steps rising to the right, from the river path up to the street."""
    s = Sheet(run + 0.3, rise, 200, GREY)
    h, d = rise / count, run / count
    profile = [(0.0, 0.0)]
    for i in range(count):
        profile += [(i * d, (i + 1) * h), ((i + 1) * d, (i + 1) * h)]
    s.polygon([*profile, (run + 0.3, rise), (run + 0.3, 0.0)], SANDSTONE, TREAD)
    s.rect(run + 0.29, 0.0, run + 0.3, rise, TREAD)
    for i in range(count):
        s.rect(i * d, (i + 1) * h - 0.04, run + 0.3, (i + 1) * h, TREAD)
    return s.image


STEEL: Rgb = (112, 122, 120)
DARK_STEEL: Rgb = (64, 70, 72)
CREAM: Rgb = (222, 214, 186)
TEAL: Rgb = (58, 132, 130)
WINDOW: Rgb = (58, 68, 82)
HAZARD: Rgb = (232, 188, 52)


def train_carriage(length: float = 11.0, height: float = 3.36) -> Image.Image:
    """A metro carriage's side on its bogies, its flat roof along the top edge to stand on."""
    s = Sheet(length, height, 120)
    for x in (1.6, length - 1.6):
        s.rect(x - 1.0, 0.3, x + 1.0, 0.5, DARK_STEEL)
        for wheel in (x - 0.6, x + 0.6):
            s.ellipse(wheel - 0.38, 0.0, wheel + 0.38, 0.76, IRON)
    s.rect(0.05, 0.45, length - 0.05, height - 0.2, CREAM, DARK_STEEL)
    s.rect(0.05, 1.05, length - 0.05, 1.3, TEAL)
    s.rect(0.0, height - 0.2, length, height, STEEL, DARK_STEEL)
    for x in np.arange(0.9, length - 0.5, 1.2):
        s.rect(x, height - 0.17, x + 0.5, height - 0.05, DARK_STEEL)
    doors = (length * 0.27, length * 0.73)
    for x in np.arange(0.5, length - 0.6, 1.05):
        if all(abs(x + 0.35 - d) > 1.0 for d in doors):
            s.rect(x, 1.6, x + 0.75, 2.6, WINDOW, DARK_STEEL)
    for d in doors:
        for side in (-1, 1):
            x0, x1 = sorted((d, d + side * 0.62))
            s.rect(x0, 0.5, x1, 2.75, CREAM, DARK_STEEL)
            s.rect(x0 + 0.12, 1.6, x1 - 0.12, 2.55, WINDOW)
    return s.image


def catwalk(length: float = 3.3, height: float = 2.16, deck: float = 1.16) -> Image.Image:
    """A railed steel deck on a girder, to stretch, its deck `deck` up from the bottom."""
    s = Sheet(length, height, 200)
    s.rect(0.0, deck - 0.6, length, deck - 0.08, STEEL, DARK_STEEL)
    for x in np.arange(0.2, length, 0.55):
        s.rect(x - 0.025, deck - 0.6, x + 0.025, deck - 0.08, DARK_STEEL)
    s.rect(0.0, deck - 0.08, length, deck, DARK_STEEL)
    for x in np.arange(0.05, length, 1.1):
        s.rect(x, deck, x + 0.06, height - 0.04, DARK_STEEL)
    for y in (deck + 0.5, height - 0.06):
        s.rect(0.0, y, length, y + 0.05, STEEL, DARK_STEEL)
    for x, out in ((0.12, 0.3), (length - 0.12, -0.3)):
        s.polygon(
            [(x, deck - 0.6), (x + out * 0.3, deck - 0.6), (x + out, 0.0), (x + out * 0.8, 0.0)],
            DARK_STEEL,
        )
    s.image.paste((255, 255, 255), (0, 0, round(s.x0), s.image.height))
    s.image.paste((255, 255, 255), (round(s.x0 + length * s.ppm), 0, s.image.width, s.image.height))
    return s.image


def metro_steps(run: float = 3.3, rise: float = 3.36, count: int = 12) -> Image.Image:
    """Tiled steps rising to the left, a little fuller than the street's, to cover them."""
    s = Sheet(run, rise, 150)
    h, d = rise / count, (run - 0.3) / count
    profile = [(run, 0.0)]
    for i in range(count):
        x = run - i * d
        profile += [(x, (i + 1) * h), (x - d, (i + 1) * h)]
    s.polygon([*profile, (0.0, rise), (0.0, 0.0)], CREAM, DARK_STEEL)
    for i in range(count):
        x = run - i * d
        s.rect(x - d, (i + 1) * h - 0.07, x, (i + 1) * h, DARK_STEEL)
    for y in np.arange(0.42, rise - 0.3, 0.42):
        s.rect(0.0, y - 0.015, run - (y // h) * d - 0.05, y + 0.015, (196, 188, 160))
    return s.image


def freight_lift(width: float = 2.2, height: float = 4.4) -> Image.Image:
    """A dead freight lift's car behind a grille gate, under its winding gear."""
    s = Sheet(width, height, 180)
    s.rect(0.15, 0.0, width - 0.15, 3.5, (44, 48, 52))
    s.rect(0.25, 0.1, width - 0.25, 2.5, (92, 86, 74), DARK_STEEL)
    s.rect(0.25, 0.0, width - 0.25, 0.12, HAZARD)
    for x in np.arange(0.3, width - 0.4, 0.3):
        s.rect(x - 0.02, 0.12, x + 0.02, 2.5, STEEL)
        for y in np.arange(0.12, 2.4, 0.6):
            s.polygon([(x, y), (x + 0.05, y), (x + 0.3, y + 0.6), (x + 0.25, y + 0.6)], STEEL)
            s.polygon([(x + 0.3, y), (x + 0.25, y), (x, y + 0.6), (x + 0.05, y + 0.6)], STEEL)
    for x in (width / 2 - 0.25, width / 2 + 0.25):
        s.rect(x - 0.015, 2.5, x + 0.015, 3.7, IRON)
    s.rect(0.0, 0.0, 0.15, 3.6, STEEL, DARK_STEEL)
    s.rect(width - 0.15, 0.0, width, 3.6, STEEL, DARK_STEEL)
    s.rect(-0.05, 3.5, width + 0.05, 3.62, DARK_STEEL)
    s.rect(0.2, 3.62, width - 0.2, height - 0.05, STEEL, DARK_STEEL)
    s.ellipse(width / 2 - 0.35, 3.7, width / 2 + 0.35, 4.3, IRON)
    s.ellipse(width / 2 - 0.12, 3.88, width / 2 + 0.12, 4.12, STEEL)
    return s.image


CONCRETE: Rgb = (138, 132, 116)
GRIME: Rgb = (84, 78, 62)
SLIME: Rgb = (104, 122, 70)
RUST: Rgb = (132, 80, 52)
BRICK: Rgb = (126, 70, 54)
MORTAR: Rgb = (82, 62, 52)


def bricks(s: Sheet, x0: float, y0: float, x1: float, y1: float, size: float = 0.25) -> None:
    """Courses of brick filling a box, each course set half a brick along from the one below."""
    s.rect(x0, y0, x1, y1, BRICK, MORTAR)
    for i, y in enumerate(np.arange(y0 + size, y1, size)):
        s.rect(x0, y - 0.015, x1, y + 0.015, MORTAR)
        for x in np.arange(x0 + (size if i % 2 else 0.0), x1, 2 * size):
            s.rect(x - 0.015, y - size, x + 0.015, y, MORTAR)


def sewer_walkway(length: float = 3.3, height: float = 2.16, deck: float = 1.16) -> Image.Image:
    """A concrete walkway on iron brackets with a railing, its deck `deck` up from the bottom."""
    s = Sheet(length, height, 200)
    s.rect(0.0, deck - 0.66, length, deck, CONCRETE, GRIME)
    s.rect(0.0, deck - 0.74, length, deck - 0.66, SLIME)
    for x in np.arange(0.4, length, 1.1):
        s.polygon([(x - 0.3, deck - 0.66), (x + 0.3, deck - 0.66), (x, 0.0)], RUST, GRIME)
    for x in np.arange(0.05, length, 1.1):
        s.rect(x, deck, x + 0.06, height - 0.04, RUST)
    for y in (deck + 0.5, height - 0.06):
        s.rect(0.0, y, length, y + 0.05, RUST, GRIME)
    return s.image


def sewer_pipe(length: float = 3.3, height: float = 1.16) -> Image.Image:
    """A big iron pipe lying along, banded at each joint, its top level with a row's."""
    s = Sheet(length, height, 200)
    s.rect(0.0, 0.0, length, height, RUST, GRIME)
    s.rect(0.0, height * 0.55, length, height * 0.75, (156, 100, 66))
    s.rect(0.0, 0.12, length, 0.3, SLIME)
    s.rect(0.0, 0.0, length, 0.12, GRIME)
    for x in np.arange(0.5, length, 1.1):
        s.rect(x - 0.08, 0.0, x + 0.08, height, GRIME)
    return s.image


def sewer_pier(width: float = 1.2, height: float = 4.46) -> Image.Image:
    """A brick pier between two rooms, a stone cap on each end."""
    s = Sheet(width, height, 160)
    bricks(s, 0.0, 0.0, width, height)
    for y in (0.0, height - 0.22):
        s.rect(-0.04, y, width + 0.04, y + 0.22, CONCRETE, GRIME)
    s.rect(0.0, 0.22, width, 0.6, SLIME)
    return s.image


def sewer_vault(length: float = 3.3, height: float = 2.3) -> Image.Image:
    """The vault over the sewers, brick down to a slimy underside."""
    s = Sheet(length, height, 160)
    bricks(s, 0.0, 0.0, length, height)
    s.rect(0.0, 0.0, length, 0.2, GRIME)
    s.rect(0.0, 0.2, length, 0.34, SLIME)
    return s.image


def sewer_weir(width: float = 2.2, height: float = 3.36, footing: float = 2.2) -> Image.Image:
    """A brick weir with an iron sluice gate in its face, on the walkway's edge `footing` deep."""
    s = Sheet(width, height + footing, 160)
    bricks(s, 0.0, 0.0, width, footing)
    s.rect(-0.05, footing - 0.4, width + 0.05, footing, CONCRETE, GRIME)
    s.rect(0.0, footing - 0.55, width, footing - 0.4, SLIME)
    bricks(s, 0.0, footing, width, footing + height)
    s.rect(-0.05, footing + height - 0.2, width + 0.05, footing + height, CONCRETE, GRIME)
    s.rect(0.45, footing + 0.3, width - 0.45, footing + 2.2, IRON, GRIME)
    for y in np.arange(footing + 0.5, footing + 2.1, 0.4):
        s.rect(0.45, y, width - 0.45, y + 0.04, RUST)
    s.ellipse(width / 2 - 0.35, footing + 2.35, width / 2 + 0.35, footing + 3.05, RUST)
    s.ellipse(width / 2 - 0.1, footing + 2.6, width / 2 + 0.1, footing + 2.8, IRON)
    s.rect(0.0, footing, width, footing + 0.35, SLIME)
    return s.image


def metro_ladder(height: float = 3.6) -> Image.Image:
    """The village's ladder in steel, with round rungs."""
    s = Sheet(0.6, height, 200)
    s.rect(0.0, 0.0, 0.08, height, STEEL, DARK_STEEL)
    s.rect(0.52, 0.0, 0.6, height, STEEL, DARK_STEEL)
    for y in np.arange(0.3, height - 0.1, 0.3):
        s.rect(0.05, y - 0.025, 0.55, y + 0.025, DARK_STEEL)
    return s.image


def metro_flight(rise: float = 2.2, run: float = 2.2, count: int = 8) -> Image.Image:
    """The village's steps rising to the right, in concrete with steel nosings over cream tiles."""
    s = Sheet(run + 0.3, rise, 200, GREY)
    h, d = rise / count, run / count
    profile = [(0.0, 0.0)]
    for i in range(count):
        profile += [(i * d, (i + 1) * h), ((i + 1) * d, (i + 1) * h)]
    s.polygon([*profile, (run + 0.3, rise), (run + 0.3, 0.0)], CREAM, DARK_STEEL)
    for y in np.arange(0.3, rise - 0.1, 0.3):
        s.rect(min(y / h, count) * d + 0.05, y - 0.012, run + 0.3, y + 0.012, (196, 188, 160))
    for i in range(count):
        s.rect(i * d, (i + 1) * h - 0.06, run + 0.3, (i + 1) * h, DARK_STEEL)
    return s.image


def metro_ledge(length: float = 3.0, height: float = 0.6) -> Image.Image:
    """The village's ledge as a steel grating deck on angled steel brackets."""
    s = Sheet(length, height, 300)
    deck = 0.12
    s.rect(0, height - deck, length, height, STEEL, DARK_STEEL)
    for x in np.arange(0.15, length, 0.15):
        s.rect(x - 0.012, height - deck, x + 0.012, height, DARK_STEEL)
    for x in (0.45, length - 0.45):
        s.polygon(
            [(x - 0.3, height - deck), (x + 0.3, height - deck), (x + 0.04, 0), (x - 0.04, 0)],
            DARK_STEEL,
        )
    return s.image


def sewer_ladder(height: float = 3.6) -> Image.Image:
    """The village's ladder in rusty iron, slimy at its foot."""
    s = Sheet(0.6, height, 200)
    s.rect(0.0, 0.0, 0.08, height, RUST, GRIME)
    s.rect(0.52, 0.0, 0.6, height, RUST, GRIME)
    for y in np.arange(0.3, height - 0.1, 0.3):
        s.rect(0.05, y - 0.03, 0.55, y + 0.03, RUST, GRIME)
    s.rect(0.0, 0.0, 0.08, 0.4, SLIME)
    s.rect(0.52, 0.0, 0.6, 0.4, SLIME)
    return s.image


def sewer_ledge(length: float = 3.0, height: float = 0.6) -> Image.Image:
    """The village's ledge as a concrete slab on rusty iron brackets."""
    s = Sheet(length, height, 300)
    deck = 0.16
    s.rect(0, height - deck, length, height, CONCRETE, GRIME)
    s.rect(0, height - deck - 0.04, length, height - deck, SLIME)
    for x in (0.45, length - 0.45):
        top = height - deck - 0.04
        s.polygon([(x - 0.28, top), (x + 0.28, top), (x, 0)], RUST)
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
    s = Sheet(0.75, 1.7, 300, GREY)
    s.rect(0.0, 0.08, 0.75, 1.7, MINT, (150, 190, 170))
    s.rect(0.02, 1.08, 0.73, 1.12, (150, 190, 170))
    s.rect(0.06, 1.25, 0.1, 1.5, (210, 210, 200))
    s.rect(0.06, 0.7, 0.1, 0.95, (210, 210, 200))
    for x in (0.08, 0.6):
        s.rect(x, 0.0, x + 0.07, 0.08, IRON)
    return s.image


CONTAINER_BLUE: Rgb = (62, 98, 128)


def shipping_container(length: float = 6.6, height: float = 3.36) -> Image.Image:
    """A container's corrugated side, its doors at the east end, its flat top along the top edge
    to stand on."""
    s = Sheet(length, height, 120)
    s.rect(0.0, 0.0, length, height, CONTAINER_BLUE, DARK_STEEL)
    for x in np.arange(0.35, length - 1.3, 0.3):
        s.rect(x, 0.2, x + 0.12, height - 0.2, (52, 84, 112))
    s.rect(0.0, height - 0.2, length, height, DARK_STEEL)
    s.rect(0.0, 0.0, length, 0.2, DARK_STEEL)
    for x in (0.0, length - 0.2):
        s.rect(x, 0.0, x + 0.2, height, DARK_STEEL)
    s.rect(length - 1.3, 0.2, length - 0.2, height - 0.2, (70, 108, 138), DARK_STEEL)
    for x in (length - 1.05, length - 0.5):
        s.rect(x, 0.2, x + 0.06, height - 0.2, STEEL)
        s.rect(x - 0.08, 1.2, x + 0.14, 1.32, IRON)
    s.rect(0.6, 0.6, 1.6, 1.2, RUST)
    return s.image


def bulkhead(width: float = 3.3, height: float = 7.8, footing: float = 2.2) -> Image.Image:
    """A tiled wall with a jammed steel door at its foot and a vent near its top, on the floor's
    edge `footing` deep."""
    s = Sheet(width, height + footing, 120)
    s.rect(0.0, 0.0, width, footing, CONCRETE, GRIME)
    s.rect(0.0, footing - 0.25, width, footing, (110, 106, 94))
    s.rect(0.0, footing, width, footing + height, CREAM, DARK_STEEL)
    for y in np.arange(footing + 0.3, footing + height, 0.3):
        s.rect(0.0, y - 0.01, width, y + 0.01, (196, 188, 160))
    s.rect(0.0, footing + height - 0.25, width, footing + height, DARK_STEEL)
    s.rect(0.2, footing, width - 0.2, footing + 2.4, DARK_STEEL)
    s.rect(0.32, footing, width - 0.32, footing + 2.28, STEEL, IRON)
    for y in (0.3, 2.0):
        s.rect(0.32, footing + y, width - 0.32, footing + y + 0.12, HAZARD)
    s.ellipse(width / 2 - 0.3, footing + 0.9, width / 2 + 0.3, footing + 1.5, IRON)
    s.rect(0.32, footing + 1.6, 0.9, footing + 1.9, RUST)
    top = footing + height
    s.rect(0.5, top - 1.2, width - 0.5, top - 0.6, IRON)
    for x in np.arange(0.6, width - 0.5, 0.15):
        s.rect(x, top - 1.15, x + 0.06, top - 0.65, DARK_STEEL)
    return s.image


LINEN: Rgb = (240, 236, 226)
CUSHION: Rgb = (200, 64, 56)
MARBLE: Rgb = (232, 230, 224)
LANTERN: Rgb = (214, 60, 48)
CANVAS: Rgb = (238, 230, 210)
OAK: Rgb = (214, 178, 130)
DARK_OAK: Rgb = (160, 124, 84)
FABRIC: Rgb = (128, 132, 140)
THROW: Rgb = (214, 168, 60)
CORAL: Rgb = (226, 110, 92)
PLYWOOD: Rgb = (196, 150, 100)
STEEL_GREY: Rgb = (64, 68, 74)
WORKTOP: Rgb = (200, 160, 110)
SINK: Rgb = (170, 178, 184)
HOB: Rgb = (40, 42, 46)
OVEN: Rgb = (70, 78, 88)
PAN: Rgb = (196, 70, 56)
FRAME: Rgb = (44, 46, 52)
GLASS: Rgb = (176, 210, 228)
BLIND: Rgb = (232, 226, 210)
SANDSTONE: Rgb = (200, 186, 164)
TREAD: Rgb = (150, 136, 116)


def bed(length: float = 1.57, height: float = 1.05, mattress: float = 0.45) -> Image.Image:
    """A double bed from the side, its padded headboard on the left and its mattress's top
    `mattress` up at its front edge."""
    s = Sheet(length, height, 300, GREY)
    for x in (0.02, length - 0.1):
        s.rect(x, 0.0, x + 0.08, 0.2, DARK_OAK)
    s.rect(0.0, 0.16, length, 0.28, OAK, DARK_OAK)
    s.rect(0.1, 0.28, length - 0.04, mattress, LINEN)
    s.rect(0.85, 0.26, length - 0.02, mattress, THROW)
    s.ellipse(0.14, mattress - 0.06, 0.5, mattress + 0.12, LINEN)
    s.rect(0.0, 0.0, 0.1, height, FABRIC, DARK_OAK)
    s.rect(length - 0.06, 0.0, length, mattress + 0.08, OAK, DARK_OAK)
    return s.image


def stool(width: float = 0.42, height: float = 0.7, seat: float = 0.567) -> Image.Image:
    """A bar stool from the front, the front edge of its padded seat `seat` up."""
    s = Sheet(width, height, 500)
    s.rect(0.08, 0.0, width - 0.08, 0.04, IRON)
    s.rect(width / 2 - 0.02, 0.04, width / 2 + 0.02, seat - 0.06, IRON)
    s.rect(0.06, 0.22, width - 0.06, 0.25, IRON)
    s.ellipse(0.02, seat - 0.04, width - 0.02, height, CUSHION)
    s.rect(0.0, seat - 0.08, width, seat, CUSHION, (150, 44, 40))
    return s.image


def bench(width: float = 1.48, height: float = 0.9, seat: float = 0.392) -> Image.Image:
    """A street bench from the front, the top of its seat `seat` up."""
    s = Sheet(width, height, 300)
    for x in (0.12, width - 0.2):
        s.rect(x, 0.0, x + 0.08, height - 0.05, STEEL_GREY)
    s.rect(0.0, seat - 0.07, width, seat, OAK, DARK_OAK)
    for y in (seat + 0.16, seat + 0.32, height - 0.08):
        s.rect(0.04, y, width - 0.04, y + 0.08, OAK, DARK_OAK)
    return s.image


def _chair(s: Sheet, x0: float, x1: float, seat: float, back: float, outer: float, wood: Rgb):
    """A chair from the side between `x0` and `x1`, its back on the `outer` x."""
    s.rect(x0, seat - 0.05, x1, seat, wood)
    for x in (x0 + 0.02, x1 - 0.06):
        s.rect(x, 0.0, x + 0.04, seat - 0.05, wood)
    s.rect(outer - 0.02, seat, outer + 0.02, back, wood)
    s.rect(outer - 0.03, back - 0.25, outer + 0.03, back - 0.05, wood)


def _table_with_chairs(
    width: float,
    height: float,
    seat: float,
    top: Rgb,
    leg: Rgb,
    chairs: Rgb,
    pedestal: bool,
    ppm: float,
    backdrop: Rgb = (255, 255, 255),
) -> Image.Image:
    """A table from the side with a chair at each side facing it, their seats `seat` up."""
    s = Sheet(width, height, ppm, backdrop)
    chair = 0.44
    _chair(s, 0.0, chair, seat, height, 0.02, chairs)
    _chair(s, width - chair, width, seat, height, width - 0.02, chairs)
    x0, x1 = chair + 0.1, width - chair - 0.1
    if pedestal:
        s.rect(width / 2 - 0.04, 0.04, width / 2 + 0.04, 0.72, leg)
        s.rect(width / 2 - 0.22, 0.0, width / 2 + 0.22, 0.04, leg)
    else:
        for x in (x0 + 0.04, x1 - 0.1):
            s.rect(x, 0.0, x + 0.06, 0.72, leg)
    s.rect(x0, 0.72, x1, 0.77, top, leg)
    return s.image


def cafe_table(width: float = 1.91, height: float = 0.95, seat: float = 0.442) -> Image.Image:
    return _table_with_chairs(width, height, seat, MARBLE, IRON, PLYWOOD, True, 300, GREY)


def table(width: float = 1.94, height: float = 0.95, seat: float = 0.442) -> Image.Image:
    return _table_with_chairs(width, height, seat, OAK, DARK_OAK, CORAL, False, 300)


def noodle_table(width: float = 1.9, height: float = 1.9, seat: float = 0.483) -> Image.Image:
    """A square table from the side with a stool each side, their seats `seat` up, under a
    lantern on a cord from the top edge."""
    s = Sheet(width, height, 280, GREY)
    stool_w = 0.4
    for x0 in (0.0, width - stool_w):
        s.rect(x0, seat - 0.07, x0 + stool_w, seat, CUSHION, (150, 44, 40))
        for x in (x0 + 0.04, x0 + stool_w - 0.08):
            s.rect(x, 0.0, x + 0.04, seat - 0.07, DARK_WOOD)
    x0, x1 = stool_w + 0.15, width - stool_w - 0.15
    for x in (x0 + 0.04, x1 - 0.1):
        s.rect(x, 0.0, x + 0.06, 0.72, DARK_WOOD)
    s.rect(x0, 0.72, x1, 0.77, WOOD, DARK_WOOD)
    s.rect(width / 2 - 0.01, 1.55, width / 2 + 0.01, height, IRON)
    s.ellipse(width / 2 - 0.2, 1.15, width / 2 + 0.2, 1.57, LANTERN)
    return s.image


def picture_frame(width: float = 0.75, height: float = 0.9, moulding: float = 0.1) -> Image.Image:
    """An empty frame from the front, its moulding `moulding` wide all round its canvas."""
    s = Sheet(width, height, 400, GREY)
    s.rect(0.0, 0.0, width, height, OAK, DARK_OAK)
    s.rect(moulding, moulding, width - moulding, height - moulding, CANVAS, DARK_OAK)
    return s.image


def kitchen(width: float = 2.6, height: float = 0.95, top: float = 0.84) -> Image.Image:
    """Base cupboards with the sink and hob inside the ends a stretch keeps, so neither repeats."""
    s = Sheet(width, height, 300, GREY)
    end = 0.15 * width
    s.rect(0.03, 0.0, width - 0.03, 0.08, HOB)
    s.rect(0.0, 0.08, width, top - 0.06, WHITE, (196, 196, 192))
    for x in np.linspace(end, width - end, 6):
        s.rect(x - 0.005, 0.1, x + 0.005, top - 0.08, (196, 196, 192))
    s.rect(width - end + 0.04, 0.3, width - 0.04, 0.62, OVEN, FRAME)
    s.rect(-0.02, top - 0.06, width + 0.02, top, WORKTOP, DARK_OAK)
    s.rect(0.03, top - 0.03, 0.17, top, SINK)
    s.rect(0.08, top, 0.1, height, SINK)
    s.rect(0.04, height - 0.02, 0.1, height, SINK)
    s.rect(width - 0.26, top, width - 0.03, top + 0.02, HOB)
    s.rect(width - 0.18, top + 0.02, width - 0.05, top + 0.08, PAN)
    return s.image


def window(width: float = 1.48, height: float = 1.3, blind: float = 0.55) -> Image.Image:
    """A window from inside a room, two panes with a roller blind `blind` of the way down."""
    s = Sheet(width, height, 300, GREY)
    s.rect(0.0, 0.0, width, height, FRAME)
    s.rect(0.06, 0.11, width - 0.06, height - 0.06, GLASS)
    drop = height - 0.06 - blind * (height - 0.17)
    s.rect(0.06, drop, width - 0.06, height - 0.06, BLIND)
    s.rect(0.06, drop - 0.03, width - 0.06, drop, FRAME)
    s.rect(width / 2 - 0.03, 0.11, width / 2 + 0.03, drop - 0.03, FRAME)
    return s.image


SKETCHES: dict[str, Callable[[], Image.Image]] = {
    "stairs": stairs,
    "ladder": ladder,
    "lift": lift,
    "lift_shaft": lift_shaft,
    "steps": steps,
    "ledge": ledge,
    "rope_bridge": rope_bridge,
    "train_carriage": train_carriage,
    "catwalk": catwalk,
    "metro_steps": metro_steps,
    "freight_lift": freight_lift,
    "sewer_walkway": sewer_walkway,
    "sewer_pipe": sewer_pipe,
    "sewer_pier": sewer_pier,
    "sewer_vault": sewer_vault,
    "sewer_weir": sewer_weir,
    "metro_ladder": metro_ladder,
    "metro_flight": metro_flight,
    "metro_ledge": metro_ledge,
    "sewer_ladder": sewer_ladder,
    "sewer_ledge": sewer_ledge,
    "bathtub": bathtub,
    "washbasin": washbasin,
    "fridge": fridge,
    "shipping_container": shipping_container,
    "bulkhead": bulkhead,
    "bed": bed,
    "stool": stool,
    "bench": bench,
    "cafe_table": cafe_table,
    "noodle_table": noodle_table,
    "table": table,
    "picture_frame": picture_frame,
    "kitchen": kitchen,
    "window": window,
}
