"""Every doll piece, drawn flat from a `Look`. Units are 1/100 of a standing doll's height, with
y down and each piece's pivot at (0, 0). Side pieces face +x; front and back pieces are seen
straight on, with x to the picture's right."""

import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from PIL import Image, ImageDraw

from simile.dolls.colour import RGB, darker, lighter, mix
from simile.dolls.look import Look

Pt = tuple[float, float]

SUPERSAMPLE = 3
INK = (44, 34, 42)
BLUSH = (224, 110, 110)

SKULL = (0.6, -14.2)
SKULL_R = (11.0, 11.8)
FACE = (0.0, -14.2)
FACE_R = (11.2, 11.8)
NECK = -32.0
SHOULDER = -28.0
THIGH = 18.5
SHIN = 17.5
SOLE = 4.8
UPPER_ARM = 13.0
FOREARM = 10.5
STANDING_HEIGHT = THIGH + SHIN + SOLE - NECK - FACE[1] + FACE_R[1]
"""Sole to crown, without hair or hats."""

SIDE = ("head", "torso", "upper_arm", "lower_arm", "upper_leg", "lower_leg", "shoe")
FRONT_BACK = ("head_front", "torso_front", "head_back", "torso_back", "shoe_front")
PIECES = SIDE + FRONT_BACK


def arc(c: Pt, rx: float, ry: float, t0: float, t1: float, n: int = 24) -> list[Pt]:
    return [
        (
            c[0] + rx * math.cos(math.radians(t0 + (t1 - t0) * i / n)),
            c[1] + ry * math.sin(math.radians(t0 + (t1 - t0) * i / n)),
        )
        for i in range(n + 1)
    ]


def mirrored(points: Iterable[Pt]) -> list[Pt]:
    return [(-x, y) for x, y in points]


class Pen:
    """Draws shapes given in units onto a supersampled RGBA layer covering `box`."""

    def __init__(self, box: tuple[float, float, float, float], scale: float) -> None:
        self.box = box
        self.scale = scale
        self.k = scale * SUPERSAMPLE
        self.size = (math.ceil((box[2] - box[0]) * scale), math.ceil((box[3] - box[1]) * scale))
        w, h = self.size
        self.layer = Image.new("RGBA", (w * SUPERSAMPLE, h * SUPERSAMPLE), (0, 0, 0, 0))
        self.draw = ImageDraw.Draw(self.layer)

    def _p(self, p: Pt) -> tuple[float, float]:
        return (p[0] - self.box[0]) * self.k, (p[1] - self.box[1]) * self.k

    def px(self, p: Pt) -> tuple[float, float]:
        return (p[0] - self.box[0]) * self.scale, (p[1] - self.box[1]) * self.scale

    def poly(self, pts: Iterable[Pt], fill: RGB) -> None:
        self.draw.polygon([self._p(p) for p in pts], fill=(*fill, 255))

    def blob(self, pts: list[Pt], r: float, fill: RGB) -> None:
        """The polygon grown by `r` all round, so its corners are rounded."""
        self.poly(pts, fill)
        ring = [self._p(p) for p in [*pts, pts[0]]]
        self.draw.line(ring, fill=(*fill, 255), width=round(2 * r * self.k), joint="curve")
        for p in pts:
            self.ellipse(p, r, r, fill)

    def ellipse(self, c: Pt, rx: float, ry: float, fill: RGB) -> None:
        x, y = self._p(c)
        self.draw.ellipse(
            (x - rx * self.k, y - ry * self.k, x + rx * self.k, y + ry * self.k), fill=(*fill, 255)
        )

    def line(self, pts: list[Pt], width: float, fill: RGB) -> None:
        self.draw.line(
            [self._p(p) for p in pts], fill=(*fill, 255), width=round(width * self.k), joint="curve"
        )
        for p in (pts[0], pts[-1]):
            self.ellipse(p, width / 2, width / 2, fill)

    def capsule(self, a: Pt, b: Pt, ra: float, rb: float, fill: RGB) -> None:
        dx, dy = b[0] - a[0], b[1] - a[1]
        d = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / d, dx / d
        self.poly(
            [
                (a[0] + nx * ra, a[1] + ny * ra),
                (b[0] + nx * rb, b[1] + ny * rb),
                (b[0] - nx * rb, b[1] - ny * rb),
                (a[0] - nx * ra, a[1] - ny * ra),
            ],
            fill,
        )
        self.ellipse(a, ra, ra, fill)
        self.ellipse(b, rb, rb, fill)

    def image(self) -> Image.Image:
        return self.layer.resize(self.size, Image.Resampling.LANCZOS)


def strand(look: Look) -> RGB:
    """A lighter shade for strands: on grey hair a darker one reads as the seams of a cap."""
    return lighter(look.hair, 0.4) if look.light_hair else lighter(look.hair, 0.22)


