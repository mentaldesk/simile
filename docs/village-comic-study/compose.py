"""Every picture in the README, composed in Python at the client's retina size from the pieces
`pieces.py` cut, the game's committed tunnels and the real figures in content/dolls/.

`python compose.py [step …]`, with no step for all of them. Paints nothing.
"""

import json
import math
from collections import Counter
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps
from study import CONTENT, IMAGES, OUT, args

from simile.papercraft.catalogue import TIMES
from simile.papercraft.preview import MapView, haze, read_views, repeat, shadow, tint
from simile.papercraft.village import TILE

PPM = 95
"""The client's pixels a metre on a retina screen: 19 m of view on a 1800 px tall canvas."""
VIEW_M = 19.0
FEET_AT = 0.82
WIDE_M = 27.0
"""How wide a street is shown: a little narrower than a 16:9 screen's 33.8 m."""
GROUND_LIFT_M = 0.35
FURNITURE_DROP_M = 0.06
STRETCH_FILL = 0.96
LADDER_ABOVE_M = 0.6
PLACES = {"far": (7.5, 5.75), "mid": (2.75, 6.25), "near": (-0.1, None)}
"""Metres above the feet line to a layer's bottom, and its height, as `camera.ts` has them."""
CITY = (4.0, 8.0)
"""The city's bottom above the feet line and its height: it shows over the mid layer and
between buildings."""
HAZE = 0.35
"""How far the city is mixed towards the time's haze colour, besides the far layer's own."""
SEAT_M = {"stool": 0.567, "bench": 0.392, "cafe_table": 0.442}
BED_M = 0.45
DOLLS = CONTENT / "dolls"
LINE_NAMES = {"a": "A, smooth line", "b": "B, scratchy line"}
INK = (44, 36, 32)
PAPER = (240, 236, 228)
DAY, NIGHT = "afternoon", "night"


class Kit:
    """The pieces of one build, by key, from its manifest."""

    def __init__(self, content: Path) -> None:
        self.content = content
        self.manifest = json.loads((content / "manifest.json").read_text())
        self.images: dict[str, Image.Image] = {}

    def has(self, key: str) -> bool:
        return key in self.manifest["pieces"]

    def entry(self, key: str) -> dict:
        return self.manifest["pieces"][key]

    def file(self, name: str) -> Image.Image:
        if name not in self.images:
            self.images[name] = Image.open(self.content / name).convert("RGBA")
        return self.images[name]

    def piece(self, key: str) -> Image.Image:
        return self.file(self.entry(key)["file"])

    def at(self, key: str, ppm: float, height: float | None = None) -> Image.Image:
        image = self.piece(key)
        h = max(1, round((height or self.entry(key)["height"]) * ppm))
        return image.resize((max(1, round(image.width * h / image.height)), h), Image.LANCZOS)

    def furniture(self, name: str) -> tuple[str, bool] | None:
        """A map's furniture or platform piece, and whether it stretches, if this build has it."""
        found = self.manifest["furniture"].get(name)
        if found and self.has(found["piece"]):
            return found["piece"], bool(found.get("stretch"))
        key = f"platforms/{name}"
        return (key, False) if self.has(key) else None


class Chain(Kit):
    """Each piece from the first build that has it: #326's references' pieces over a new set."""

    def __init__(self, kits: list[Kit]) -> None:
        self.kits = kits
        pieces = {k: v for c in reversed(kits) for k, v in c.manifest["pieces"].items()}
        self.manifest = {**kits[-1].manifest, "pieces": pieces}

    def piece(self, key: str) -> Image.Image:
        return next(c for c in self.kits if c.has(key)).piece(key)

    def file(self, name: str) -> Image.Image:
        return next(c for c in self.kits if (c.content / name).exists()).file(name)


@cache
def kit(name: str) -> Kit:
    """`game` for the committed scenery, a study build like `a-new`, or builds chained with `+`."""
    if "+" in name:
        return Chain([kit(n) for n in name.split("+")])
    return Kit(CONTENT / "papercraft" if name == "game" else OUT / name / "papercraft")


@cache
def views() -> dict[str, MapView]:
    return read_views()


def stretch(image: Image.Image, width: int, cap: float = 0.15) -> Image.Image:
    """`image` made `width` wide by repeating its middle and keeping its ends, as the client
    stretches runs."""
    w, h = image.size
    c = round(w * cap)
    middle = image.crop((c, 0, w - c, h))
    out = Image.new("RGBA", (max(width, 2 * c), h), (0, 0, 0, 0))
    for x in range(c, out.width - c, middle.width):
        out.paste(middle.crop((0, 0, min(middle.width, out.width - c - x), h)), (x, 0))
    out.paste(image.crop((0, 0, c, h)), (0, 0))
    out.paste(image.crop((w - c, 0, w, h)), (out.width - c, 0))
    return out


