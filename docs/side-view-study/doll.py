"""Paper-doll residents: part shapes from `Appearance`, an exploded parts sheet for FLUX to paint
over, and a 2D rig that poses the painted parts. Units are 1/100 of a standing figure's height."""

import math
from collections.abc import Iterable
from dataclasses import dataclass, field

from PIL import Image, ImageChops, ImageDraw, ImageFilter

Pt = tuple[float, float]
RGB = tuple[int, int, int]

SUPERSAMPLE = 3
BUILD = {"slim": 0.86, "average": 1.0, "broad": 1.2}
ACCENTS = {"amber": "#feae34", "cyan": "#2ce8f5", "red": "#e43b44", "lime": "#63c74d"}
APRON_ON_LIGHT = "#733e39"
APRON = "#ead4aa"
SKULL = (0.5, -13.0)
SKULL_R = (9.3, 10.0)
PIECES = ("head", "torso", "upper_arm", "lower_arm", "upper_leg", "lower_leg", "shoe")


def rgb(hex_colour: str) -> RGB:
    h = hex_colour.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def mix(a: RGB, b: RGB, t: float) -> RGB:
    return (
        round(a[0] + (b[0] - a[0]) * t),
        round(a[1] + (b[1] - a[1]) * t),
        round(a[2] + (b[2] - a[2]) * t),
    )


def darker(c: RGB, f: float = 0.78) -> RGB:
    return round(c[0] * f), round(c[1] * f), round(c[2] * f)


def luminance(c: RGB) -> float:
    return (0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]) / 255


def arc(c: Pt, rx: float, ry: float, t0: float, t1: float, n: int = 24) -> list[Pt]:
    return [
        (
            c[0] + rx * math.cos(math.radians(t0 + (t1 - t0) * i / n)),
            c[1] + ry * math.sin(math.radians(t0 + (t1 - t0) * i / n)),
        )
        for i in range(n + 1)
    ]


@dataclass
class Look:
    """The colours and options a resident's paper doll is cut from."""

    skin: RGB
    hair: RGB
    top: RGB
    bottom: RGB
    shoe: RGB
    accent: RGB
    apron: RGB
    hair_style: str
    width: float
    accessories: tuple[str, ...]

    @classmethod
    def of(cls, appearance, seed: str) -> "Look":
        from simile.characters.palette import accent

        top = rgb(appearance.top_colour)
        return cls(
            skin=rgb(appearance.skin),
            hair=rgb(appearance.hair_colour),
            top=top,
            bottom=rgb(appearance.bottom_colour),
            shoe=rgb(appearance.shoe_colour),
            accent=rgb(ACCENTS.get(accent(appearance, seed), "#feae34")),
            apron=rgb(APRON_ON_LIGHT if luminance(top) > 0.6 else APRON),
            hair_style=appearance.hair_style.value,
            width=BUILD[appearance.build.value],
            accessories=tuple(a.value for a in appearance.accessories),
        )


class Pen:
    """Draws shapes given in units onto a supersampled RGBA layer covering `box`."""

    def __init__(self, box: tuple[float, float, float, float], scale: float) -> None:
        self.box = box
        self.scale = scale
        self.k = scale * SUPERSAMPLE
        w = math.ceil((box[2] - box[0]) * scale)
        h = math.ceil((box[3] - box[1]) * scale)
        self.size = (w, h)
        self.layer = Image.new("RGBA", (w * SUPERSAMPLE, h * SUPERSAMPLE), (0, 0, 0, 0))
        self.draw = ImageDraw.Draw(self.layer)

    def _p(self, p: Pt) -> tuple[float, float]:
        return (p[0] - self.box[0]) * self.k, (p[1] - self.box[1]) * self.k

    def px(self, p: Pt) -> tuple[float, float]:
        return (p[0] - self.box[0]) * self.scale, (p[1] - self.box[1]) * self.scale

    def poly(self, pts: Iterable[Pt], fill: RGB) -> None:
        self.draw.polygon([self._p(p) for p in pts], fill=(*fill, 255))

    def ellipse(self, c: Pt, rx: float, ry: float, fill: RGB) -> None:
        x, y = self._p(c)
        self.draw.ellipse(
            (x - rx * self.k, y - ry * self.k, x + rx * self.k, y + ry * self.k), fill=(*fill, 255)
        )

    def line(self, pts: list[Pt], width: float, fill: RGB) -> None:
        self.draw.line([self._p(p) for p in pts], fill=(*fill, 255), width=round(width * self.k))
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


