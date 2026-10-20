import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from simile.schema import (
    VILLAGE_MAP,
    Door,
    DoorKind,
    Facing,
    Interactable,
    InteractableKind,
    Location,
    LocationKind,
    MapArea,
    MapTile,
    Pose,
    Tile,
    TileArea,
)

CONTENT_DIR = Path(__file__).resolve().parents[3] / "content"
MAP_ID = VILLAGE_MAP
MAP_DIR = CONTENT_DIR / "map"
MAP_PATH = MAP_DIR / f"{MAP_ID}.tmj"
STREET_DIR = CONTENT_DIR / "street"
INTERIORS = "interiors"
FLOORS = "floors"
COLLISION_LAYER = "collision"
CLIMBABLE_LAYER = "climbable"
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


class MapKind(StrEnum):
    """What a side-view map is."""

    STREET = "street"
    FLOOR = "floor"


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
    side_view: bool = False
    kind: MapKind | None = None
    """A street or a floor, on side-view maps."""
    building: str | None = None
    """A floor's building, by its location id."""
    floor: int | None = None
    """A floor's number, 0 for the ground floor."""
    climbable: tuple[tuple[DoorKind | None, ...], ...] = ()
    """climbable[y][x] is `stairs` or `ladder` on a climbable cell, or None. Empty without any."""

    def walkable(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height and not self.blocked[y][x]

    def climb(self, x: int, y: int) -> DoorKind | None:
        """What's climbable on the cell, if anything."""
        if not self.climbable or not (0 <= x < self.width and 0 <= y < self.height):
            return None
        return self.climbable[y][x]

    def standing(self, x: int, y: int) -> bool:
        """Walkable and not partway up stairs or a ladder."""
        return self.walkable(x, y) and self.climb(x, y) is None

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
    interactables from its objects, and on a side-view map its properties and climbable cells.
    Its id is the file's name. Raises ValueError if two of its links share an end tile."""
    data = json.loads(path.read_text())
    map_id, width, height, size = path.stem, data["width"], data["height"], data["tilewidth"]
    layers = {layer["name"]: layer for layer in data["layers"]}
    props = _props(data)

    def rows[T](layer: str, cell: Callable[[int], T]) -> tuple[tuple[T, ...], ...]:
        cells = layers[layer]["data"]
        return tuple(
            tuple(cell(gid) for gid in cells[y * width : (y + 1) * width]) for y in range(height)
        )

    def objects(layer: str) -> list[dict[str, Any]]:
        return layers.get(layer, {}).get("objects", [])

    climbable: tuple[tuple[DoorKind | None, ...], ...] = ()
    if CLIMBABLE_LAYER in layers:
        names = _tile_names(data)
        climbable = rows(CLIMBABLE_LAYER, lambda gid: DoorKind(names[gid]) if gid else None)
    doors = tuple(_door(o, size, map_id) for o in objects(DOORS_LAYER))
    _one_link_per_end(doors)
    return TownMap(
        map_id,
        width,
        height,
        rows(COLLISION_LAYER, lambda gid: gid != 0),
        locations=tuple(_location(o, size, map_id) for o in objects(LOCATIONS_LAYER)),
        murals=tuple(_mural(o, size) for o in objects(MURALS_LAYER)),
        doors=doors,
        interactables=tuple(_interactable(o, size, map_id) for o in objects(INTERACTABLES_LAYER)),
        spots=tuple(_spot(o, size, map_id) for o in objects(SPOTS_LAYER)),
        side_view=props.get("view") == "side",
        kind=MapKind(props["kind"]) if "kind" in props else None,
        building=props.get("building"),
        floor=props.get("floor"),
        climbable=climbable,
    )


def load_maps(directory: Path = MAP_DIR) -> dict[str, TownMap]:
    """Every map in the directory, by map id: the village and then every interior in
    interiors/, or without a village, as in content/street/, the streets and then every floor in
    floors/. Raises ValueError if the maps break docs/protocol.md's rules for links and floors."""
    village = directory / f"{MAP_ID}.tmj"
    if village.exists():
        paths = [village, *sorted((directory / INTERIORS).glob("*.tmj"))]
    else:
        paths = [*sorted(directory.glob("*.tmj")), *sorted((directory / FLOORS).glob("*.tmj"))]
        if not paths:
            raise FileNotFoundError(f"No maps in {directory}")
    maps = {town.id: town for town in map(load_map, paths)}
    links = _first_by_id(door for town in maps.values() for door in town.doors)
    _one_link_per_end(links)
    if not village.exists():
        _check_side_view(maps, links)
    return maps


def with_every_location(maps: Mapping[str, TownMap], home: str = MAP_ID) -> TownMap:
    """The home map, carrying the locations, doors and mural walls of every map, as today's
    village has every door and wall, so `location(id)` finds any location. An id on more than one
    map is the home map's, or else the first map's. Without the home map, as on side-view maps,
    home is the first street, or else the first map."""
    if home not in maps:
        streets = [town.id for town in maps.values() if town.kind is MapKind.STREET]
        home = streets[0] if streets else next(iter(maps))
    towns = (maps[home], *maps.values())
    return replace(
        maps[home],
        locations=_first_by_id(location for town in towns for location in town.locations),
        doors=_first_by_id(door for town in towns for door in town.doors),
        murals=_first_by_id(wall for town in towns for wall in town.murals),
    )


def _first_by_id[T: (Location, Door, MuralWall)](items: Iterable[T]) -> tuple[T, ...]:
    found: dict[str, T] = {}
    for item in items:
        found.setdefault(item.id, item)
    return tuple(found.values())


def _one_link_per_end(links: Iterable[Door]) -> None:
    ends: dict[tuple[str, int, int], str] = {}
    for link in links:
        for end in (link.outside, link.inside):
            if (other := ends.setdefault((end.map, end.x, end.y), link.id)) != link.id:
                raise ValueError(f"{link.id} and {other} share an end tile: {end}")


def _check_side_view(maps: Mapping[str, TownMap], links: Iterable[Door]) -> None:
    for link in links:
        outside, inside = (maps.get(end.map) for end in (link.outside, link.inside))
        if outside is None or inside is None:
            raise ValueError(f"{link.id} leads to a map that isn't there")
        for end, town in ((link.outside, outside), (link.inside, inside)):
            if link not in town.doors:
                raise ValueError(f"{link.id} isn't the same link on {town.id}")
            if not town.standing(end.x, end.y):
                raise ValueError(f"{link.id}'s end on {town.id} isn't a standing cell")
        _check_link(link, outside, inside)
    locations = {loc.id: loc for town in maps.values() for loc in town.locations}
    for town in maps.values():
        if town.kind is MapKind.FLOOR:
            location = locations.get(town.building or "")
            if location is None or town.id not in _maps_of(location):
                raise ValueError(f"{town.id} isn't one of {town.building}'s floors")
    for location in locations.values():
        for floor in location.floors:
            if floor.map not in maps or maps[floor.map].building != location.id:
                raise ValueError(f"{location.id}'s floor {floor.map} isn't a floor of it")


def _check_link(link: Door, outside: TownMap, inside: TownMap) -> None:
    """Each kind of link joins the maps docs/protocol.md says it does."""
    kinds = (outside.kind, inside.kind)
    if link.kind is DoorKind.DOOR:
        if kinds == (MapKind.STREET, MapKind.STREET):
            if outside.id > inside.id:
                raise ValueError(f"{link.id}'s outside isn't the street whose id comes first")
        elif kinds != (MapKind.STREET, MapKind.FLOOR) or inside.floor != 0:
            raise ValueError(f"{link.id} doesn't join two streets or a street and a ground floor")
    elif (
        kinds != (MapKind.FLOOR, MapKind.FLOOR)
        or outside.building != inside.building
        or (outside.floor or 0) >= (inside.floor or 0)
    ):
        raise ValueError(f"{link.id} doesn't join a floor of a building to one above it")


def _maps_of(location: Location) -> list[str]:
    return [location.map, *(floor.map for floor in location.floors)]


def _props(obj: dict[str, Any]) -> dict[str, Any]:
    return {p["name"]: p["value"] for p in obj.get("properties", [])}


def _tile_names(data: dict[str, Any]) -> dict[int, str]:
    """Each embedded tile's `name` property, by gid."""
    return {
        tileset["firstgid"] + tile["id"]: _props(tile)["name"]
        for tileset in data["tilesets"]
        for tile in tileset.get("tiles", [])
    }


def _area(obj: dict[str, Any], size: int) -> TileArea:
    return TileArea(
        x=round(obj["x"] / size),
        y=round(obj["y"] / size),
        width=round(obj["width"] / size),
        height=round(obj["height"] / size),
    )


def _location(obj: dict[str, Any], size: int, map_id: str) -> Location:
    """A location from its object, with `floors` listing its building's other floors, if any."""
    props = _props(obj)
    floors = {"floors": [_floor(f) for f in props["floors"].split()]} if "floors" in props else {}
    return Location(
        id=obj["name"],
        name=props["label"],
        kind=LocationKind(obj["type"]),
        map=map_id,
        area=_area(obj, size),
        entry=Tile(x=props["entry_x"], y=props["entry_y"]),
        **floors,
    )


def _floor(text: str) -> MapArea:
    """A floor from `map:x,y,width,height`."""
    map_id, area = text.split(":")
    x, y, width, height = (int(n) for n in area.split(","))
    return MapArea(map=map_id, x=x, y=y, width=width, height=height)


def _door(obj: dict[str, Any], size: int, map_id: str) -> Door:
    """A link from its object on one map: `side` says which end that is, `to_*` the other end, and
    `kind` how it's crossed, a door if it's missing."""
    props, area = _props(obj), _area(obj, size)
    here = MapTile(map=map_id, x=area.x, y=area.y)
    there = MapTile(map=props["to_map"], x=props["to_x"], y=props["to_y"])
    outside, inside = (here, there) if props["side"] == "outside" else (there, here)
    kind = {"kind": DoorKind(props["kind"])} if "kind" in props else {}
    return Door(id=obj["name"], outside=outside, inside=inside, **kind)


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