class Canvas:
    def __init__(self, size: tuple[int, int], fill=(0, 0, 0, 255)) -> None:
        self.image = Image.new("RGBA", size, fill)

    def over(self, image: Image.Image, x: float, y: float) -> None:
        layer = Image.new("RGBA", self.image.size, (0, 0, 0, 0))
        layer.paste(image, (round(x), round(y)))
        self.image = Image.alpha_composite(self.image, layer)

    def put(self, image, x, y, anchor=(0.5, 1.0), shadowed=True) -> tuple[float, float]:
        """`image` with its `anchor` at x, y, over a soft drop shadow."""
        image = image.convert("RGBA")
        left, top = x - image.width * anchor[0], y - image.height * anchor[1]
        if shadowed:
            s = shadow(image, 0.06 * PPM, 0.36)
            pad = (s.width - image.width) / 2
            self.over(s, left - pad + 0.07 * PPM, top - pad + 0.05 * PPM)
        self.over(image, left, top)
        return left, top

    def add(self, light: Image.Image, x: float, y: float, strength: float) -> None:
        layer = Image.new("RGB", self.image.size, (0, 0, 0))
        layer.paste(light.convert("RGB"), (round(x), round(y)))
        a = np.asarray(self.image, dtype=np.float32)
        a[..., :3] += np.asarray(layer, dtype=np.float32) * strength
        self.image = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGBA")


@dataclass(frozen=True)
class Figure:
    """A resident on a scene: who, their pose, the tile they're on, and the seat under them."""

    who: str
    pose: str = "stand"
    x: float = 0.0
    flip: bool = False
    seat: float = 0.0
    """Metres up the seat or mattress, as drawn: the client's `SEAT_M` or `BED_M` less the
    furniture's drop."""


@cache
def doll(who: str) -> tuple[dict, Image.Image]:
    manifest = json.loads((DOLLS / f"{who}.json").read_text())
    return manifest, Image.open(DOLLS / f"{who}.webp").convert("RGBA")


def figure_image(f: Figure, ppm: float) -> tuple[Image.Image, tuple[float, float]]:
    """The figure's frame at `ppm`, and the point the client puts on its spot: its feet, the seat
    under its thighs, or the middle of its underside in bed."""
    manifest, atlas = doll(f.who)
    frame = manifest["frames"][manifest["poses"][f.pose][0]]
    x, y, w, h = frame["frame"]
    image = atlas.crop((x, y, x + w, y + h))
    point = {"lie": frame.get("bed"), "sit": frame.get("seat")}.get(f.pose) or frame["feet"]
    s = ppm / manifest["ppm"]
    image = image.resize((max(1, round(w * s)), max(1, round(h * s))), Image.LANCZOS)
    px, py = point[0] * s, point[1] * s
    if f.flip:
        image, px = ImageOps.mirror(image), image.width - px
    return image, (px, py)


def place_figure(canvas: Canvas, f: Figure, x: float, floor: float, colour) -> None:
    image, (px, py) = figure_image(f, PPM)
    canvas.put(tint(image, colour), x - px, floor - f.seat * PPM - py, (0, 0))


@dataclass
class Scene:
    """A view of a street map: which build draws it, from which tile, how wide and when."""

    street: str
    x0: float
    when: str = DAY
    build: str = "a-new"
    width_m: float = WIDE_M
    city: str | None = None
    """The build whose city and Apex are drawn, if not this scene's own."""
    apex: str | None = "twin"
    apex_at: float = 0.62
    """The Apex's middle as a fraction of the view's width: at parallax 0.1 it barely moves."""
    apex_scale: float = 0.8
    apex_bottom: float = 4.0
    haze: float = HAZE
    figures: list[Figure] = field(default_factory=list)
    stand_ins: dict[str, str] = field(default_factory=dict)
    """A map's building drawn with another's front."""
    extra: list[tuple[str, float, float]] = field(default_factory=list)
    """Furniture the map hasn't got, on the ground: name, tile, cells wide."""
    swap: dict[str, str] = field(default_factory=dict)
    """A furniture piece drawn from another build: key to `build:key`."""
    layers: dict[str, str] = field(default_factory=dict)
    feet_row: int | None = None
    """The row the camera follows, if not the street's: Banyan Row's riverside is 3 rows lower."""
    """A street layer drawn with another street's piece: name to key."""

    @property
    def underground(self) -> bool:
        return views()[self.street].props.get("underground", False)


