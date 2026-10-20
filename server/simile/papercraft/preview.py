"""Contact sheets of the committed pieces, and streets and dollhouses composed from them on the
side-view maps, for people to look at. Part 5 draws the game's own scenes; these are Python
composites, and the tints are the manifest's suggestions."""

import json
import math
from collections import Counter
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from simile.papercraft.build import CONTENT, MANIFEST
from simile.papercraft.layout import STREET_DIR, _objects, _props, _tiles
from simile.papercraft.village import TILE

W, H = 1600, 900
CREAM = (238, 232, 220)
TIMES = ("morning", "afternoon", "evening", "night")


@cache
def manifest() -> dict:
    return json.loads((CONTENT / MANIFEST).read_text())


@cache
def piece(key: str) -> Image.Image:
    return Image.open(CONTENT / manifest()["pieces"][key]["file"]).convert("RGBA")


def entry(key: str) -> dict:
    return manifest()["pieces"][key]


def at(key: str, ppm: float, height: float | None = None) -> Image.Image:
    """A piece scaled to `ppm` px a metre, or to `height` metres."""
    image = piece(key)
    h = max(1, round((height or entry(key)["height"]) * ppm))
    w = max(1, round(image.width * h / image.height))
    return image.resize((w, h), Image.Resampling.LANCZOS)


def furnish(p: "Placed", ppm: float) -> Image.Image:
    """A map's piece of furniture at scale, a run stretched to its cells' width."""
    entry_ = manifest()["furniture"][p.name]
    image = at(entry_["piece"], ppm)
    if entry_.get("stretch"):
        image = stretch(image, round(p.w * TILE * ppm * 0.96))
    return image


def stretch(image: Image.Image, width: int, cap: float = 0.15) -> Image.Image:
    """`image` made `width` wide by repeating its middle and keeping its ends."""
    w, h = image.size
    c = round(w * cap)
    middle = image.crop((c, 0, w - c, h))
    out = Image.new("RGBA", (max(width, 2 * c), h), (0, 0, 0, 0))
    for x in range(c, out.width - c, middle.width):
        out.paste(middle.crop((0, 0, min(middle.width, out.width - c - x), h)), (x, 0))
    out.paste(image.crop((0, 0, c, h)), (0, 0))
    out.paste(image.crop((w - c, 0, w, h)), (out.width - c, 0))
    return out


def tint(image: Image.Image, rgb) -> Image.Image:
    a = np.asarray(image.convert("RGBA"), dtype=np.float32)
    a[..., :3] *= np.array(rgb[:3])
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGBA")


def haze(image: Image.Image, amount: float, colour) -> Image.Image:
    a = np.asarray(image.convert("RGBA"), dtype=np.float32)
    a[..., :3] = a[..., :3] * (1 - amount) + np.array(colour) * amount
    return Image.fromarray(a.astype(np.uint8), "RGBA")


def repeat(image: Image.Image, width: int, offset: int = 0) -> Image.Image:
    out = Image.new("RGBA", (max(1, width), image.height), (0, 0, 0, 0))
    for x in range(-(offset % image.width), width, image.width):
        out.alpha_composite(image, (x, 0)) if x >= 0 else out.paste(image, (x, 0), image)
    return out


def shadow(image: Image.Image, blur: float, opacity: float) -> Image.Image:
    pad = round(blur * 3)
    s = Image.new("RGBA", (image.width + 2 * pad, image.height + 2 * pad), (0, 0, 0, 0))
    alpha = Image.new("L", s.size, 0)
    alpha.paste(image.getchannel("A").point(lambda v: round(v * opacity)), (pad, pad))
    s.putalpha(alpha.filter(ImageFilter.GaussianBlur(blur)))
    return s


class Canvas:
    def __init__(self, size: tuple[int, int], fill=(0, 0, 0, 255)) -> None:
        self.image = Image.new("RGBA", size, fill)

    def over(self, image: Image.Image, x: float, y: float) -> None:
        layer = Image.new("RGBA", self.image.size, (0, 0, 0, 0))
        layer.paste(image, (round(x), round(y)))
        self.image = Image.alpha_composite(self.image, layer)

    def put(self, image, x, y, anchor=(0.5, 1.0), offset=(7, 5), opacity=0.38, blur=6.0):
        left, top = x - image.width * anchor[0], y - image.height * anchor[1]
        if offset and opacity > 0:
            s = shadow(image, blur, opacity)
            pad = (s.width - image.width) / 2
            self.over(s, left - pad + offset[0], top - pad + offset[1])
        self.over(image, left, top)
        return left, top

    def add(self, light: Image.Image, x: float, y: float, strength: float) -> None:
        layer = Image.new("RGB", self.image.size, (0, 0, 0))
        layer.paste(light.convert("RGB"), (round(x), round(y)))
        a = np.asarray(self.image, dtype=np.float32)
        a[..., :3] += np.asarray(layer, dtype=np.float32) * strength
        self.image = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGBA")


