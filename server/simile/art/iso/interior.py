"""An interior as the iso renders see it: floor, walls, fittings and frames, read from its map."""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from simile.art.iso.camera import TILE_M
from simile.art.iso.lighting import LightingSet
from simile.art.iso.town import gap, shades

WALL_M = 3.0
PARTITION_M = 2.4
CUT_M = 0.45
WALL_T = 0.25
NEAR = 1.5
FRAME_W_M = 1.5
FRAME_Z = (1.1, 2.1)
FRAME_D_M = 0.05
MOULDING_M = 0.08
LIGHT_SPACING = 5.0
LIGHT_Z = 2.7

RUNS = {
    "back_counter": ("back_counter", "grinder", "espresso_machine"),
    "kitchen": ("kitchen_counter", "stove"),
    "counter": (
        *("counter_l", "counter", "counter_r", "counter_corner", "counter_run"),
        *("counter_till", "counter_case"),
    ),
}
PAIRS = ("workbench", "laser_cutter", "loom", "bench")
SINGLES = (
    *("cafe_table", "noodle_table", "stool", "planter", "planter_flowers"),
    *("printer_3d", "sewing_machine", "plinth"),
)
WALL_DECOR = ("shelf", "menu_board", "neon_cup", "lantern", "neon_bowl", "pegboard")
FLOOR_DECOR = ("mat",)

# kind: inset from the cell edge (tiles) and height (metres); a point footprint for walkable kinds
FITTING_SHAPE: dict[str, tuple[float, float]] = {
    "back_counter": (0.25, 0.92),
    "kitchen": (0.25, 0.92),
    "counter": (0.12, 1.05),
    "cafe_table": (0.12, 0.9),
    "noodle_table": (0.12, 0.85),
    "stool": (0.5, 0.75),
    "planter": (0.09, 1.0),
    "planter_flowers": (0.09, 1.1),
    "workbench": (0.15, 1.1),
    "laser_cutter": (0.1, 1.15),
    "loom": (0.15, 1.65),
    "printer_3d": (0.15, 1.45),
    "sewing_machine": (0.15, 1.05),
    "bench": (0.14, 0.5),
    "plinth": (0.28, 1.45),
}

ROOM_LIGHT: dict[str, tuple[tuple[float, float, float], float]] = {
    "coffee_shop": ((1.0, 0.76, 0.5), 240.0),
    "noodle_bar": ((1.0, 0.7, 0.48), 240.0),
    "maker_space": ((0.92, 0.96, 1.0), 220.0),
    "gallery": ((1.0, 0.94, 0.86), 220.0),
}
DEFAULT_LIGHT = ((1.0, 0.85, 0.7), 220.0)


@dataclass
class Piece:
    id: str
    kind: str
    footprint: tuple[float, float, float, float]
    height_m: float
    anchor: tuple[float, float]
    model: dict[str, Any] = field(default_factory=dict)

    def spec(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": "interior",
            "kind": self.kind,
            "footprint": list(self.footprint),
            "height_m": self.height_m,
            **self.model,
        }

    def canvas(self) -> list[tuple[float, float, float]] | None:
        """A frame's opening, top left first and clockwise as seen: map x, y and metres up."""
        if self.kind != "frame":
            return None
        m = self.model["moulding"]
        x0, x1 = self.model["x0"] + m / TILE_M, self.model["x1"] - m / TILE_M
        y = self.model["face_y"]
        z0, z1 = self.model["z0"] + m, self.model["z1"] - m
        return [(x0, y, z1), (x1, y, z1), (x1, y, z0), (x0, y, z0)]


