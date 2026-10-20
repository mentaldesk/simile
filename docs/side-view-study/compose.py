"""Cuts out the paintings, rigs the residents and composites the study's pictures. `python
compose.py [step ...]` from `server/` with `uv run`. Committed pictures go to images/, full-size
ones to out/previews/."""

import json
import math
import sys
from dataclasses import dataclass
from functools import cache

import cutout
import doll
import numpy as np
from assets import ALL, FURNITURE, SWATCHES
from common import IMAGES, OUT, RAW, player_appearance, residents
from PIL import Image, ImageDraw, ImageFilter, ImageOps

CUTS = OUT / "cuts"
FULL = OUT / "previews"
W, H = 1600, 900
FIGURE_M = 1.65
FIGURE_BOOST = 1.2
"""Residents are drawn this much over true scale, as the references draw them."""
LAYERS = {"far", "mid", "ground", "paper-card"}
OPAQUE = {"sky", "canopy"}
CREAM = (238, 232, 220)


def base(name: str) -> str:
    return name.removesuffix("-text").removeprefix("night-")


def kind(name: str) -> str:
    b = base(name)
    if b in OPAQUE or (b.startswith("paper-") and b != "paper-card"):
        return "opaque"
    return "layer" if b in LAYERS else "sprite"


def cut(name: str) -> Image.Image:
    """`name`'s painting cut out, full size and untrimmed, cached in out/cuts."""
    path = CUTS / f"{name}.png"
    if path.exists():
        return Image.open(path).convert("RGBA")
    raw = Image.open(RAW / f"{name}.png").convert("RGB")
    if kind(name) == "opaque":
        out = raw.convert("RGBA")
    else:
        mask = cutout.hybrid(raw)
        if kind(name) == "layer":
            mask = cutout.skyline(mask)
        out = cutout.unmix(raw, mask)
    CUTS.mkdir(parents=True, exist_ok=True)
    out.save(path)
    return out


@cache
def trimmed(name: str) -> tuple[Image.Image, tuple[int, int, int, int]]:
    image = cut(name)
    box = image.getchannel("A").getbbox() or (0, 0, *image.size)
    return image.crop(box), box


def scaled(image: Image.Image, height: float) -> Image.Image:
    h = max(1, round(height))
    return image.resize(
        (max(1, round(image.width * h / image.height)), h), Image.Resampling.LANCZOS
    )


def sprite(name: str, ppm: float, height_m: float | None = None) -> Image.Image:
    return scaled(trimmed(name)[0], (height_m or ALL[base(name)].height) * ppm)


def emission(name: str, like: Image.Image) -> Image.Image | None:
    """The light a building gives off at night: what's warm and bright in its night painting
    and not in its day one, cropped and scaled like its day sprite `like`."""
    night = RAW / f"night-{name}.png"
    if not night.exists():
        return None
    _, box = trimmed(name)
    day = np.asarray(Image.open(RAW / f"{name}.png").convert("RGB"), dtype=np.float32)
    lit = np.asarray(Image.open(night).convert("RGB"), dtype=np.float32)
    mask = np.asarray(cut(name).getchannel("A"), dtype=np.float32)[..., None] / 255
    warm = np.clip((lit.mean(axis=2) - 110) / 90, 0, 1) * (lit[..., 0] > lit[..., 2] + 20)
    glow = np.clip(lit - day * np.array(TIMES["night"].tint), 0, 255) * warm[..., None] * mask
    image = Image.fromarray(glow.astype(np.uint8)).crop(box)
    return image.resize(like.size, Image.Resampling.LANCZOS)


def tile_x(image: Image.Image, width: int, inset: float = 0.06, overlap: int = 120) -> Image.Image:
    """`image` repeated across `width`, without its end caps, crossfading at each seam."""
    w, h = image.size
    core = image.crop((round(w * inset), 0, round(w * (1 - inset)), h))
    out = Image.new("RGBA", (width, h), (0, 0, 0, 0))
    ramp = Image.linear_gradient("L").rotate(90).resize((overlap, h))
    x = 0
    while x < width:
        piece = core.copy()
        if x > 0:
            a = piece.getchannel("A")
            fade = Image.new("L", piece.size, 255)
            fade.paste(ImageOps.mirror(ramp), (0, 0))
            piece.putalpha(Image.fromarray(np.minimum(np.asarray(a), np.asarray(fade))))
        out.alpha_composite(piece, (x, 0))
        x += core.width - overlap
    return out


def mirror_x(image: Image.Image, width: int, inset: float = 0.1) -> Image.Image:
    """`image` repeated across `width`, every other copy mirrored, so each seam matches."""
    w, h = image.size
    core = image.crop((round(w * inset), 0, round(w * (1 - inset)), h))
    out = Image.new("RGBA", (width, h), (0, 0, 0, 0))
    for i, x in enumerate(range(0, width, core.width)):
        out.paste(ImageOps.mirror(core) if i % 2 else core, (x, 0))
    return out


def tint(image: Image.Image, rgb: tuple[float, float, float]) -> Image.Image:
    if rgb == (1.0, 1.0, 1.0):
        return image
    a = np.asarray(image.convert("RGBA"), dtype=np.float32)
    a[..., :3] *= np.array(rgb)
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGBA")


def fade(image: Image.Image, colour: tuple[int, int, int], amount: float) -> Image.Image:
    """Mixes the picture towards `colour`, keeping alpha: distance haze."""
    a = np.asarray(image.convert("RGBA"), dtype=np.float32)
    a[..., :3] = a[..., :3] * (1 - amount) + np.array(colour) * amount
    return Image.fromarray(a.astype(np.uint8), "RGBA")


