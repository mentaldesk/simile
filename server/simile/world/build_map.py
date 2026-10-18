import json
import os
import random
from collections.abc import Iterable
from dataclasses import dataclass
from itertools import count
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from simile.art.palette import rgba
from simile.art.preview import label
from simile.art.tiles import edge_variant
from simile.schema import (
    Door,
    Facing,
    Interactable,
    InteractableKind,
    Location,
    LocationKind,
    MapTile,
    Tile,
    TileArea,
)
from simile.world.map import (
    COLLISION_LAYER,
    DOORS_LAYER,
    INTERACTABLES_LAYER,
    INTERIORS,
    LOCATIONS_LAYER,
    MAP_ID,
    MURALS_LAYER,
    SPOTS_LAYER,
    Face,
    MuralWall,
    Spot,
    SpotKind,
)

TILE_SIZE = 16
WIDTH, HEIGHT = 64, 42
TERRAIN = {"P": "pavement", "G": "grass", "R": "road", "W": "water", "Z": "plaza"}
TERRAIN |= {"B": "floor_wood", "T": "floor_tiles", "C": "floor_concrete", "L": "floor_gallery"}
PATCHES = {"G", "R", "W"}
TILE_LAYERS = ("ground", "buildings", "decor", "above")
CHAIR_REACH = 0.6
"""From a seat's tile to its chair, which stands on the table's tile."""
BENCH_REACH = 0.7
"""From a seat's tile to where the sitter's feet are, in front of the bench."""
LEAN = 0.2
"""How far towards what they're using people stand at a counter, desk or screen."""
STOOL_M = 0.25
"""How much higher a bar stool's seat is than a chair's."""
STEPS = {Facing.EAST: (1, 0), Facing.SOUTH: (0, 1), Facing.WEST: (-1, 0), Facing.NORTH: (0, -1)}
GROUND_ON = {
    "grass_tufts": "G",
    "grass_flowers": "G",
    "road_line_h": "R",
    "road_line_v": "R",
    "crosswalk_h": "R",
    "crosswalk_v": "R",
    "tactile_h": "PZ",
    "tactile_v": "PZ",
    "plaza_inlay": "Z",
}


@dataclass(frozen=True)
class Tileset:
    data: dict[str, Any]
    ids: dict[str, int]
    collides: frozenset[str]
    above: frozenset[str]
    sheet: Image.Image

    @classmethod
    def load(cls, art: Path) -> "Tileset":
        data = json.loads((art / "tiles.tsj").read_text())
        ids, collides, above = {}, set(), set()
        for tile in data["tiles"]:
            props = {p["name"]: p["value"] for p in tile["properties"]}
            ids[props["name"]] = tile["id"]
            if props["collides"]:
                collides.add(props["name"])
            if props["above"]:
                above.add(props["name"])
        with Image.open(art / data["image"]) as image:
            sheet = image.convert("RGBA")
        return cls(data, ids, frozenset(collides), frozenset(above), sheet)

    def image(self, name: str) -> Image.Image:
        i, columns = self.ids[name], self.data["columns"]
        x, y = i % columns * TILE_SIZE, i // columns * TILE_SIZE
        return self.sheet.crop((x, y, x + TILE_SIZE, y + TILE_SIZE))


def facade(material: str, *rows: str) -> list[list[str]]:
    """Facade tiles from one string per row, top to bottom; the last row is the ground floor.

    . wall, w window, d door (a d in the row above draws its top), s shop window, D shop door.
    """
    upper = {".": f"wall_{material}", "w": f"window_{material}", "d": f"door_{material}_top"}
    ground = {".": f"base_{material}", "w": f"base_window_{material}", "d": f"door_{material}"}
    ground |= {"s": "shopfront", "D": "shop_door"}
    out = []
    for i, row in enumerate(rows):
        key = ground if i == len(rows) - 1 else upper
        names = []
        for col, char in enumerate(row):
            name = key[char]
            if char == "s":
                left, right = row[col - 1 : col] == "s", row[col + 1 : col + 2] == "s"
                name += "" if left and right else "_r" if left else "_l"
            elif char == "." and col in (0, len(row) - 1):
                name += "_l" if col == 0 else "_r"
            names.append(name)
        out.append(names)
    return out