class Interior:
    ground_heights: dict[str, float] = {}

    def __init__(self, path: Path) -> None:
        data = json.loads(path.read_text())
        self.id = path.stem
        self.width: int = data["width"]
        self.height: int = data["height"]
        tileset = data["tilesets"][0]
        names = {}
        for tile in tileset["tiles"]:
            props = {p["name"]: p["value"] for p in tile.get("properties", [])}
            names[tile["id"] + tileset["firstgid"]] = props.get("name")
        self.layers: dict[str, list[list[str | None]]] = {}
        self.paintings: dict[tuple[int, int], str] = {}
        for layer in data["layers"]:
            if layer["type"] == "tilelayer":
                cells = [names.get(g) if g else None for g in layer["data"]]
                self.layers[layer["name"]] = [
                    cells[y * self.width : (y + 1) * self.width] for y in range(self.height)
                ]
            elif layer["name"] == "interactables":
                for obj in layer["objects"]:
                    if obj.get("type") == "painting":
                        self.paintings[(int(obj["x"]) // 16, int(obj["y"]) // 16)] = obj["name"]
        self._read_walls()
        self.walls = self._walls()
        self.fittings = self._fittings()
        self.frames = self._frames()

    def at(self, layer: str, x: int, y: int) -> str | None:
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.layers[layer][y][x]
        return None

    @property
    def objects(self) -> list[Piece]:
        return [*self.walls, *self.fittings, *self.frames]

    @property
    def finish(self) -> str:
        name = next(n for n in self.layers["buildings"][0] if n and not n.startswith("inwall_top"))
        return name.removeprefix("inwall_").split("_")[0]

    @property
    def floor(self) -> str:
        return self.layers["ground"][self.fy0][self.fx0] or "floor_wood"

    def ground(self) -> list[list[str]]:
        return [
            [
                (name or self.floor) if (x, y) not in self.perimeter else "void"
                for x, name in enumerate(row)
            ]
            for y, row in enumerate(self.layers["ground"])
        ]

    def heights(self) -> list[list[float]]:
        return [[0.0] * self.width for _ in range(self.height)]

    def mats(self) -> list[tuple[int, int]]:
        return [
            (x, y)
            for y in range(self.height)
            for x in range(self.width)
            if self.at("decor", x, y) in FLOOR_DECOR
        ]

    def lights(self) -> list[tuple[float, float, float]]:
        """Ceiling lights in an even grid over the floor, about LIGHT_SPACING tiles apart."""
        w, h = self.fx1 - self.fx0, self.fy1 - self.fy0
        nx, ny = max(round(w / LIGHT_SPACING), 1), max(round(h / LIGHT_SPACING), 1)
        return [
            (self.fx0 + (i + 0.5) * w / nx, self.fy0 + (j + 0.5) * h / ny, LIGHT_Z)
            for j in range(ny)
            for i in range(nx)
        ]

    def room(self) -> dict[str, Any]:
        colour, energy = ROOM_LIGHT.get(self.id, DEFAULT_LIGHT)
        return {
            "id": self.id,
            "finish": self.finish,
            "mats": [list(m) for m in self.mats()],
            "lights": [list(p) for p in self.lights()],
            "light_colour": list(colour),
            "light_energy": energy,
        }

    def blender(self) -> dict[str, Any]:
        """The whole room for Blender's ground and light map passes."""
        return {
            "width": self.width,
            "height": self.height,
            "ground": self.ground(),
            "heights": self.heights(),
            "room": self.room(),
            "objects": [o.spec() for o in self.objects],
        }

    @property
    def open_ground(self) -> list[Piece]:
        """What the ground is rendered without underneath, for a cutaway."""
        return [w for w in self.walls if w.model["face"] == "partition"]

    def context(self, target: Piece, light: LightingSet) -> list[Piece]:
        """What can shade or light a piece: anything near it, and whatever's shadow reaches it."""
        x0, y0, x1, y1 = target.footprint
        box = (x0 - NEAR, y0 - NEAR, x1 + NEAR, y1 + NEAR)
        return [
            o
            for o in self.objects
            if o is not target
            and (gap(o.footprint, target.footprint) <= NEAR or shades(o, box, light))
        ]

    def _read_walls(self) -> None:
        wall_cells = {
            (x, y)
            for y in range(self.height)
            for x in range(self.width)
            if (self.at("buildings", x, y) or "").startswith("inwall_")
        }
        self.components: list[set[tuple[int, int]]] = []
        seen: set[tuple[int, int]] = set()
        for cell in sorted(wall_cells, key=lambda c: (c[1], c[0])):
            if cell in seen or self.at("buildings", *cell).startswith("inwall_top"):
                continue
            stack, part = [cell], set()
            seen.add(cell)
            while stack:
                cx, cy = stack.pop()
                part.add((cx, cy))
                for n in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                    name = self.at("buildings", *n) or ""
                    if n in wall_cells and n not in seen and not name.startswith("inwall_top"):
                        seen.add(n)
                        stack.append(n)
            self.components.append(part)
        self.back = next(c for c in self.components if any(y == 0 for _, y in c))
        self.partitions = [c for c in self.components if c is not self.back]
        tops = {c for c in wall_cells if self.at("buildings", *c).startswith("inwall_top")}
        self.perimeter = tops | self.back
        floor = [
            (x, y)
            for y in range(self.height)
            for x in range(self.width)
            if (x, y) not in self.perimeter and self.at("decor", x, y) not in FLOOR_DECOR
        ]
        self.fx0, self.fy0 = min(x for x, _ in floor), min(y for _, y in floor)
        self.fx1, self.fy1 = max(x for x, _ in floor) + 1, max(y for _, y in floor) + 1

    def _wall(
        self, wid: str, box: tuple[float, ...], height: float, face: str, decor: list | None = None
    ) -> Piece:
        x0, y0, x1, y1 = box
        model = {"finish": self.finish, "face": face, "decor": decor or []}
        return Piece(wid, "wall", (x0, y0, x1, y1), height, (x1, y1), model)

    def _walls(self) -> list[Piece]:
        t = WALL_T
        fx0, fy0, fx1, fy1 = self.fx0, self.fy0, self.fx1, self.fy1
        out = [
            self._wall(
                "wall-north",
                (fx0 - t, fy0 - t, fx1 + t, fy0),
                WALL_M,
                "south",
                decor=self._decor(self.back),
            ),
            self._wall("wall-west", (fx0 - t, fy0, fx0, fy1 + t), WALL_M, "east"),
            self._wall("wall-east", (fx1, fy0, fx1 + t, fy1), CUT_M, "west"),
        ]
        doorways = sorted(x for x, y in self.mats() if y == fy1)
        start = fx0
        for doorway in [*doorways, None]:
            end = fx1 + t if doorway is None else doorway
            if end > start:
                out.append(
                    self._wall(f"wall-south-{start}", (start, fy1, end, fy1 + t), CUT_M, "north")
                )
            if doorway is not None:
                start = doorway + 1
        for part in self.partitions:
            xs, ys = [c[0] for c in part], [c[1] for c in part]
            x0, x1, y1 = min(xs), max(xs) + 1, max(ys) + 1
            out.append(
                self._wall(
                    f"partition-{x0}-{min(ys)}",
                    (x0, y1 - t, x1, y1),
                    PARTITION_M,
                    "partition",
                    decor=self._decor(part),
                )
            )
        return out

    def _decor(self, part: set[tuple[int, int]]) -> list[list[Any]]:
        out = []
        for x, y in sorted(part, key=lambda c: (c[1], c[0])):
            name = self.at("decor", x, y) or ""
            base = name.removesuffix("_l")
            if name.endswith("_r") or base not in WALL_DECOR:
                continue
            out.append([base, x, x + (2 if name.endswith("_l") else 1)])
        return out

    def _fittings(self) -> list[Piece]:
        kinds = {}
        for y in range(self.height):
            for x in range(self.width):
                name = self.at("decor", x, y)
                if not name:
                    continue
                run = next((k for k, names in RUNS.items() if name in names), None)
                base = name.removesuffix("_l").removesuffix("_r")
                if run:
                    kinds[(x, y)] = run
                elif base in PAIRS and name.endswith("_l"):
                    kinds[(x, y)] = base
                elif name in SINGLES:
                    kinds[(x, y)] = name
        out, seen = [], set()
        for cell in sorted(kinds, key=lambda c: (c[1], c[0])):
            if cell in seen:
                continue
            kind = kinds[cell]
            if kind in RUNS:
                cells = self._flood(cell, kinds)
            elif kind in PAIRS:
                cells = [cell, (cell[0] + 1, cell[1])]
            else:
                cells = [cell]
            seen.update(cells)
            out.append(self._fitting(kind, sorted(cells, key=lambda c: (c[1], c[0]))))
        return out

    def _flood(self, start: tuple[int, int], kinds: dict) -> list[tuple[int, int]]:
        kind, stack, out = kinds[start], [start], {start}
        while stack:
            cx, cy = stack.pop()
            for n in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                if kinds.get(n) == kind and n not in out:
                    out.add(n)
                    stack.append(n)
        return list(out)

    def _fitting(self, kind: str, cells: list[tuple[int, int]]) -> Piece:
        inset, height = FITTING_SHAPE[kind]
        x, y = cells[0]
        boxes = [self._cell_box(c, cells, inset) for c in cells]
        footprint = (
            min(b[0] for b in boxes),
            min(b[1] for b in boxes),
            max(b[2] for b in boxes),
            max(b[3] for b in boxes),
        )
        anchor = ((footprint[0] + footprint[2]) / 2, (footprint[1] + footprint[3]) / 2)
        model = {
            "cells": [[cx, cy, self.at("decor", cx, cy)] for cx, cy in cells],
            "boxes": [list(b) for b in boxes],
        }
        return Piece(f"{kind}-{x}-{y}", kind, footprint, height, anchor, model)

    def _cell_box(
        self, cell: tuple[int, int], cells: list[tuple[int, int]], inset: float
    ) -> tuple[float, float, float, float]:
        """A cell's part of a fitting: inset on each side, but flush to a neighbour or a wall."""
        x, y = cell
        if inset >= 0.5:
            return (x + 0.5, y + 0.5, x + 0.5, y + 0.5)

        def flush(nx: int, ny: int) -> bool:
            return (nx, ny) in cells or (nx, ny) in self.perimeter

        return (
            x if flush(x - 1, y) else x + inset,
            y if flush(x, y - 1) else y + inset,
            x + 1 if flush(x + 1, y) else x + 1 - inset,
            y + 1 if flush(x, y + 1) else y + 1 - inset,
        )

    def _frames(self) -> list[Piece]:
        out = []
        for y in range(self.height):
            for x in range(self.width):
                if self.at("decor", x, y) != "frame_l":
                    continue
                part = next(p for p in self.components if (x, y) in p)
                face_y = self.fy0 if part is self.back else max(c[1] for c in part) + 1
                half = FRAME_W_M / TILE_M / 2
                cx = x + 1.0
                depth = FRAME_D_M / TILE_M
                out.append(
                    Piece(
                        self.paintings.get((x, y), f"frame-{x}-{y}"),
                        "frame",
                        (cx - half, face_y, cx + half, face_y + depth),
                        FRAME_Z[1],
                        (cx, face_y + depth),
                        {
                            "x0": cx - half,
                            "x1": cx + half,
                            "face_y": face_y,
                            "z0": FRAME_Z[0],
                            "z1": FRAME_Z[1],
                            "moulding": MOULDING_M,
                            "depth": depth,
                        },
                    )
                )
        return out


def find(content: Path) -> list[Interior]:
    return [Interior(p) for p in sorted((content / "map" / "interiors").glob("*.tmj"))]