def tufted(c: Pt, rx: float, ry: float, t0: float, t1: float, tufts: int, depth: float) -> list[Pt]:
    """An arc whose edge bulges into `tufts` locks, so hair doesn't read as a smooth cap."""
    n = max(24, tufts * 8)
    pts = []
    for i in range(n + 1):
        t = math.radians(t0 + (t1 - t0) * i / n)
        bump = depth * abs(math.sin(math.pi * tufts * i / n)) ** 0.7
        pts.append((c[0] + (rx + bump) * math.cos(t), c[1] + (ry + bump) * math.sin(t)))
    return pts


# Side view, facing +x.


def side_shell(pen: Pen, look: Look, dr: float, t_front: float, t_back: float) -> None:
    rx, ry = SKULL_R
    tufts = 0 if look.hair_style == "buzz" else 5
    outer = tufted(
        SKULL, rx + dr - 0.6, ry + dr - 0.6, t_front, t_back, tufts, 1.0 if tufts else 0.6
    )
    back = arc(SKULL, rx - 0.4, ry - 0.4, t_back, t_back, 1)[0]
    front = arc(SKULL, rx - 0.4, ry - 0.4, t_front, t_front, 1)[0]
    hairline = [(x + 5.6, y) for x, y in fringe(4.2, front[1] + 0.4, 1.3, 2)]
    pen.poly([*outer, back, (-3.6, -15.2), (-1.4, -19.2), *reversed(hairline), front], look.hair)
    pen.poly([(0.0, -19.4), (2.4, -19.0), (1.8, -14.2), (0.8, -13.6)], look.hair)


def side_strands(pen: Pen, look: Look, dr: float) -> None:
    rx, ry = SKULL_R
    for t0, t1, inset in ((-60, -150, 2.2), (-45, -120, 4.4), (-95, -175, 3.4)):
        pen.line(arc(SKULL, rx + dr - inset, ry + dr - inset, t0, t1, 10), 0.45, strand(look))


def head(pen: Pen, look: Look) -> None:
    style, acc, hair = look.hair_style, look.accessories, look.hair
    rx, ry = SKULL_R
    if style == "long":
        pen.blob([(-11.0, -22.0), (-4.0, -24.0), (-2.5, 6.0), (-12.5, 8.0)], 1.8, hair)
        pen.line([(-8.0, -6.0), (-7.4, 6.5)], 0.45, strand(look))
    if style == "ponytail":
        pen.capsule((-9.5, -21.0), (-15.5, -10.0), 3.0, 2.6, hair)
        pen.capsule((-15.5, -10.0), (-15.2, 1.5), 2.6, 1.4, hair)
        pen.ellipse((-10.8, -19.2), 1.8, 1.8, look.accent)
    if style == "bun":
        pen.ellipse((-9.0, -23.4), 5.0, 4.7, hair)
        pen.line(arc((-9.0, -23.4), 3.0, 2.8, 200, 320, 8), 0.45, strand(look))
    if "headphones" in acc:
        pen.line([(-1.8, -17.0), (-1.4, -24.0), (-0.7, -28.4)], 1.5, look.accent)
    pen.capsule((0.6, -1.0), (1.1, -6.3), 3.4, 3.4, look.skin)
    pen.ellipse(SKULL, rx, ry, look.skin)
    pen.ellipse((6.2, -5.6), 5.0, 3.6, look.skin)
    pen.ellipse((11.1, -12.6), 2.0, 2.3, look.skin)
    pen.ellipse((-1.8, -13.0), 2.2, 3.0, darker(look.skin, 0.9))
    pen.ellipse((6.4, -10.0), 2.0, 1.4, mix(look.skin, BLUSH, 0.45))
    pen.ellipse((7.4, -15.0), 1.2, 1.5, INK)
    pen.line([(8.6, -7.6), (10.0, -8.0)], 0.55, darker(look.skin, 0.55))
    brow = hair if style != "bald" else darker(look.skin, 0.7)
    pen.line([(5.8, -18.6), (8.8, -19.0)], 0.8, brow)
    shells = {
        "buzz": (0.5, -36, -196),
        "short": (1.6, -28, -204),
        "bob": (2.2, -26, -186),
        "long": (2.2, -26, -198),
        "ponytail": (1.4, -30, -198),
        "bun": (1.4, -30, -198),
        "curly": (1.2, -28, -228),
    }
    if style == "curly":
        for t in range(-20, -240, -20):
            x = SKULL[0] + (rx + 1.2) * math.cos(math.radians(t))
            y = SKULL[1] + (ry + 1.2) * math.sin(math.radians(t))
            pen.ellipse((x, y), 3.4, 3.4, hair)
    if style in shells:
        side_shell(pen, look, *shells[style])
    if style == "short":
        for x, y in ((6.8, -23.6), (3.4, -25.4), (9.2, -21.0)):
            pen.ellipse((x, y), 2.6, 1.8, hair)
        pen.poly([(9.6, -21.0), (12.4, -18.8), (8.6, -19.8)], hair)
    if style == "bob":
        pen.blob([(-11.0, -17.0), (-12.0, -6.0), (-4.5, -5.0), (-3.0, -15.0)], 0.8, hair)
        pen.ellipse((6.4, -23.8), 5.0, 2.8, hair)
    if style == "curly":
        for x, y in ((8.6, -22.4), (4.4, -25.6), (10.8, -19.0)):
            pen.ellipse((x, y), 2.4, 2.4, hair)
        for t in (-70, -120, -170):
            c = arc(SKULL, rx - 2.6, ry - 2.6, t, t, 1)[0]
            pen.line(arc(c, 1.6, 1.6, 200, 380, 8), 0.45, strand(look))
    elif style in shells:
        side_strands(pen, look, shells[style][0])
    if "cap" in acc:
        cap(pen, look, side=True)
    if "beanie" in acc:
        beanie(pen, look, SKULL, side=True)
    if "headphones" in acc:
        pen.capsule((-1.9, -15.4), (-1.9, -10.6), 2.8, 2.8, darker(look.accent, 0.5))
    if "glasses" in acc:
        pen.line([(4.8, -15.6), (-0.6, -14.4)], 0.6, INK)
        ring = arc((7.8, -15.0), 2.6, 2.4, 0, 360, 24)
        pen.line(ring, 0.6, INK)
    if "sunglasses" in acc:
        pen.line([(4.8, -15.6), (-0.6, -14.4)], 0.7, INK)
        pen.ellipse((8.2, -15.0), 3.2, 2.3, (30, 26, 34))


