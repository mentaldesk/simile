"""Approach 2: A1's tiles and sprites, reprojected to a 2:1 isometric grid.

cd server && uv run python ../docs/style-study/pixel_iso.py
"""

import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scene as S  # noqa: E402

from simile.art import tiles as A1  # noqa: E402
from simile.art.canvas import Canvas  # noqa: E402
from simile.art.characters import draw_frame  # noqa: E402
from simile.art.palette import RGB, shade  # noqa: E402
from simile.schema import Appearance  # noqa: E402

UNIT = 16
ROW = 16
ZPX = 14
(SX0, SX1), (SY0, SY1) = S.VIEW["sx"], S.VIEW["sy"]
WIDTH, HEIGHT = round((SX1 - SX0) * UNIT), round((SY1 - SY0) * UNIT)
TILES = {t.name: t.canvas for g in A1.groups() for t in g.tiles}
SCALE = 3

# A1 has no 3/4 views; each grid facing uses the nearest of its four.
A1_FACING = {
    "s": "down",
    "se": "down",
    "e": "right",
    "ne": "right",
    "n": "up",
    "nw": "up",
    "w": "left",
    "sw": "left",
}
BILLBOARDS = {
    "tree": (A1.tree, 32),
    "palm": (A1.palm, 16),
    "lamp": (A1.lamp, 16),
    "terminal": (A1.terminal, 16),
    "vending": (A1.vending, 16),
}


def P(tx: float, ty: float, z_px: float = 0.0) -> tuple[int, int]:
    return round((tx - ty - SX0) * UNIT), round(((tx + ty) / 2 - SY0) * UNIT - z_px)


def to_tile(px: float, py: float) -> tuple[float, float]:
    sx, sy = px / UNIT + SX0, py / UNIT + SY0
    return sy + sx / 2, sy - sx / 2


