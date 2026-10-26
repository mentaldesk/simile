import json
from dataclasses import dataclass
from itertools import count
from typing import Any

from simile.schema import (
    CreatureKind,
    Door,
    DoorKind,
    Facing,
    Interactable,
    Item,
    Location,
    TileArea,
)
from simile.world.map import (
    CLIMBABLE_LAYER,
    COLLISION_LAYER,
    DOORS_LAYER,
    INTERACTABLES_LAYER,
    LIGHT_LAYER,
    LOCATIONS_LAYER,
    MURALS_LAYER,
    SOLID_LAYER,
    SPOTS_LAYER,
    Light,
    MapKind,
    MuralWall,
    Spot,
    SpotKind,
)

type Cell = tuple[int, int]

TILE_SIZE = 16
BUILDINGS_LAYER = "buildings"
FURNITURE_LAYER = "furniture"
PICKUPS_LAYER = "pickups"
CREATURES_LAYER = "creatures"
MARKERS = ("blocked", "solid", "stairs", "ladder")
"""The marker tiles, in tile id order, that the tile layers use."""
MARKERS_IMAGE = "markers.png"
FORMAT = {"version": "1.10", "tiledversion": "1.11.2"}


def gid(marker: str) -> int:
    return MARKERS.index(marker) + 1


@dataclass(frozen=True)
class Piece:
    """A piece of furniture or a street prop, by the name it's painted as, and where it stands."""

    name: str
    area: TileArea


@dataclass(frozen=True)
class Pickup:
    """A standing cell where `salvage` can lie, or a `secret` holding money or an item."""

    id: str
    kind: str
    x: int
    y: int
    money: float = 0.0
    item: Item | None = None
    needs: str | None = None
    """What reaching it takes, on `simile.street.jump.NEEDS`' scale, or None for a walk."""


@dataclass(frozen=True)
class Spawn:
    """Where a creature starts, and the `area` it keeps to, if any."""

    id: str
    kind: CreatureKind
    x: int
    y: int
    area: TileArea | None = None


@dataclass(frozen=True)
class Facade:
    """A building's front on a street, covering its storeys above the street's standing row."""

    id: str
    label: str
    area: TileArea
    storeys: int
    interior: bool
    """Whether it has floor maps, as a location's building does."""


class Plan:
    """A side-view map being built."""

    def __init__(self, map_id: str, width: int, height: int, kind: MapKind, **props: Any) -> None:
        self.id, self.width, self.height, self.kind = map_id, width, height, kind
        self.properties: dict[str, Any] = {"kind": kind.value, "view": "side", **props}
        self.solid: set[Cell] = set()
        self.climbable: dict[Cell, DoorKind] = {}
        self.buildings: list[Facade] = []
        self.furniture: list[Piece] = []
        self.locations: list[Location] = []
        self.murals: list[MuralWall] = []
        self.doors: list[Door] = []
        self.interactables: list[Interactable] = []
        self.spots: list[Spot] = []
        self.light: list[Light] = []
        self.pickups: list[Pickup] = []
        self.creatures: list[Spawn] = []

    def fill(self, x: int, y: int, width: int, height: int) -> None:
        for cell in ((cx, cy) for cy in range(y, y + height) for cx in range(x, x + width)):
            self._bounds(*cell)
            self.solid.add(cell)

    def clear(self, x: int, y: int, width: int, height: int) -> None:
        self.solid -= {(cx, cy) for cy in range(y, y + height) for cx in range(x, x + width)}

    def stairs(self, bottom: Cell, east: bool, steps: int) -> None:
        """A flight up from the standing cell `bottom`, `steps` stairs up to the east or west."""
        x, y = bottom
        for i in range(1, steps + 1):
            self._climbable(x + (i if east else -i), y - i, DoorKind.STAIRS)

    def ladder(self, bottom: Cell, rungs: int) -> None:
        """A ladder straight up from the standing cell `bottom`, stepped off sideways at the top."""
        x, y = bottom
        for i in range(1, rungs + 1):
            self._climbable(x, y - i, DoorKind.LADDER)

    def piece(self, name: str, x: int, y: int, width: int = 1, height: int = 1) -> None:
        self.furniture.append(Piece(name, TileArea(x=x, y=y, width=width, height=height)))

    def spot(
        self, spot_id: str, kind: SpotKind, x: int, y: int, facing: Facing, dz: float = 0.0
    ) -> None:
        self.spots.append(Spot(spot_id, kind, self.id, x, y, facing, dz=dz))

    def walkable(self, x: int, y: int) -> bool:
        """Open, with solid under it or climbable."""
        if not (0 <= x < self.width and 0 <= y < self.height) or (x, y) in self.solid:
            return False
        return (x, y) in self.climbable or (x, y + 1) in self.solid

    def standing(self, x: int, y: int) -> bool:
        return self.walkable(x, y) and (x, y) not in self.climbable

    def check(self) -> None:
        """Raise unless everywhere people stop is a standing cell, and spot ids are unique."""
        stops = [(f"spot {s.id}", s.x, s.y) for s in self.spots]
        stops += [(f"{loc.id}'s entry", loc.entry.x, loc.entry.y) for loc in self.locations]
        stops += [
            (f"{item.id}'s stand", tile.x, tile.y)
            for item in self.interactables
            for tile in item.stand
        ]
        stops += [(f"{wall.id}'s stand", wall.stand.x, wall.stand.y) for wall in self.murals]
        stops += [(f"pickup {p.id}", p.x, p.y) for p in self.pickups]
        stops += [
            (f"{door.id}'s end", end.x, end.y)
            for door in self.doors
            for end in (door.outside, door.inside)
            if end.map == self.id
        ]
        for what, x, y in stops:
            if not self.standing(x, y):
                raise ValueError(f"{what} on {self.id} at ({x}, {y}) isn't a standing cell")
        ids = [spot.id for spot in self.spots]
        if len(ids) != len(set(ids)):
            raise ValueError(f"{self.id} has two spots with one id")
        for area in (light.area for light in self.light):
            self._bounds(area.x, area.y)
            self._bounds(area.x + area.width - 1, area.y + area.height - 1)

    def _climbable(self, x: int, y: int, kind: DoorKind) -> None:
        self._bounds(x, y)
        if (x, y) in self.solid or (x, y + 1) in self.solid:
            raise ValueError(f"{kind} at ({x}, {y}) on {self.id} is in or on something solid")
        self.climbable[x, y] = kind

    def _bounds(self, x: int, y: int) -> None:
        if not (0 <= x < self.width and 0 <= y < self.height):
            raise ValueError(f"({x}, {y}) is off {self.id}")