def cap(pen: Pen, look: Look, side: bool) -> None:
    centre = SKULL if side else FACE
    rx, ry = SKULL_R if side else FACE_R
    dome = arc(centre, rx + 1.8, ry + 2.0, -10 if side else -6, -194 if side else -174, 28)
    pen.poly(dome, look.accent)
    pen.line(arc(centre, rx - 1.0, ry - 1.2, -40, -140, 10), 0.45, darker(look.accent, 0.85))
    if side:
        pen.blob(
            [(5.0, -18.6), (16.6, -17.6), (16.6, -16.8), (5.0, -16.9)], 0.5, darker(look.accent)
        )
    pen.ellipse((centre[0], centre[1] - ry - 2.0), 1.2, 0.9, darker(look.accent))


def beanie(pen: Pen, look: Look, centre: Pt, side: bool) -> None:
    rx, ry = SKULL_R if side else FACE_R
    pen.poly(
        arc(centre, rx + 2.2, ry + 2.6, -14 if side else -8, -200 if side else -172, 28),
        look.accent,
    )
    band_top = centre[1] - ry * 0.32
    band_y = centre[1] - ry * 0.08
    if side:
        pen.poly(
            [
                (rx + 2.4, band_top),
                (rx + 2.6, band_y),
                (-rx - 2.4, band_y + 1.0),
                (-rx - 2.0, band_top),
            ],
            darker(look.accent),
        )
    else:
        pen.blob(
            [(-rx - 1.8, band_top), (rx + 1.8, band_top), (rx + 1.8, band_y), (-rx - 1.8, band_y)],
            0.6,
            darker(look.accent),
        )
    for t in range(-160 if side else -150, -20, 18):
        a = arc(centre, rx + 0.8, ry + 1.2, t, t, 1)[0]
        pen.line([(a[0], a[1]), (a[0] * 0.98, band_top - 0.6)], 0.4, darker(look.accent, 0.88))


# Front view: the face.


def front_shell(pen: Pen, look: Look, dr: float, drop: float, hairline: list[Pt]) -> None:
    rx, ry = FACE_R
    tufts, depth = (0, 0.0) if look.hair_style == "buzz" else (6, 1.0)
    outer = tufted(
        FACE, rx + dr - depth / 2, ry + dr - depth / 2, 180 - drop, 360 + drop, tufts, depth
    )
    pen.poly([*outer, *hairline], look.hair)


def fringe(width: float, top: float, depth: float, tufts: int) -> list[Pt]:
    """A tufted hairline from right to left across the forehead."""
    pts: list[Pt] = []
    for i in range(tufts * 2 + 1):
        x = width - 2 * width * i / (tufts * 2)
        y = top + (depth if i % 2 else 0.0) - 0.06 * abs(x) ** 1.5
        pts.append((x, y))
    return pts


def front_strands(pen: Pen, look: Look, dr: float) -> None:
    rx, ry = FACE_R
    for t0, t1, inset in ((250, 200, 2.6), (290, 340, 2.6), (265, 225, 4.6), (275, 315, 4.6)):
        pen.line(arc(FACE, rx + dr - inset, ry + dr - inset, t0, t1, 10), 0.45, strand(look))


