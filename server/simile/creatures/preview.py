"""The preview sheet for judging the creatures by eye: a stretch of sewer with each of them in it
beside the player at play size, then every frame at twice that, and an animation of each one's
cycles."""

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from simile.creatures.build import CONTENT, PPM, REPO
from simile.creatures.catalogue import CREATURES

PAPERCRAFT = REPO / "content" / "papercraft"
DOLLS = REPO / "content" / "dolls"
ZOOM = 2
ROOM_M = 4.4
FLIGHT_M = 1.6
SCENE_W = 1500
GAP = 24
INK = (236, 230, 214)
BACK = (46, 50, 48)
FLOOR = (92, 98, 92)
CYCLE_MS = 160
QUALITY = 88


def figures(directory: Path, name: str) -> dict:
    """Each frame of a figure's atlas, by name: its image and its anchor."""
    body = json.loads((directory / f"{name}.json").read_text())
    with Image.open(directory / body["painted"]) as painted:
        sheet = painted.convert("RGBA")
    out = {}
    for frame, entry in body["frames"].items():
        x, y, w, h = entry["frame"]
        point = entry.get("anchor") or entry["feet"]
        out[frame] = (sheet.crop((x, y, x + w, y + h)), tuple(point), entry.get("hangs", False))
    return {"frames": out, "poses": body["poses"], "moves": body.get("moves", "walk")}


def layer(key: str) -> Image.Image:
    """A sewer layer at the figures' `PPM`."""
    found = json.loads((PAPERCRAFT / "manifest.json").read_text())["pieces"][key]
    with Image.open(PAPERCRAFT / found["file"]) as image:
        picture = image.convert("RGBA")
    tall = round(found["height"] * PPM)
    return picture.resize((round(picture.width * tall / picture.height), tall))


def tiled(canvas: Image.Image, picture: Image.Image, top: int) -> None:
    for x in range(0, canvas.width, picture.width):
        canvas.alpha_composite(picture, (x, top))


def put(canvas: Image.Image, frame: tuple, x: float, y: float, zoom: int = 1) -> None:
    """`frame` with its anchor at (x, y)."""
    image, (ax, ay), _ = frame
    if zoom != 1:
        image = image.resize((image.width * zoom, image.height * zoom), Image.Resampling.LANCZOS)
    canvas.alpha_composite(image, (round(x - ax * zoom), round(y - ay * zoom)))


def font(size: int) -> ImageFont.ImageFont:
    return ImageFont.load_default(size=size)


def scene(made: dict, player: dict) -> Image.Image:
    """A sewer room at play size: the player, then each creature in its first pose."""
    tall = round(ROOM_M * PPM)
    out = Image.new("RGBA", (SCENE_W, tall), BACK)
    tiled(out, layer("layers/sewer-vault"), 0)
    ground = layer("layers/ground-sewer")
    floor = tall - ground.height // 2
    tiled(out, layer("layers/mid-sewer"), floor - layer("layers/mid-sewer").height)
    tiled(out, ground, floor)
    x = 80
    put(out, player["frames"]["stand"], x, floor)
    x += 120
    for name, figure in made.items():
        first = figure["frames"][CREATURES[name].first]
        flies = figure["moves"] == "fly"
        put(out, first, x + first[1][0], floor - FLIGHT_M * PPM if flies else floor)
        x += first[0].width + GAP
        for hanging in (f for f in figure["frames"].values() if f[2]):
            put(out, hanging, x + hanging[1][0], 0)
            x += hanging[0].width + GAP
        x += 50
    return out


def strip(name: str, figure: dict) -> Image.Image:
    """Every frame at `ZOOM` times play size, named, on a floor under their anchors."""
    frames = figure["frames"]
    zoomed = {f: (i.width * ZOOM, i.height * ZOOM, a, h) for f, (i, a, h) in frames.items()}
    above = max(a[1] * ZOOM for _, _, a, h in zoomed.values() if not h)
    below = max(hh - a[1] * ZOOM for _, hh, a, h in zoomed.values() if not h)
    width = sum(w for w, *_ in zoomed.values()) + GAP * (len(zoomed) + 1)
    tall = round(above + below) + 70
    out = Image.new("RGBA", (max(width, 300), tall), BACK)
    draw = ImageDraw.Draw(out)
    draw.text((GAP, 8), name, INK, font(22))
    line = 40 + above
    if figure["moves"] != "fly":
        draw.rectangle((0, line, out.width, line + 2), FLOOR)
    x = GAP
    for frame, (w, _, (ax, ay), hangs) in zoomed.items():
        y = 40 + ay * ZOOM if hangs else line
        put(out, frames[frame], x + ax * ZOOM, y, ZOOM)
        draw.text((x, tall - 24), frame, INK, font(16))
        x += w + GAP
    return out


def sheet(directory: Path = CONTENT) -> Image.Image:
    made = {name: figures(directory, name) for name in CREATURES}
    parts = [scene(made, figures(DOLLS, "player"))]
    parts += [strip(name, figure) for name, figure in made.items()]
    out = Image.new("RGBA", (max(p.width for p in parts), sum(p.height for p in parts)), BACK)
    y = 0
    for part in parts:
        out.alpha_composite(part, (0, y))
        y += part.height
    return out.convert("RGB")


def cycles(directory: Path = CONTENT) -> list[Image.Image]:
    """Each creature playing each of its poses side by side, at `ZOOM` times play size."""
    made = {name: figures(directory, name) for name in CREATURES}
    played = [
        (name, pose, frames) for name, f in made.items() for pose, frames in f["poses"].items()
    ]
    steps = 4
    cells = []
    for name, pose, frames in played:
        images = [made[name]["frames"][f] for f in frames]
        w = max(i.width for i, _, _ in images) * ZOOM + GAP
        above = max(a[1] for _, a, _ in images) * ZOOM
        below = max(i.height - a[1] for i, a, _ in images) * ZOOM
        cells.append((name, pose, frames, w, above, below))
    tall = round(max(c[4] + c[5] for c in cells)) + 60
    width = sum(c[3] for c in cells) + GAP
    out = []
    for step in range(steps):
        canvas = Image.new("RGBA", (width, tall), BACK)
        draw = ImageDraw.Draw(canvas)
        x = GAP
        for name, pose, frames, w, above, _ in cells:
            frame = made[name]["frames"][frames[step % len(frames)]]
            image, (ax, ay), hangs = frame
            put(canvas, frame, x + ax * ZOOM, 10 + (ay * ZOOM if hangs else above), ZOOM)
            draw.text((x, tall - 26), f"{name} {pose}", INK, font(16))
            x += w
        out.append(canvas.convert("RGB"))
    return out


def write_preview(directory: Path = CONTENT) -> Path:
    path = directory / "preview.webp"
    sheet(directory).save(path, quality=QUALITY, method=6)
    played = cycles(directory)
    played[0].save(
        directory / "cycles.webp",
        save_all=True,
        append_images=played[1:],
        duration=CYCLE_MS,
        loop=0,
        quality=QUALITY,
        method=6,
    )
    return path