def grid(cells: list[tuple[str, Image.Image]], cell: tuple[int, int], cols: int) -> Image.Image:
    rows = math.ceil(len(cells) / cols)
    out = Canvas((cols * cell[0], rows * (cell[1] + 28)), (214, 200, 182, 255))
    font = ImageFont.load_default(size=16)
    for i, (name, image) in enumerate(cells):
        s = min((cell[0] - 20) / image.width, (cell[1] - 20) / image.height, 1.0)
        size = (max(1, round(image.width * s)), max(1, round(image.height * s)))
        image = image.resize(size, Image.Resampling.LANCZOS)
        x0, y0 = (i % cols) * cell[0], (i // cols) * (cell[1] + 28)
        out.put(image, x0 + cell[0] / 2, y0 + cell[1] - 6, offset=(5, 4))
        ImageDraw.Draw(out.image).text((x0 + 8, y0 + cell[1] + 4), name, (60, 50, 40), font)
    return out.image.convert("RGB")


def contact_sheets() -> dict[str, Image.Image]:
    groups: dict[str, list[str]] = {}
    for key in manifest()["pieces"]:
        groups.setdefault(key.split("/")[0], []).append(key)
    sheets = {}
    for group in ("layers", "papers", "furniture", "platforms"):
        wide = group in ("layers", "papers")
        cells = [(k.split("/", 1)[1], piece(k)) for k in groups.get(group, [])]
        sheets[group] = grid(cells, (380, 260) if wide else (240, 240), 5 if wide else 7)
    night = manifest()["times"]["night"]["tint"]
    fronts = []
    for key in groups.get("fronts", []):
        day = piece(key)
        lit = Canvas(day.size, (0, 0, 0, 0))
        lit.over(tint(day, night), 0, 0)
        lit.add(piece(key.replace("fronts/", "glow/")), 0, 0, 1.0)
        lit.image.putalpha(day.getchannel("A"))
        pair = Image.new("RGBA", (day.width * 2 + 40, day.height), (0, 0, 0, 0))
        pair.paste(day, (0, 0))
        pair.paste(lit.image, (day.width + 40, 0))
        fronts.append((key.split("/")[1], pair))
    sheets["fronts"] = grid(fronts, (640, 420), 3)
    return sheets


@dataclass
class Placed:
    name: str
    x: int
    y: int
    w: int
    h: int


@dataclass
class MapView:
    """What the previews need from one side-view map."""

    id: str
    width: int
    height: int
    props: dict
    solid: set[tuple[int, int]] = field(default_factory=set)
    furniture: list[Placed] = field(default_factory=list)
    buildings: list[Placed] = field(default_factory=list)
    locations: list[Placed] = field(default_factory=list)
    paintings: list[Placed] = field(default_factory=list)
    links: list[tuple[str, str, int, str, int]] = field(default_factory=list)
    """(id, kind, x here, other map, x there) for each stairs, ladder or lift link."""
    climbable: dict[tuple[int, int], str] = field(default_factory=dict)

    def ground(self, x: int) -> int:
        """The top of the solid ground column `x` stands on, under any ledges."""
        y = self.height
        while (x, y - 1) in self.solid:
            y -= 1
        return y


def read_views(directory: Path = STREET_DIR) -> dict[str, MapView]:
    views = {}
    for path in sorted(directory.rglob("*.tmj")):
        data = json.loads(path.read_text())
        view = MapView(path.stem, data["width"], data["height"], _props(data))
        names = {t["id"] + 1: _props(t)["name"] for t in data["tilesets"][0].get("tiles", [])}
        for layer in data["layers"]:
            if layer["type"] != "tilelayer":
                continue
            for i, gid in enumerate(layer["data"]):
                cell = (i % data["width"], i // data["width"])
                if layer["name"] == "solid" and gid:
                    view.solid.add(cell)
                if layer["name"] == "climbable" and gid:
                    view.climbable[cell] = names[gid]
        for name, out in (
            ("furniture", view.furniture),
            ("buildings", view.buildings),
            ("locations", view.locations),
        ):
            out += [Placed(o["name"], *_tiles(o)) for o in _objects(data, name)]
        view.paintings += [
            Placed(o["name"], *_tiles(o))
            for o in _objects(data, "interactables")
            if o["type"] == "painting"
        ]
        for o in _objects(data, "doors"):
            p = _props(o)
            if p.get("kind", "door") != "door":
                view.links.append((o["name"], p["kind"], _tiles(o)[0], p["to_map"], p["to_x"]))
        views[view.id] = view
    return views


SCENE_PPM = 40


def street_scene(view: MapView, when: str, x0: float = 0, width: int | None = None) -> Image.Image:
    """`view`'s street from tile `x0`, `width` px wide, at `SCENE_PPM`."""
    m = manifest()
    t = m["times"][when]
    tile = TILE * SCENE_PPM
    width = width or round(view.width * tile - x0 * tile)
    ground_row = Counter(view.ground(x) for x in range(view.width)).most_common(1)[0][0]
    camera = x0 * tile
    canvas = Canvas((width, H))
    lowest = max(view.ground(x) for x in range(view.width))
    ground_y = H - 150 - (lowest - ground_row) * tile
    origin = ground_y - ground_row * tile
    layers = m["streets"][view.id]
    sky = piece(layers["sky"])
    sky = sky.resize((round(sky.width * H / sky.height), H), Image.Resampling.LANCZOS)
    canvas.over(tint(repeat(sky, width, round(camera * 0.04)), t["sky"]), 0, 0)
    amount, *colour = t["haze"]
    for name, height, lift, fog in (("far", 230, 300, 1.0), ("mid", 250, 110, 0.6)):
        image = piece(layers[name])
        image = image.resize((round(image.width * height / image.height), height))
        offset = round(camera * m["parallax"][name])
        strip = tint(haze(repeat(image, width, offset), amount * fog, colour), t["tint"])
        canvas.put(strip, 0, ground_y - lift, (0, 1), (4, 3), 0.25)
    near = at(layers["near"], SCENE_PPM)
    offset = round(camera * m["parallax"]["near"])
    canvas.put(tint(repeat(near, width, offset), t["tint"]), 0, ground_y + 4, (0, 1), (5, 3), 0.3)
    places = {p.name: p for p in view.locations}

    def ground_key(x: int) -> str:
        if view.ground(x) > ground_row:
            return m["grounds"]["riverside"]
        for place in ("square", "park"):
            a = places.get(place)
            if a and a.x <= x < a.x + a.w:
                return m["grounds"][place]
        return layers["ground"]

    x = 0
    while x < view.width:
        key, row = ground_key(x), min(view.ground(x), view.height)
        end = x
        while end < view.width and ground_key(end) == key and view.ground(end) == row:
            end += 1
        top = origin + row * tile - 14
        strip = at(key, SCENE_PPM, max(1.0, (H - top) / SCENE_PPM))
        span = round((end - x) * tile)
        canvas.over(tint(repeat(strip, span), t["tint"]), x * tile - camera, top)
        x = end
    for y in range(ground_row):
        xs = sorted(x for (x, row) in view.solid if row == y)
        runs = [[xs[0]]] if xs else []
        for x in xs[1:]:
            runs[-1].append(x) if x == runs[-1][-1] + 1 else runs.append([x])
        for run in runs:
            ledge = at("platforms/ledge", SCENE_PPM)
            ledge = ledge.resize((round(len(run) * tile), ledge.height))
            canvas.put(tint(ledge, t["tint"]), run[0] * tile - camera, origin + y * tile, (0, 0))
    steps = sorted(c for c, kind in view.climbable.items() if kind == "stairs")
    if steps:
        (x0, y0), (x1, y1) = steps[0], steps[-1]
        image = at("platforms/steps", SCENE_PPM, (abs(y1 - y0) + 2) * TILE)
        image = image.resize((round((abs(x1 - x0) + 2) * tile), image.height))
        if (x1 - x0) * (y1 - y0) > 0:
            image = ImageOps.mirror(image)
        bottom = origin + (max(y0, y1) + 2) * tile
        canvas.put(
            tint(image, t["tint"]),
            ((x0 + x1) / 2 + 0.5) * tile - camera,
            bottom,
            offset=None,
        )
    for (x, y), kind in sorted(view.climbable.items()):
        if kind == "ladder":
            image = at("platforms/ladder", SCENE_PPM, TILE * 1.2)
            canvas.put(tint(image, t["tint"]), (x + 0.5) * tile - camera, origin + (y + 1) * tile)
    for b in sorted(view.buildings, key=lambda b: b.x):
        key = m["buildings"][b.name]["front"]
        e = entry(key)
        image = at(key, SCENE_PPM)
        middle = (b.x + b.w / 2) * tile - camera
        bottom = origin + (b.y + b.h) * tile
        left, top = canvas.put(tint(image, t["tint"]), middle, bottom + 3, e["anchor"], (9, 6), 0.3)
        if t["glow"] > 0:
            glow = at(m["buildings"][b.name]["glow"], SCENE_PPM)
            canvas.add(glow, left, top, t["glow"])
            canvas.add(glow.filter(ImageFilter.GaussianBlur(10)), left, top, t["glow"] * 0.8)
    for p in view.furniture:
        if p.name not in m["furniture"]:
            continue
        image = furnish(p, SCENE_PPM)
        bottom = origin + (p.y + p.h) * tile
        canvas.put(tint(image, t["tint"]), (p.x + p.w / 2) * tile - camera, bottom + 4)
        if p.name == "lamp" and t["glow"] > 0:
            glow = Image.new("RGB", (round(tile * 4), round(tile * 4)), (0, 0, 0))
            ring = (glow.width / 4, glow.height / 4, glow.width * 3 / 4, glow.height * 3 / 4)
            ImageDraw.Draw(glow).ellipse(ring, (255, 214, 140))
            glow = glow.filter(ImageFilter.GaussianBlur(tile / 2))
            cx, cy = (p.x + 0.5) * tile - camera, bottom - image.height - glow.height / 2
            canvas.add(glow, cx - glow.width / 2, cy, t["glow"])
    front = at(layers["foreground"], SCENE_PPM * 1.4).filter(ImageFilter.GaussianBlur(3))
    shade = [c * 0.55 for c in t["tint"]]
    offset = round(camera * m["parallax"]["foreground"])
    canvas.put(tint(repeat(front, width, offset), shade), 0, H + 70, (0, 1), None)
    return canvas.image.convert("RGB")


def wall(key: str, size: tuple[int, int], ppm: float) -> Image.Image:
    """A room's back wall: its paper tiled at scale, shaded towards the ceiling and corners."""
    paper = piece(key)
    s = ppm / manifest()["ppm"]
    paper = paper.resize((max(1, round(paper.width * s)), max(1, round(paper.height * s))))
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


def dollhouse(views: dict[str, MapView], building: str, when: str = "afternoon") -> Image.Image:
    """`building` with its front lifted off: each floor's back wall, slab and furniture from its
    own map, stairs and lifts between them, and its roof, in front of its street."""
    m = manifest()
    t = m["times"][when]
    entry_ = m["buildings"][building]
    street = views[entry_["street"]]
    facade = next(b for b in street.buildings if b.name == building)
    floors = sorted(
        (v for v in views.values() if v.props.get("building") == building),
        key=lambda v: v.props["floor"],
    )
    rows = facade.h + 3
    ppm = min(W * 0.8 / (facade.w * TILE), H * 0.84 / (rows * TILE))
    tile = TILE * ppm
    x_left = (W - facade.w * tile) / 2
    ground_y = H - 60
    span = W / (TILE * SCENE_PPM)
    x0 = min(max(0, facade.x + facade.w / 2 - span / 2), max(0, street.width - span))
    backdrop = street_scene(street, when, x0, W)
    canvas = Canvas((W, H))
    canvas.over(backdrop.convert("RGBA").filter(ImageFilter.GaussianBlur(3)), 0, 0)
    inside = (1.0, 1.0, 1.0) if when != "night" else (0.85, 0.76, 0.62)

    def y_of(view: MapView, row: float) -> float:
        street_row = view.props["street_y"] + row
        return ground_y - (facade.y + facade.h - street_row) * tile

    slab = piece(m["slab"])
    lines = [y_of(view, 3) for view in floors] + [ground_y - facade.h * tile]
    for n, view in enumerate(floors):
        paper = entry_["floors"][n]
        room_h = round(lines[n] - lines[n + 1])
        room = tint(wall(paper, (round((view.width - 2) * tile), room_h), ppm), inside)
        canvas.over(room, x_left + tile, lines[n + 1])
        for wx in (0.3, 0.7):
            canvas.put(
                tint(at("platforms/window", ppm), inside),
                x_left + facade.w * tile * wx,
                y_of(view, 1.9),
                (0.5, 0.5),
                (4, 3),
                0.3,
            )
    for view in floors:
        for _, kind, x, other, ox in view.links:
            if view.props["floor"] > views[other].props["floor"]:
                continue
            if kind == "ladder":
                ladder = tint(at("platforms/ladder", ppm, 4 * TILE + 0.4), inside)
                canvas.put(ladder, x_left + (x + 0.5) * tile, y_of(view, 3), offset=(5, 3))
            if kind != "stairs":
                continue
            x0 = x_left + (min(x, ox) + 0.5) * tile
            run = abs(ox - x) * tile
            stairs = at("platforms/stairs", ppm, 4.4 + 0.9)
            stairs = stairs.resize((round(run + tile * 0.4), stairs.height))
            if ox < x:
                stairs = ImageOps.mirror(stairs)
            canvas.put(tint(stairs, inside), x0 + run / 2, y_of(view, 3), (0.5, 1), (6, 4))
    frame = "furniture/picture_frame"
    for view in floors:
        for p in view.paintings if frame in m["pieces"] else []:
            image = tint(at(frame, ppm), inside)
            middle = y_of(view, p.y + p.h / 2)
            canvas.put(image, x_left + (p.x + p.w / 2) * tile, middle, (0.5, 0.5), (4, 3), 0.3)
        for p in view.furniture:
            if p.name not in m["furniture"]:
                continue
            image = tint(furnish(p, ppm), inside)
            if p.name == "lift":
                shaft = tint(at("platforms/lift_shaft", ppm, 4.4), inside)
                canvas.put(shaft, x_left + (p.x + p.w / 2) * tile, y_of(view, 3), offset=None)
            if p.y + p.h <= 1:
                middle = y_of(view, p.y + p.h / 2)
                canvas.put(image, x_left + (p.x + p.w / 2) * tile, middle, (0.5, 0.5), (4, 3), 0.3)
                continue
            canvas.put(
                image,
                x_left + (p.x + p.w / 2) * tile,
                y_of(view, p.y + p.h) + 3,
                offset=(7, 3),
                opacity=0.4,
            )
    band_h = max(4, round(0.3 * ppm))
    band = slab.resize((round(slab.width * band_h / slab.height), band_h))
    for y in lines:
        canvas.put(repeat(band, round(facade.w * tile)), x_left, y, (0, 0), (0, 5), 0.35)
    post = repeat(band, round(facade.h * tile + band_h)).rotate(90, expand=True)
    for side in (x_left, x_left + facade.w * tile - post.width):
        canvas.put(post, side, ground_y + band_h, (0, 1), (5, 0), 0.3)
    front = piece(entry_["front"])
    e = entry(entry_["front"])
    s = ppm / m["ppm"]
    eaves_y = front.height * e["anchor"][1] - e["eaves"] * m["ppm"]
    roof = front.crop((0, 0, front.width, max(1, round(eaves_y))))
    roof = roof.resize((round(roof.width * s), max(1, round(roof.height * s))))
    canvas.put(
        tint(roof, t["tint"]),
        x_left + facade.w * tile / 2,
        ground_y - facade.h * tile + 4,
        (e["anchor"][0], 1),
        (0, 8),
    )
    return canvas.image.convert("RGB")


def times_grid(view: MapView, x0: float) -> Image.Image:
    out = Image.new("RGB", (W, H))
    for i, when in enumerate(TIMES):
        frame = street_scene(view, when, x0, W).resize((W // 2, H // 2), Image.Resampling.LANCZOS)
        out.paste(frame, ((i % 2) * W // 2, (i // 2) * H // 2))
    return out


def preview(out: Path, maps: Path = STREET_DIR) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    written = []

    def save(image: Image.Image, name: str) -> None:
        path = out / f"{name}.jpg"
        image.convert("RGB").save(path, quality=88, optimize=True)
        written.append(path)

    for group, sheet in contact_sheets().items():
        save(sheet, f"sheet-{group}")
    views = read_views(maps)
    for street in manifest()["streets"]:
        view = views[street]
        save(street_scene(view, "afternoon"), f"street-{street}")
        save(street_scene(view, "night"), f"street-{street}-night")
        save(times_grid(view, 0), f"times-{street}")
    for building, b in manifest()["buildings"].items():
        if b["floors"]:
            save(dollhouse(views, building), f"dollhouse-{building}")
            save(dollhouse(views, building, "night"), f"dollhouse-{building}-night")
    return written