def head_front(pen: Pen, look: Look) -> None:
    style, acc, hair = look.hair_style, look.accessories, look.hair
    rx, ry = FACE_R
    if style == "long":
        pen.blob([(-12.4, -22.0), (12.4, -22.0), (12.4, -10.0), (-12.4, -10.0)], 1.6, hair)
        for side in (-1, 1):
            pen.blob(
                [(side * 13.0, -8.0), (side * 7.8, -8.0), (side * 8.4, 12.0), (side * 13.2, 12.0)],
                1.4,
                hair,
            )
    if style == "bob":
        pen.blob([(-12.0, -20.0), (12.0, -20.0), (12.4, -2.0), (-12.4, -2.0)], 1.4, hair)
    if style == "curly":
        for t in range(150, 400, 18):
            x = FACE[0] + (rx + 1.4) * math.cos(math.radians(t))
            y = FACE[1] + (ry + 1.4) * math.sin(math.radians(t))
            pen.ellipse((x, y), 3.4, 3.4, hair)
    if style == "bun":
        pen.ellipse((0.0, -27.8), 5.0, 4.4, hair)
        pen.line(arc((0.0, -27.8), 3.0, 2.6, 200, 340, 8), 0.45, strand(look))
    if style == "ponytail":
        pen.capsule((10.6, -18.0), (13.6, -6.0), 2.4, 1.6, hair)
    pen.capsule((0.0, 1.0), (0.0, -6.0), 3.6, 3.6, look.skin)
    for side in (-1, 1):
        pen.ellipse((side * (rx - 0.2), -13.2), 2.2, 3.0, darker(look.skin, 0.92))
    pen.ellipse(FACE, rx, ry, look.skin)
    for side in (-1, 1):
        pen.ellipse((side * 6.4, -9.2), 2.0, 1.4, mix(look.skin, BLUSH, 0.45))
        pen.ellipse((side * 4.0, -12.8), 1.2, 1.5, INK)
    pen.ellipse((0.0, -10.4), 1.1, 0.8, darker(look.skin, 0.84))
    pen.line(arc((0.0, -8.4), 1.9, 1.2, 20, 160, 8), 0.55, darker(look.skin, 0.55))
    brow = hair if style != "bald" else darker(look.skin, 0.7)
    for side in (-1, 1):
        pen.line([(side * 2.6, -16.6), (side * 5.6, -17.0)], 0.8, brow)
    if style == "buzz":
        front_shell(pen, look, 0.5, 6, fringe(10.2, -19.4, 0.4, 5))
    if style == "short":
        front_shell(
            pen, look, 1.6, 10, [(10.6, -11.0), *fringe(9.6, -17.0, 1.6, 4), (-10.6, -11.0)]
        )
    if style == "curly":
        front_shell(pen, look, 1.2, 8, [(10.6, -12.0), *fringe(9.6, -17.2, 1.4, 5), (-10.6, -12.0)])
        for x in (-6.4, -2.2, 2.2, 6.4):
            pen.ellipse((x, -18.4), 2.4, 2.2, hair)
    if style == "bob":
        front_shell(
            pen,
            look,
            2.2,
            70,
            [
                (10.4, -2.0),
                (10.0, -12.0),
                (8.6, -16.2),
                (-8.6, -16.2),
                (-10.0, -12.0),
                (-10.4, -2.0),
            ],
        )
    if style == "long":
        outer = rx + 1.7
        front_shell(
            pen,
            look,
            2.2,
            0,
            [
                (outer, 9.0),
                (10.6, 9.0),
                (10.2, -10.0),
                (6.0, -17.4),
                (1.2, -20.6),
                (0.0, -19.4),
                (-1.2, -20.6),
                (-6.0, -17.4),
                (-10.2, -10.0),
                (-10.6, 9.0),
                (-outer, 9.0),
            ],
        )
    if style in ("ponytail", "bun"):
        front_shell(
            pen,
            look,
            1.2,
            6,
            [
                (10.4, -12.4),
                (8.8, -17.6),
                (4.6, -20.2),
                (0.0, -20.8),
                (-4.6, -20.2),
                (-8.8, -17.6),
                (-10.4, -12.4),
            ],
        )
    if style in ("buzz", "short", "bob", "long", "ponytail", "bun"):
        front_strands(pen, look, {"buzz": 0.5, "short": 1.6}.get(style, 1.6))
    if "cap" in acc:
        cap(pen, look, side=False)
        pen.blob(
            [(-11.6, -17.4), (11.6, -17.4), (11.0, -15.8), (-11.0, -15.8)], 0.7, darker(look.accent)
        )
    if "beanie" in acc:
        beanie(pen, look, FACE, side=False)
    if "headphones" in acc:
        pen.line(arc(FACE, rx + 2.4, ry + 2.8, 198, 342, 24), 1.5, look.accent)
        for side in (-1, 1):
            pen.capsule(
                (side * 12.0, -15.0), (side * 12.0, -11.2), 2.8, 2.8, darker(look.accent, 0.5)
            )
    if "glasses" in acc:
        for side in (-1, 1):
            pen.line(arc((side * 4.0, -12.8), 2.6, 2.4, 0, 360, 24), 0.6, INK)
            pen.line([(side * 6.6, -13.2), (side * 10.4, -13.6)], 0.5, INK)
        pen.line([(-1.4, -13.2), (1.4, -13.2)], 0.55, INK)
    if "sunglasses" in acc:
        for side in (-1, 1):
            pen.ellipse((side * 4.2, -12.8), 3.1, 2.2, (30, 26, 34))
            pen.line([(side * 7.0, -13.4), (side * 10.4, -13.8)], 0.6, INK)
        pen.line([(-1.4, -13.4), (1.4, -13.4)], 0.6, (30, 26, 34))