@dataclass
class Shape:
    """A part in units: how to draw it, its bounds, its pivot and where its children attach."""

    box: tuple[float, float, float, float]
    joints: dict[str, Pt] = field(default_factory=dict)


def hair_shell(pen: Pen, look: Look, dr: float, t_front: float, t_back: float) -> None:
    outer = arc(SKULL, SKULL_R[0] + dr, SKULL_R[1] + dr, t_front, t_back, 32)
    back = arc(SKULL, SKULL_R[0] - 0.3, SKULL_R[1] - 0.3, t_back, t_back, 1)[0]
    front = arc(SKULL, SKULL_R[0] - 0.3, SKULL_R[1] - 0.3, t_front, t_front, 1)[0]
    pen.poly([*outer, back, (-2.5, -15.8), (3.0, front[1] - 0.2), front], look.hair)


def draw_head(pen: Pen, look: Look) -> None:
    style, acc = look.hair_style, look.accessories
    if style == "long":
        pen.poly(
            arc(SKULL, SKULL_R[0] + 2.0, SKULL_R[1] + 2.0, -100, -200, 16)
            + [(-11.0, 8.0), (-3.0, 9.0), (-1.0, -6.0)],
            look.hair,
        )
    if style == "ponytail":
        pen.capsule((-8.5, -18.0), (-13.5, -9.0), 2.6, 2.2, look.hair)
        pen.capsule((-13.5, -9.0), (-13.0, 0.5), 2.2, 1.2, look.hair)
    if style == "bun":
        pen.ellipse((-7.5, -21.5), 4.2, 4.0, look.hair)
    if "headphones" in acc:
        pen.line([(-1.5, -15.0), (-1.2, -21.0), (-0.6, -25.3)], 1.3, look.accent)
    pen.capsule((0.6, -1.0), (1.0, -5.5), 2.7, 2.7, look.skin)
    pen.ellipse(SKULL, *SKULL_R, look.skin)
    pen.ellipse((5.2, -5.6), 4.2, 2.9, look.skin)
    pen.ellipse((9.4, -11.6), 1.7, 1.9, look.skin)
    pen.ellipse((-1.5, -12.0), 1.8, 2.6, darker(look.skin, 0.9))
    pen.ellipse((5.2, -9.6), 1.6, 1.2, mix(look.skin, (224, 110, 110), 0.45))
    pen.ellipse((6.2, -13.8), 0.85, 1.05, (40, 30, 40))
    pen.line([(7.2, -7.6), (8.4, -7.9)], 0.45, darker(look.skin, 0.55))
    brow = look.hair if style != "bald" else darker(look.skin, 0.7)
    pen.line([(4.9, -16.6), (7.3, -16.9)], 0.7, brow)
    shells = {
        "buzz": (0.5, -38, -192),
        "short": (1.5, -30, -200),
        "bob": (2.0, -28, -185),
        "long": (2.0, -28, -195),
        "ponytail": (1.3, -32, -195),
        "bun": (1.3, -32, -195),
    }
    if style in shells:
        hair_shell(pen, look, *shells[style])
    if style == "short":
        pen.ellipse((5.0, -20.6), 3.6, 2.0, look.hair)
    if style == "bob":
        pen.poly(
            [(-9.6, -15.0), (-11.3, -14.0), (-10.8, -4.0), (-3.0, -4.5), (-2.6, -13.0)], look.hair
        )
        pen.ellipse((5.5, -20.6), 4.2, 2.4, look.hair)
    if style == "curly":
        for t in range(-20, -230, -21):
            x = SKULL[0] + (SKULL_R[0] + 1.0) * math.cos(math.radians(t))
            y = SKULL[1] + (SKULL_R[1] + 1.0) * math.sin(math.radians(t))
            pen.ellipse((x, y), 3.0, 3.0, look.hair)
        hair_shell(pen, look, 1.0, -30, -225)
    if "cap" in acc:
        pen.poly(arc(SKULL, SKULL_R[0] + 1.6, SKULL_R[1] + 1.8, -12, -192, 28), look.accent)
        pen.poly([(4.0, -16.4), (15.0, -15.6), (15.0, -14.4), (4.0, -14.6)], darker(look.accent))
        pen.ellipse((0.3, -24.7), 1.0, 0.8, darker(look.accent))
    if "beanie" in acc:
        pen.poly(arc(SKULL, SKULL_R[0] + 2.0, SKULL_R[1] + 2.4, -18, -198, 28), look.accent)
        pen.poly(
            arc(SKULL, SKULL_R[0] + 2.2, SKULL_R[1] + 2.2, -16, -34, 6)
            + arc(SKULL, SKULL_R[0] + 2.2, SKULL_R[1] + 2.2, -186, -200, 4),
            darker(look.accent),
        )
    if "headphones" in acc:
        pen.capsule((-1.7, -14.0), (-1.7, -10.0), 2.4, 2.4, darker(look.accent, 0.5))
    if "glasses" in acc:
        pen.line([(4.0, -14.6), (-0.4, -13.6)], 0.55, (40, 30, 40))
        x, y = 6.6, -13.9
        for t in range(0, 360, 30):
            a, b = math.radians(t), math.radians(t + 30)
            pen.line(
                [
                    (x + 2.2 * math.cos(a), y + 2.0 * math.sin(a)),
                    (x + 2.2 * math.cos(b), y + 2.0 * math.sin(b)),
                ],
                0.55,
                (40, 30, 40),
            )
    if "sunglasses" in acc:
        pen.line([(4.0, -14.6), (-0.4, -13.6)], 0.6, (30, 26, 34))
        pen.ellipse((7.0, -13.8), 2.7, 1.9, (30, 26, 34))


