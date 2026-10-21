"""#309's `preview.street_scene` at `scale` times its pixels, as the client draws the street on a
screen with that pixel ratio. At a scale of 1 it is #309's own function."""

from collections import Counter

from PIL import Image, ImageDraw, ImageFilter, ImageOps

from simile.papercraft import preview
from simile.papercraft.preview import Canvas, at, furnish, haze, piece, repeat, tint
from simile.papercraft.village import TILE


def street_scene(view, when: str, x0: float, width: int, scale: int = 1) -> Image.Image:
    """`view`'s street from tile `x0`, `width` px wide, at `scale` times `SCENE_PPM`: a copy of
    #309's with its pixel sizes multiplied by `scale`."""
    if scale == 1:
        return preview.street_scene(view, when, x0, width)
    s = scale
    ppm = preview.SCENE_PPM * s
    H = preview.H * s
    m = preview.manifest()
    t = m["times"][when]
    tile = TILE * ppm
    ground_row = Counter(view.ground(x) for x in range(view.width)).most_common(1)[0][0]
    camera = x0 * tile
    canvas = Canvas((width, H))

    def put(image, x, y, anchor=(0.5, 1.0), offset=(7, 5), opacity=0.38, blur=6.0):
        shift = (offset[0] * s, offset[1] * s) if offset else None
        return canvas.put(image, x, y, anchor, shift, opacity, blur * s)

    lowest = max(view.ground(x) for x in range(view.width))
    ground_y = H - 150 * s - (lowest - ground_row) * tile
    origin = ground_y - ground_row * tile
    layers = m["streets"][view.id]
    sky = piece(layers["sky"])
    sky = sky.resize((round(sky.width * H / sky.height), H), Image.Resampling.LANCZOS)
    canvas.over(tint(repeat(sky, width, round(camera * 0.04)), t["sky"]), 0, 0)
    amount, *colour = t["haze"]
    for name, height, lift, fog in (("far", 230, 300, 1.0), ("mid", 250, 110, 0.6)):
        image = piece(layers[name])
        image = image.resize((round(image.width * height * s / image.height), height * s))
        offset = round(camera * m["parallax"][name])
        strip = tint(haze(repeat(image, width, offset), amount * fog, colour), t["tint"])
        put(strip, 0, ground_y - lift * s, (0, 1), (4, 3), 0.25)
    near = at(layers["near"], ppm)
    offset = round(camera * m["parallax"]["near"])
    put(tint(repeat(near, width, offset), t["tint"]), 0, ground_y + 4 * s, (0, 1), (5, 3), 0.3)
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
        top = origin + row * tile - 14 * s
        strip = at(key, ppm, max(1.0, (H - top) / ppm))
        span = round((end - x) * tile)
        canvas.over(tint(repeat(strip, span), t["tint"]), x * tile - camera, top)
        x = end
    for y in range(ground_row):
        xs = sorted(x for (x, row) in view.solid if row == y)
        runs = [[xs[0]]] if xs else []
        for x in xs[1:]:
            runs[-1].append(x) if x == runs[-1][-1] + 1 else runs.append([x])
        for run in runs:
            ledge = at("platforms/ledge", ppm)
            ledge = ledge.resize((round(len(run) * tile), ledge.height))
            put(tint(ledge, t["tint"]), run[0] * tile - camera, origin + y * tile, (0, 0))
    steps = sorted(c for c, kind in view.climbable.items() if kind == "stairs")
    if steps:
        (sx0, sy0), (sx1, sy1) = steps[0], steps[-1]
        image = at("platforms/steps", ppm, (abs(sy1 - sy0) + 2) * TILE)
        image = image.resize((round((abs(sx1 - sx0) + 2) * tile), image.height))
        if (sx1 - sx0) * (sy1 - sy0) > 0:
            image = ImageOps.mirror(image)
        bottom = origin + (max(sy0, sy1) + 2) * tile
        put(tint(image, t["tint"]), ((sx0 + sx1) / 2 + 0.5) * tile - camera, bottom, offset=None)
    for (x, y), kind in sorted(view.climbable.items()):
        if kind == "ladder":
            image = at("platforms/ladder", ppm, TILE * 1.2)
            put(tint(image, t["tint"]), (x + 0.5) * tile - camera, origin + (y + 1) * tile)
    for b in sorted(view.buildings, key=lambda b: b.x):
        key = m["buildings"][b.name]["front"]
        e = preview.entry(key)
        image = at(key, ppm)
        middle = (b.x + b.w / 2) * tile - camera
        bottom = origin + (b.y + b.h) * tile
        left, top = put(tint(image, t["tint"]), middle, bottom + 3 * s, e["anchor"], (9, 6), 0.3)
        if t["glow"] > 0:
            glow = at(m["buildings"][b.name]["glow"], ppm)
            canvas.add(glow, left, top, t["glow"])
            canvas.add(glow.filter(ImageFilter.GaussianBlur(10 * s)), left, top, t["glow"] * 0.8)
    for p in view.furniture:
        if p.name not in m["furniture"]:
            continue
        image = furnish(p, ppm)
        bottom = origin + (p.y + p.h) * tile
        put(tint(image, t["tint"]), (p.x + p.w / 2) * tile - camera, bottom + 4 * s)
        if p.name == "lamp" and t["glow"] > 0:
            glow = Image.new("RGB", (round(tile * 4), round(tile * 4)), (0, 0, 0))
            ring = (glow.width / 4, glow.height / 4, glow.width * 3 / 4, glow.height * 3 / 4)
            ImageDraw.Draw(glow).ellipse(ring, (255, 214, 140))
            glow = glow.filter(ImageFilter.GaussianBlur(tile / 2))
            cx, cy = (p.x + 0.5) * tile - camera, bottom - image.height - glow.height / 2
            canvas.add(glow, cx - glow.width / 2, cy, t["glow"])
    front = at(layers["foreground"], ppm * 1.4).filter(ImageFilter.GaussianBlur(3 * s))
    shade = [c * 0.55 for c in t["tint"]]
    offset = round(camera * m["parallax"]["foreground"])
    canvas.put(tint(repeat(front, width, offset), shade), 0, H + 70 * s, (0, 1), None)
    return canvas.image.convert("RGB")


def ground_line(view, scale: int = 1) -> float:
    """Where `street_scene` puts the street's feet line."""
    tile = TILE * preview.SCENE_PPM * scale
    row = Counter(view.ground(x) for x in range(view.width)).most_common(1)[0][0]
    lowest = max(view.ground(x) for x in range(view.width))
    return preview.H * scale - 150 * scale - (lowest - row) * tile
