import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from simile.schema import Location, LocationKind, Tile, TileArea

CONTENT_DIR = Path(__file__).resolve().parents[3] / "content"
MAP_ID = "village"
MAP_PATH = CONTENT_DIR / "map" / f"{MAP_ID}.tmj"
COLLISION_LAYER = "collision"
LOCATIONS_LAYER = "locations"
MURALS_LAYER = "murals"
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
    """Read a Tiled map: walls from its collision layer, places and mural walls from its objects."""
    data = json.loads(path.read_text())
    width, height, size = data["width"], data["height"], data["tilewidth"]
    layers = {layer["name"]: layer for layer in data["layers"]}
    cells = layers[COLLISION_LAYER]["data"]
    blocked = tuple(
        tuple(gid != 0 for gid in cells[y * width : (y + 1) * width]) for y in range(height)
    )
    locations = tuple(_location(o, size) for o in layers[LOCATIONS_LAYER]["objects"])
    murals = tuple(_mural(o, size) for o in layers.get(MURALS_LAYER, {}).get("objects", []))
    return TownMap(path.stem, width, height, blocked, locations, murals)


def _location(obj: dict[str, Any], size: int) -> Location:
    props = {p["name"]: p["value"] for p in obj.get("properties", [])}
    return Location(
        id=obj["name"],
        name=props["label"],
        kind=LocationKind(obj["type"]),
        area=TileArea(
            x=round(obj["x"] / size),
            y=round(obj["y"] / size),
            width=round(obj["width"] / size),
            height=round(obj["height"] / size),
        ),
        entry=Tile(x=props["entry_x"], y=props["entry_y"]),
    )


def _mural(obj: dict[str, Any], size: int) -> MuralWall:
    props = {p["name"]: p["value"] for p in obj.get("properties", [])}
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