def head_shape() -> Shape:
    return Shape(box=(-17.0, -27.0, 17.0, 10.0))


def torso_w(look: Look) -> float:
    return 13.0 * look.width


def draw_torso(pen: Pen, look: Look) -> None:
    w = torso_w(look) / 2
    acc = look.accessories
    if "backpack" in acc:
        pen.poly(
            [(-w - 6.0, -25.0), (-w + 1.0, -27.5), (-w + 1.5, -9.0), (-w - 5.5, -9.5)],
            look.accent,
        )
        pen.poly(
            [(-w - 6.6, -20.0), (-w - 4.0, -20.0), (-w - 4.0, -12.0), (-w - 6.6, -12.0)],
            darker(look.accent),
        )
    body = [
        (-w, 1.0),
        (-w + 0.2, -24.0),
        (-w + 2.2, -29.6),
        (w - 3.0, -30.0),
        (w - 0.2, -26.5),
        (w + 0.3, -18.0),
        (w - 0.6, -10.0),
        (w, 1.0),
    ]
    pen.poly(body, look.top)
    pen.poly(
        [(-w, -6.0), (w - 0.4, -6.0), (w, 1.0), (w - 1.5, 4.0), (-w + 1.0, 4.0), (-w, 1.0)],
        look.bottom,
    )
    pen.poly(
        [(-w + 0.1, -6.8), (w - 0.5, -6.8), (w - 0.45, -5.6), (-w + 0.1, -5.6)],
        darker(look.bottom, 0.6),
    )
    pen.poly([(-1.8, -30.4), (3.6, -30.4), (3.0, -28.6), (-1.4, -28.6)], darker(look.top))
    if "apron" in acc:
        pen.poly(
            [
                (-0.5, -24.0),
                (w + 0.9, -24.0),
                (w + 1.6, -6.0),
                (w + 2.4, 14.0),
                (-2.0, 14.0),
                (-1.5, -6.0),
            ],
            look.apron,
        )
        pen.poly(
            [(-w, -8.6), (w + 1.6, -8.6), (w + 1.6, -7.2), (-w, -7.2)], darker(look.apron, 0.85)
        )
        pen.line([(0.0, -24.0), (-1.0, -29.5)], 0.8, darker(look.apron, 0.85))
    if "backpack" in acc:
        pen.line(
            [(-w + 1.5, -27.0), (w - 3.5, -28.5), (w - 1.5, -22.0), (w - 1.8, -13.0)],
            1.5,
            darker(look.accent),
        )
    if "scarf" in acc:
        pen.ellipse((0.6, -29.8), w + 1.0, 2.6, look.accent)
        pen.capsule((-w + 0.5, -29.0), (-w - 1.6, -19.0), 1.7, 1.4, darker(look.accent, 0.88))


