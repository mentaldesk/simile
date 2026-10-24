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
    s = Sheet(run + 0.3, rise, 200)
    h, d = rise / count, run / count
    profile = [(0.0, 0.0)]
    for i in range(count):
        profile += [(i * d, (i + 1) * h), ((i + 1) * d, (i + 1) * h)]
    s.polygon([*profile, (run + 0.3, rise), (run + 0.3, 0.0)], STONE, (150, 142, 128))
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


def sewer_weir(width: float = 2.2, height: float = 3.36) -> Image.Image:
    """A brick weir across the floor with an iron sluice gate in its face."""
    s = Sheet(width, height, 160)
    bricks(s, 0.0, 0.0, width, height)
    s.rect(-0.05, height - 0.2, width + 0.05, height, CONCRETE, GRIME)
    s.rect(0.45, 0.3, width - 0.45, 2.2, IRON, GRIME)
    for y in np.arange(0.5, 2.1, 0.4):
        s.rect(0.45, y, width - 0.45, y + 0.04, RUST)
    s.ellipse(width / 2 - 0.35, 2.35, width / 2 + 0.35, 3.05, RUST)
    s.ellipse(width / 2 - 0.1, 2.6, width / 2 + 0.1, 2.8, IRON)
    s.rect(0.0, 0.0, width, 0.35, SLIME)
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
    "bathtub": bathtub,
    "washbasin": washbasin,
    "fridge": fridge,
}