class Town:
    def __init__(
        self,
        tileset: Tileset,
        map_id: str = MAP_ID,
        width: int = WIDTH,
        height: int = HEIGHT,
        terrain: str = "P",
    ) -> None:
        self.tileset = tileset
        self.map_id = map_id
        self.width, self.height = width, height
        self.terrain = [[terrain] * width for _ in range(height)]
        self.overrides: dict[tuple[int, int], str] = {}
        self.layers: dict[str, dict[tuple[int, int], str]] = {name: {} for name in TILE_LAYERS[1:]}
        self.locations: list[Location] = []
        self.murals: list[MuralWall] = []
        self.doors: list[Door] = []
        self.interactables: list[Interactable] = []
        self.spots: list[Spot] = []
        self.mat: Tile | None = None
        self.doorsteps: dict[str, Tile] = {}

    def fill(self, terrain: str, x: int, y: int, w: int, h: int) -> None:
        for yy in range(max(y, 0), min(y + h, self.height)):
            for xx in range(max(x, 0), min(x + w, self.width)):
                self.terrain[yy][xx] = terrain

    def paint(self, x: int, y: int, *names: str, down: bool = False) -> None:
        for i, name in enumerate(names):
            self.overrides[(x, y + i) if down else (x + i, y)] = name

    def put(self, x: int, y: int, *names: str) -> None:
        for i, name in enumerate(names):
            self._set("above" if name in self.tileset.above else "decor", x + i, y, name)

    def tall(self, x: int, y: int, name: str) -> None:
        self.put(x, y - 1, f"{name}_top")
        self.put(x, y, name)

    def tree(self, x: int, y: int) -> None:
        self.put(x, y - 1, "tree_tl", "tree_tr")
        self.put(x, y, "tree_bl", "tree_br")

    def bench(self, x: int, y: int, facing: Facing | None = None) -> None:
        """A bench, with a seat for two facing north or south off it."""
        self.put(x, y, "bench_l", "bench_r")
        if facing is not None:
            dy = STEPS[facing][1]
            for i in (0, 1):
                self.spot(SpotKind.SEAT, x + i, y + dy, facing, dy=-dy * BENCH_REACH)

    def spot(
        self,
        kind: SpotKind,
        x: int,
        y: int,
        facing: Facing,
        lean: float = 0.0,
        dy: float = 0.0,
        dz: float = 0.0,
    ) -> None:
        """A spot on (x, y), with the figure `lean` tiles towards what it faces, then `dy` south."""
        step_x, step_y = STEPS[facing]
        spot_id = f"{kind}-{x}-{y}"
        dx, dy = step_x * lean, step_y * lean + dy
        self.spots.append(Spot(spot_id, kind, self.map_id, x, y, facing, dx, dy, dz))

    def table(self, x: int, y: int, name: str) -> None:
        """A table with a chair either side, east and west."""
        self.put(x, y, name)
        self.spot(SpotKind.SEAT, x - 1, y, Facing.EAST, CHAIR_REACH)
        self.spot(SpotKind.SEAT, x + 1, y, Facing.WEST, CHAIR_REACH)

    def fountain(self, x: int, y: int) -> None:
        self.put(x, y, "fountain_tl", "fountain_tr")
        self.put(x, y + 1, "fountain_bl", "fountain_br")

    def building(
        self,
        x: int,
        y: int,
        material: str,
        rows: tuple[str, ...],
        roof: str = "roof",
        roof_rows: int = 3,
        extras: Iterable[tuple[int, int, str]] = (),
    ) -> TileArea:
        return self.block(x, y, roof, roof_rows, facade(material, *rows), extras)

    def block(
        self,
        x: int,
        y: int,
        roof: str,
        roof_rows: int,
        front: list[list[str]],
        extras: Iterable[tuple[int, int, str]] = (),
    ) -> TileArea:
        width = len(front[0])
        for row in range(roof_rows):
            for col in range(width):
                ns = "n" if row == 0 else "s" if row == roof_rows - 1 else ""
                ew = "w" if col == 0 else "e" if col == width - 1 else ""
                self._set("buildings", x + col, y + row, f"{roof}_{ns}{ew}" if ns or ew else roof)
        for row, names in enumerate(front):
            for col, name in enumerate(names):
                self._set("buildings", x + col, y + roof_rows + row, name)
        for dx, dy, name in extras:
            self._set("buildings", x + dx, y + dy, name, replace=True)
        return TileArea(x=x, y=y, width=width, height=roof_rows + len(front))

    def place(
        self,
        location_id: str,
        name: str,
        kind: LocationKind,
        area: TileArea,
        entry: tuple[int, int],
    ) -> None:
        location = Location(
            id=location_id,
            name=name,
            kind=kind,
            map=self.map_id,
            area=area,
            entry=Tile(x=entry[0], y=entry[1]),
        )
        self.locations.append(location)

    def place_building(
        self,
        location_id: str,
        name: str,
        kind: LocationKind,
        area: TileArea,
        door: int,
        front: int = 1,
    ) -> None:
        """The location takes in `front` rows outside; the doorstep is its entry."""
        step = self.doorstep(location_id, area, door)
        grown = area.model_copy(update={"height": area.height + front})
        self.place(location_id, name, kind, grown, (step.x, step.y))

    def doorstep(self, building_id: str, area: TileArea, door: int) -> Tile:
        """The tile in front of a building's door, where a door to its interior would go."""
        step = Tile(x=door, y=area.y + area.height)
        self.doorsteps[building_id] = step
        return step

    def house(
        self,
        number: int,
        name: str,
        x: int,
        y: int,
        material: str,
        rows: tuple[str, ...],
        roof: str = "roof",
        roof_rows: int = 3,
        extras: Iterable[tuple[int, int, str]] = (),
    ) -> None:
        area = self.building(x, y, material, rows, roof, roof_rows, extras)
        door = x + rows[-1].index("d")
        self.place_building(f"house_{number}", name, LocationKind.HOUSE, area, door)

    def mural(
        self, wall_id: str, face: Face, x: int, y: int, width: int, bottom: float, top: float
    ) -> None:
        """A mural wall, with its painter on the middle tile in front of it."""
        if face == "south":
            stand = Tile(x=x + width // 2, y=y + 1)
        else:
            stand = Tile(x=x + 1, y=y + width // 2)
        self.murals.append(MuralWall(wall_id, x, y, width, face, bottom, top, stand))
        facing = Facing.NORTH if face == "south" else Facing.WEST
        self.spot(SpotKind.VIEWING, stand.x, stand.y, facing)

    def terminal(self, number: int, name: str, x: int, y: int) -> None:
        self.tall(x, y, "terminal")
        area = TileArea(x=x, y=y - 1, width=1, height=3)
        self.place(f"terminal_{number}", name, LocationKind.TERMINAL, area, (x, y + 1))
        self.spot(SpotKind.TERMINAL, x, y + 1, Facing.NORTH, LEAN)

    def walls(self, material: str, door: int) -> None:
        """A room's walls: the back wall face on, the others' tops, and a mat in the doorway."""
        w, h = self.width, self.height
        for x in range(1, w - 1):
            self._set("buildings", x, 0, f"inwall_{material}")
            self._set("buildings", x, 1, f"inwall_{material}_base")
            if x != door:
                self._set("buildings", x, h - 1, "inwall_top_s")
        for y in range(h - 1):
            self._set("buildings", 0, y, "inwall_top_w")
            self._set("buildings", w - 1, y, "inwall_top_e")
        self._set("buildings", 0, h - 1, "inwall_top_sw")
        self._set("buildings", w - 1, h - 1, "inwall_top_se")
        self.put(door, h - 1, "mat")
        self.mat = Tile(x=door, y=h - 1)

    def floor(self) -> TileArea:
        """The room inside its walls."""
        return TileArea(x=1, y=2, width=self.width - 2, height=self.height - 3)

    def partition(self, material: str, x: int, y: int, width: int) -> None:
        """A free-standing wall, two rows like the back wall, seen face on."""
        for row, part in ((y, ""), (y + 1, "_base")):
            for i in range(width):
                end = "_l" if i == 0 else "_r" if i == width - 1 else ""
                self._set("buildings", x + i, row, f"inwall_{material}{part}{end}")

    def interactable(
        self,
        item_id: str,
        label: str,
        kind: InteractableKind,
        area: TileArea,
        stand: Iterable[tuple[int, int]],
    ) -> None:
        self.interactables.append(
            Interactable(
                id=item_id,
                label=label,
                kind=kind,
                map=self.map_id,
                area=area,
                stand=[Tile(x=x, y=y) for x, y in stand],
            )
        )

    def machine(self, item_id: str, label: str, x: int, y: int, *names: str) -> None:
        """A machine against the back wall, used from the tiles in front of it."""
        self.put(x, y, *names)
        area = TileArea(x=x, y=y, width=len(names), height=1)
        stand = [(x + i, y + 1) for i in range(len(names))]
        self.interactable(item_id, label, InteractableKind.MACHINE, area, stand)
        for sx, sy in stand:
            self.spot(SpotKind.DESK, sx, sy, Facing.NORTH, LEAN)

    def workbench(self, x: int, y: int) -> None:
        """A workbench, worked at from both long sides."""
        self.put(x, y, "workbench_l", "workbench_r")
        for i in (0, 1):
            self.spot(SpotKind.DESK, x + i, y - 1, Facing.SOUTH, LEAN)
            self.spot(SpotKind.DESK, x + i, y + 1, Facing.NORTH, LEAN)

    def painting(self, number: int, x: int, y: int) -> None:
        """A frame on the upper row of a wall, looked at from in front of the wall's base."""
        self.put(x, y, "frame_l", "frame_r")
        area = TileArea(x=x, y=y, width=2, height=1)
        stand = [(x, y + 2), (x + 1, y + 2)]
        self.interactable(f"painting_{number}", "Painting", InteractableKind.PAINTING, area, stand)
        for sx, sy in stand:
            self.spot(SpotKind.VIEWING, sx, sy, Facing.NORTH)

    def ground(self, x: int, y: int) -> str:
        if (x, y) in self.overrides:
            return self.overrides[x, y]
        cell = self.terrain[y][x]
        if cell not in PATCHES:
            return TERRAIN[cell]

        def same(dx: int, dy: int) -> bool:
            nx, ny = x + dx, y + dy
            inside = 0 <= nx < self.width and 0 <= ny < self.height
            return not inside or self.terrain[ny][nx] == cell

        return edge_variant(TERRAIN[cell], same)

    def tiles(self, layer: str) -> dict[tuple[int, int], str]:
        if layer == "ground":
            return {
                (x, y): self.ground(x, y) for y in range(self.height) for x in range(self.width)
            }
        return self.layers[layer]

    def blocked(self) -> set[tuple[int, int]]:
        return {
            cell
            for layer in TILE_LAYERS
            for cell, name in self.tiles(layer).items()
            if name in self.tileset.collides
        }

    def check(self) -> None:
        """Raise if terrain patches are too thin or touch, or details sit on the wrong terrain."""
        for y in range(self.height):
            for x in range(self.width):
                cell = self.terrain[y][x]
                if cell in PATCHES and not self._thick(x, y):
                    raise ValueError(f"{TERRAIN[cell]} at ({x}, {y}) is less than two tiles thick")
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        nx, ny = x + dx, y + dy
                        if 0 <= nx < self.width and 0 <= ny < self.height:
                            other = self.terrain[ny][nx]
                            if cell in PATCHES and other in PATCHES and other != cell:
                                raise ValueError(f"({x}, {y}) touches another terrain patch")
        for (x, y), name in self.overrides.items():
            if self.terrain[y][x] not in GROUND_ON[name]:
                raise ValueError(f"{name} at ({x}, {y}) is on {TERRAIN[self.terrain[y][x]]}")

    def _thick(self, x: int, y: int) -> bool:
        cell = self.terrain[y][x]
        for ox in (x - 1, x):
            for oy in (y - 1, y):
                square = [(ox + dx, oy + dy) for dx in (0, 1) for dy in (0, 1)]
                if all(
                    not (0 <= sx < self.width and 0 <= sy < self.height)
                    or self.terrain[sy][sx] == cell
                    for sx, sy in square
                ):
                    return True
        return False

    def _set(self, layer: str, x: int, y: int, name: str, replace: bool = False) -> None:
        self._check_bounds(x, y)
        if name not in self.tileset.ids:
            raise ValueError(f"no tile named {name}")
        existing = self.layers[layer].get((x, y))
        if existing and not replace:
            raise ValueError(f"{name} at ({x}, {y}) would cover {existing}")
        self.layers[layer][x, y] = name

    def _check_bounds(self, x: int, y: int) -> None:
        if not (0 <= x < self.width and 0 <= y < self.height):
            raise ValueError(f"({x}, {y}) is off the map")


def scatter_grass(town: Town) -> None:
    rng = random.Random(MAP_ID)
    for y in range(town.height):
        for x in range(town.width):
            if town.terrain[y][x] == "G" and town.ground(x, y) == "grass":
                roll = rng.random()
                if roll < 0.04:
                    town.paint(x, y, "grass_flowers")
                elif roll < 0.16:
                    town.paint(x, y, "grass_tufts")


def village(tileset: Tileset) -> Town:
    town = Town(tileset)
    main_road(town)
    lychee_lane(town)
    kapok_walk(town)
    square(town)
    park(town)
    banyan_row(town)
    riverside(town)
    mural_walls(town)
    scatter_grass(town)
    town.check()
    return town


def main_road(town: Town) -> None:
    town.fill("R", 0, 0, WIDTH, 3)
    town.paint(0, 1, *["road_line_h"] * WIDTH)
    for x in (26, 44):
        town.paint(x, 0, "crosswalk_h", "crosswalk_h", "crosswalk_h", down=True)
        town.paint(x - 1, 3, "tactile_h", "tactile_h", "tactile_h")
        town.paint(x, 4, *["tactile_v"] * 9, down=True)
        town.put(x - 2, 3, "bollard")
        town.put(x + 2, 3, "bollard")
    for x in (3, 15, 33, 51):
        town.tall(x, 4, "lamp")
    for x in (8, 19, 31, 38, 48):
        town.tree(x, 4)


def lychee_lane(town: Town) -> None:
    town.house(1, "1 Lychee Lane", 1, 6, "cream", (".wdw.", ".wdw."), extras=[(1, 1, "roof_solar")])
    town.put(5, 9, "ac_unit")
    town.put(1, 11, "planter_flowers")
    town.house(2, "2 Lychee Lane", 7, 6, "slate", (".w.d.", ".wwd."), roof="roof_green")
    town.put(11, 11, "bike_blue")

    noodles = town.building(
        13, 6, "slate", (".www.", ".....", "sssD."), roof_rows=2, extras=[(1, 0, "roof_ac")]
    )
    town.put(13, 10, "awning_red_l", "awning_red", "awning_red_r")
    town.put(14, 9, "neon_bowl")
    town.put(17, 8, "neon_vertical_top")
    town.put(17, 9, "neon_vertical_bottom")
    town.put(13, 11, "bike_yellow", "bike_yellow")
    town.doorstep("noodle_bar", noodles, 16)

    town.building(18, 6, "cream", (".ww.", "....", ".Dss"), roof_rows=2, extras=[(2, 0, "roof_ac")])
    town.put(20, 10, "awning_blue_l", "awning_blue_r")
    town.put(19, 9, "neon_24h")
    town.tall(22, 10, "vending")
    town.put(22, 11, "bins")

    cafe = town.block(
        28,
        6,
        "roof_green",
        3,
        [
            ["cafe_wall_l", "cafe_wall", "cafe_wall", "cafe_sign_l", "cafe_sign_r"]
            + ["cafe_wall", "cafe_wall", "cafe_wall_r"],
            ["cafe_window_l", "cafe_window", "cafe_window", "cafe_door"]
            + ["cafe_window", "cafe_window", "cafe_window", "cafe_window_r"],
        ],
    )
    town.put(28, 10, "cafe_awning_l", "cafe_awning", "cafe_awning_r")
    town.put(32, 10, "cafe_awning_l", "cafe_awning", "cafe_awning", "cafe_awning_r")
    town.put(34, 9, "neon_cup")
    town.put(28, 11, "cafe_table")
    town.put(30, 11, "cafe_menu")
    town.put(33, 11, "cafe_table")
    town.put(35, 11, "cafe_table")
    town.doorstep("coffee_shop", cafe, 31)
    terrace = TileArea(x=cafe.x, y=cafe.y + cafe.height, width=cafe.width, height=2)
    town.place("cafe_terrace", "The Daily Grind's terrace", LocationKind.AMENITY, terrace, (34, 11))

    maker = town.building(
        37,
        5,
        "slate",
        (".wwww.", "......", "ssssD."),
        extras=[(1, 1, "roof_solar"), (2, 1, "roof_solar"), (4, 1, "roof_skylight")],
    )
    town.put(37, 10, "awning_blue_l", "awning_blue", "awning_blue", "awning_blue_r")
    town.put(38, 9, "screen_l", "screen_r")
    town.put(41, 9, "neon_bolt")
    town.put(37, 11, "bike_blue")
    town.doorstep("maker_space", maker, 41)

    town.house(3, "3 Lychee Lane", 45, 6, "cream", (".d.w.", ".dww."), roof="roof_green")
    town.put(49, 11, "planter")
    town.house(4, "4 Lychee Lane", 51, 6, "slate", (".wdw.", ".wdw."), extras=[(3, 1, "roof_ac")])
    town.put(51, 9, "ac_unit")

    tower = (".wwww.", ".wwww.", ".wwww.", ".wdww.", ".wdww.")
    town.building(57, 4, "slate", tower, roof_rows=2, extras=[(2, 0, "roof_ac"), (3, 1, "roof_ac")])
    town.put(62, 6, "neon_vertical_top")
    town.put(62, 7, "neon_vertical_bottom")
    town.put(60, 11, "bike_yellow", "bike_blue", "bike_yellow")


def kapok_walk(town: Town) -> None:
    town.house(5, "1 Kapok Walk", 1, 14, "slate", (".w.d.", ".wwd."))
    town.house(6, "2 Kapok Walk", 7, 14, "cream", (".wdw.", ".wdw."), roof="roof_green")
    town.house(7, "3 Kapok Walk", 13, 14, "cream", (".dw.", ".dw."), extras=[(1, 1, "roof_solar")])
    town.fill("G", 1, 21, 17, 5)
    for x, y in ((2, 23), (7, 25), (12, 23), (15, 25)):
        town.tree(x, y)
    town.bench(9, 22)
    town.put(5, 22, "bush")
    town.put(16, 22, "bush")


def square(town: Town) -> None:
    town.fill("Z", 20, 13, 24, 14)
    town.fill("Z", 27, 11, 10, 2)
    for x, y in ((21, 14), (39, 14), (21, 23), (39, 23)):
        town.fill("G", x, y, 4, 3)
    for x, y in ((22, 15), (40, 15), (22, 24), (40, 24)):
        town.tree(x, y)
    town.fountain(31, 19)
    for x, y in ((26, 16), (37, 16), (26, 23), (37, 23), (31, 15), (32, 24)):
        town.paint(x, y, "plaza_inlay")
    town.place(
        "square",
        "Town Square",
        LocationKind.SQUARE,
        TileArea(x=20, y=13, width=24, height=14),
        (31, 22),
    )
    town.terminal(1, "News terminal on the square", 36, 14)
    for x in (27, 34):
        town.bench(x, 18, Facing.SOUTH)
        town.bench(x, 22, Facing.NORTH)
    for x, y, facing in (
        (31, 18, Facing.SOUTH),
        (32, 21, Facing.NORTH),
        (30, 20, Facing.EAST),
        (33, 19, Facing.WEST),
        (26, 20, Facing.EAST),
        (37, 20, Facing.WEST),
    ):
        town.spot(SpotKind.STANDING, x, y, facing)
    for x, y in ((30, 18), (33, 18), (30, 21), (33, 21)):
        town.put(x, y, "planter_flowers")
    for x, y in ((25, 20), (38, 20)):
        town.tall(x, y, "lamp")
    for x, y in ((20, 19), (43, 19)):
        town.tall(x, y, "palm")


def park(town: Town) -> None:
    town.fill("G", 46, 13, WIDTH - 46, 22)
    lake = [(55, 19, 9, 2), (53, 21, 11, 6), (55, 27, 9, 2)]
    for x, y, w, h in lake:
        town.fill("P", x - 1, y - 1, w + 2, h + 2)
    for x, y, w, h in lake:
        town.fill("W", x, y, w, h)
    town.fill("P", 46, 24, 6, 1)
    town.fill("P", 58, 30, 1, 5)
    town.place(
        "park",
        "Lotus Lake Park",
        LocationKind.AMENITY,
        TileArea(x=46, y=13, width=WIDTH - 46, height=22),
        (47, 24),
    )
    town.terminal(2, "News terminal at the park gate", 44, 22)
    for x, y in (
        (47, 15),
        (51, 17),
        (56, 15),
        (61, 16),
        (48, 21),
        (47, 28),
        (50, 32),
        (55, 33),
        (61, 32),
    ):
        town.tree(x, y)
    town.bench(49, 26, Facing.SOUTH)
    town.bench(59, 17, Facing.SOUTH)
    town.put(53, 14, "bush")
    town.put(48, 31, "bush")
    town.put(60, 31, "bush")


def banyan_row(town: Town) -> None:
    town.house(8, "1 Banyan Row", 2, 29, "cream", (".w.d.", ".wwd."), roof="roof_green")
    town.house(
        9, "2 Banyan Row", 8, 29, "slate", (".wdw.", ".wdw."), extras=[(1, 1, "roof_skylight")]
    )
    town.put(12, 32, "ac_unit")
    town.house(10, "3 Banyan Row", 14, 29, "cream", (".dw.", ".dw."))
    town.put(16, 34, "bike_blue")

    town.building(21, 29, "cream", (".wwww.", ".ssDw."), extras=[(4, 1, "roof_ac")])
    town.put(22, 33, "awning_red_l", "awning_red_r")
    town.put(24, 32, "neon_tea")
    town.put(21, 34, "planter_flowers")

    flats = (".www.", ".www.", ".wdw.", ".wdw.")
    town.building(
        29, 28, "slate", flats, roof_rows=2, extras=[(1, 0, "roof_solar"), (2, 0, "roof_solar")]
    )
    town.put(29, 31, "screen_l", "screen_r")
    town.put(33, 34, "bike_yellow", "bike_yellow")

    town.fill("G", 36, 28, 2, 5)
    town.put(36, 30, "bush")
    gallery = town.building(38, 28, "cream", (".wwww.", ".sDss."), roof="roof_green")
    town.doorstep("gallery", gallery, 40)


def riverside(town: Town) -> None:
    town.fill("W", 0, 38, WIDTH, HEIGHT - 38)
    town.paint(0, 35, *["tactile_h"] * WIDTH)
    town.terminal(3, "News terminal by the river", 46, 36)
    for x in (3, 15, 27, 39, 51, 61):
        town.tall(x, 37, "lamp")
    for x in (8, 20, 33, 55):
        town.bench(x, 37)
    for x in (12, 24, 30, 42, 49, 58):
        town.tall(x, 36, "palm")


def mural_walls(town: Town) -> None:
    town.mural("corner_shop", "east", 21, 6, 4, 0.7, 2.85)
    town.mural("daily_grind", "south", 28, 10, 3, 1.05, 1.9)
    town.mural("tower", "east", 62, 5, 5, 0.15, 3.0)
    town.mural("garden_flats", "east", 33, 29, 4, 0.15, 2.5)
    town.mural("banyan_row", "east", 17, 31, 3, 0.15, 1.85)


ROOM = (20, 14)
GALLERY = (32, 20)


def coffee_shop(tileset: Tileset) -> Town:
    room = Town(tileset, "coffee_shop", *ROOM, terrain="B")
    room.walls("panel", door=10)
    room.put(2, 0, "shelf")
    room.put(4, 0, "menu_board_l", "menu_board_r")
    room.put(7, 0, "shelf")
    room.put(13, 0, "neon_cup")
    room.put(16, 0, "shelf")
    room.put(1, 2, "back_counter", "grinder", "espresso_machine", "back_counter")
    room.put(5, 2, "back_counter", "back_counter", "espresso_machine", "back_counter")
    for y in (2, 3, 4):
        room.put(9, y, "counter_run")
    room.put(2, 5, "counter_l", "counter", "counter", "counter_till", "counter_case")
    room.put(7, 5, "counter_case", "counter", "counter_corner")
    for x, y in ((12, 3), (15, 3), (12, 7), (15, 7), (12, 10), (15, 10), (2, 8), (2, 11)):
        room.table(x, y, "cafe_table")
    for x in (2, 3):
        room.spot(SpotKind.BAR, x, 6, Facing.NORTH, LEAN)
    for y in (3, 4, 5):
        room.spot(SpotKind.BAR, 10, y, Facing.WEST, LEAN)
    room.put(18, 2, "planter_flowers")
    room.put(18, 12, "planter")
    front = (5, 6)
    counter = TileArea(x=2, y=5, width=8, height=1)
    room.interactable("coffee_shop_counter", "Counter", InteractableKind.COUNTER, counter, [front])
    room.place("coffee_shop", "The Daily Grind", LocationKind.COFFEE_SHOP, room.floor(), front)
    staff = TileArea(x=1, y=3, width=8, height=2)
    behind = "Behind the counter at the Daily Grind"
    room.place("coffee_shop_staff", behind, LocationKind.AMENITY, staff, (5, 4))
    queue = TileArea(x=5, y=6, width=1, height=4)
    room.place(
        "coffee_shop_queue", "The queue at the Daily Grind", LocationKind.AMENITY, queue, front
    )
    return room


def gallery(tileset: Tileset) -> Town:
    room = Town(tileset, "gallery", *GALLERY, terrain="L")
    room.walls("plaster", door=16)
    spots = [(x, 0) for x in range(3, 29, 4)]
    for x in (4, 18):
        room.partition("plaster", x, 9, 10)
        spots += [(x + dx, 9) for dx in (1, 4, 7)]
    for number, (x, y) in enumerate(spots, 1):
        room.painting(number, x, y)
    for x, y in ((8, 5), (22, 5), (8, 14), (22, 14)):
        room.bench(x, y, Facing.NORTH)
    for x, y in ((15, 5), (16, 15)):
        room.put(x, y, "plinth")
    for x, y in ((1, 2), (30, 2), (1, 18), (30, 18)):
        room.put(x, y, "planter")
    room.place("gallery", "The Gallery", LocationKind.GALLERY, room.floor(), (16, 12))
    return room


def maker_space(tileset: Tileset) -> Town:
    room = Town(tileset, "maker_space", *ROOM, terrain="C")
    room.walls("block", door=14)
    for x in (2, 8, 16):
        room.put(x, 0, "pegboard_l", "pegboard_r")
    room.put(13, 0, "shelf")
    room.machine("laser_cutter", "Laser cutter", 2, 2, "laser_cutter_l", "laser_cutter_r")
    room.machine("printer_3d", "3D printer", 6, 2, "printer_3d")
    room.machine("loom", "Loom", 10, 2, "loom_l", "loom_r")
    room.machine("sewing_machine", "Sewing machine", 15, 2, "sewing_machine")
    for x in (3, 8, 13):
        for y in (6, 9):
            room.workbench(x, y)
    room.put(1, 12, "planter")
    room.place("maker_space", "Spark Maker Space", LocationKind.MAKER_SPACE, room.floor(), (8, 7))
    return room


def noodle_bar(tileset: Tileset) -> Town:
    room = Town(tileset, "noodle_bar", *ROOM, terrain="T")
    room.walls("brick", door=15)
    for x in (2, 6, 12, 16):
        room.put(x, 0, "lantern")
    room.put(9, 0, "neon_bowl")
    room.put(1, 2, "kitchen_counter", "kitchen_counter", "stove", "stove", "kitchen_counter")
    room.put(6, 2, "kitchen_counter", "kitchen_counter", "stove", "kitchen_counter")
    room.put(10, 2, "kitchen_counter", "kitchen_counter", "kitchen_counter")
    for y in (2, 3):
        room.put(13, y, "counter_run")
    room.put(2, 4, "counter_l", *["counter"] * 10, "counter_corner")
    for x in range(3, 13, 2):
        room.put(x, 5, "stool")
        room.spot(SpotKind.SEAT, x, 5, Facing.NORTH, dz=STOOL_M)
    for x in (4, 8, 12, 16):
        for y in (8, 11):
            room.table(x, y, "noodle_table")
    room.table(16, 3, "noodle_table")
    room.place("noodle_bar", "Golden Bowl Noodles", LocationKind.NOODLE_BAR, room.floor(), (7, 5))
    return room


def connect(town: Town, room: Town) -> None:
    """A door from the doorstep of the room's building on the village to the mat inside."""
    step, mat = town.doorsteps[room.map_id], room.mat
    assert mat is not None, room.map_id
    door = Door(
        id=room.map_id,
        outside=MapTile(map=town.map_id, x=step.x, y=step.y),
        inside=MapTile(map=room.map_id, x=mat.x, y=mat.y),
    )
    town.doors.append(door)
    room.doors.append(door)


def world(tileset: Tileset) -> list[Town]:
    """The village and its interiors, with a door into every building that has one."""
    town = village(tileset)
    rooms = [coffee_shop(tileset), gallery(tileset), maker_space(tileset), noodle_bar(tileset)]
    for room in rooms:
        if room.map_id in town.doorsteps:
            connect(town, room)
    return [town, *rooms]


def tmj(town: Town, image: str) -> dict[str, Any]:
    ids = town.tileset.ids
    width, height = town.width, town.height
    cells = [(x, y) for y in range(height) for x in range(width)]
    layers: list[dict[str, Any]] = []
    for name in TILE_LAYERS:
        tiles = town.tiles(name)
        data = [ids[tiles[cell]] + 1 if cell in tiles else 0 for cell in cells]
        layers.append(_tile_layer(len(layers) + 1, name, data, width, height))
    blocked = town.blocked()
    marker = ids["blocked"] + 1
    collision = [marker if cell in blocked else 0 for cell in cells]
    layers.append(
        _tile_layer(len(layers) + 1, COLLISION_LAYER, collision, width, height, visible=False)
    )
    object_ids = count(1)
    objects = {
        LOCATIONS_LAYER: [_object(next(object_ids), location) for location in town.locations],
        MURALS_LAYER: [_wall(next(object_ids), wall) for wall in town.murals],
        DOORS_LAYER: [_door(next(object_ids), door, town.map_id) for door in town.doors],
        INTERACTABLES_LAYER: [_interactable(next(object_ids), i) for i in town.interactables],
        SPOTS_LAYER: [_spot(next(object_ids), spot) for spot in town.spots],
    }
    for name, group in objects.items():
        layers.append(_object_layer(len(layers) + 1, name, group))
    tileset = {
        k: v for k, v in town.tileset.data.items() if k not in ("type", "version", "tiledversion")
    }
    tileset["image"] = image
    return {
        "compressionlevel": -1,
        "height": height,
        "infinite": False,
        "layers": layers,
        "nextlayerid": len(layers) + 1,
        "nextobjectid": next(object_ids),
        "orientation": "orthogonal",
        "renderorder": "right-down",
        "tiledversion": town.tileset.data["tiledversion"],
        "tileheight": TILE_SIZE,
        "tilesets": [{"firstgid": 1, **tileset}],
        "tilewidth": TILE_SIZE,
        "type": "map",
        "version": town.tileset.data["version"],
        "width": width,
    }


def _tile_layer(
    layer_id: int, name: str, data: list[int], width: int, height: int, visible: bool = True
) -> dict[str, Any]:
    return {
        "data": data,
        "height": height,
        "id": layer_id,
        "name": name,
        "opacity": 1,
        "type": "tilelayer",
        "visible": visible,
        "width": width,
        "x": 0,
        "y": 0,
    }


def _object_layer(layer_id: int, name: str, objects: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "draworder": "topdown",
        "id": layer_id,
        "name": name,
        "objects": objects,
        "opacity": 1,
        "type": "objectgroup",
        "visible": True,
        "x": 0,
        "y": 0,
    }


def _rectangle(
    object_id: int, name: str, kind: str, area: TileArea, properties: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "height": area.height * TILE_SIZE,
        "id": object_id,
        "name": name,
        "properties": properties,
        "rotation": 0,
        "type": kind,
        "visible": True,
        "width": area.width * TILE_SIZE,
        "x": area.x * TILE_SIZE,
        "y": area.y * TILE_SIZE,
    }


def _object(object_id: int, location: Location) -> dict[str, Any]:
    properties = [
        {"name": "entry_x", "type": "int", "value": location.entry.x},
        {"name": "entry_y", "type": "int", "value": location.entry.y},
        {"name": "label", "type": "string", "value": location.name},
    ]
    return _rectangle(object_id, location.id, location.kind.value, location.area, properties)


def _door(object_id: int, door: Door, map_id: str) -> dict[str, Any]:
    here, there, side = (
        (door.outside, door.inside, "outside")
        if door.outside.map == map_id
        else (door.inside, door.outside, "inside")
    )
    properties = [
        {"name": "side", "type": "string", "value": side},
        {"name": "to_map", "type": "string", "value": there.map},
        {"name": "to_x", "type": "int", "value": there.x},
        {"name": "to_y", "type": "int", "value": there.y},
    ]
    tile = TileArea(x=here.x, y=here.y, width=1, height=1)
    return _rectangle(object_id, door.id, "door", tile, properties)


def _interactable(object_id: int, item: Interactable) -> dict[str, Any]:
    stand = " ".join(f"{tile.x},{tile.y}" for tile in item.stand)
    properties = [
        {"name": "label", "type": "string", "value": item.label},
        {"name": "stand", "type": "string", "value": stand},
    ]
    return _rectangle(object_id, item.id, item.kind.value, item.area, properties)


def _spot(object_id: int, spot: Spot) -> dict[str, Any]:
    properties = [{"name": "facing", "type": "string", "value": spot.facing.value}]
    for name in ("dx", "dy", "dz"):
        if value := round(getattr(spot, name), 3):
            properties.append({"name": name, "type": "float", "value": value})
    tile = TileArea(x=spot.x, y=spot.y, width=1, height=1)
    return _rectangle(object_id, spot.id, spot.kind.value, tile, properties)


def _wall(object_id: int, wall: MuralWall) -> dict[str, Any]:
    along, across = wall.width * TILE_SIZE, TILE_SIZE
    width, height = (along, across) if wall.face == "south" else (across, along)
    return {
        "height": height,
        "id": object_id,
        "name": wall.id,
        "properties": [
            {"name": "bottom", "type": "float", "value": wall.bottom},
            {"name": "face", "type": "string", "value": wall.face},
            {"name": "stand_x", "type": "int", "value": wall.stand.x},
            {"name": "stand_y", "type": "int", "value": wall.stand.y},
            {"name": "top", "type": "float", "value": wall.top},
        ],
        "rotation": 0,
        "type": "mural_wall",
        "visible": True,
        "width": width,
        "x": wall.x * TILE_SIZE,
        "y": wall.y * TILE_SIZE,
    }


def dumps(data: dict[str, Any]) -> str:
    """JSON with one map row per line in each tile layer, so diffs show where tiles moved."""
    width, height = data["width"], data["height"]
    rows: dict[str, str] = {}
    for layer in data["layers"]:
        if layer["type"] == "tilelayer":
            token = f"@rows:{layer['name']}"
            cells = layer["data"]
            lines = [
                ",".join(str(gid) for gid in cells[y * width : (y + 1) * width])
                for y in range(height)
            ]
            rows[json.dumps(token)] = (
                "[\n" + ",\n".join(f"        {line}" for line in lines) + "\n      ]"
            )
            layer["data"] = token
    text = json.dumps(data, indent=2, ensure_ascii=False)
    for token, value in rows.items():
        text = text.replace(token, value)
    return text + "\n"


def render(town: Town) -> Image.Image:
    image = Image.new("RGBA", (town.width * TILE_SIZE, town.height * TILE_SIZE))
    cache: dict[str, Image.Image] = {}
    for layer in TILE_LAYERS:
        for (x, y), name in town.tiles(layer).items():
            if name not in cache:
                cache[name] = town.tileset.image(name)
            image.alpha_composite(cache[name], (x * TILE_SIZE, y * TILE_SIZE))
    return image


def annotate(town: Town, image: Image.Image, scale: int = 2) -> Image.Image:
    out = image.resize((image.width * scale, image.height * scale), Image.Resampling.NEAREST)
    draw = ImageDraw.Draw(out)
    cell = TILE_SIZE * scale

    def outline(area: TileArea, colour: str) -> None:
        x1, y1 = (area.x + area.width) * cell - 1, (area.y + area.height) * cell - 1
        draw.rectangle((area.x * cell, area.y * cell, x1, y1), outline=rgba(colour), width=2)

    def mark(tile: Tile, colour: str) -> None:
        x0, y0, inset = tile.x * cell, tile.y * cell, cell // 4
        draw.rectangle(
            (x0 + inset, y0 + inset, x0 + cell - 1 - inset, y0 + cell - 1 - inset), rgba(colour)
        )

    labels = []
    for location in town.locations:
        outline(location.area, "neon")
        mark(location.entry, "yellow")
        text = label(location.id.upper(), "white")
        labels.append((text, location.area.x * cell + 4, location.area.y * cell + 4))
    for wall in town.murals:
        x0, y0 = wall.x * cell, wall.y * cell
        text = label(wall.id.upper(), "cyan")
        if wall.face == "south":
            bar = (x0, y0 + cell - 3, x0 + wall.width * cell - 1, y0 + cell + 2)
            labels.append((text, x0 + 4, y0 + cell - 7 - text.height))
        else:
            bar = (x0 + cell - 3, y0, x0 + cell + 2, y0 + wall.width * cell - 1)
            labels.append((text, x0 + cell - 7 - text.width, y0 + 4))
        draw.rectangle(bar, fill=rgba("cyan"))
        mark(wall.stand, "cyan")
    for item in town.interactables:
        outline(item.area, "orange")
        for tile in item.stand:
            mark(tile, "orange")
        text = label(item.id.upper(), "orange")
        above = item.area.y * cell - text.height - 6
        below = (item.area.y + item.area.height) * cell + 4
        labels.append((text, item.area.x * cell + 4, above if item.area.y else below))
    for door in town.doors:
        here = door.outside if door.outside.map == town.map_id else door.inside
        outline(TileArea(x=here.x, y=here.y, width=1, height=1), "lime")
    for spot in town.spots:
        x, y = ((c + 0.5) * cell for c in spot.seat)
        step_x, step_y = STEPS[spot.facing]
        reach, r = cell * 0.4, cell // 8
        draw.line((x, y, x + step_x * reach, y + step_y * reach), fill=rgba("violet"), width=2)
        draw.ellipse((x - r, y - r, x + r, y + r), fill=rgba("violet"))
    for text, x, y in labels:
        draw.rectangle((x - 3, y - 3, x + text.width + 2, y + text.height + 2), fill=rgba("ink"))
        out.alpha_composite(text, (x, y))
    return out


def write(town: Town, art: Path, folder: Path) -> list[Path]:
    """Write a map and its previews: the village's are preview.png and locations.png."""
    folder.mkdir(parents=True, exist_ok=True)
    image_path = Path(os.path.relpath(art / town.tileset.data["image"], folder)).as_posix()
    tmj_path = folder / f"{town.map_id}.tmj"
    tmj_path.write_text(dumps(tmj(town, image_path)))
    prefix, scale = ("", 2) if town.map_id == MAP_ID else (f"{town.map_id}_", 3)
    image = render(town)
    preview = folder / f"{prefix}preview.png"
    image.resize((image.width * scale, image.height * scale), Image.Resampling.NEAREST).save(
        preview
    )
    locations = folder / f"{prefix}locations.png"
    annotate(town, image, scale).save(locations)
    return [tmj_path, preview, locations]


def generate(art: Path, out: Path) -> list[Path]:
    """Build the village and its interiors from the tileset in art/, and write them and their
    previews to out/ and out/interiors/."""
    written = []
    for town in world(Tileset.load(art)):
        written += write(town, art, out if town.map_id == MAP_ID else out / INTERIORS)
    return written