class Picture:
    def __init__(self) -> None:
        self.img = Image.new("RGB", (WIDTH, HEIGHT), RGB["ink"])
        self.pix = self.img.load()
        self.draw = ImageDraw.Draw(self.img)

    def put(self, x: int, y: int, colour: str | None) -> None:
        if colour and 0 <= x < WIDTH and 0 <= y < HEIGHT:
            self.pix[x, y] = RGB[colour]

    def name_at(self, x: int, y: int) -> str:
        rgb = self.pix[min(max(x, 0), WIDTH - 1), min(max(y, 0), HEIGHT - 1)]
        return next(n for n, c in RGB.items() if c == rgb)

    def sprite(self, c: Canvas, foot_x: int, foot_y: int) -> None:
        for y in range(c.height):
            for x in range(c.width):
                self.put(foot_x - c.width // 2 + x, foot_y - c.height + 1 + y, c.get(x, y))

    def poly(self, points, colour: str) -> None:
        self.draw.polygon(points, fill=RGB[colour])

    def shadow(self, x: int, y: int, rx: int, ry: int) -> None:
        for dy in range(-ry, ry + 1):
            for dx in range(-rx, rx + 1):
                if (dx / rx) ** 2 + (dy / ry) ** 2 <= 1:
                    px, py = x + dx + rx // 2, y + dy
                    if 0 <= px < WIDTH and 0 <= py < HEIGHT:
                        self.put(px, py, shade(self.name_at(px, py)))


def ground(pic: Picture, town: S.TownMap) -> None:
    for py in range(HEIGHT):
        for px in range(WIDTH):
            tx, ty = to_tile(px + 0.5, py + 0.5)
            cx, cy = math.floor(tx), math.floor(ty)
            name = town.at("ground", cx, cy) or "pavement"
            texel = TILES[name].get(int((tx - cx) * 16), int((ty - cy) * 16))
            pic.put(px, py, texel)


def roof_name(b: dict, town: S.TownMap, x: int, y: int) -> str | None:
    roof_rows = [
        r
        for r in range(b["y0"], b["y1"])
        if (town.at("buildings", b["x0"], r) or "").startswith("roof")
    ]
    if not roof_rows:
        return "roof"
    j = y - b["y0"]
    last = b["y1"] - 1 - b["y0"]
    if j < len(roof_rows) - 1:
        src = roof_rows[j]
    elif j == last or len(roof_rows) == 1:
        src = roof_rows[-1]
    else:
        src = roof_rows[-2] if len(roof_rows) > 1 else roof_rows[0]
    return town.at("buildings", x, src) or "roof"


def building(pic: Picture, town: S.TownMap, b: dict) -> None:
    x0, x1, y0, y1 = b["x0"], b["x1"], b["y0"], b["y1"]
    rows = b["facade"] or [[("wall_cream", None)] * (x1 - x0)]
    height = len(rows) * ROW

    face = Canvas((x1 - x0) * 16, len(rows) * ROW)
    for r, row in enumerate(rows):
        for c, (tile, deco) in enumerate(row):
            if tile in TILES:
                face.paste(TILES[tile], c * 16, r * ROW)
            if deco in TILES:
                face.paste(TILES[deco], c * 16, r * ROW)
    left, ground_y = P(x0, y1)
    offset = face.height - height
    for u in range(face.width):
        for v in range(height):
            pic.put(left + u, ground_y - height + v + u // 2, face.get(u, v + offset))

    material = {"cafe": "cafe_wall", "slate": "wall_slate", "cream": "wall_cream"}[b["material"]]
    window = {"cafe": None, "slate": "window_slate", "cream": "window_cream"}[b["material"]]
    side = Canvas((y1 - y0) * 16, len(rows) * ROW)
    for r in range(len(rows)):
        for c in range(y1 - y0):
            last = r == len(rows) - 1
            name = (
                material.replace("wall", "base") if last and material != "cafe_wall" else material
            )
            if window and not last and c % 2 == 1:
                name = window
            side.paste(TILES.get(name, TILES[material]), c * 16, r * ROW)
    side.recolour({n: shade(n) for n in side.colours()})
    corner_x, corner_y = P(x1, y1)
    for u in range(side.width):
        for v in range(height):
            pic.put(corner_x + u, corner_y - height + v - (u + 1) // 2, side.get(u, v + offset))

    top = [P(x0, y0, height), P(x1, y0, height), P(x1, y1, height), P(x0, y1, height)]
    xs, ys = [p[0] for p in top], [p[1] for p in top]
    for py in range(min(ys), max(ys) + 1):
        for px in range(min(xs), max(xs) + 1):
            tx, ty = to_tile(px + 0.5, py + 0.5 + height)
            if not (x0 <= tx < x1 and y0 <= ty < y1):
                continue
            cx, cy = math.floor(tx), math.floor(ty)
            name = roof_name(b, town, cx, cy)
            pic.put(px, py, TILES[name].get(int((tx - cx) * 16), int((ty - cy) * 16)))


def box(pic: Picture, x0, y0, x1, y1, z0, z1, top: str, south: str, east: str) -> None:
    pic.poly([P(x1, y0, z0), P(x1, y1, z0), P(x1, y1, z1), P(x1, y0, z1)], east)
    pic.poly([P(x0, y1, z0), P(x1, y1, z0), P(x1, y1, z1), P(x0, y1, z1)], south)
    pic.poly([P(x0, y0, z1), P(x1, y0, z1), P(x1, y1, z1), P(x0, y1, z1)], top)


def bench(pic: Picture, tx: float, ty: float) -> None:
    for dx in (-0.6, 0.6):
        box(
            pic, tx + dx - 0.04, ty - 0.12, tx + dx + 0.04, ty + 0.12, 0, 5, "night", "night", "ink"
        )
    box(pic, tx - 0.85, ty - 0.2, tx + 0.85, ty + 0.2, 5, 7, "sand", "brown", "umber")
    for i in range(1, 4):
        a, b = P(tx - 0.85 + i * 0.42, ty - 0.2, 7), P(tx - 0.85 + i * 0.42, ty + 0.2, 7)
        pic.draw.line([a, b], fill=RGB["tan"])


def ellipse(pic: Picture, cx: int, cy: int, rx: float, ry: float, colour: str) -> None:
    pic.draw.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=RGB[colour])


def fountain(pic: Picture, tx: float, ty: float) -> None:
    cx, cy = P(tx, ty)
    rx, ry = 24, 12
    ellipse(pic, cx, cy, rx, ry, "steel")
    pic.draw.rectangle([cx - rx, cy - 7, cx + rx, cy], fill=RGB["concrete"])
    pic.draw.rectangle([cx + rx // 3, cy - 7, cx + rx, cy], fill=RGB["steel"])
    ellipse(pic, cx, cy - 7, rx, ry, "pavement")
    ellipse(pic, cx, cy - 7, rx - 3, ry - 2, "blue")
    for dx, dy in ((-9, -2), (6, 3), (12, -1), (-3, 5), (-14, 1)):
        pic.put(cx + dx, cy - 7 + dy, "cyan")
        pic.put(cx + dx + 1, cy - 7 + dy, "ice")
    pic.draw.rectangle([cx - 2, cy - 17, cx + 2, cy - 7], fill=RGB["concrete"])
    ellipse(pic, cx, cy - 18, 8, 4, "pavement")
    ellipse(pic, cx, cy - 18, 6, 3, "blue")
    for y in range(cy - 27, cy - 18):
        pic.put(cx, y, "ice" if y % 3 else "white")
        pic.put(cx + 1, y, "cyan")


def tree_shadow(pic: Picture, tx: float, ty: float, r: int) -> None:
    x, y = P(tx, ty)
    pic.shadow(x + r // 2, y, r, r // 2)


def build(town: S.TownMap) -> Image.Image:
    pic = Picture()
    ground(pic, town)
    things = []
    for b in town.buildings():
        things.append(
            ((b["x0"] + b["x1"] + b["y0"] + b["y1"]) / 2, lambda b=b: building(pic, town, b))
        )
    for kind, tx, ty in town.props():
        key = tx + ty
        if kind in BILLBOARDS:
            make, _ = BILLBOARDS[kind]
            canvas = make()

            def draw(canvas=canvas, tx=tx, ty=ty, kind=kind):
                if kind in ("tree", "palm"):
                    tree_shadow(pic, tx, ty, 10 if kind == "tree" else 6)
                pic.sprite(canvas, *P(tx, ty, -2))

            things.append((key, draw))
        elif kind == "bench":
            things.append((key, lambda tx=tx, ty=ty: bench(pic, tx, ty)))
        elif kind == "fountain":
            things.append((key, lambda tx=tx, ty=ty: fountain(pic, tx, ty)))
        elif kind in TILES:
            things.append((key, lambda c=TILES[kind], tx=tx, ty=ty: pic.sprite(c, *P(tx, ty, -4))))
    for npc_id, tx, ty, facing, frame in S.RESIDENTS:
        look = Appearance.model_validate(S.appearance(npc_id))
        sprite = draw_frame(look, A1_FACING[facing], 1 if frame is None else 0, seed=npc_id)

        def person(sprite=sprite, tx=tx, ty=ty):
            x, y = P(tx, ty)
            pic.shadow(x - 2, y, 5, 2)
            pic.sprite(sprite, x, y)

        things.append((tx + ty, person))
    for _, draw in sorted(things, key=lambda t: t[0]):
        draw()
    return pic.img


def main() -> None:
    town = S.TownMap()
    img = build(town)
    used = {img.getpixel((x, y)) for x in range(WIDTH) for y in range(HEIGHT)}
    assert used <= set(RGB.values()), "every pixel is one of A1's 32 colours"
    S.OUT.mkdir(exist_ok=True)
    img.save(S.OUT / "pixel_scene.png")
    (cx0, cx1), (cy0, cy1) = S.CROP["sx"], S.CROP["sy"]
    crop = img.crop(
        (
            round((cx0 - SX0) * UNIT),
            round((cy0 - SY0) * UNIT),
            round((cx1 - SX0) * UNIT),
            round((cy1 - SY0) * UNIT),
        )
    )
    S.IMAGES.mkdir(exist_ok=True)
    for name, im, k in (("2-pixel-scene.png", img, 2), ("2-pixel-crop.png", crop, SCALE)):
        big = im.resize((im.width * k, im.height * k), Image.Resampling.NEAREST)
        big.quantize(32, dither=Image.Dither.NONE).save(S.IMAGES / name, optimize=True)
        print(name, big.size, (S.IMAGES / name).stat().st_size // 1024, "KB")


if __name__ == "__main__":
    main()