# Back view: hair and the back of the head.


def dashes(
    pen: Pen,
    look: Look,
    inside: Callable[[float, float], bool],
    origin: Pt,
    n: int,
    towards: bool = False,
) -> None:
    """Short strokes scattered over the hair, each along the line from `origin` (the crown, or
    with `towards` the point the hair is gathered to), so it reads as hair and not a helmet."""
    import random

    rng = random.Random(f"{look.hair_style}/{n}")
    placed = 0
    for _ in range(n * 40):
        if placed == n:
            break
        x, y = rng.uniform(-11.0, 11.0), rng.uniform(-26.0, 12.0)
        if not inside(x, y):
            continue
        dx, dy = (origin[0] - x, origin[1] - y) if towards else (x - origin[0], y - origin[1])
        d = math.hypot(dx, dy) or 1.0
        length = rng.uniform(2.0, 3.6)
        end = (x + dx / d * length, y + dy / d * length)
        bend = rng.uniform(-0.5, 0.5)
        mid = ((x + end[0]) / 2 - dy / d * bend, (y + end[1]) / 2 + dx / d * bend)
        pen.line([(x, y), mid, end], 0.42, strand(look))
        placed += 1


def back_cover(pen: Pen, look: Look, dr: float, nape: float, ragged: float) -> None:
    rx, ry = FACE_R
    drop = math.degrees(math.asin(min(1.0, max(-1.0, (nape - FACE[1] - 1.5) / (ry + dr)))))
    tufts, depth = (0, 0.0) if look.hair_style == "buzz" else (7, 1.0)
    outer = tufted(
        FACE, rx + dr - depth / 2, ry + dr - depth / 2, 180 - drop, 360 + drop, tufts, depth
    )
    edge = fringe(outer[-1][0] - 0.6, nape, ragged, 4)
    pen.poly([*outer, *edge], look.hair)


def head_back(pen: Pen, look: Look) -> None:
    style, acc, hair = look.hair_style, look.accessories, look.hair
    rx, ry = FACE_R
    pen.capsule((0.0, 1.0), (0.0, -6.0), 3.6, 3.6, look.skin)
    for side in (-1, 1):
        pen.ellipse((side * (rx - 0.2), -13.2), 2.2, 3.0, darker(look.skin, 0.92))
    pen.ellipse(FACE, rx, ry, look.skin)
    if style == "buzz":
        back_cover(pen, look, 0.5, -6.0, 0.5)
    if style == "short":
        back_cover(pen, look, 1.6, -5.0, 1.4)
    if style in ("ponytail", "bun"):
        back_cover(pen, look, 1.2, -5.4, 0.8)
    if style == "curly":
        for t in range(150, 400, 16):
            x = FACE[0] + (rx + 1.4) * math.cos(math.radians(t))
            y = FACE[1] + (ry + 1.4) * math.sin(math.radians(t))
            pen.ellipse((x, y), 3.4, 3.4, hair)
        back_cover(pen, look, 1.2, -3.6, 1.6)
        for x, y in (
            (-5.0, -20.0),
            (3.0, -22.0),
            (6.0, -14.0),
            (-6.0, -10.0),
            (0.0, -8.0),
            (-1.0, -16.0),
        ):
            pen.line(arc((x, y), 1.6, 1.6, 200, 380, 8), 0.45, strand(look))
    if style == "bob":
        pen.blob([(-12.0, -18.0), (12.0, -18.0), (12.4, -1.4), (-12.4, -1.4)], 1.4, hair)
        back_cover(pen, look, 2.2, -2.0, 0.0)
    if style == "long":
        pen.blob([(-12.4, -18.0), (12.4, -18.0), (12.0, 12.0), (-12.0, 12.0)], 1.8, hair)
        back_cover(pen, look, 2.2, -2.0, 0.0)
        dashes(pen, look, lambda x, y: abs(x) < 11.0 and -22.0 < y < 10.0, (0.0, -30.0), 22)
    if style in ("buzz", "short", "bob"):
        nape = {"buzz": -7.5, "short": -6.5, "bob": -3.5}[style]
        dashes(
            pen,
            look,
            lambda x, y: (x / 9.6) ** 2 + ((y - FACE[1]) / 10.4) ** 2 < 1 and y < nape,
            (1.0, -27.0),
            16,
        )
    if style in ("ponytail", "bun"):
        gather = (0.0, -15.0) if style == "ponytail" else (0.0, -20.4)
        dashes(
            pen,
            look,
            lambda x, y: (
                (x / 9.6) ** 2 + ((y - FACE[1]) / 10.4) ** 2 < 1
                and y < -7.0
                and math.dist((x, y), gather) > 4.5
            ),
            gather,
            16,
            towards=True,
        )
    if style == "ponytail":
        pen.capsule((0.0, -15.0), (0.4, -2.0), 3.2, 2.6, hair)
        pen.capsule((0.4, -2.0), (0.0, 6.0), 2.6, 1.4, hair)
        dashes(pen, look, lambda x, y: abs(x) < 1.6 and -12.0 < y < 4.0, (0.0, -30.0), 4)
        pen.blob([(-2.4, -15.6), (2.4, -15.6), (2.4, -14.4), (-2.4, -14.4)], 0.4, look.accent)
    if style == "bun":
        pen.ellipse((0.0, -20.4), 5.2, 4.8, hair)
        pen.line(arc((0.0, -20.4), 3.2, 3.0, 200, 340, 8), 0.45, strand(look))
        pen.line(arc((0.0, -20.4), 2.2, 2.0, 20, 160, 8), 0.45, strand(look))
    if "cap" in acc:
        cap(pen, look, side=False)
        pen.ellipse((0.0, -15.8), 3.0, 1.6, look.hair if look.hair_style != "bald" else look.skin)
        pen.line([(-3.0, -16.6), (3.0, -16.6)], 0.7, darker(look.accent))
    if "beanie" in acc:
        beanie(pen, look, FACE, side=False)
    if "headphones" in acc:
        pen.line(arc(FACE, rx + 2.4, ry + 2.8, 198, 342, 24), 1.5, look.accent)
        for side in (-1, 1):
            pen.capsule(
                (side * 12.0, -15.0), (side * 12.0, -11.2), 2.8, 2.8, darker(look.accent, 0.5)
            )
    if acc & {"glasses", "sunglasses"}:
        for side in (-1, 1):
            pen.line([(side * 9.2, -14.0), (side * 11.2, -13.4)], 0.5, INK)