def torso_shape(look: Look) -> Shape:
    w = torso_w(look) / 2
    return Shape(
        box=(-w - 8.0, -33.0, w + 4.5, 16.0),
        joints={"neck": (0.8, -30.0), "shoulder": (-0.4, -26.5), "hip": (0.0, -1.0)},
    )


def draw_upper_arm(pen: Pen, look: Look) -> None:
    pen.capsule((0.0, 0.0), (0.0, 13.0), 2.9 * look.width**0.5, 2.4 * look.width**0.5, look.top)
    pen.poly([(-2.6, 10.6), (2.6, 10.6), (2.5, 12.0), (-2.5, 12.0)], darker(look.top, 0.85))


def draw_lower_arm(pen: Pen, look: Look) -> None:
    pen.capsule((0.0, 0.0), (0.0, 11.0), 2.1 * look.width**0.5, 1.8 * look.width**0.5, look.skin)
    pen.ellipse((0.5, 12.8), 2.3, 2.7, look.skin)


def draw_upper_leg(pen: Pen, look: Look) -> None:
    pen.capsule((0.0, 0.0), (0.0, 22.0), 3.9 * look.width**0.6, 3.1 * look.width**0.5, look.bottom)


def draw_lower_leg(pen: Pen, look: Look) -> None:
    pen.capsule((0.0, 0.0), (0.0, 19.5), 3.1 * look.width**0.5, 2.6 * look.width**0.5, look.bottom)
    pen.poly([(-2.9, 16.5), (2.9, 16.5), (2.9, 18.0), (-2.9, 18.0)], darker(look.bottom, 0.85))


def draw_shoe(pen: Pen, look: Look) -> None:
    pen.poly(
        arc((4.4, 1.6), 3.4, 2.8, -90, 0, 8) + [(7.8, 3.6), (-3.4, 3.6), (-3.4, 0.2), (-2.6, -1.3)],
        look.shoe,
    )
    pen.poly([(-3.5, 3.0), (7.9, 3.0), (7.9, 4.2), (-3.5, 4.2)], darker(look.shoe, 0.55))


SHAPES = {
    "head": (draw_head, lambda look: head_shape()),
    "torso": (draw_torso, torso_shape),
    "upper_arm": (
        draw_upper_arm,
        lambda look: Shape((-4.0, -4.0, 4.0, 16.5), {"elbow": (0.0, 13.0)}),
    ),
    "lower_arm": (draw_lower_arm, lambda look: Shape((-4.0, -3.5, 4.5, 16.5), {})),
    "upper_leg": (
        draw_upper_leg,
        lambda look: Shape((-5.5, -5.0, 5.5, 26.0), {"knee": (0.0, 22.0)}),
    ),
    "lower_leg": (
        draw_lower_leg,
        lambda look: Shape((-4.5, -4.0, 4.5, 22.5), {"ankle": (0.0, 19.5)}),
    ),
    "shoe": (draw_shoe, lambda look: Shape((-4.5, -2.5, 9.0, 5.5), {})),
}


@dataclass
class Piece:
    """A cut-out part: RGBA, its pivot and child joints in pixels."""

    image: Image.Image
    pivot: tuple[float, float]
    joints: dict[str, tuple[float, float]]


def flat_piece(name: str, look: Look, scale: float) -> Piece:
    draw, shape_of = SHAPES[name]
    shape = shape_of(look)
    pen = Pen(shape.box, scale)
    draw(pen, look)
    return Piece(pen.image(), pen.px((0.0, 0.0)), {k: pen.px(v) for k, v in shape.joints.items()})


def flat_pieces(look: Look, scale: float) -> dict[str, Piece]:
    return {name: flat_piece(name, look, scale) for name in PIECES}


def trim(piece: Piece, pad: int = 2) -> Piece:
    box = piece.image.getchannel("A").getbbox()
    if box is None:
        return piece
    x0, y0 = max(0, box[0] - pad), max(0, box[1] - pad)
    x1, y1 = min(piece.image.width, box[2] + pad), min(piece.image.height, box[3] + pad)

    def shift(p: tuple[float, float]) -> tuple[float, float]:
        return p[0] - x0, p[1] - y0

    return Piece(
        piece.image.crop((x0, y0, x1, y1)),
        shift(piece.pivot),
        {k: shift(v) for k, v in piece.joints.items()},
    )