def street(scene: Scene) -> Image.Image:
    """The street as the client draws it, at `PPM`: sky, the city and the Apex, the far, mid
    and near layers, the ground, ledges and climbs, fronts with their glow, furniture and
    figures. A piece the build hasn't got is left out, except underground, where the game's
    own are drawn."""
    view = views()[scene.street]
    t = dict(TIMES[DAY], glow=0.55) if scene.underground else TIMES[scene.when]
    own = kit(scene.build)
    game = kit("game")
    pieces = game if scene.underground else own
    width, height = round(scene.width_m * PPM), round(VIEW_M * PPM)
    tile = TILE * PPM
    canvas = Canvas((width, height))
    camera = scene.x0 * tile
    row = Counter(view.ground(x) for x in range(view.width)).most_common(1)[0][0]
    lower = ((scene.feet_row or row) - row) * tile
    feet = FEET_AT * height
    origin = feet - row * tile - lower
    layers = {**game.manifest["streets"][scene.street], **scene.layers}
    parallax = game.manifest["parallax"]
    amount, *colour = t["haze"]
    sky = pieces.piece(layers["sky"])
    sky = sky.resize((round(sky.width * height / sky.height), height), Image.LANCZOS)
    canvas.over(tint(repeat(sky, width, round(camera * parallax["sky"])), t["sky"]), 0, 0)
    if not scene.underground:
        backdrop(canvas, scene, t, feet - lower * 0.1, camera)
    for name, (bottom, tall) in PLACES.items():
        if not pieces.has(layers[name]):
            continue
        image = pieces.at(layers[name], PPM, tall)
        fog = {"far": 1.0, "mid": 0.5}.get(name, 0.0)
        strip = repeat(image, width, round(camera * parallax[name]))
        strip = tint(haze(strip, amount * fog, colour), t["tint"])
        canvas.over(strip, 0, feet - lower * parallax[name] - bottom * PPM - strip.height)
    ground(canvas, scene, pieces, t, origin, camera, row)
    for b in sorted(view.buildings, key=lambda b: b.x):
        name = scene.stand_ins.get(b.name, b.name)
        if not pieces.has(f"fronts/{name}"):
            continue
        e = pieces.entry(f"fronts/{name}")
        image = tint(pieces.at(f"fronts/{name}", PPM), t["tint"])
        middle = (b.x + b.w / 2) * tile - camera
        left, top = canvas.put(image, middle, origin + (b.y + b.h) * tile, tuple(e["anchor"]))
        if t["glow"] > 0 and pieces.has(f"glow/{name}"):
            light = pieces.at(f"glow/{name}", PPM)
            canvas.add(light, left, top, t["glow"])
            canvas.add(
                light.filter(ImageFilter.GaussianBlur(0.25 * PPM)), left, top, t["glow"] * 0.8
            )
    placed = [(p.name, p.x, p.y, p.w, p.h) for p in view.furniture]
    placed += [(name, x, row - 1, w, 1) for name, x, w in scene.extra]
    for name, x, y, w, h in placed:
        found = pieces.furniture(name)
        if not found:
            continue
        key, stretched = found
        source = pieces
        if key in scene.swap:
            build, key = scene.swap[key].split(":")
            source = kit(build)
        image = source.at(key, PPM)
        if stretched:
            image = stretch(image, round(w * tile * STRETCH_FILL))
        bottom = origin + (y + h) * tile + FURNITURE_DROP_M * PPM
        canvas.put(tint(image, t["tint"]), (x + w / 2) * tile - camera, bottom)
    for f in scene.figures:
        place_figure(
            canvas, f, (f.x + 0.5) * tile - camera, origin + view.ground(int(f.x)) * tile, t["tint"]
        )
    return canvas.image.convert("RGB")


def backdrop(canvas: Canvas, scene: Scene, t: dict, feet: float, camera: float) -> None:
    """The city behind the street, and the Apex rising over it."""
    k = kit(scene.city or scene.build)
    width = canvas.image.width
    amount, *colour = t["haze"]
    if k.has("layers/city"):
        bottom, tall = CITY
        strip = repeat(k.at("layers/city", PPM, tall), width, round(camera * 0.1))
        lights = city_lights(strip) if scene.when == NIGHT else None
        strip = tint(haze(strip, min(1.0, amount + scene.haze), colour), t["tint"])
        top = feet - bottom * PPM - strip.height
        canvas.over(strip, 0, top)
        if lights is not None:
            canvas.add(lights, 0, top, 1.0)
    key = f"apex/{scene.apex}"
    if scene.apex and k.has(key):
        e = k.entry(key)
        image = k.at(key, PPM, e["height"] * scene.apex_scale)
        fog = min(1.0, amount + scene.haze * 0.6)
        x = width * scene.apex_at
        left, top = canvas.put(
            tint(haze(image, fog, colour), t["tint"]),
            x,
            feet - scene.apex_bottom * PPM,
            shadowed=False,
        )
        if scene.when == NIGHT and "glow" in e:
            light = k.file(e["glow"]).convert("RGB").resize(image.size, Image.LANCZOS)
            canvas.add(light, left, top, 0.7)
            canvas.add(light.filter(ImageFilter.GaussianBlur(0.2 * PPM)), left, top, 0.7)


