"""The scene every mock-up shows: the town square from the W1 map, with three residents in it.

Pure standard library, so Blender's Python and uv's Python can both import it.
"""

import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MAP = ROOT / "content" / "map" / "village.tmj"
NPCS = ROOT / "content" / "npcs"
OUT = HERE / "out"
IMAGES = HERE / "images"

TILE_M = 1.1
STOREY_M = 3.0

# Screen-space view of the square, in iso units: sx = tx - ty, sy = (tx + ty) / 2.
VIEW = {"sx": (-9.0, 38.0), "sy": (9.5, 36.0)}
CROP = {"sx": (2.0, 24.0), "sy": (15.5, 29.5)}

# (id, tile x, tile y, grid facing, walk frame or None for standing)
RESIDENTS = [
    ("odalys", 32.5, 13.9, "s", None),
    ("ingrid", 26.4, 20.5, "e", 2),
    ("lachlan", 30.0, 23.6, "ne", None),
]
WALKER = "ingrid"

GRID_FACINGS = ("s", "se", "e", "ne", "n", "nw", "w", "sw")
# Degrees about +Z for a model that faces south (-Y) at rest; Blender's Y is the map's -y.
FACING_DEG = {"s": 0, "se": 45, "e": 90, "ne": 135, "n": 180, "nw": 225, "w": 270, "sw": 315}


def a1_palette():
    spec = importlib.util.spec_from_file_location(
        "a1_palette", ROOT / "server" / "simile" / "art" / "palette.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def appearance(npc_id: str) -> dict:
    return json.loads((NPCS / f"{npc_id}.json").read_text())["appearance"]


def colours(npc_id: str) -> dict[str, str]:
    """A1's colour choices for a resident (Colours.of), as palette names."""
    pal = a1_palette()
    a = appearance(npc_id)
    cloth = tuple(n for n in pal.PALETTE if n != "ink")

    def snap(hex_colour, choices):
        return pal.nearest(pal.hex_to_rgb(hex_colour), choices)

    import zlib

    top, bottom, hair = (snap(a[k], cloth) for k in ("top_colour", "bottom_colour", "hair_colour"))
    free = [
        c
        for c in ("amber", "cyan", "red", "lime", "violet", "neon")
        if c not in (top, bottom, hair)
    ]
    light = {"white", "pavement", "ice", "cream", "peach", "yellow", "sand", "amber"}
    return {
        "skin": snap(a["skin"], ("cream", "peach", "sand", "tan", "brown", "umber")),
        "hair": hair,
        "top": top,
        "bottom": bottom,
        "shoe": snap(a["shoe_colour"], cloth),
        "accent": free[zlib.crc32(npc_id.encode()) % len(free)],
        "apron": "umber" if top in light else "cream",
    }


class TownMap:
    def __init__(self, path: Path = MAP) -> None:
        data = json.loads(path.read_text())
        self.width = data["width"]
        self.height = data["height"]
        tileset = data["tilesets"][0]
        names = {}
        for tile in tileset["tiles"]:
            props = {p["name"]: p["value"] for p in tile.get("properties", [])}
            names[tile["id"] + tileset["firstgid"]] = props.get("name")
        self.layers: dict[str, list[list[str | None]]] = {}
        self.locations = []
        for layer in data["layers"]:
            if layer["type"] == "tilelayer":
                cells = [names.get(g) if g else None for g in layer["data"]]
                self.layers[layer["name"]] = [
                    cells[y * self.width : (y + 1) * self.width] for y in range(self.height)
                ]
            elif layer["type"] == "objectgroup":
                self.locations = layer["objects"]

    def at(self, layer: str, x: int, y: int) -> str | None:
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.layers[layer][y][x]
        return None

    def ground(self):
        for y in range(self.height):
            for x in range(self.width):
                yield x, y, self.layers["ground"][y][x]

    def buildings(self) -> list[dict]:
        """Each connected block of building tiles: footprint, roof kind, roof items, facade."""
        seen = set()
        out = []
        for y in range(self.height):
            for x in range(self.width):
                if (x, y) in seen or not self.at("buildings", x, y):
                    continue
                stack, cells = [(x, y)], []
                seen.add((x, y))
                while stack:
                    cx, cy = stack.pop()
                    cells.append((cx, cy))
                    for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                        if (nx, ny) not in seen and self.at("buildings", nx, ny):
                            seen.add((nx, ny))
                            stack.append((nx, ny))
                xs = [c[0] for c in cells]
                ys = [c[1] for c in cells]
                x0, x1, y0, y1 = min(xs), max(xs) + 1, min(ys), max(ys) + 1
                roof_rows = [
                    r
                    for r in range(y0, y1)
                    if (self.at("buildings", x0, r) or "").startswith("roof")
                ]
                facade_rows = [r for r in range(y0, y1) if r not in roof_rows]
                roof_items = [
                    (cx, cy, name.removeprefix("roof_"))
                    for cx, cy in cells
                    if (name := self.at("buildings", cx, cy))
                    in ("roof_solar", "roof_ac", "roof_skylight")
                ]
                facade = [
                    [(self.at("buildings", cx, r), self.at("decor", cx, r)) for cx in range(x0, x1)]
                    for r in facade_rows
                ]
                first = self.at("buildings", x0, y0) or ""
                out.append(
                    {
                        "x0": x0,
                        "x1": x1,
                        "y0": y0,
                        "y1": y1,
                        "storeys": max(len(facade_rows), 1),
                        "green_roof": first.startswith("roof_green"),
                        "roof_items": roof_items,
                        "facade": facade,
                        "material": _facade_material(facade),
                    }
                )
        return out

    def props(self) -> list[tuple[str, float, float]]:
        """Free-standing props as (kind, x, y) in tiles, at the centre of their footprint."""
        out = []
        decor = self.layers["decor"]
        for y in range(self.height):
            for x in range(self.width):
                name = decor[y][x]
                if not name or self.at("buildings", x, y):
                    continue
                if name == "tree_bl":
                    out.append(("tree", x + 1.0, y + 0.5))
                elif name == "fountain_bl":
                    out.append(("fountain", x + 1.0, y))
                elif name == "bench_l":
                    out.append(("bench", x + 1.0, y + 0.5))
                elif name.endswith(("_br", "_tr", "_tl", "bench_r")) or name.startswith(WALL_DECOR):
                    continue
                else:
                    out.append((name, x + 0.5, y + 0.5))
        return out


WALL_DECOR = ("awning", "cafe_awning", "neon", "screen")


def _facade_material(facade) -> str:
    names = " ".join(b or "" for row in facade for b, _ in row)
    if "cafe" in names:
        return "cafe"
    if "slate" in names:
        return "slate"
    return "cream"


def iso(tx: float, ty: float) -> tuple[float, float]:
    return tx - ty, (tx + ty) / 2