def sheet_layout(
    pieces: dict[str, Piece], size: tuple[int, int], gap: int = 48
) -> dict[str, tuple[int, int]]:
    """Top-left corners that spread the pieces over a sheet in rows, centred, with gaps."""
    order = ["head", "torso", "upper_leg", "lower_leg", "upper_arm", "lower_arm", "shoe"]
    rows: list[list[str]] = [[]]
    width = gap
    for name in order:
        w = pieces[name].image.width + gap
        if width + w > size[0] and rows[-1]:
            rows.append([])
            width = gap
        rows[-1].append(name)
        width += w
    heights = [max(pieces[n].image.height for n in row) for row in rows]
    total = sum(heights) + gap * (len(rows) - 1)
    y = (size[1] - total) // 2
    spots: dict[str, tuple[int, int]] = {}
    for row, h in zip(rows, heights, strict=True):
        row_w = sum(pieces[n].image.width for n in row) + gap * (len(row) - 1)
        x = (size[0] - row_w) // 2
        for name in row:
            spots[name] = (x, y + (h - pieces[name].image.height) // 2)
            x += pieces[name].image.width + gap
        y += h + gap
    return spots


SHEET = (1024, 768)
SHEET_SCALE = 9.0


def sheet_pieces(look: Look) -> tuple[dict[str, Piece], dict[str, tuple[int, int]]]:
    pieces = {k: trim(v) for k, v in flat_pieces(look, SHEET_SCALE).items()}
    return pieces, sheet_layout(pieces, SHEET)


def sheet(
    pieces: dict[str, Piece], spots: dict[str, tuple[int, int]], size: tuple[int, int]
) -> Image.Image:
    out = Image.new("RGB", size, (246, 244, 240))
    for name, (x, y) in spots.items():
        out.paste(pieces[name].image, (x, y), pieces[name].image)
    return out


def cut_from_sheet(
    painted: Image.Image,
    flat: dict[str, Piece],
    spots: dict[str, tuple[int, int]],
    look: Look,
    keep_colour: float = 0.9,
) -> dict[str, Piece]:
    """The painted pieces, cut out along the flat pieces' outlines and pulled `keep_colour` of
    the way back to their flat colours, so the resident keeps their `Appearance`."""
    out = {}
    for name, piece in flat.items():
        x, y = spots[name]
        box = (x, y, x + piece.image.width, y + piece.image.height)
        crop = painted.crop(box).convert("RGB")
        alpha = piece.image.getchannel("A").filter(ImageFilter.MinFilter(3))
        alpha = alpha.filter(ImageFilter.GaussianBlur(0.6))
        crop = match_colour(crop, piece.image, keep_colour)
        crop.putalpha(alpha)
        out[name] = Piece(crop, piece.pivot, piece.joints)
    return out


def match_colour(painted: Image.Image, flat: Image.Image, amount: float) -> Image.Image:
    """Scale each flat-colour region of `painted` so its mean moves `amount` of the way to the
    flat colour, keeping the painted texture and shading. Edge pixels join the nearest region."""
    import numpy as np

    p = np.asarray(painted, dtype=np.float32)
    f = np.asarray(flat.convert("RGBA"), dtype=np.float32)
    opaque = f[..., 3] > 0
    colours, counts = np.unique(f[opaque][:, :3], axis=0, return_counts=True)
    main = colours[counts >= 30]
    nearest = np.argmin(((f[..., None, :3] - main[None, None]) ** 2).sum(axis=3), axis=2)
    out = p.copy()
    for i, target in enumerate(main):
        region = opaque & (nearest == i)
        core = region & (np.abs(f[..., :3] - target).max(axis=2) < 1)
        mean = p[core].mean(axis=0)
        gain = np.clip(np.maximum(target, 8) / np.maximum(mean, 8), 0.15, 4.0)
        out[region] = p[region] * (1 + (gain - 1) * amount)
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))