@dataclass
class Shadow:
    dx: float = 7
    dy: float = 5
    blur: float = 6
    opacity: float = 0.38


class Canvas:
    """An RGBA picture that sprites are put on, each with an optional drop shadow first."""

    def __init__(self, size: tuple[int, int], fill: tuple[int, ...] = (0, 0, 0, 0)) -> None:
        self.image = Image.new("RGBA", size, fill)

    def put(
        self,
        image: Image.Image,
        x: float,
        y: float,
        anchor: str = "mb",
        shadow: Shadow | None = None,
    ) -> tuple[int, int]:
        w, h = image.size
        left = x - {"l": 0, "m": w / 2, "r": w}[anchor[0]]
        top = y - {"t": 0, "m": h / 2, "b": h}[anchor[1]]
        left, top = round(left), round(top)
        if shadow and shadow.opacity > 0:
            s, (ox, oy) = cutout.drop_shadow(
                image, (round(shadow.dx), round(shadow.dy)), shadow.blur, shadow.opacity
            )
            self._over(s, left + ox, top + oy)
        self._over(image, left, top)
        return left, top

    def _over(self, image: Image.Image, x: int, y: int) -> None:
        layer = Image.new("RGBA", self.image.size, (0, 0, 0, 0))
        layer.paste(image, (x, y))
        self.image = Image.alpha_composite(self.image, layer)

    def add(self, image: Image.Image, x: int, y: int, strength: float = 1.0) -> None:
        """Adds light: `image`'s RGB, times `strength`, on top."""
        layer = Image.new("RGB", self.image.size, (0, 0, 0))
        layer.paste(image.convert("RGB"), (x, y))
        a = np.asarray(self.image, dtype=np.float32)
        a[..., :3] += np.asarray(layer, dtype=np.float32) * strength
        self.image = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGBA")


@cache
def painted_pieces(who: str) -> dict[str, doll.Piece]:
    """A resident's paper-doll pieces at the sheet's scale: painted if FLUX has painted their
    sheet, else the flat ones."""
    people = people_looks()
    look = doll.Look.of(people[who], who)
    flat, spots = doll.sheet_pieces(look)
    painted = RAW / f"doll-{who}.png"
    if not painted.exists():
        return flat
    return doll.cut_from_sheet(Image.open(painted), flat, spots, look)


@cache
def people_looks() -> dict:
    return {**{k: v.appearance for k, v in residents().items()}, "player": player_appearance()}


@cache
def sized_pieces(who: str, unit: float) -> dict[str, doll.Piece]:
    f = unit / doll.SHEET_SCALE
    out = {}
    for name, p in painted_pieces(who).items():
        size = (max(1, round(p.image.width * f)), max(1, round(p.image.height * f)))
        out[name] = doll.Piece(
            p.image.resize(size, Image.Resampling.LANCZOS),
            (p.pivot[0] * f, p.pivot[1] * f),
            {k: (v[0] * f, v[1] * f) for k, v in p.joints.items()},
        )
    return out