def tmj(plan: Plan, markers: str) -> dict[str, Any]:
    """The plan as a Tiled map, with the marker tileset's image at `markers`."""
    cells = [(x, y) for y in range(plan.height) for x in range(plan.width)]
    climb = {DoorKind.STAIRS: gid("stairs"), DoorKind.LADDER: gid("ladder")}
    tiles = {
        SOLID_LAYER: [gid("solid") if cell in plan.solid else 0 for cell in cells],
        CLIMBABLE_LAYER: [climb[plan.climbable[c]] if c in plan.climbable else 0 for c in cells],
        COLLISION_LAYER: [0 if plan.walkable(*cell) else gid("blocked") for cell in cells],
    }
    layers = [
        _tile_layer(i, name, data, plan, visible=name != COLLISION_LAYER)
        for i, (name, data) in enumerate(tiles.items(), 1)
    ]
    ids = count(1)
    objects = {
        BUILDINGS_LAYER: [_facade(next(ids), facade) for facade in plan.buildings],
        FURNITURE_LAYER: [_piece(next(ids), piece) for piece in plan.furniture],
        LOCATIONS_LAYER: [_location(next(ids), location) for location in plan.locations],
        MURALS_LAYER: [_wall(next(ids), wall) for wall in plan.murals],
        DOORS_LAYER: [_door(next(ids), door, plan.id) for door in plan.doors],
        INTERACTABLES_LAYER: [_interactable(next(ids), item) for item in plan.interactables],
        SPOTS_LAYER: [_spot(next(ids), spot) for spot in plan.spots],
        LIGHT_LAYER: [_light(next(ids), light) for light in plan.light],
        PICKUPS_LAYER: [_pickup(next(ids), pickup) for pickup in plan.pickups],
    }
    if plan.creatures:
        objects[CREATURES_LAYER] = [_spawn(next(ids), spawn) for spawn in plan.creatures]
    for name, group in objects.items():
        layers.append(_object_layer(len(layers) + 1, name, group))
    return {
        "compressionlevel": -1,
        "height": plan.height,
        "infinite": False,
        "layers": layers,
        "nextlayerid": len(layers) + 1,
        "nextobjectid": next(ids),
        "orientation": "orthogonal",
        "properties": _properties(plan.properties),
        "renderorder": "right-down",
        "tiledversion": FORMAT["tiledversion"],
        "tileheight": TILE_SIZE,
        "tilesets": [_tileset(markers)],
        "tilewidth": TILE_SIZE,
        "type": "map",
        "version": FORMAT["version"],
        "width": plan.width,
    }


def dumps(data: dict[str, Any]) -> str:
    """JSON with one map row per line in each tile layer, so diffs show which cells changed."""
    width = data["width"]
    rows: dict[str, str] = {}
    for layer in data["layers"]:
        if layer["type"] == "tilelayer":
            token = json.dumps(f"@rows:{layer['name']}")
            cells = layer["data"]
            lines = [",".join(map(str, cells[i : i + width])) for i in range(0, len(cells), width)]
            rows[token] = "[\n" + ",\n".join(f"        {line}" for line in lines) + "\n      ]"
            layer["data"] = json.loads(token)
    text = json.dumps(data, indent=2, ensure_ascii=False)
    for token, value in rows.items():
        text = text.replace(token, value)
    return text + "\n"


def _properties(props: dict[str, Any]) -> list[dict[str, Any]]:
    kinds = {bool: "bool", int: "int", float: "float", str: "string"}
    return [
        {"name": name, "type": kinds[type(value)], "value": value}
        for name, value in sorted(props.items())
    ]