@dataclass
class Pose:
    """Joint angles in degrees: positive swings a limb forward (towards +x)."""

    lean: float = 0.0
    head: float = 0.0
    near_thigh: float = 0.0
    near_knee: float = 0.0
    near_foot: float = 0.0
    far_thigh: float = 0.0
    far_knee: float = 0.0
    far_foot: float = 0.0
    near_shoulder: float = 0.0
    near_elbow: float = 0.0
    far_shoulder: float = 0.0
    far_elbow: float = 0.0
    rise: float = 0.0


def walk_pose(phase: float) -> Pose:
    """A walk cycle at `phase` in [0, 1)."""
    t = 2 * math.pi * phase

    def leg(t: float) -> tuple[float, float, float]:
        thigh = 24 * math.sin(t)
        knee = 8 + 34 * max(0.0, math.sin(t + 1.9)) ** 1.5
        foot = -thigh + knee + (18 * max(0.0, -math.cos(t + 0.4)) - 6 * max(0.0, math.cos(t)))
        return thigh, knee, foot

    nt, nk, nf = leg(t)
    ft, fk, ff = leg(t + math.pi)
    return Pose(
        lean=3.0,
        head=-2.0,
        near_thigh=nt,
        near_knee=nk,
        near_foot=nf,
        far_thigh=ft,
        far_knee=fk,
        far_foot=ff,
        near_shoulder=-22 * math.sin(t),
        near_elbow=14 + 10 * max(0.0, -math.sin(t)),
        far_shoulder=22 * math.sin(t),
        far_elbow=14 + 10 * max(0.0, math.sin(t)),
    )


JUMP = Pose(
    lean=14.0,
    head=-8.0,
    near_thigh=82.0,
    near_knee=105.0,
    near_foot=12.0,
    far_thigh=-38.0,
    far_knee=78.0,
    far_foot=-25.0,
    near_shoulder=105.0,
    near_elbow=15.0,
    far_shoulder=-70.0,
    far_elbow=25.0,
)

STAND = Pose(
    near_shoulder=4.0, near_elbow=8.0, far_shoulder=-4.0, far_elbow=8.0, far_thigh=-3, near_thigh=3
)


def rotate(v: Pt, deg: float) -> Pt:
    a = math.radians(deg)
    return v[0] * math.cos(a) + v[1] * math.sin(a), -v[0] * math.sin(a) + v[1] * math.cos(a)


def add(a: Pt, b: Pt) -> Pt:
    return a[0] + b[0], a[1] + b[1]


def sub(a: Pt, b: Pt) -> Pt:
    return a[0] - b[0], a[1] - b[1]


@dataclass
class Placed:
    piece: Piece
    at: Pt
    angle: float
    shade: float


def place(pieces: dict[str, Piece], pose: Pose) -> list[Placed]:
    """Every piece's pivot position and angle, back to front, with the hip at the origin."""
    torso = pieces["torso"]
    hip = torso.joints["hip"]

    def joint(parent: Piece, at: Pt, angle: float, name: str) -> Pt:
        return add(at, rotate(sub(parent.joints[name], parent.pivot), angle))

    torso_at = rotate(sub(torso.pivot, hip), pose.lean)
    shoulder = joint(torso, torso_at, pose.lean, "shoulder")
    neck = joint(torso, torso_at, pose.lean, "neck")
    hip_at = (0.0, 0.0)

    def leg(thigh: float, knee: float, foot: float, shade: float) -> list[Placed]:
        ul, ll = pieces["upper_leg"], pieces["lower_leg"]
        knee_at = add(hip_at, rotate(sub(ul.joints["knee"], ul.pivot), thigh))
        ankle_at = add(knee_at, rotate(sub(ll.joints["ankle"], ll.pivot), thigh - knee))
        return [
            Placed(ul, hip_at, thigh, shade),
            Placed(ll, knee_at, thigh - knee, shade),
            Placed(pieces["shoe"], ankle_at, thigh - knee + foot, shade),
        ]

    def arm(shoulder_angle: float, elbow: float, shade: float) -> list[Placed]:
        ua = pieces["upper_arm"]
        a = pose.lean + shoulder_angle
        elbow_at = add(shoulder, rotate(sub(ua.joints["elbow"], ua.pivot), a))
        return [
            Placed(ua, shoulder, a, shade),
            Placed(pieces["lower_arm"], elbow_at, a + elbow, shade),
        ]

    far = 0.8
    return [
        *arm(pose.far_shoulder, pose.far_elbow, far),
        *leg(pose.far_thigh, pose.far_knee, pose.far_foot, far),
        *leg(pose.near_thigh, pose.near_knee, pose.near_foot, 1.0),
        Placed(torso, torso_at, pose.lean, 1.0),
        Placed(pieces["head"], neck, pose.lean + pose.head, 1.0),
        *arm(pose.near_shoulder, pose.near_elbow, 1.0),
    ]