def city_lights(strip: Image.Image, seed: int = 7) -> Image.Image:
    """Lit windows in the city at night, drawn in code: a sparse grid inside its towers, below
    their tops."""
    solid = np.asarray(strip.getchannel("A")) > 200
    h, w = solid.shape
    tops = np.where(solid.any(axis=0), solid.argmax(axis=0), h)
    rng = np.random.default_rng(seed)
    out = np.zeros((h, w, 3), np.float32)
    across, up = max(3, round(0.35 * PPM)), max(3, round(0.5 * PPM))
    for y in range(0, h, up):
        for x in range(0, w, across):
            if y < tops[x] + 0.6 * PPM or not solid[y, x] or rng.random() > 0.22:
                continue
            colour = (255, 214, 150) if rng.random() < 0.6 else (190, 230, 255)
            out[y : y + max(2, up // 3), x : x + max(2, across // 2)] = colour
    light = Image.fromarray(out.astype(np.uint8)).filter(ImageFilter.GaussianBlur(1))
    return Image.fromarray((np.asarray(light, dtype=np.float32) * 0.7).astype(np.uint8))


def ground(
    canvas: Canvas, scene: Scene, pieces: Kit, t: dict, origin: float, camera: float, row: int
) -> None:
    """The ground strips at each column's own ground row, the ledges above them and the climbs,
    as the client draws them. Ledges, steps and ladders are always the game's own."""
    view = views()[scene.street]
    tile = TILE * PPM
    key = kit("game").manifest["streets"][scene.street]["ground"]
    x = 0
    while x < view.width and pieces.has(key):
        level = view.ground(x)
        end = x
        while end < view.width and view.ground(end) == level:
            end += 1
        strip = pieces.at(key, PPM)
        top = origin + level * tile - GROUND_LIFT_M * PPM
        span = round((end - x) * tile)
        canvas.over(tint(repeat(strip, span, round(x * tile)), t["tint"]), x * tile - camera, top)
        a = np.asarray(strip).reshape(-1, 4)[-strip.width * 12 :]
        fill = a[a[:, 3] > 200, :3].mean(axis=0) * np.array(t["tint"])
        block = Image.new("RGBA", (span, canvas.image.height), (*fill.astype(int), 255))
        canvas.over(block, x * tile - camera, top + strip.height - 1)
        x = end
    game = kit("game")
    roofs = {(x, b.y) for b in view.buildings for x in range(b.x, b.x + b.w)}
    for level in range(row):
        runs: list[list[int]] = []
        for x in range(view.width):
            if (x, level) in view.solid and level < view.ground(x) and (x, level) not in roofs:
                runs[-1].append(x) if runs and x == runs[-1][-1] + 1 else runs.append([x])
        for run in runs:
            image = stretch(game.at("platforms/ledge", PPM), round(len(run) * tile))
            canvas.put(
                tint(image, t["tint"]), run[0] * tile - camera, origin + level * tile, (0, 0)
            )
    for cells, kind in climbs(view):
        foot, head = max(cells, key=lambda c: c[1]), min(cells, key=lambda c: c[1])
        bottom = origin + (foot[1] + 1) * tile
        if kind == "ladder":
            tall = (foot[1] - head[1] + 1) * TILE + LADDER_ABOVE_M
            image = tint(game.at("platforms/ladder", PPM, tall), t["tint"])
            canvas.put(image, (foot[0] + 0.5) * tile - camera, bottom)
        else:
            image = game.at("platforms/steps", PPM, (foot[1] - head[1] + 2) * TILE)
            image = image.resize((round((abs(head[0] - foot[0]) + 2) * tile), image.height))
            if head[0] < foot[0]:
                image = ImageOps.mirror(image)
            canvas.put(
                tint(image, t["tint"]), ((foot[0] + head[0]) / 2 + 0.5) * tile - camera, bottom
            )


def climbs(view: MapView) -> list[tuple[list[tuple[int, int]], str]]:
    """The map's ladders and flights of stairs, each as its cells."""
    left = dict(view.climbable)
    out = []
    while left:
        start, kind = next(iter(left.items()))
        cells, todo = [], [start]
        while todo:
            c = todo.pop()
            if left.get(c) != kind:
                continue
            del left[c]
            cells.append(c)
            todo += [(c[0] + dx, c[1] + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)]
        out.append((cells, kind))
    return out


@cache
def font(size: int) -> ImageFont.FreeTypeFont:
    for path in ("/System/Library/Fonts/Supplemental/Arial.ttf", "/Library/Fonts/Arial.ttf"):
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def captioned(image: Image.Image, text: str, size: int = 40) -> Image.Image:
    out = Image.new("RGB", (image.width, image.height + size + 24), PAPER)
    out.paste(image.convert("RGB"), (0, size + 24))
    ImageDraw.Draw(out).text((16, 10), text, INK, font(size))
    return out


def row(images: list[Image.Image], gap: int = 16, fill=PAPER) -> Image.Image:
    out = Image.new(
        "RGB",
        (sum(i.width for i in images) + gap * (len(images) - 1), max(i.height for i in images)),
        fill,
    )
    x = 0
    for i in images:
        out.paste(i.convert("RGB"), (x, 0), i if i.mode == "RGBA" else None)
        x += i.width + gap
    return out


def column(images: list[Image.Image], gap: int = 16, fill=PAPER) -> Image.Image:
    out = Image.new(
        "RGB",
        (max(i.width for i in images), sum(i.height for i in images) + gap * (len(images) - 1)),
        fill,
    )
    y = 0
    for i in images:
        out.paste(i.convert("RGB"), (0, y))
        y += i.height + gap
    return out


def save(image: Image.Image, name: str, quality: int = 84) -> None:
    IMAGES.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(IMAGES / f"{name}.jpg", quality=quality, optimize=True, subsampling=0)
    print(f"{name}.jpg {image.size}", flush=True)


def grid(
    cells: list[tuple[str, Image.Image]], cell: tuple[int, int], cols: int, fill=(214, 206, 192)
) -> Image.Image:
    """Pieces on a contact sheet, each at most 1:1, with its name."""
    rows = math.ceil(len(cells) / cols)
    out = Canvas((cols * cell[0], rows * (cell[1] + 40)), (*fill, 255))
    for i, (name, image) in enumerate(cells):
        s = min((cell[0] - 24) / image.width, (cell[1] - 24) / image.height, 1.0)
        image = image.resize(
            (max(1, round(image.width * s)), max(1, round(image.height * s))), Image.LANCZOS
        )
        x0, y0 = (i % cols) * cell[0], (i // cols) * (cell[1] + 40)
        out.put(image, x0 + cell[0] / 2, y0 + cell[1] - 8)
        ImageDraw.Draw(out.image).text((x0 + 12, y0 + cell[1] + 6), name, INK, font(24))
    return out.image.convert("RGB")


def half(image: Image.Image) -> Image.Image:
    return image.resize((image.width // 2, image.height // 2), Image.LANCZOS)


def seated(piece: str) -> float:
    return SEAT_M[piece] - FURNITURE_DROP_M


BUILDS = ("a-new", "b-new")
SQUARE = [
    Figure("kofi", "stand", 36.6),
    Figure("lachlan", "stand", 41.2, True),
    Figure("henrietta", "sit", 48, seat=seated("bench")),
    Figure("priya", "sit", 49, True, seat=seated("bench")),
    Figure("desmond", "stand", 50.8),
    Figure("odalys", "sit", 52, seat=seated("bench")),
    Figure("mirela", "stand", 56.2, True),
]
ROOFTOPS = [
    Figure("ingrid", "stand", 12.6),
    Figure("raymond", "sit", 22, seat=seated("bench")),
    Figure("marguerite", "sit", 23, True, seat=seated("bench")),
    Figure("tobias", "stand", 32.6, True),
]


def high_street(build: str, when: str = DAY, **kw) -> Image.Image:
    return street(Scene("high_street", 35.0, when, build, figures=SQUARE, **kw))


def rooftops(build: str, when: str = DAY, **kw) -> Image.Image:
    scene = Scene(
        "rooftops",
        10.0,
        when,
        build,
        figures=ROOFTOPS,
        stand_ins={"print_works": "house_1", "tea_house": "house_1", "laundry": "house_1"},
        extra=[("bench", 22, 2), ("plant", 32, 1), ("plant", 12, 1)],
        layers={"mid": "layers/mid-shophouses"},
        apex_at=0.42,
        **kw,
    )
    return street(scene)


def streets() -> None:
    for build in BUILDS:
        line = LINE_NAMES[build[0]]
        for when, label in ((DAY, "day"), (NIGHT, "night")):
            text = f"High Street, {line}, {label}, 95 px/m"
            save(captioned(high_street(build, when), text), f"{build}-high-street-{label}")
            text = f"The Rooftops, {line}, {label}, 95 px/m (house_1 stands in for its buildings)"
            save(captioned(rooftops(build, when), text), f"{build}-rooftops-{label}")


def dollhouse(build: str, when: str = DAY) -> Image.Image:
    """The coffee shop with its front lifted off, as `preview.dollhouse` draws it, at `PPM`: one
    paper for every floor, the study's furniture where the maps have it, and residents."""
    k = kit(build)
    t = TIMES[when]
    street_view = views()["high_street"]
    facade = next(b for b in street_view.buildings if b.name == "coffee_shop")
    floors = sorted(
        (v for v in views().values() if v.props.get("building") == "coffee_shop"),
        key=lambda v: v.props["floor"],
    )
    tile = TILE * PPM
    width = round((facade.w + 4) * tile)
    height = round((facade.h + 4) * tile)
    x_left = 2 * tile
    ground_y = height - 0.6 * tile
    canvas = Canvas((width, height))
    back = street(Scene("high_street", facade.x - 2, when, build, width_m=width / PPM, apex=None))
    canvas.over(
        back.convert("RGBA").filter(ImageFilter.GaussianBlur(4)),
        0,
        min(0, ground_y - back.height * FEET_AT),
    )
    inside = (1.0, 1.0, 1.0) if when != NIGHT else (0.85, 0.76, 0.62)

    def y_of(view: MapView, at: float) -> float:
        return ground_y - (facade.y + facade.h - (view.props["street_y"] + at)) * tile

    lines = [y_of(view, 3) for view in floors] + [ground_y - facade.h * tile]
    paper = k.piece("papers/plaster-cream")
    s = PPM / k.manifest["ppm"]
    paper = paper.resize((round(paper.width * s), round(paper.height * s)), Image.LANCZOS)
    for n, view in enumerate(floors):
        room_h = round(lines[n] - lines[n + 1])
        room = wall(paper, (round((view.width - 2) * tile), room_h))
        canvas.over(tint(room, inside), x_left + tile, lines[n + 1])
        for wx in (0.3, 0.7):
            canvas.put(
                tint(k.at("platforms/window", PPM), inside),
                x_left + facade.w * tile * wx,
                y_of(view, 1.9),
                (0.5, 0.5),
            )
    frames = {1: (3.5, 10.5), 2: (17.5,)}
    for n, view in enumerate(floors):
        for x in frames.get(n, ()):
            canvas.put(
                tint(k.at("furniture/picture_frame", PPM), inside),
                x_left + x * tile,
                y_of(view, 1.3),
                (0.5, 0.5),
            )
        for _, kind, x, other, ox in view.links:
            if kind != "stairs" or view.props["floor"] > views()[other].props["floor"]:
                continue
            run = abs(ox - x) * tile
            stairs = k.at("platforms/stairs", PPM, 4.4 + 0.9)
            stairs = stairs.resize((round(run + tile * 0.4), stairs.height))
            if ox < x:
                stairs = ImageOps.mirror(stairs)
            canvas.put(
                tint(stairs, inside), x_left + (min(x, ox) + 0.5) * tile + run / 2, y_of(view, 3)
            )
    door = k.at("platforms/door", PPM)
    canvas.put(tint(door, inside), x_left + (facade.w - 2 + 0.5) * tile, y_of(floors[0], 3))
    for view in floors:
        for p in view.furniture:
            found = k.furniture(p.name)
            if not found:
                continue
            key, stretched = found
            image = k.at(key, PPM)
            if stretched:
                image = stretch(image, round(p.w * tile * STRETCH_FILL))
            bottom = y_of(view, p.y + p.h) + FURNITURE_DROP_M * PPM
            canvas.put(tint(image, inside), x_left + (p.x + p.w / 2) * tile, bottom)
    people = {
        0: [
            Figure("kofi", "sit", 11, seat=seated("stool")),
            Figure("odalys", "sit", 13, True, seat=seated("stool")),
            Figure("annelie", "stand", 6),
        ],
        1: [
            Figure("priya", "sit", 1, seat=seated("cafe_table")),
            Figure("lachlan", "sit", 2, True, seat=seated("cafe_table")),
            Figure("desmond", "sit", 9, seat=seated("cafe_table")),
        ],
        2: [
            Figure("henrietta", "lie", 1.5, seat=BED_M - FURNITURE_DROP_M),
            Figure("tobias", "stand", 15.5, True),
        ],
    }
    for n, view in enumerate(floors):
        for f in people[n]:
            place_figure(canvas, f, x_left + (f.x + 0.5) * tile, y_of(view, 3), inside)
    slab = k.piece("papers/slab")
    band_h = max(4, round(0.3 * PPM))
    band = slab.resize((round(slab.width * band_h / slab.height), band_h))
    for y in lines:
        canvas.put(repeat(band, round(facade.w * tile)), x_left, y, (0, 0))
    post = repeat(band, round(facade.h * tile + band_h)).rotate(90, expand=True)
    for side in (x_left, x_left + facade.w * tile - post.width):
        canvas.put(post, side, ground_y + band_h, (0, 1))
    front = k.piece("fronts/coffee_shop")
    e = k.entry("fronts/coffee_shop")
    eaves = front.height * e["anchor"][1] - e["eaves"] * k.manifest["ppm"]
    roof = front.crop((0, 0, front.width, max(1, round(eaves))))
    roof = roof.resize((round(roof.width * s), max(1, round(roof.height * s))), Image.LANCZOS)
    canvas.put(
        tint(roof, t["tint"]),
        x_left + facade.w * tile / 2,
        ground_y - facade.h * tile + 4,
        (e["anchor"][0], 1),
    )
    return canvas.image.convert("RGB")


def wall(paper: Image.Image, size: tuple[int, int]) -> Image.Image:
    """A back wall: its paper tiled, shaded towards the ceiling and corners, as #309's
    preview draws it."""
    tiled = Image.new("RGBA", size)
    for y in range(0, size[1], paper.height):
        for x in range(0, size[0], paper.width):
            tiled.paste(paper, (x, y))
    yy = np.linspace(0, 1, size[1])[:, None]
    xx = np.linspace(0, 1, size[0])[None, :]
    shade = (0.72 + 0.28 * np.clip(yy / 0.35, 0, 1)) * (
        0.88 + 0.12 * np.clip(np.minimum(xx, 1 - xx) / 0.12, 0, 1)
    )
    a = np.asarray(tiled, dtype=np.float32)
    a[..., :3] *= shade[..., None]
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGBA")


def interiors() -> None:
    for build in BUILDS:
        line = LINE_NAMES[build[0]]
        text = f"The coffee shop, {line}, 95 px/m (pieces the study didn't paint are left out)"
        save(captioned(dollhouse(build), text), f"{build}-dollhouse")


def poses() -> None:
    """Each seat and the bed at 95 px/m with residents on them where the client puts them, for
    the game's pieces and each line's: a line at each `SEAT_M` and `BED_M`."""
    rows = []
    for build, label in (("game", "The game now"), *((b, LINE_NAMES[b[0]]) for b in BUILDS)):
        k = kit(build)
        cells = []
        for name, sitters in (
            ("stool", [("kofi", 0.0, False)]),
            ("bench", [("henrietta", -0.32, False), ("priya", 0.32, True)]),
            ("cafe_table", [("odalys", -0.55, False), ("lachlan", 0.55, True)]),
            ("bed", [("desmond", 0.0, False)]),
        ):
            image = k.at(k.furniture(name)[0], PPM)
            width = max(image.width + round(1.6 * PPM), round(2.4 * PPM))
            cell = Canvas((width, round(2.6 * PPM)), (*PAPER, 255))
            floor = cell.image.height - round(0.3 * PPM)
            middle = width / 2
            ImageDraw.Draw(cell.image).line((0, floor, width, floor), (150, 140, 130), 2)
            cell.put(image, middle, floor + FURNITURE_DROP_M * PPM)
            mark = BED_M if name == "bed" else SEAT_M[name]
            y = floor - (mark - FURNITURE_DROP_M) * PPM
            for who, dx, flip in sitters:
                pose = "lie" if name == "bed" else "sit"
                f = Figure(who, pose, 0, flip, mark - FURNITURE_DROP_M)
                place_figure(cell, f, middle + dx * PPM, floor, (1, 1, 1))
            ImageDraw.Draw(cell.image).line((4, y, 40, y), (220, 40, 40), 3)
            ImageDraw.Draw(cell.image).text((8, 8), name, INK, font(26))
            cells.append(cell.image.convert("RGB"))
        rows.append(captioned(row(cells), label, 32))
    save(column(rows), "poses")


def ladder(build: str) -> Image.Image:
    """The village, the metro and the sewers side by side, each 16 m wide at 95 px/m."""
    panels = [
        captioned(
            street(Scene("high_street", 46, DAY, build, 16, figures=SQUARE[2:])), "The village"
        ),
        captioned(
            street(
                Scene(
                    "metro",
                    43,
                    DAY,
                    build,
                    16,
                    figures=[Figure("annelie", "stand", 47), Figure("kofi", "sit", 49, seat=0.45)],
                )
            ),
            "The metro (the game's pieces)",
        ),
        captioned(
            street(Scene("sewers", 10, DAY, build, 16, figures=[Figure("tobias", "stand", 19)])),
            "The sewers (the game's pieces)",
        ),
    ]
    return row(panels, 0)


def ladders() -> None:
    for build in BUILDS:
        save(ladder(build), f"{build}-grime-ladder")


def entrance() -> None:
    """Banyan Row's metro entrance clean in each line, and a little dirty as the metro is."""
    panels = []
    for build, key, label in (
        ("a-new", "furniture/metro_entrance", "Clean, A"),
        ("b-new", "furniture/metro_entrance", "Clean, B"),
        ("a-new", "furniture/metro_entrance-dirty", "A little dirty, the metro's style"),
    ):
        scene = Scene(
            "banyan_row",
            55.5,
            DAY,
            build,
            12,
            figures=[
                Figure("ingrid", "stand", 59.5),
                Figure("raymond", "sit", 57, seat=seated("bench")),
            ],
            feet_row=19,
            swap={"furniture/metro_entrance": f"{build}:{key}"},
            layers={"mid": "layers/mid-shophouses", "near": "layers/near-walls"},
            apex_at=0.8,
        )
        panels.append(captioned(street(scene), label))
    save(row(panels, 0), "metro-entrance")


def apexes() -> None:
    """The three silhouettes in each line, by day and night, and the twin in three places."""
    for when, label in ((DAY, "day"), (NIGHT, "night")):
        rows = []
        for build in BUILDS:
            cells = [
                captioned(
                    half(street(Scene("high_street", 44, when, build, 16, apex=name, apex_at=0.5))),
                    name,
                    30,
                )
                for name in ("twin", "trio", "helix")
            ]
            rows.append(captioned(row(cells, 0), LINE_NAMES[build[0]], 32))
        save(column(rows), f"apex-{label}")
    places = [
        ("1. Over the square, as in the street pictures", dict()),
        (
            "2. Over the square, bigger, rising past the top of the view",
            dict(apex_at=0.62, apex_scale=1.25, apex_bottom=2.0),
        ),
        (
            "3. Off to the right, smaller and further away",
            dict(apex_at=0.86, apex_scale=0.8, apex_bottom=4.0),
        ),
        (
            "4. Behind the coffee shop, peeking over its roof",
            dict(apex_at=0.18, apex_scale=1.0, apex_bottom=3.0),
        ),
    ]
    save(
        column([captioned(half(high_street("a-new", **kw)), text, 30) for text, kw in places]),
        "apex-places",
    )


def hazes() -> None:
    cells = []
    for amount in (0.15, 0.35, 0.55):
        image = half(high_street("a-new", haze=amount))
        cells.append(captioned(image, f"City haze {amount}", 30))
    save(column(cells), "haze")


def references() -> None:
    from study import DOCS

    cells = []
    for label, folder in (
        ("#326's clean cartoon", "style-study-2/references/cartoon"),
        ("New, line A", "village-comic-study/references/a"),
        ("New, line B", "village-comic-study/references/b"),
    ):
        pictures = [
            Image.open(DOCS / folder / f"{scene}.jpg").convert("RGB")
            for scene in ("street", "interior")
        ]
        pictures = [
            p.resize((800, round(p.height * 800 / p.width)), Image.LANCZOS) for p in pictures
        ]
        cells.append(captioned(column(pictures, 8), label, 30))
    save(row(cells), "references")
    from references import REJECTED

    cells = [
        (f"{name}: {why}", Image.open(OUT / "references" / f"{name}.png").convert("RGBA"))
        for name, why in REJECTED.items()
    ]
    save(grid(cells, (480, 300), 4), "references-rejected")


def pieces_sheets() -> None:
    for build in BUILDS:
        k = kit(build)
        line = LINE_NAMES[build[0]]
        fronts = []
        for building in ("house_1", "coffee_shop", "maker_space"):
            day, night = k.piece(f"fronts/{building}"), night_front(k, building)
            fronts.append((building, row([day, night], 40, (214, 206, 192))))
        save(
            captioned(grid(fronts, (1500, 720), 1), f"Fronts by day and at night, {line}"),
            f"{build}-fronts",
        )
        keys = [
            key for key in k.manifest["pieces"] if key.split("/")[0] in ("furniture", "platforms")
        ]
        cells = [(key.split("/")[1], k.piece(key)) for key in keys]
        save(
            captioned(grid(cells, (340, 340), 6), f"Furniture and platforms, {line}"),
            f"{build}-furniture",
        )
        keys = [key for key in k.manifest["pieces"] if key.split("/")[0] in ("layers", "papers")]
        cells = [(key.split("/")[1], k.piece(key)) for key in keys]
        save(captioned(grid(cells, (760, 420), 3), f"Layers and papers, {line}"), f"{build}-layers")


def night_front(k: Kit, building: str) -> Image.Image:
    day = k.piece(f"fronts/{building}")
    lit = Canvas(day.size, (0, 0, 0, 0))
    lit.over(tint(day, TIMES[NIGHT]["tint"]), 0, 0)
    lit.add(k.piece(f"glow/{building}"), 0, 0, 1.0)
    lit.image.putalpha(day.getchannel("A"))
    return lit.image


def compared() -> None:
    """The pieces #326's references painted beside the new references', and High Street with
    them."""
    keys = (
        "layers/sky",
        "layers/city",
        "layers/mid-shophouses",
        "layers/ground-street",
        "furniture/sofa",
        "furniture/bed",
        "furniture/bench",
        "furniture/kitchen",
    )
    rows = []
    for build in ("a-new", "a-326", "b-new", "b-326"):
        k = kit(build)
        refs = "new references" if build.endswith("new") else "#326 references"
        label = f"{LINE_NAMES[build[0]]}, {refs}"
        rows.append(
            captioned(
                grid([(key.split("/")[1], k.piece(key)) for key in keys], (400, 300), 8), label, 30
            )
        )
    save(column(rows), "compare-references")
    streets = []
    for line in "ab":
        for refs, chain in (("new", f"{line}-new"), ("#326", f"{line}-326+{line}-new")):
            image = half(high_street(chain))
            streets.append(captioned(image, f"{LINE_NAMES[line]}, {refs} references", 30))
    save(column([row(streets[:2]), row(streets[2:])]), "compare-references-street")


def numbers() -> None:
    """Paintings and seconds from out/timings.jsonl, by kind of piece."""
    rows: dict[str, list[float]] = {}
    loads = []
    for line in (OUT / "timings.jsonl").read_text().splitlines():
        entry = json.loads(line)
        if entry["event"] == "load":
            loads.append(entry["seconds"])
            continue
        rows.setdefault(entry["key"].split("/")[0], []).append(entry["seconds"])
    total = sum(sum(v) for v in rows.values())
    for kind, seconds in sorted(rows.items()):
        mean, minutes = sum(seconds) / len(seconds), sum(seconds) / 60
        print(f"| {kind} | {len(seconds)} | {mean:.0f} | {minutes:.1f} |")
    print(f"| all | {sum(len(v) for v in rows.values())} | | {total / 60:.1f} |")
    print(f"{len(loads)} model loads, {sum(loads) / 60:.1f} min")


def main(steps: list[str]) -> None:
    every = {
        "references": references,
        "pieces": pieces_sheets,
        "compared": compared,
        "streets": streets,
        "interiors": interiors,
        "poses": poses,
        "ladders": ladders,
        "entrance": entrance,
        "apex": apexes,
        "haze": hazes,
        "numbers": numbers,
    }
    for step in steps or list(every):
        every[step]()


if __name__ == "__main__":
    main(args())
