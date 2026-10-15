import json
import random
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from simile.art.palette import rgba
from simile.art.preview import label
from simile.art.tiles import edge_variant
from simile.schema import Location, LocationKind, Tile, TileArea
from simile.world.map import COLLISION_LAYER, LOCATIONS_LAYER, MAP_ID

TILE_SIZE = 16
WIDTH, HEIGHT = 64, 42
TERRAIN = {"P": "pavement", "G": "grass", "R": "road", "W": "water", "Z": "plaza"}
PATCHES = {"G", "R", "W"}
TILE_LAYERS = ("ground", "buildings", "decor", "above")
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
    def __init__(self, tileset: Tileset) -> None:
        self.tileset = tileset
        self.terrain = [["P"] * WIDTH for _ in range(HEIGHT)]
        self.overrides: dict[tuple[int, int], str] = {}
        self.layers: dict[str, dict[tuple[int, int], str]] = {name: {} for name in TILE_LAYERS[1:]}
        self.locations: list[Location] = []

    def fill(self, terrain: str, x: int, y: int, w: int, h: int) -> None:
        for yy in range(max(y, 0), min(y + h, HEIGHT)):
            for xx in range(max(x, 0), min(x + w, WIDTH)):
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

    def bench(self, x: int, y: int) -> None:
        self.put(x, y, "bench_l", "bench_r")

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
            id=location_id, name=name, kind=kind, area=area, entry=Tile(x=entry[0], y=entry[1])
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
        grown = area.model_copy(update={"height": area.height + front})
        self.place(location_id, name, kind, grown, (door, area.y + area.height))

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

    def terminal(self, number: int, name: str, x: int, y: int) -> None:
        self.tall(x, y, "terminal")
        area = TileArea(x=x, y=y - 1, width=1, height=3)
        self.place(f"terminal_{number}", name, LocationKind.TERMINAL, area, (x, y + 1))

    def ground(self, x: int, y: int) -> str:
        if (x, y) in self.overrides:
            return self.overrides[x, y]
        cell = self.terrain[y][x]
        if cell not in PATCHES:
            return TERRAIN[cell]

        def same(dx: int, dy: int) -> bool:
            nx, ny = x + dx, y + dy
            return not (0 <= nx < WIDTH and 0 <= ny < HEIGHT) or self.terrain[ny][nx] == cell

        return edge_variant(TERRAIN[cell], same)

    def tiles(self, layer: str) -> dict[tuple[int, int], str]:
        if layer == "ground":
            return {(x, y): self.ground(x, y) for y in range(HEIGHT) for x in range(WIDTH)}
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
        for y in range(HEIGHT):
            for x in range(WIDTH):
                cell = self.terrain[y][x]
                if cell in PATCHES and not self._thick(x, y):
                    raise ValueError(f"{TERRAIN[cell]} at ({x}, {y}) is less than two tiles thick")
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        nx, ny = x + dx, y + dy
                        if 0 <= nx < WIDTH and 0 <= ny < HEIGHT:
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
                    not (0 <= sx < WIDTH and 0 <= sy < HEIGHT) or self.terrain[sy][sx] == cell
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

    @staticmethod
    def _check_bounds(x: int, y: int) -> None:
        if not (0 <= x < WIDTH and 0 <= y < HEIGHT):
            raise ValueError(f"({x}, {y}) is off the map")


def scatter_grass(town: Town) -> None:
    rng = random.Random(MAP_ID)
    for y in range(HEIGHT):
        for x in range(WIDTH):
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
    town.place_building("noodle_bar", "Golden Bowl Noodles", LocationKind.AMENITY, noodles, 16)

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
    town.place_building(
        "coffee_shop", "The Daily Grind", LocationKind.COFFEE_SHOP, cafe, 31, front=2
    )

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
    town.place_building("maker_space", "Spark Maker Space", LocationKind.AMENITY, maker, 41)

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
        town.bench(x, 18)
        town.bench(x, 22)
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
    town.bench(49, 26)
    town.bench(59, 17)
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

    town.fill("G", 36, 28, 8, 5)
    for x, y in ((37, 30), (41, 32)):
        town.tree(x, y)
    town.tall(42, 29, "palm")
    town.put(40, 29, "bush")


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