# Torsos.


def side_depth(look: Look) -> float:
    return 17.0 * look.width


def front_width(look: Look) -> float:
    return 24.0 * look.width


def torso(pen: Pen, look: Look) -> None:
    h = side_depth(look) / 2
    acc = look.accessories
    if "backpack" in acc:
        pen.blob(
            [(-h - 6.0, -27.0), (-h + 1.0, -29.0), (-h + 1.5, -10.5), (-h - 5.6, -11.0)],
            1.0,
            look.accent,
        )
        pen.blob(
            [(-h - 6.6, -21.0), (-h - 4.4, -21.0), (-h - 4.4, -13.5), (-h - 6.6, -13.5)],
            0.5,
            darker(look.accent),
        )
    pen.blob(
        [
            (-h + 1.5, 2.0),
            (-h + 1.4, -26.0),
            (-h + 4.0, -30.6),
            (h - 4.4, -30.6),
            (h - 1.6, -27.0),
            (h - 1.0, -18.0),
            (h - 1.8, -9.0),
            (h - 1.5, 2.0),
        ],
        1.5,
        look.top,
    )
    pen.blob(
        [
            (-h + 0.6, -7.5),
            (h - 0.8, -7.5),
            (h - 0.4, 2.5),
            (h - 2.0, 4.8),
            (-h + 2.0, 4.8),
            (-h + 0.4, 2.5),
        ],
        0.8,
        look.bottom,
    )
    pen.poly(
        [(-h + 0.2, -8.4), (h - 0.8, -8.4), (h - 0.7, -6.8), (-h + 0.2, -6.8)],
        darker(look.bottom, 0.6),
    )
    pen.blob([(-1.6, -32.4), (4.0, -32.4), (3.4, -30.8), (-1.2, -30.8)], 0.4, darker(look.top))
    if "apron" in acc:
        pen.blob(
            [
                (-0.2, -26.0),
                (h + 0.6, -26.0),
                (h + 1.4, -7.0),
                (h + 2.2, 15.0),
                (-1.6, 15.0),
                (-1.2, -7.0),
            ],
            0.6,
            look.apron,
        )
        pen.poly(
            [(-h + 0.2, -9.4), (h + 1.6, -9.4), (h + 1.6, -7.8), (-h + 0.2, -7.8)],
            darker(look.apron, 0.85),
        )
        pen.line([(0.4, -26.0), (-0.8, -31.6)], 0.9, darker(look.apron, 0.85))
    if "backpack" in acc:
        pen.line(
            [(-h + 1.5, -28.4), (h - 4.6, -30.4), (h - 2.0, -23.0), (h - 2.4, -13.0)],
            1.7,
            darker(look.accent),
        )
    if "scarf" in acc:
        pen.ellipse((0.6, -31.6), h + 1.4, 3.0, look.accent)
        pen.capsule((-h + 0.6, -30.6), (-h - 1.8, -19.0), 1.9, 1.5, darker(look.accent, 0.88))


