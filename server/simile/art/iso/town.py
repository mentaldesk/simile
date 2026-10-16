"""The village as the iso renders see it: ground cells, buildings and props, read from the map."""

import json
import math
import zlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from simile.art.iso.camera import TILE_M
from simile.art.iso.lighting import LightingSet, shadow_direction

STOREY_M = 3.0
GRASS_M = 0.18
WALL_DECOR = ("awning", "cafe_awning", "neon", "screen")
ROOF_ITEMS = ("roof_solar", "roof_ac", "roof_skylight")
VARIANTS = {"tree": 3}

# kind: half width and half depth at the base, reach of the top (all in tiles), height in metres
PROP_SHAPE: dict[str, tuple[float, float, float, float]] = {
    "tree": (0.0, 0.0, 1.4, 4.3),
    "palm": (0.0, 0.0, 1.6, 4.6),
    "lamp": (0.0, 0.0, 0.8, 4.0),
    "bench": (0.86, 0.23, 0.9, 0.5),
    "fountain": (1.05, 1.05, 1.05, 2.1),
    "cafe_table": (0.9, 0.33, 0.9, 0.9),
    "terminal": (0.27, 0.16, 0.3, 2.1),
    "vending": (0.41, 0.32, 0.45, 1.95),
}
SMALL_PROP = (0.0, 0.0, 0.5, 1.0)
MODELLED = {
    *PROP_SHAPE,
    *("bush", "planter", "planter_flowers", "bins", "bike_blue", "bike_yellow"),
    *("cafe_menu", "bollard"),
}


@dataclass(frozen=True)
class Building:
    x0: int
    y0: int
    x1: int
    y1: int
    storeys: int
    green_roof: bool
    material: str
    roof_items: tuple[tuple[int, int, str], ...]
    facade: tuple[tuple[tuple[str | None, str | None], ...], ...]

    @property
    def id(self) -> str:
        return f"building-{self.x0}-{self.y0}"

    @property
    def footprint(self) -> tuple[float, float, float, float]:
        return (self.x0, self.y0, self.x1, self.y1)

    @property
    def anchor(self) -> tuple[float, float]:
        return (self.x1, self.y1)

    @property
    def height_m(self) -> float:
        return self.storeys * STOREY_M + 2.2

    def spec(self) -> dict[str, Any]:
        return {"id": self.id, "type": "building", **asdict(self)}


@dataclass(frozen=True)
class Prop:
    kind: str
    tile: tuple[int, int]
    x: float
    y: float
    z: float

    @property
    def id(self) -> str:
        return f"{self.kind}-{self.tile[0]}-{self.tile[1]}"

    @property
    def variant(self) -> int:
        return zlib.crc32(self.id.encode()) % VARIANTS.get(self.kind, 1)

    @property
    def footprint(self) -> tuple[float, float, float, float]:
        w, d, _, _ = PROP_SHAPE.get(self.kind, SMALL_PROP)
        return (self.x - w, self.y - d, self.x + w, self.y + d)

    @property
    def anchor(self) -> tuple[float, float]:
        return (self.x, self.y)

    @property
    def height_m(self) -> float:
        return PROP_SHAPE.get(self.kind, SMALL_PROP)[3] + self.z

    @property
    def reach(self) -> float:
        return PROP_SHAPE.get(self.kind, SMALL_PROP)[2]

    def spec(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": "prop",
            "kind": self.kind,
            "variant": self.variant,
            "x": self.x,
            "y": self.y,
            "z": self.z,
        }


Object = Building | Prop