def _tileset(image: str) -> dict[str, Any]:
    return {
        "columns": len(MARKERS),
        "firstgid": 1,
        "image": image,
        "imageheight": TILE_SIZE,
        "imagewidth": TILE_SIZE * len(MARKERS),
        "margin": 0,
        "name": "markers",
        "spacing": 0,
        "tilecount": len(MARKERS),
        "tileheight": TILE_SIZE,
        "tiles": [
            {"id": i, "properties": _properties({"name": name})} for i, name in enumerate(MARKERS)
        ],
        "tilewidth": TILE_SIZE,
    }


def _tile_layer(
    layer_id: int, name: str, data: list[int], plan: Plan, visible: bool
) -> dict[str, Any]:
    return {
        "data": data,
        "height": plan.height,
        "id": layer_id,
        "name": name,
        "opacity": 1,
        "type": "tilelayer",
        "visible": visible,
        "width": plan.width,
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
    object_id: int, name: str, kind: str, area: TileArea, props: dict[str, Any]
) -> dict[str, Any]:
    return {
        "height": area.height * TILE_SIZE,
        "id": object_id,
        "name": name,
        "properties": _properties(props),
        "rotation": 0,
        "type": kind,
        "visible": True,
        "width": area.width * TILE_SIZE,
        "x": area.x * TILE_SIZE,
        "y": area.y * TILE_SIZE,
    }


def _tile(x: int, y: int) -> TileArea:
    return TileArea(x=x, y=y, width=1, height=1)


def _facade(object_id: int, facade: Facade) -> dict[str, Any]:
    props = {"interior": facade.interior, "label": facade.label, "storeys": facade.storeys}
    return _rectangle(object_id, facade.id, "building", facade.area, props)


def _piece(object_id: int, piece: Piece) -> dict[str, Any]:
    return _rectangle(object_id, piece.name, piece.name, piece.area, {})


def _location(object_id: int, location: Location) -> dict[str, Any]:
    props: dict[str, Any] = {
        "entry_x": location.entry.x,
        "entry_y": location.entry.y,
        "label": location.name,
    }
    if location.floors:
        props["floors"] = " ".join(
            f"{f.map}:{f.x},{f.y},{f.width},{f.height}" for f in location.floors
        )
    return _rectangle(object_id, location.id, location.kind.value, location.area, props)


def _door(object_id: int, door: Door, map_id: str) -> dict[str, Any]:
    here, there, side = (
        (door.outside, door.inside, "outside")
        if door.outside.map == map_id
        else (door.inside, door.outside, "inside")
    )
    props = {
        "kind": door.kind.value,
        "side": side,
        "to_map": there.map,
        "to_x": there.x,
        "to_y": there.y,
    }
    return _rectangle(object_id, door.id, "door", _tile(here.x, here.y), props)


def _interactable(object_id: int, item: Interactable) -> dict[str, Any]:
    props: dict[str, Any] = {
        "label": item.label,
        "stand": " ".join(f"{t.x},{t.y}" for t in item.stand),
    }
    if item.items:
        found = [thing.model_dump(mode="json") for thing in item.items]
        props["items"] = json.dumps(found, ensure_ascii=False)
    if item.teaches is not None:
        props["teaches"] = item.teaches.value
    return _rectangle(object_id, item.id, item.kind.value, item.area, props)


def _spot(object_id: int, spot: Spot) -> dict[str, Any]:
    props: dict[str, Any] = {"facing": spot.facing.value}
    if spot.dz:
        props["dz"] = spot.dz
    return _rectangle(object_id, spot.id, spot.kind.value, _tile(spot.x, spot.y), props)


def _wall(object_id: int, wall: MuralWall) -> dict[str, Any]:
    props = {
        "bottom": wall.bottom,
        "face": wall.face,
        "stand_x": wall.stand.x,
        "stand_y": wall.stand.y,
        "top": wall.top,
    }
    area = TileArea(x=wall.x, y=wall.y, width=wall.width, height=1)
    return _rectangle(object_id, wall.id, "mural_wall", area, props)


def _light(object_id: int, light: Light) -> dict[str, Any]:
    return _rectangle(object_id, light.id, "light", light.area, {"lit": light.lit})


def _pickup(object_id: int, pickup: Pickup) -> dict[str, Any]:
    props: dict[str, Any] = {}
    if pickup.money:
        props["money"] = pickup.money
    if pickup.item is not None:
        item = pickup.item
        props |= {"item": item.id, "item_kind": item.kind.value, "item_name": item.name}
        props["item_weight"] = item.weight
    if pickup.needs is not None:
        props["needs"] = str(pickup.needs)
    return _rectangle(object_id, pickup.id, pickup.kind, _tile(pickup.x, pickup.y), props)


def _spawn(object_id: int, spawn: Spawn) -> dict[str, Any]:
    props = {}
    if (area := spawn.area) is not None:
        props["area"] = f"{area.x},{area.y},{area.width},{area.height}"
    return _rectangle(object_id, spawn.id, spawn.kind.value, _tile(spawn.x, spawn.y), props)