def front_torso(pen: Pen, look: Look) -> list[Pt]:
    h = front_width(look) / 2
    outline = [
        (-h + 2.4, -29.4),
        (-3.6, -30.8),
        (3.6, -30.8),
        (h - 2.4, -29.4),
        (h - 1.8, -16.0),
        (h - 2.6, -7.5),
        (h - 2.4, 3.0),
        (-h + 2.4, 3.0),
        (-h + 2.6, -7.5),
        (-h + 1.8, -16.0),
    ]
    pen.blob(outline, 2.0, look.top)
    pen.poly(
        [
            (-h + 0.8, -7.6),
            (h - 0.8, -7.6),
            (h - 0.6, 5.0),
            (1.4, 5.0),
            (0.0, 2.4),
            (-1.4, 5.0),
            (-h + 0.6, 5.0),
        ],
        look.bottom,
    )
    pen.poly(
        [(-h + 0.6, -8.4), (h - 0.6, -8.4), (h - 0.6, -6.8), (-h + 0.6, -6.8)],
        darker(look.bottom, 0.6),
    )
    return outline


def torso_front(pen: Pen, look: Look) -> None:
    h = front_width(look) / 2
    acc = look.accessories
    front_torso(pen, look)
    pen.poly(arc((0.0, -31.8), 4.4, 2.8, 0, 180, 16), darker(look.top))
    pen.line([(0.0, -27.0), (0.0, -9.0)], 0.4, darker(look.top, 0.88))
    if "apron" in acc:
        w = 6.4 * look.width
        pen.blob([(-w, -24.0), (w, -24.0), (w, -9.0), (-w, -9.0)], 0.6, look.apron)
        pen.blob(
            [(-w - 3.0, -9.0), (w + 3.0, -9.0), (w + 4.2, 15.0), (-w - 4.2, 15.0)], 0.6, look.apron
        )
        pen.poly(
            [(-h + 0.4, -9.6), (h - 0.4, -9.6), (h - 0.4, -8.0), (-h + 0.4, -8.0)],
            darker(look.apron, 0.85),
        )
        pen.blob([(-3.6, -3.0), (3.6, -3.0), (3.6, 2.6), (-3.6, 2.6)], 0.4, darker(look.apron, 0.9))
        for side in (-1, 1):
            pen.line(
                [(side * (w - 0.4), -24.0), (side * 3.4, -31.0)], 0.9, darker(look.apron, 0.85)
            )
    if "backpack" in acc:
        for side in (-1, 1):
            pen.line(
                [(side * (h - 5.6), -30.6), (side * (h - 4.6), -20.0), (side * (h - 3.8), -11.0)],
                1.9,
                darker(look.accent),
            )
    if "scarf" in acc:
        pen.ellipse((0.0, -31.0), 8.6, 3.2, look.accent)
        pen.capsule((-3.0, -30.0), (-4.2, -18.0), 2.0, 1.6, darker(look.accent, 0.88))
        pen.capsule((-0.6, -30.0), (-0.6, -20.0), 1.8, 1.5, darker(look.accent, 0.94))


def torso_back(pen: Pen, look: Look) -> None:
    h = front_width(look) / 2
    acc = look.accessories
    front_torso(pen, look)
    pen.line([(-4.2, -31.0), (4.2, -31.0)], 0.9, darker(look.top))
    pen.line(arc((0.0, -32.0), h - 3.0, 5.0, 25, 155, 16), 0.45, darker(look.top, 0.88))
    for side in (-1, 1):
        pen.blob(
            [(side * 3.0, -4.4), (side * 7.6, -4.4), (side * 7.4, 0.8), (side * 3.2, 0.8)],
            0.4,
            darker(look.bottom, 0.84),
        )
    if "apron" in acc:
        for side in (-1, 1):
            pen.line([(side * (h - 4.0), -30.0), (-side * (h - 5.0), -9.0)], 1.3, look.apron)
        pen.poly([(-h + 0.4, -9.6), (h - 0.4, -9.6), (h - 0.4, -7.8), (-h + 0.4, -7.8)], look.apron)
        pen.ellipse((-2.6, -8.6), 2.6, 1.8, darker(look.apron, 0.9))
        pen.ellipse((2.6, -8.6), 2.6, 1.8, darker(look.apron, 0.9))
        pen.capsule((-0.6, -8.0), (-1.6, -2.0), 0.9, 0.8, look.apron)
        pen.capsule((0.6, -8.0), (1.8, -2.4), 0.9, 0.8, look.apron)
        pen.ellipse((0.0, -8.6), 1.2, 1.2, look.apron)
    if "backpack" in acc:
        w = 8.2 * look.width
        pen.blob([(-w, -27.0), (w, -27.0), (w + 0.4, -6.0), (-w - 0.4, -6.0)], 1.6, look.accent)
        pen.blob([(-w, -27.4), (w, -27.4), (w, -21.0), (-w, -21.0)], 1.4, darker(look.accent))
        pen.blob(
            [(-w + 2.6, -15.0), (w - 2.6, -15.0), (w - 2.6, -8.4), (-w + 2.6, -8.4)],
            0.8,
            darker(look.accent, 0.88),
        )
        pen.line(arc((0.0, -28.6), 2.4, 1.8, 180, 360, 8), 0.8, darker(look.accent, 0.6))
    if "scarf" in acc:
        pen.ellipse((0.0, -31.0), 8.6, 3.2, look.accent)