def figure(
    who: str, pose: doll.Pose, ppm: float, facing: int = 1, plant: bool = True
) -> tuple[Image.Image, tuple[float, float]]:
    """A posed resident and where their feet are in the frame. Drawn at twice the size and
    scaled down, for clean edges."""
    unit = ppm * FIGURE_M * FIGURE_BOOST / 100
    ss = 2
    pieces = sized_pieces(who, unit * ss)
    size = (round(170 * unit * ss), round(150 * unit * ss))
    feet = (size[0] / 2, size[1] - 12 * unit * ss)
    frame = doll.render(pieces, pose, size, feet, plant=plant)
    frame = frame.resize((size[0] // ss, size[1] // ss), Image.Resampling.LANCZOS)
    if facing < 0:
        frame = ImageOps.mirror(frame)
    return frame, (frame.width / 2, feet[1] / ss)


def put_figure(
    canvas: Canvas,
    who: str,
    pose: doll.Pose,
    x: float,
    y: float,
    ppm: float,
    facing: int = 1,
    light: tuple[float, float, float] = (1.0, 1.0, 1.0),
    contact: float = 0.3,
    plant: bool = True,
) -> None:
    frame, feet = figure(who, pose, ppm, facing, plant)
    if contact > 0:
        w = ppm * 0.55
        blob = Image.new("RGBA", (round(w * 2), round(w)), (0, 0, 0, 0))
        ImageDraw.Draw(blob).ellipse(
            (w * 0.3, w * 0.3, w * 1.7, w * 0.7), fill=(20, 14, 10, round(255 * contact))
        )
        canvas._over(
            blob.filter(ImageFilter.GaussianBlur(w * 0.12)), round(x - w), round(y - w * 0.5)
        )
    canvas._over(tint(frame, light), round(x - feet[0]), round(y - feet[1]))


@dataclass
class Time:
    tint: tuple[float, float, float]
    sky: tuple[float, float, float]
    haze: tuple[int, int, int]
    glow: float
    shadow: float


TIMES = {
    "morning": Time((1.0, 0.95, 0.88), (1.02, 0.94, 0.86), (246, 232, 214), 0.0, 0.32),
    "afternoon": Time((1.0, 1.0, 1.0), (1.0, 1.0, 1.0), (232, 238, 240), 0.0, 0.38),
    "evening": Time((1.0, 0.74, 0.58), (1.05, 0.66, 0.5), (226, 160, 130), 0.55, 0.3),
    "night": Time((0.3, 0.36, 0.6), (0.16, 0.2, 0.42), (40, 50, 90), 1.0, 0.18),
}

STREET_PPM = 65
PAVEMENT = 745
STREET_W = 3000
PARALLAX = {"sky": 0.04, "far": 0.2, "mid": 0.45, "near": 1.0, "front": 1.3}
STREET_ROW = [
    ("house", 0, False),
    ("banyan", -150, False),
    ("cafe", -120, False),
    ("lamp", 10, False),
    ("noodle", 10, False),
    ("pot", 0, False),
    ("shophouse", 20, False),
    ("banyan", -170, True),
    ("grocer", -130, False),
    ("lamp", 10, False),
    ("house", 30, True),
]
WALKERS = [
    ("odalys", 700, 1, 0.0, 70),
    ("lachlan", 1180, -1, 0.35, 55),
    ("ingrid", 1520, 1, 0.6, 80),
]


@cache
def street_layers(suffix: str = "") -> dict[str, tuple[Image.Image, int]]:
    """The street's layers at full width, each with the y of its top edge."""
    pan = STREET_W - W
    sky = cut(f"sky{suffix}")
    sky = sky.resize((round(W + pan * PARALLAX["sky"]) + 2, H), Image.Resampling.LANCZOS)
    far = scaled(trimmed(f"far{suffix}")[0], 230)
    far = tile_x(far, round(W + pan * PARALLAX["far"]) + 2)
    mid = scaled(trimmed(f"mid{suffix}")[0], 380)
    mid = tile_x(mid, round(W + pan * PARALLAX["mid"]) + 2)
    ground = scaled(trimmed(f"ground{suffix}")[0], 190)
    ground = mirror_x(ground, STREET_W)
    return {
        "sky": (sky, 0),
        "far": (far, 560 - far.height),
        "mid": (mid, 712 - mid.height),
        "ground": (ground, PAVEMENT - 18),
    }


@dataclass
class Prop:
    image: Image.Image
    x: float
    glow: Image.Image | None


@cache
def street_props(suffix: str = "") -> list[Prop]:
    props = []
    x = 40.0
    for name, gap, mirror in STREET_ROW:
        image = sprite(f"{name}{suffix}", STREET_PPM)
        glow = emission(name, image) if not suffix else None
        if mirror:
            image = ImageOps.mirror(image)
            glow = ImageOps.mirror(glow) if glow else None
        x += gap
        props.append(Prop(image, x + image.width / 2, glow))
        x += image.width
    return props


def street(
    camera: float, when: str = "afternoon", suffix: str = "", t: float = 0.0, lights: bool = True
) -> Image.Image:
    """The street with the camera's left edge at `camera` world px, `t` seconds into the walk."""
    tod = TIMES[when]
    glow = tod.glow if lights else 0.0
    layers = street_layers(suffix)
    canvas = Canvas((W, H), (0, 0, 0, 255))
    sky, _ = layers["sky"]
    canvas._over(tint(sky, tod.sky), -round(camera * PARALLAX["sky"]), 0)
    for name, haze in (("far", 0.35), ("mid", 0.15)):
        image, top = layers[name]
        image = tint(fade(image, tod.haze, haze), tod.tint)
        canvas.put(image, -camera * PARALLAX[name], top, "lt", Shadow(4, 3, 5, tod.shadow * 0.6))
    ground, top = layers["ground"]
    canvas.put(tint(ground, tod.tint), -camera, top, "lt")
    near = Shadow(9, 6, 7, tod.shadow)
    big = [p for p in street_props(suffix) if p.image.height > 300]
    small = [p for p in street_props(suffix) if p.image.height <= 300]
    for prop in big + small:
        left, top = canvas.put(
            tint(prop.image, tod.tint), prop.x - camera, PAVEMENT + 6, "mb", near
        )
        if prop.glow and glow > 0:
            canvas.add(prop.glow, left, top, glow)
            canvas.add(prop.glow.filter(ImageFilter.GaussianBlur(14)), left, top, glow * 0.9)
    for who, x, facing, phase, speed in WALKERS:
        wx = x + facing * speed * t
        pose = doll.walk_pose((phase + t / 1.1) % 1.0)
        light = lamp_light(wx, tod) if when == "night" else tod.tint
        put_figure(canvas, who, pose, wx - camera, PAVEMENT + 32, STREET_PPM, facing, light)
    front = sprite(f"pot{suffix}", STREET_PPM, 6.5).filter(ImageFilter.GaussianBlur(3))
    for fx in (560, 2050, 3300):
        canvas.put(
            tint(front, tuple(c * 0.45 for c in tod.tint)),
            fx - camera * PARALLAX["front"],
            H + 250,
            "mb",
        )
    return canvas.image.convert("RGB")


def lamp_light(x: float, tod: Time) -> tuple[float, float, float]:
    """A resident's tint at night, brighter near a street lamp."""
    lamps = [p.x for p in street_props("") if p.glow is not None and p.image.width < 200]
    near = max((max(0.0, 1 - abs(x - lx) / 260) for lx in lamps), default=0.0)
    return tuple(a + (b - a) * near * 0.7 for a, b in zip(tod.tint, (1.0, 0.85, 0.6), strict=True))


def save(image: Image.Image, name: str, width: int | None = None, quality: int = 84) -> None:
    FULL.mkdir(parents=True, exist_ok=True)
    IMAGES.mkdir(parents=True, exist_ok=True)
    image.save(FULL / f"{name}.png")
    small = image if width is None or image.width <= width else scaled_w(image, width)
    small.convert("RGB").save(
        IMAGES / f"{name}.jpg", quality=quality, optimize=True, progressive=True
    )
    print(f"images/{name}.jpg", flush=True)


def scaled_w(image: Image.Image, width: int) -> Image.Image:
    return image.resize(
        (width, round(image.height * width / image.width)), Image.Resampling.LANCZOS
    )


def step_street() -> None:
    save(street(380), "1-street", 1600)
    save(street(380, suffix="-text"), "consistency-street-text", 1200)


def step_times() -> None:
    frames = {when: street(380, when) for when in TIMES}
    grid = Image.new("RGB", (W, H))
    for i, (when, frame) in enumerate(frames.items()):
        grid.paste(scaled_w(frame, W // 2), ((i % 2) * W // 2, (i // 2) * H // 2))
        frame.save(FULL / f"time-{when}.png")
    save(grid, "time-of-day", 1600)
    night = frames["night"]
    flat = street(380, "night", lights=False)
    painted = Image.open(RAW / "night-cafe.png").convert("RGB")
    row = Image.new("RGB", (1500, 500), CREAM)
    row.paste(flat.crop((500, 260, 1000, 760)), (0, 0))
    row.paste(night.crop((500, 260, 1000, 760)), (500, 0))
    row.paste(scaled(painted, 500).crop((0, 0, 500, 500)), (1000, 0))
    save(row, "time-night-compare", 1500)


def step_parallax(frames: int = 40) -> None:
    images = []
    for i in range(frames):
        t = i / frames * 4.4
        camera = 40 + (STREET_W - W - 80) * (0.5 - 0.5 * math.cos(math.pi * i / frames))
        images.append(street(camera, t=t))
    gif([scaled_w(f, 480) for f in images], "1-street-parallax", 110, 96)
    FULL.mkdir(parents=True, exist_ok=True)
    images[0].save(
        FULL / "1-street-parallax.webp",
        save_all=True,
        append_images=images[1:],
        duration=110,
        loop=0,
        quality=80,
    )


def gif(frames: list[Image.Image], name: str, ms: int, colours: int = 128) -> None:
    IMAGES.mkdir(parents=True, exist_ok=True)
    first = frames[0].quantize(colours, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    rest = [f.quantize(palette=first, dither=Image.Dither.NONE) for f in frames[1:]]
    first.save(
        IMAGES / f"{name}.gif",
        save_all=True,
        append_images=rest,
        duration=ms,
        loop=0,
        optimize=True,
    )
    print(f"images/{name}.gif {(IMAGES / f'{name}.gif').stat().st_size / 1e6:.2f} MB", flush=True)


HOUSE_PPM = 95
GROUND = 846
STOREY = round(2.8 * HOUSE_PPM)
SLAB = 18
X0, X1 = 230, 1370
STAIRWELL = 1080


def wall(name: str, size: tuple[int, int]) -> Image.Image:
    """A room's back wall: its paper, cropped to fill, shaded towards the ceiling and corners."""
    paper = cut(name)
    s = max(size[0] / paper.width, size[1] / paper.height) * 1.0
    paper = paper.resize(
        (math.ceil(paper.width * s), math.ceil(paper.height * s)), Image.Resampling.LANCZOS
    )
    paper = paper.crop((0, 0, *size))
    y = np.linspace(0, 1, size[1])[:, None]
    x = np.linspace(0, 1, size[0])[None, :]
    shade = 0.72 + 0.28 * np.clip(y / 0.35, 0, 1)
    shade = shade * (0.88 + 0.12 * np.clip(np.minimum(x, 1 - x) / 0.12, 0, 1))
    a = np.asarray(paper, dtype=np.float32)
    a[..., :3] *= shade[..., None]
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGBA")


def slab(width: int, height: int) -> Image.Image:
    band = trimmed("paper-card")[0]
    band = band.crop((0, 4, band.width, band.height - 4))
    return tile_x(
        band.resize((round(band.width * height / band.height), height)),
        width,
        inset=0.04,
        overlap=40,
    )


ROOMS = [
    ("paper-kitchen", X0, 620, 0),
    ("paper-living", 620, X1, 0),
    ("paper-bedroom", X0, 700, 1),
    ("paper-bathroom", 700, STAIRWELL, 1),
    ("paper-living", STAIRWELL, X1, 1),
]
FURNISH = [
    ("fridge", 280, 0, False),
    ("counter", 410, 0, False),
    ("stove", 548, 0, False),
    ("floor-lamp", 668, 0, False),
    ("sofa", 800, 0, False),
    ("armchair", 965, 0, False),
    ("monstera", 1240, 0, False),
    ("wardrobe", 300, 1, False),
    ("bed", 500, 1, False),
    ("bedside", 645, 1, False),
    ("bathtub", 820, 1, False),
    ("basin", 1000, 1, False),
]
HOME = [
    ("odalys", "stand", 480, 0, 1),
    ("henrietta", "stand", 900, 0, -1),
    ("kofi", 0.45, 0, 0, -1),
]


def floor_y(level: int) -> int:
    return GROUND - level * (STOREY + SLAB)


def dollhouse(ppm: float = HOUSE_PPM, suffix: str = "") -> Image.Image:
    canvas = Canvas((W, H), (0, 0, 0, 255))
    layers = street_layers()
    canvas._over(layers["sky"][0], 0, 0)
    for name in ("far", "mid"):
        image, top = layers[name]
        canvas._over(fade(image, (232, 238, 240), 0.3 if name == "far" else 0.15), -300, top + 120)
    ground, top = layers["ground"]
    canvas._over(ground, -200, GROUND - 30)
    for paper, a, b, level in ROOMS:
        canvas._over(wall(paper, (b - a, STOREY)), a, floor_y(level) - STOREY)
    for x, level in ((420, 0), (850, 0), (430, 1), (890, 1)):
        canvas.put(sprite("window", ppm), x, floor_y(level) - 1.0 * ppm, "mb", Shadow(4, 3, 4, 0.3))
    canvas._over(wall("paper-living", (X1 - STAIRWELL, SLAB + 8)), STAIRWELL, floor_y(1) - 4)
    for x in (620, 700, STAIRWELL):
        level = 0 if x == 620 else 1
        canvas.image.paste(
            (214, 190, 160, 255), (x - 4, floor_y(level) - STOREY, x + 4, floor_y(level))
        )
    stairs = ImageOps.mirror(sprite("stairs", ppm, (STOREY + SLAB) / ppm))
    stairs_at = canvas.put(stairs, X1 - 20, GROUND, "rb", Shadow(6, 4, 5, 0.35))
    slope, offset = treads(stairs)
    for name, x, level, mirror in FURNISH:
        image = sprite(f"{name}{suffix}", ppm)
        canvas.put(
            ImageOps.mirror(image) if mirror else image,
            x,
            floor_y(level) + 4,
            "mb",
            Shadow(8, 4, 6, 0.4),
        )
    for who, pose, x, level, facing in HOME:
        if isinstance(pose, float):
            sx = stairs.width * (1 - pose)
            fx, fy = stairs_at[0] + sx, stairs_at[1] + slope * sx + offset
            put_figure(canvas, who, doll.walk_pose(0.2), fx, fy, ppm, facing, contact=0.0)
        else:
            put_figure(canvas, who, doll.STAND, x, floor_y(level) + 2, ppm, facing, contact=0.25)
    canvas.put(slab(STAIRWELL - X0 + 20, SLAB), X0 - 20, floor_y(1), "lt", Shadow(0, 6, 5, 0.35))
    canvas.put(slab(X1 - X0 + 40, SLAB), X0 - 20, floor_y(1) - STOREY, "lb", Shadow(0, 6, 5, 0.35))
    canvas.put(slab(X1 - X0 + 60, 26), X0 - 30, GROUND, "lt", Shadow(0, 6, 5, 0.35))
    rail = Image.new("RGBA", (X1 - STAIRWELL - 10, 10), (120, 84, 52, 255))
    canvas.put(rail, STAIRWELL, floor_y(1) - 0.95 * ppm, "lt", Shadow(3, 3, 3, 0.3))
    for x in range(STAIRWELL + 30, X1 - 10, 46):
        canvas.put(
            Image.new("RGBA", (5, round(0.95 * ppm)), (120, 84, 52, 255)), x, floor_y(1), "mb"
        )
    for x in (X0 - 20, X1):
        canvas.put(
            slab(2 * (STOREY + SLAB) + 26, 22).rotate(90, expand=True),
            x,
            GROUND + 26,
            "lb",
            Shadow(5, 0, 5, 0.3),
        )
    roof = trimmed("roof")[0]
    roof = roof.resize((X1 - X0 + 140, round(2.1 * ppm)), Image.Resampling.LANCZOS)
    canvas.put(roof, (X0 + X1 + 22) / 2, floor_y(2) + 8, "mb", Shadow(0, 8, 8, 0.4))
    return canvas.image.convert("RGB")


def treads(image: Image.Image) -> tuple[float, float]:
    """The line along the stairs' step edges, y = slope * x + offset in the image: the top of
    each column's lowest solid run, fitted, then moved up to the step edges."""
    alpha = np.asarray(image.getchannel("A")) > 128
    xs, ys = [], []
    for x in range(image.width // 10, image.width * 9 // 10, 2):
        column = alpha[:, x]
        if not column.any():
            continue
        y = len(column) - 1 - int(np.argmax(column[::-1]))
        while y > 0 and column[y - 1]:
            y -= 1
        xs.append(x)
        ys.append(y)
    slope, offset = np.polyfit(xs, ys, 1)
    residuals = np.array(ys) - (slope * np.array(xs) + offset)
    return float(slope), float(offset + np.percentile(residuals, 15))


def step_house() -> None:
    save(dollhouse(), "2-dollhouse", 1600)
    save(dollhouse(suffix="-text"), "consistency-dollhouse-text", 1200)


PLATFORM_PPM = 95


def stretch3(image: Image.Image, width: int, cap: float = 0.14) -> Image.Image:
    """A platform made `width` wide by repeating its middle and keeping its ends."""
    w, h = image.size
    c = round(w * cap)
    left, right = image.crop((0, 0, c, h)), image.crop((w - c, 0, w, h))
    out = Image.new("RGBA", (width, h), (0, 0, 0, 0))
    out.paste(
        tile_x(image.crop((c, 0, w - c, h)), width - 2 * c + 40, inset=0.0, overlap=40), (c - 20, 0)
    )
    out.alpha_composite(left, (0, 0))
    out.alpha_composite(right, (width - c, 0))
    return out


def rope_bridge(
    x0: float, x1: float, y: float, sag: float, ppm: float
) -> tuple[Image.Image, int, int]:
    """Planks along a hanging curve with two ropes, from the painted plank."""
    pad = 60
    w, h = round(x1 - x0) + 2 * pad, round(sag + 2 * ppm) + 2 * pad
    canvas = Canvas((w, h))
    plank = trimmed("plank")[0]
    plank = plank.resize((round(0.2 * ppm), round(0.07 * ppm)), Image.Resampling.LANCZOS)

    def deck(u: float) -> tuple[float, float]:
        return pad + u * (x1 - x0), pad + ppm + sag * 4 * u * (1 - u)

    def rope(u: float) -> tuple[float, float]:
        x, yy = deck(u)
        return x, yy - 0.9 * ppm + sag * 0.15 * 4 * u * (1 - u)

    draw = ImageDraw.Draw(canvas.image)
    pts = [rope(i / 40) for i in range(41)]
    for i in range(0, 41, 4):
        draw.line([pts[i], deck(i / 40)], fill=(150, 112, 70, 255), width=3)
    n = round((x1 - x0) / (0.25 * ppm))
    for i in range(n + 1):
        u = i / n
        x, yy = deck(u)
        slope = math.degrees(math.atan2(sag * 4 * (1 - 2 * u), x1 - x0))
        p = plank.rotate(-slope, expand=True, resample=Image.Resampling.BICUBIC)
        canvas.put(p, x, yy, "mt", Shadow(3, 3, 3, 0.35))
    for line in (pts, [deck(i / 40) for i in range(41)]):
        draw = ImageDraw.Draw(canvas.image)
        draw.line(line, fill=(112, 80, 48, 255), width=6, joint="curve")
        draw.line([(x, yy - 1) for x, yy in line], fill=(186, 146, 98, 255), width=2)
    return canvas.image, round(x0 - pad), round(y - ppm - pad)


def orb(r: float) -> Image.Image:
    size = round(r * 6)
    y, x = np.mgrid[0:size, 0:size] - size / 2
    d = np.hypot(x, y) / r
    alpha = np.clip(1.2 - d, 0, 1) ** 1.5 + 0.6 * np.exp(-((d / 2.2) ** 2))
    rgb = np.stack(
        [np.full_like(d, 255), 230 - 40 * np.clip(d - 0.5, 0, 1), 150 - 60 * np.clip(d, 0, 1)],
        axis=2,
    )
    out = np.dstack([rgb, np.clip(alpha, 0, 1) * 255]).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def platforms(ppm: float = PLATFORM_PPM, suffix: str = "") -> Image.Image:
    canvas = Canvas((W, H), (0, 0, 0, 255))
    back = cut(f"canopy{suffix}")
    s = max(W / back.width, H / back.height)
    back = back.resize(
        (math.ceil(back.width * s), math.ceil(back.height * s)), Image.Resampling.LANCZOS
    )
    canvas._over(fade(back, (230, 236, 226), 0.25), 0, 0)
    tree = sprite(f"banyan{suffix}", ppm, 10.5)
    canvas.put(fade(tree, (200, 214, 200), 0.2), 1180, H + 60, "mb", Shadow(10, 6, 8, 0.3))
    canvas.put(
        fade(ImageOps.mirror(tree), (200, 214, 200), 0.2), 170, H + 120, "mb", Shadow(10, 6, 8, 0.3)
    )
    shadow = Shadow(9, 7, 7, 0.42)
    ridge = sprite(f"ridge{suffix}", ppm)
    canvas.put(stretch3(ridge, 430), 0, 690, "lt", shadow)
    planks = sprite(f"planks{suffix}", ppm)
    canvas.put(stretch3(planks, 380), 560, 520, "lt", shadow)
    canvas.put(stretch3(planks, 520), 640, 805, "lt", shadow)
    ladder = sprite(f"ladder{suffix}", ppm, (805 - 520) / ppm + 0.5)
    canvas.put(ladder, 700, 812, "mb", shadow)
    bridge, bx, by = rope_bridge(930, 1250, 530, 70, ppm)
    canvas.put(bridge, bx, by, "lt", Shadow(8, 8, 7, 0.35))
    canvas.put(stretch3(planks, 380), 1240, 520, "lt", shadow)
    awning = sprite(f"awning{suffix}", ppm)
    canvas.put(scaled_w(awning, 300), 1470, 526, "mb", shadow)
    glow = orb(0.16 * ppm)
    for ox, oy in ((480, 470), (760, 440), (1060, 470), (1380, 270), (880, 740), (1000, 740)):
        canvas._over(glow, round(ox - glow.width / 2), round(oy - glow.height / 2))
    put_figure(canvas, "player", doll.JUMP, 470, 560, ppm, 1, contact=0.0, plant=False)
    put_figure(canvas, "priya", doll.STAND, 1290, 522, ppm, -1, contact=0.25)
    return canvas.image.convert("RGB")


def step_platforms() -> None:
    save(platforms(), "3-platforms", 1600)


WALK_CAST = ["odalys", "lachlan", "ingrid", "kofi", "henrietta", "player"]


def step_walk(frames: int = 12) -> None:
    ppm = 110
    cells = []
    for i in range(frames):
        row = Canvas((180 * len(WALK_CAST), 300), (*CREAM, 255))
        for j, who in enumerate(WALK_CAST):
            put_figure(
                row, who, doll.walk_pose(i / frames), 90 + 180 * j, 280, ppm, 1, contact=0.25
            )
        cells.append(row.image.convert("RGB"))
    gif(cells, "walk-cycle", 1100 // frames, 160)
    strip = Canvas((8 * 160, 300), (*CREAM, 255))
    for i in range(8):
        put_figure(strip, "ingrid", doll.walk_pose(i / 8), 80 + 160 * i, 280, ppm, 1, contact=0.25)
    save(strip.image.convert("RGB"), "walk-frames", 1280, 88)
    lineup = Canvas((150 * 12 + 20, 320), (*CREAM, 255))
    for j, who in enumerate(list(residents()) + ["player"]):
        put_figure(lineup, who, doll.STAND, 85 + 150 * j, 300, ppm, 1, contact=0.25)
    save(lineup.image.convert("RGB"), "residents", 1820, 88)
    flat = Canvas((150 * 6 + 20, 320), (*CREAM, 255))
    for j, who in enumerate(WALK_CAST):
        look = doll.Look.of(people_looks()[who], who)
        pieces = {
            k: doll.trim(v)
            for k, v in doll.flat_pieces(look, 2 * ppm * FIGURE_M * FIGURE_BOOST / 100).items()
        }
        f = doll.render(pieces, doll.STAND, (360, 600), (180, 576))
        f = f.resize((180, 300), Image.Resampling.LANCZOS)
        flat._over(f, 85 + 150 * j - 90, 300 - 288)
    sheet_who = "odalys"
    pieces, spots = doll.sheet_pieces(doll.Look.of(people_looks()[sheet_who], sheet_who))
    before = doll.sheet(pieces, spots, doll.SHEET)
    after = Image.open(RAW / f"doll-{sheet_who}.png").convert("RGB")
    pair = Image.new("RGB", (2 * doll.SHEET[0], doll.SHEET[1]), CREAM)
    pair.paste(before, (0, 0))
    pair.paste(after, (doll.SHEET[0], 0))
    save(pair, "doll-sheet", 1400, 86)


def grid(
    items: list[Image.Image], cols: int, cell: tuple[int, int], bg=(214, 200, 182)
) -> Image.Image:
    rows = math.ceil(len(items) / cols)
    out = Canvas((cols * cell[0], rows * cell[1]), (*bg, 255))
    for i, item in enumerate(items):
        x = (i % cols) * cell[0] + cell[0] / 2
        y = (i // cols) * cell[1] + cell[1] - 16
        out.put(item, x, y, "mb", Shadow(6, 4, 5, 0.38))
    return out.image.convert("RGB")


def step_furniture() -> None:
    ppm = 120
    for suffix, name in (("", "furniture"), ("-text", "consistency-furniture-text")):
        items = [sprite(f"{a.name}{suffix}", ppm) for a in FURNITURE]
        save(grid(items, 8, (220, 270)), name, 1760, 86)
    sofa = trimmed("sofa")[0]
    variants = [scaled(sofa, 120)] + [scaled(trimmed(f"sofa-{c}")[0], 120) for c in SWATCHES]
    variants += [scaled(recolour(sofa, hue), 120) for hue in (0.97, 0.12, 0.83)]
    save(grid(variants, 7, (260, 170)), "swatches", 1820, 86)
    shadows = []
    for name in ("armchair", "bookshelf", "monstera"):
        raw = Image.open(RAW / f"{name}.png").convert("RGB")
        mask = cutout.hybrid(raw)
        x0, y0, x1, y1 = mask.getbbox()
        pad = round((x1 - x0) * 0.3)
        box = (x0 - pad, y0, x1 + pad, y1 + pad)
        both = Image.alpha_composite(cutout.baked_shadow(raw, mask), cutout.unmix(raw, mask))
        f = 240 / (y1 - y0)
        size = (round((box[2] - box[0]) * f), round((box[3] - box[1]) * f))
        shadows += [
            both.crop(box).resize(size, Image.Resampling.LANCZOS),
            scaled(trimmed(name)[0], 240),
        ]
    out = Canvas((6 * 230, 330), (*CREAM, 255))
    wallp = wall("paper-living", (6 * 230, 330))
    out._over(wallp, 0, 0)
    for i, item in enumerate(shadows):
        baked = i % 2 == 0
        y = 300 + (round((item.height - 240) * 1.0) if baked else 0)
        out.put(item, 115 + 230 * i, y, "mb", None if baked else Shadow(10, 5, 7, 0.42))
    save(out.image.convert("RGB"), "shadows", 1380, 86)


def recolour(image: Image.Image, hue: float) -> Image.Image:
    """Runtime-style recolour: the saturated upholstery rotated to `hue`, the rest left alone."""
    hsv = np.asarray(image.convert("RGB").convert("HSV"), dtype=np.float32)
    sat = hsv[..., 1] / 255
    fabric = np.clip((sat - 0.25) / 0.2, 0, 1) * (np.abs(hsv[..., 0] / 255 - 0.5) < 0.12)
    hsv[..., 0] = np.where(fabric > 0, hue * 255, hsv[..., 0])
    out = Image.fromarray(hsv.astype(np.uint8), "HSV").convert("RGB")
    blend = Image.composite(
        out, image.convert("RGB"), Image.fromarray((fabric * 255).astype(np.uint8))
    )
    blend.putalpha(image.getchannel("A"))
    return blend


def palette(image: Image.Image, n: int = 8) -> np.ndarray:
    """`image`'s main colours in CIELAB, from its opaque pixels."""
    rgba = np.asarray(image.convert("RGBA"))
    px = rgba[rgba[..., 3] > 200][:, :3]
    if len(px) > 40000:
        px = px[np.random.default_rng(0).choice(len(px), 40000, replace=False)]
    q = Image.fromarray(px[None]).quantize(n, method=Image.Quantize.MEDIANCUT)
    cols = np.array(q.getpalette()[: 3 * n], dtype=np.float32).reshape(-1, 3)
    counts = np.bincount(np.asarray(q).ravel(), minlength=n)[:n]
    return lab(cols), counts / counts.sum()


def lab(rgb: np.ndarray) -> np.ndarray:
    c = rgb / 255
    c = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    m = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = c @ m.T / np.array([0.9505, 1.0, 1.089])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack(
        [116 * f[:, 1] - 16, 500 * (f[:, 0] - f[:, 1]), 200 * (f[:, 1] - f[:, 2])], axis=1
    )


def step_consistency() -> None:
    """How far each asset's colours sit from the references': the weighted mean CIEDE76 distance
    from each of its 8 main colours to the nearest of the references' 40."""
    refs = np.concatenate(
        [
            palette(Image.open(f"{p}"), 8)[0]
            for p in sorted((RAW.parent.parent / "references").glob("*.jpg"))
        ]
    )
    rows = []
    for asset in ALL.values():
        if not (RAW / f"{asset.name}-text.png").exists():
            continue
        row = {"asset": asset.name}
        for suffix, label in (("", "referenced"), ("-text", "text")):
            cols, weights = palette(trimmed(f"{asset.name}{suffix}")[0])
            d = np.sqrt(((cols[:, None] - refs[None]) ** 2).sum(axis=2)).min(axis=1)
            row[label] = round(float((d * weights).sum()), 1)
        rows.append(row)
    (OUT / "consistency.json").write_text(json.dumps(rows, indent=1))
    for r in rows:
        print(r)
    print(
        "mean", {k: round(float(np.mean([r[k] for r in rows])), 1) for k in ("referenced", "text")}
    )


def step_costs() -> None:
    entries = [json.loads(line) for line in (OUT / "timings.jsonl").read_text().splitlines()]
    paints = [e for e in entries if e["event"] == "paint" and not e["name"].startswith("pilot")]
    groups: dict[str, list[float]] = {}
    for e in paints:
        key = f"{e['mode']} q{e['bits'] or 16} {e['size'][0]}x{e['size'][1]} refs={e['refs']}"
        groups.setdefault(key, []).append(e["seconds"])
    for key, secs in sorted(groups.items()):
        print(f"{key}: n={len(secs)} mean={np.mean(secs):.1f}s")
    print("total paint seconds", round(sum(e["seconds"] for e in paints)), "for", len(paints))
    sizes = {}
    for name in [a.name for a in FURNITURE] + ["cafe", "noodle", "banyan"]:
        image = trimmed(name)[0]
        for ext, args in (("png", {"optimize": True}), ("webp", {"quality": 85})):
            path = OUT / "sizes" / f"{name}.{ext}"
            path.parent.mkdir(parents=True, exist_ok=True)
            scaled(image, ALL[name].height * 120).save(path, **args)
            sizes.setdefault(ext, []).append(path.stat().st_size)
    print({k: f"mean {np.mean(v) / 1e3:.0f} kB" for k, v in sizes.items()})


def step_cutouts() -> None:
    """Each cut-out method on the same paintings, over a coloured backdrop."""
    rows = []
    for name in ("cafe", "armchair", "ladder", "first-bathtub", "bathtub"):
        raw = Image.open(RAW / f"{name}.png").convert("RGB")
        cells = [scaled(raw, 300)]
        for method in ("isnet", "key", "hybrid"):
            cell = Canvas(raw.size, (120, 150, 170, 255))
            cell._over(cutout.cut(raw, method, trim=False), 0, 0)
            cells.append(scaled(cell.image, 300))
        row = Image.new("RGB", (sum(c.width for c in cells) + 8 * len(cells), 300), CREAM)
        x = 0
        for c in cells:
            row.paste(c.convert("RGB"), (x, 0))
            x += c.width + 8
        rows.append(row)
    out = Image.new("RGB", (max(r.width for r in rows), 308 * len(rows)), CREAM)
    for i, r in enumerate(rows):
        out.paste(r, (0, 308 * i))
    save(out, "cutouts", 1500, 84)


def step_quantized() -> None:
    cells = []
    for name in ("armchair", "cafe"):
        for prefix in ("", "q8-", "q4-"):
            path = RAW / (f"{prefix}{name}.png" if prefix else f"{name}-text.png")
            cells.append(scaled(Image.open(path).convert("RGB"), 320))
    row = Image.new("RGB", (sum(c.width for c in cells) + 8 * len(cells), 320), CREAM)
    x = 0
    for c in cells:
        row.paste(c, (x, 0))
        x += c.width + 8
    save(row, "quantized", 1700, 84)


STEPS = {
    "street": step_street,
    "times": step_times,
    "parallax": step_parallax,
    "house": step_house,
    "platforms": step_platforms,
    "walk": step_walk,
    "furniture": step_furniture,
    "consistency": step_consistency,
    "cutouts": step_cutouts,
    "quantized": step_quantized,
    "costs": step_costs,
}

if __name__ == "__main__":
    for step in sys.argv[1:] or list(STEPS):
        STEPS[step]()
