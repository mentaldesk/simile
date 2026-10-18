import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from simile.schema import (
    VILLAGE_MAP,
    Door,
    Facing,
    Interactable,
    InteractableKind,
    Location,
    LocationKind,
    MapTile,
    Pose,
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
SPOTS_LAYER = "spots"
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


class SpotKind(StrEnum):
    SEAT = "seat"
    BAR = "bar"
    DESK = "desk"
    TERMINAL = "terminal"
    VIEWING = "viewing"
    STANDING = "standing"


POSES = {
    SpotKind.SEAT: Pose.SITTING,
    SpotKind.BAR: Pose.STANDING,
    SpotKind.DESK: Pose.WORKING,
    SpotKind.TERMINAL: Pose.READING,
    SpotKind.VIEWING: Pose.LOOKING,
    SpotKind.STANDING: Pose.STANDING,
}


@dataclass(frozen=True)
class Spot:
    """Somewhere to spend a stay. `dx`, `dy` and `dz` are where its figure is drawn."""

    id: str
    kind: SpotKind
    map: str
    x: int
    y: int
    facing: Facing
    dx: float = 0.0
    dy: float = 0.0
    dz: float = 0.0
    """Metres up, for a bar stool."""

    @property
    def pose(self) -> Pose:
        return POSES[self.kind]

    @property
    def seat(self) -> tuple[float, float]:
        """Where the figure is, in tiles."""
        return self.x + self.dx, self.y + self.dy


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
    spots: tuple[Spot, ...] = ()

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

    def spot_at(self, x: int, y: int) -> Spot | None:
        return next((spot for spot in self.spots if (spot.x, spot.y) == (x, y)), None)


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
        spots=tuple(_spot(o, size, map_id) for o in objects(SPOTS_LAYER)),
    )


def load_maps(directory: Path = MAP_DIR) -> dict[str, TownMap]:
    """The village and every interior in directory/interiors/, by map id."""
    paths = [directory / f"{MAP_ID}.tmj", *sorted((directory / INTERIORS).glob("*.tmj"))]
    return {town.id: town for town in map(load_map, paths)}


def with_every_location(maps: Mapping[str, TownMap], home: str = MAP_ID) -> TownMap:
    """The home map, carrying the locations of every map, so `location(id)` finds any of them.
    An id on more than one map is the home map's location, or else the first map's."""
    found: dict[str, Location] = {}
    for town in (maps[home], *maps.values()):
        for location in town.locations:
            found.setdefault(location.id, location)
    return replace(maps[home], locations=tuple(found.values()))


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


def _spot(obj: dict[str, Any], size: int, map_id: str) -> Spot:
    props, area = _props(obj), _area(obj, size)
    return Spot(
        id=obj["name"],
        kind=SpotKind(obj["type"]),
        map=map_id,
        x=area.x,
        y=area.y,
        facing=Facing(props["facing"]),
        dx=props.get("dx", 0.0),
        dy=props.get("dy", 0.0),
        dz=props.get("dz", 0.0),
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
