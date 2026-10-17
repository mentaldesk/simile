import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from simile.schema import (
    VILLAGE_MAP,
    Door,
    Interactable,
    InteractableKind,
    Location,
    LocationKind,
    MapTile,
    Tile,
    TileArea,
)

CONTENT_DIR = Path(__file__).resolve().parents[3] / "content"
MAP_ID = VILLAGE_MAP
MAP_DIR = CONTENT_DIR / "map"
MAP_PATH = MAP_DIR / f"{MAP_ID}.tmj"
INTERIORS = "interiors"
COLLISION_LAYER = "collision"
LOCATIONS_LAYER = "locations"
MURALS_LAYER = "murals"
DOORS_LAYER = "doors"
INTERACTABLES_LAYER = "interactables"
WALKING_SPEED = 1.3  # tiles per sim second: a 1.4 m/s walk, with a tile about 1.1 m

type Face = Literal["south", "east"]


@dataclass(frozen=True)
class MuralWall:
    """A wall for murals, as in M1's `murals` message, and the tile its painter stands on."""

    id: str
    x: int
    y: int
    width: int
    face: Face
    bottom: float
    top: float
    stand: Tile


@dataclass(frozen=True)
class TownMap:
    id: str
    width: int
    height: int
    blocked: tuple[tuple[bool, ...], ...]
    """blocked[y][x] is True where nobody can walk."""
    locations: tuple[Location, ...]
    murals: tuple[MuralWall, ...] = ()
    doors: tuple[Door, ...] = ()
    """Every door with an end on this map."""
    interactables: tuple[Interactable, ...] = ()

    def walkable(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height and not self.blocked[y][x]

    def location(self, location_id: str) -> Location:
        for location in self.locations:
            if location.id == location_id:
                return location
        raise KeyError(location_id)

    def mural(self, wall_id: str) -> MuralWall:
        for wall in self.murals:
            if wall.id == wall_id:
                return wall
        raise KeyError(wall_id)


def load_map(path: Path = MAP_PATH) -> TownMap:
    """Read a Tiled map: walls from its collision layer, and places, mural walls, doors and
    interactables from its objects. Its id is the file's name."""
    data = json.loads(path.read_text())
    map_id, width, height, size = path.stem, data["width"], data["height"], data["tilewidth"]
    layers = {layer["name"]: layer for layer in data["layers"]}
    cells = layers[COLLISION_LAYER]["data"]
    blocked = tuple(
        tuple(gid != 0 for gid in cells[y * width : (y + 1) * width]) for y in range(height)
    )

    def objects(layer: str) -> list[dict[str, Any]]:
        return layers.get(layer, {}).get("objects", [])

    return TownMap(
        map_id,
        width,
        height,
        blocked,
        locations=tuple(_location(o, size, map_id) for o in objects(LOCATIONS_LAYER)),
        murals=tuple(_mural(o, size) for o in objects(MURALS_LAYER)),
        doors=tuple(_door(o, size, map_id) for o in objects(DOORS_LAYER)),
        interactables=tuple(_interactable(o, size, map_id) for o in objects(INTERACTABLES_LAYER)),
    )


def load_maps(directory: Path = MAP_DIR) -> dict[str, TownMap]:
    """The village and every interior in directory/interiors/, by map id."""
    paths = [directory / f"{MAP_ID}.tmj", *sorted((directory / INTERIORS).glob("*.tmj"))]
    return {town.id: town for town in map(load_map, paths)}


def _props(obj: dict[str, Any]) -> dict[str, Any]:
    return {p["name"]: p["value"] for p in obj.get("properties", [])}


def _area(obj: dict[str, Any], size: int) -> TileArea:
    return TileArea(
        x=round(obj["x"] / size),
        y=round(obj["y"] / size),
        width=round(obj["width"] / size),
        height=round(obj["height"] / size),
    )


def _location(obj: dict[str, Any], size: int, map_id: str) -> Location:
    props = _props(obj)
    return Location(
        id=obj["name"],
        name=props["label"],
        kind=LocationKind(obj["type"]),
        map=map_id,
        area=_area(obj, size),
        entry=Tile(x=props["entry_x"], y=props["entry_y"]),
    )


def _door(obj: dict[str, Any], size: int, map_id: str) -> Door:
    """A door from its object on one map: `side` says which end that is, `to_*` the other end."""
    props, area = _props(obj), _area(obj, size)
    here = MapTile(map=map_id, x=area.x, y=area.y)
    there = MapTile(map=props["to_map"], x=props["to_x"], y=props["to_y"])
    outside, inside = (here, there) if props["side"] == "outside" else (there, here)
    return Door(id=obj["name"], outside=outside, inside=inside)


def _interactable(obj: dict[str, Any], size: int, map_id: str) -> Interactable:
    props = _props(obj)
    stand = [pair.split(",") for pair in props["stand"].split()]
    return Interactable(
        id=obj["name"],
        label=props["label"],
        kind=InteractableKind(obj["type"]),
        map=map_id,
        area=_area(obj, size),
        stand=[Tile(x=int(x), y=int(y)) for x, y in stand],
    )


def _mural(obj: dict[str, Any], size: int) -> MuralWall:
    props = _props(obj)
    along = obj["width"] if props["face"] == "south" else obj["height"]
    return MuralWall(
        id=obj["name"],
        x=round(obj["x"] / size),
        y=round(obj["y"] / size),
        width=round(along / size),
        face=props["face"],
        bottom=props["bottom"],
        top=props["top"],
        stand=Tile(x=props["stand_x"], y=props["stand_y"]),
    )