def padded(piece: Piece) -> tuple[Image.Image, Pt]:
    """The piece on a square canvas centred on its pivot, so it rotates without clipping."""
    w, h = piece.image.size
    px, py = piece.pivot
    r = math.ceil(max(math.hypot(x - px, y - py) for x in (0, w) for y in (0, h))) + 2
    canvas = Image.new("RGBA", (2 * r, 2 * r), (0, 0, 0, 0))
    canvas.paste(piece.image, (round(r - px), round(r - py)))
    return canvas, (r, r)


def shaded(image: Image.Image, f: float) -> Image.Image:
    if f >= 1.0:
        return image
    r, g, b, a = image.split()
    rgb_ = Image.merge("RGB", (r, g, b)).point(lambda v: round(v * f))
    return Image.merge("RGBA", (*rgb_.split(), a))


def lowest_point(placed: list[Placed]) -> float:
    lowest = -1e9
    for p in placed:
        alpha = p.piece.image.getchannel("A")
        box = alpha.getbbox()
        if box is None:
            continue
        for x, y in ((box[0], box[3]), (box[2], box[3]), (box[0], box[1]), (box[2], box[1])):
            v = rotate((x - p.piece.pivot[0], y - p.piece.pivot[1]), p.angle)
            lowest = max(lowest, p.at[1] + v[1])
    return lowest


def render(
    pieces: dict[str, Piece],
    pose: Pose,
    size: tuple[int, int],
    feet: tuple[float, float],
    shadow: float = 0.35,
    plant: bool = True,
) -> Image.Image:
    """The posed doll on a transparent `size` frame, with its lowest point at `feet` when
    `plant`, else with the hip at `feet` raised by the standing leg length. Each piece casts a
    soft shadow onto the pieces already drawn behind it."""
    placed = place(pieces, pose)
    origin_y = feet[1] - lowest_point(placed if plant else place(pieces, STAND))
    origin = (feet[0], origin_y)
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    unit = pieces["upper_leg"].image.height / 31.0
    for p in placed:
        img, centre = padded(p.piece)
        img = shaded(img.rotate(p.angle, resample=Image.Resampling.BICUBIC, center=centre), p.shade)
        img = cut_edges(img, max(1, round(unit * 0.35)))
        x = round(origin[0] + p.at[0] - centre[0])
        y = round(origin[1] + p.at[1] - centre[1])
        if shadow > 0:
            layer = Image.new("RGBA", size, (0, 0, 0, 0))
            dark = Image.new("RGBA", img.size, (20, 14, 10, 255))
            dark.putalpha(img.getchannel("A").point(lambda v: round(v * shadow)))
            dark = dark.filter(ImageFilter.GaussianBlur(unit * 0.6))
            layer.paste(dark, (x + round(unit * 0.5), y + round(unit * 0.7)))
            mask = ImageChops.multiply(layer.getchannel("A"), out.getchannel("A"))
            layer.putalpha(mask)
            out = Image.alpha_composite(out, layer)
        layer = Image.new("RGBA", size, (0, 0, 0, 0))
        layer.paste(img, (x, y))
        out = Image.alpha_composite(out, layer)
    return out


def cut_edges(image: Image.Image, width: int) -> Image.Image:
    """Card catching the light along its upper-left cut edges and darker along the lower-right."""
    import numpy as np

    a = np.asarray(image, dtype=np.float32)
    alpha = a[..., 3] / 255
    lit = np.clip(alpha - np.roll(alpha, (width, width), axis=(0, 1)), 0, 1)[..., None]
    dark = np.clip(alpha - np.roll(alpha, (-width, -width), axis=(0, 1)), 0, 1)[..., None]
    a[..., :3] += lit * 0.3 * (255 - a[..., :3])
    a[..., :3] *= 1 - dark * 0.22
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGBA")