def tmj(town: Town) -> dict[str, Any]:
    ids = town.tileset.ids
    layers: list[dict[str, Any]] = []
    for name in TILE_LAYERS:
        tiles = town.tiles(name)
        data = [
            ids[tiles[x, y]] + 1 if (x, y) in tiles else 0
            for y in range(HEIGHT)
            for x in range(WIDTH)
        ]
        layers.append(_tile_layer(len(layers) + 1, name, data))
    blocked = town.blocked()
    marker = ids["blocked"] + 1
    collision = [marker if (x, y) in blocked else 0 for y in range(HEIGHT) for x in range(WIDTH)]
    layers.append(_tile_layer(len(layers) + 1, COLLISION_LAYER, collision, visible=False))
    objects = [_object(i + 1, location) for i, location in enumerate(town.locations)]
    layers.append(
        {
            "draworder": "topdown",
            "id": len(layers) + 1,
            "name": LOCATIONS_LAYER,
            "objects": objects,
            "opacity": 1,
            "type": "objectgroup",
            "visible": True,
            "x": 0,
            "y": 0,
        }
    )
    tileset = {
        k: v for k, v in town.tileset.data.items() if k not in ("type", "version", "tiledversion")
    }
    tileset["image"] = f"../art/{tileset['image']}"
    return {
        "compressionlevel": -1,
        "height": HEIGHT,
        "infinite": False,
        "layers": layers,
        "nextlayerid": len(layers) + 1,
        "nextobjectid": len(objects) + 1,
        "orientation": "orthogonal",
        "renderorder": "right-down",
        "tiledversion": town.tileset.data["tiledversion"],
        "tileheight": TILE_SIZE,
        "tilesets": [{"firstgid": 1, **tileset}],
        "tilewidth": TILE_SIZE,
        "type": "map",
        "version": town.tileset.data["version"],
        "width": WIDTH,
    }


def _tile_layer(layer_id: int, name: str, data: list[int], visible: bool = True) -> dict[str, Any]:
    return {
        "data": data,
        "height": HEIGHT,
        "id": layer_id,
        "name": name,
        "opacity": 1,
        "type": "tilelayer",
        "visible": visible,
        "width": WIDTH,
        "x": 0,
        "y": 0,
    }


def _object(object_id: int, location: Location) -> dict[str, Any]:
    area = location.area
    return {
        "height": area.height * TILE_SIZE,
        "id": object_id,
        "name": location.id,
        "properties": [
            {"name": "entry_x", "type": "int", "value": location.entry.x},
            {"name": "entry_y", "type": "int", "value": location.entry.y},
            {"name": "label", "type": "string", "value": location.name},
        ],
        "rotation": 0,
        "type": location.kind.value,
        "visible": True,
        "width": area.width * TILE_SIZE,
        "x": area.x * TILE_SIZE,
        "y": area.y * TILE_SIZE,
    }


def dumps(data: dict[str, Any]) -> str:
    """JSON with one map row per line in each tile layer, so diffs show where tiles moved."""
    rows: dict[str, str] = {}
    for layer in data["layers"]:
        if layer["type"] == "tilelayer":
            token = f"@rows:{layer['name']}"
            cells = layer["data"]
            lines = [
                ",".join(str(gid) for gid in cells[y * WIDTH : (y + 1) * WIDTH])
                for y in range(HEIGHT)
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
    image = Image.new("RGBA", (WIDTH * TILE_SIZE, HEIGHT * TILE_SIZE))
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
    for location in town.locations:
        area = location.area
        box = (
            area.x * cell,
            area.y * cell,
            (area.x + area.width) * cell - 1,
            (area.y + area.height) * cell - 1,
        )
        draw.rectangle(box, outline=rgba("neon"), width=2)
        ex, ey = location.entry.x * cell, location.entry.y * cell
        draw.rectangle((ex + 8, ey + 8, ex + cell - 9, ey + cell - 9), fill=rgba("yellow"))
    for location in town.locations:
        text = label(location.id.upper(), "white")
        x, y = location.area.x * cell + 4, location.area.y * cell + 4
        draw.rectangle((x - 3, y - 3, x + text.width + 2, y + text.height + 2), fill=rgba("ink"))
        out.alpha_composite(text, (x, y))
    return out


def generate(art: Path, out: Path) -> list[Path]:
    """Build the village from the tileset in art/ and write the map and its previews to out/."""
    town = village(Tileset.load(art))
    out.mkdir(parents=True, exist_ok=True)
    tmj_path = out / f"{MAP_ID}.tmj"
    tmj_path.write_text(dumps(tmj(town)))
    image = render(town)
    preview = out / "preview.png"
    image.resize((image.width * 2, image.height * 2), Image.Resampling.NEAREST).save(preview)
    locations = out / "locations.png"
    annotate(town, image).save(locations)
    return [tmj_path, preview, locations]