# Limbs, the same from every side.


def upper_arm(pen: Pen, look: Look) -> None:
    w = look.width**0.5
    pen.capsule((0.0, 0.0), (0.0, UPPER_ARM), 3.4 * w, 2.9 * w, look.top)
    pen.poly(
        [
            (-2.9 * w, UPPER_ARM - 1.6),
            (2.9 * w, UPPER_ARM - 1.6),
            (2.8 * w, UPPER_ARM - 0.2),
            (-2.8 * w, UPPER_ARM - 0.2),
        ],
        darker(look.top, 0.85),
    )


def lower_arm(pen: Pen, look: Look) -> None:
    w = look.width**0.5
    pen.capsule((0.0, 0.0), (0.0, FOREARM), 2.6 * w, 2.2 * w, look.skin)
    pen.ellipse((0.4, FOREARM + 2.0), 2.8, 3.2, look.skin)


def upper_leg(pen: Pen, look: Look) -> None:
    pen.capsule((0.0, 0.0), (0.0, THIGH), 4.4 * look.width**0.6, 3.6 * look.width**0.5, look.bottom)


def lower_leg(pen: Pen, look: Look) -> None:
    w = look.width**0.5
    pen.capsule((0.0, 0.0), (0.0, SHIN), 3.6 * w, 3.0 * w, look.bottom)
    pen.poly(
        [
            (-3.3 * w, SHIN - 3.0),
            (3.3 * w, SHIN - 3.0),
            (3.2 * w, SHIN - 1.4),
            (-3.2 * w, SHIN - 1.4),
        ],
        darker(look.bottom, 0.85),
    )


def shoe(pen: Pen, look: Look) -> None:
    pen.poly(
        arc((5.0, 1.6), 4.4, 3.4, -90, 0, 10)
        + [(9.4, 4.0), (-4.0, 4.0), (-4.0, 0.0), (-3.0, -1.8)],
        look.shoe,
    )
    pen.blob([(-4.0, 3.6), (9.4, 3.6), (9.4, 4.4), (-4.0, 4.4)], 0.4, darker(look.shoe, 0.55))


def shoe_front(pen: Pen, look: Look) -> None:
    w = 4.0 * look.width**0.3
    pen.ellipse((0.0, 1.8), w, 2.8, look.shoe)
    pen.blob([(-w, 3.6), (w, 3.6), (w, 4.4), (-w, 4.4)], 0.4, darker(look.shoe, 0.55))


@dataclass(frozen=True)
class Shape:
    draw: Callable[[Pen, Look], None]
    box: tuple[float, float, float, float]
    joints: Callable[[Look], dict[str, Pt]] = field(default=lambda look: {})


def side_joints(look: Look) -> dict[str, Pt]:
    return {"neck": (0.8, NECK), "shoulder": (-0.4, SHOULDER), "hip": (0.0, 0.0)}


def front_joints(look: Look) -> dict[str, Pt]:
    h = front_width(look) / 2
    hips = 5.0 * look.width**0.6
    return {
        "neck": (0.0, NECK),
        "shoulder_left": (-(h - 3.4), SHOULDER),
        "shoulder_right": (h - 3.4, SHOULDER),
        "hip_left": (-hips, 0.0),
        "hip_right": (hips, 0.0),
    }


HEAD_BOX = (-22.0, -36.0, 22.0, 18.0)
TORSO_BOX = (-24.0, -38.0, 24.0, 20.0)

SHAPES: dict[str, Shape] = {
    "head": Shape(head, HEAD_BOX),
    "torso": Shape(torso, TORSO_BOX, side_joints),
    "upper_arm": Shape(
        upper_arm, (-5.0, -5.0, 5.0, 18.0), lambda look: {"elbow": (0.0, UPPER_ARM)}
    ),
    "lower_arm": Shape(
        lower_arm, (-5.0, -5.0, 5.0, 18.0), lambda look: {"hand": (0.4, FOREARM + 2.0)}
    ),
    "upper_leg": Shape(upper_leg, (-6.0, -6.0, 6.0, 24.0), lambda look: {"knee": (0.0, THIGH)}),
    "lower_leg": Shape(lower_leg, (-5.0, -5.0, 5.0, 22.0), lambda look: {"ankle": (0.0, SHIN)}),
    "shoe": Shape(shoe, (-6.0, -4.0, 11.0, 6.0)),
    "head_front": Shape(head_front, HEAD_BOX),
    "torso_front": Shape(torso_front, TORSO_BOX, front_joints),
    "head_back": Shape(head_back, HEAD_BOX),
    "torso_back": Shape(torso_back, TORSO_BOX, front_joints),
    "shoe_front": Shape(shoe_front, (-7.0, -4.0, 7.0, 6.0)),
}