class Town:
    def __init__(self, path: Path) -> None:
        data = json.loads(path.read_text())
        self.width: int = data["width"]
        self.height: int = data["height"]
        tileset = data["tilesets"][0]
        names = {}
        for tile in tileset["tiles"]:
            props = {p["name"]: p["value"] for p in tile.get("properties", [])}
            names[tile["id"] + tileset["firstgid"]] = props.get("name")
        self.layers: dict[str, list[list[str | None]]] = {}
        for layer in data["layers"]:
            if layer["type"] == "tilelayer":
                cells = [names.get(g) if g else None for g in layer["data"]]
                self.layers[layer["name"]] = [
                    cells[y * self.width : (y + 1) * self.width] for y in range(self.height)
                ]
        self.buildings = self._buildings()
        self.props = self._props()

    def at(self, layer: str, x: int, y: int) -> str | None:
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.layers[layer][y][x]
        return None

    def ground(self) -> list[list[str]]:
        return [[name or "pavement" for name in row] for row in self.layers["ground"]]

    @property
    def objects(self) -> list[Object]:
        return [*self.buildings, *self.props]

    def _buildings(self) -> list[Building]:
        seen: set[tuple[int, int]] = set()
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
                out.append(self._building(cells))
        return out

    def _building(self, cells: list[tuple[int, int]]) -> Building:
        xs, ys = [c[0] for c in cells], [c[1] for c in cells]
        x0, x1, y0, y1 = min(xs), max(xs) + 1, min(ys), max(ys) + 1
        roof_rows = [
            r for r in range(y0, y1) if (self.at("buildings", x0, r) or "").startswith("roof")
        ]
        facade_rows = [r for r in range(y0, y1) if r not in roof_rows]
        facade = tuple(
            tuple((self.at("buildings", cx, r), self.at("decor", cx, r)) for cx in range(x0, x1))
            for r in facade_rows
        )
        roof_items = tuple(
            (cx, cy, name.removeprefix("roof_"))
            for cx, cy in sorted(cells, key=lambda c: (c[1], c[0]))
            if (name := self.at("buildings", cx, cy)) in ROOF_ITEMS
        )
        names = " ".join(b or "" for row in facade for b, _ in row)
        material = "cafe" if "cafe" in names else "slate" if "slate" in names else "cream"
        return Building(
            x0=x0,
            y0=y0,
            x1=x1,
            y1=y1,
            storeys=max(len(facade_rows), 1),
            green_roof=(self.at("buildings", x0, y0) or "").startswith("roof_green"),
            material=material,
            roof_items=roof_items,
            facade=facade,
        )

    def _props(self) -> list[Prop]:
        out = []
        for y in range(self.height):
            for x in range(self.width):
                name = self.at("decor", x, y)
                if not name or self.at("buildings", x, y):
                    continue
                if name == "tree_bl":
                    kind, px, py = "tree", x + 1.0, y + 0.5
                elif name == "fountain_bl":
                    kind, px, py = "fountain", x + 1.0, float(y)
                elif name == "bench_l":
                    kind, px, py = "bench", x + 1.0, y + 0.5
                elif name.endswith(("_br", "_tr", "_tl", "bench_r")) or name.startswith(WALL_DECOR):
                    continue
                else:
                    kind, px, py = name, x + 0.5, y + 0.5
                ground = self.at("ground", int(px), int(py)) or ""
                z = GRASS_M if ground.startswith("grass") else 0.0
                out.append(Prop(kind=kind, tile=(x, y), x=px, y=py, z=z))
        return out

    def context(self, target: Object, light: LightingSet) -> list[Object]:
        """What can shade or light an object in a set: its shadow casters, and lamps when lit."""
        margin = target.reach if isinstance(target, Prop) else OVERHANG
        x0, y0, x1, y1 = target.footprint
        box = (x0 - margin, y0 - margin, x1 + margin, y1 + margin)
        lamps_on = light.emits("lamp") > 0
        out: list[Object] = []
        for other in self.objects:
            if other is target:
                continue
            lamp_lit = (
                lamps_on
                and isinstance(other, Prop)
                and other.kind == "lamp"
                and _gap(other.footprint, target.footprint) <= LAMP_REACH
            )
            if lamp_lit or shades(other, box, light):
                out.append(other)
        return out


LAMP_REACH = 12.0
OVERHANG = 1.0


def _gap(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    dx = max(a[0] - b[2], b[0] - a[2], 0.0)
    dy = max(a[1] - b[3], b[1] - a[3], 0.0)
    return max(dx, dy)


def shades(caster: Object, box: tuple[float, float, float, float], light: LightingSet) -> bool:
    """Whether a caster's shadow can reach a box on the map: its outline swept away from the sun."""
    reach = caster.reach if isinstance(caster, Prop) else 0.0
    x0, y0, x1, y1 = caster.footprint
    outline = (x0 - reach, y0 - reach, x1 + reach, y1 + reach)
    length = caster.height_m / math.tan(math.radians(light.elevation)) / TILE_M
    dx, dy = shadow_direction(light.azimuth)
    steps = max(int(length / 0.25), 1)
    for i in range(steps + 1):
        t = length * i / steps
        moved = (outline[0] + dx * t, outline[1] + dy * t, outline[2] + dx * t, outline[3] + dy * t)
        if _overlaps(moved, box):
            return True
    return False


def _overlaps(a: tuple[float, ...], b: tuple[float, ...]) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]
