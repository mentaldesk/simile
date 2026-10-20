from enum import StrEnum
from typing import Self

from pydantic import Field, model_validator

from simile.schema.common import Id, Key, Model

VILLAGE_MAP = "village"


class Tile(Model):
    """A cell of the map grid, about 1.1 m across, counted in tiles from the top-left corner. On a
    side-view map, x runs along the street and y counts rows down from the top, and a resident
    stands on a cell with ground under it or on a climbable cell."""

    x: int = Field(ge=0)
    y: int = Field(ge=0)


class MapTile(Model):
    """A tile on a given map: the village or an interior, or in side view a street or a floor."""

    map: Key
    x: int = Field(ge=0)
    y: int = Field(ge=0)


class Facing(StrEnum):
    """Which way someone faces on the map, x east and y south, by angle from east through south.
    In side view, the three eastward values face right and the westward ones left, `north` shows
    their back, looking into the picture, and `south` their front."""

    EAST = "east"
    SOUTH_EAST = "south_east"
    SOUTH = "south"
    SOUTH_WEST = "south_west"
    WEST = "west"
    NORTH_WEST = "north_west"
    NORTH = "north"
    NORTH_EAST = "north_east"


class Pose(StrEnum):
    """What someone is doing where they are. `climbing` is on stairs or a ladder, and `riding` in
    a lift."""

    STANDING = "standing"
    WALKING = "walking"
    SITTING = "sitting"
    READING = "reading"
    WORKING = "working"
    LOOKING = "looking"
    CLIMBING = "climbing"
    RIDING = "riding"


class TileArea(Model):
    """A rectangle of tiles, from its top-left tile (x, y). On a side-view map, x runs along the
    street and y counts rows down from the top."""

    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(ge=1)
    height: int = Field(ge=1)


class MapArea(Model):
    """A rectangle of tiles on a given map, as a `MapTile` is a tile on one."""

    map: Key
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(ge=1)
    height: int = Field(ge=1)


class LocationKind(StrEnum):
    HOUSE = "house"
    COFFEE_SHOP = "coffee_shop"
    SQUARE = "square"
    TERMINAL = "terminal"
    AMENITY = "amenity"
    GALLERY = "gallery"
    MAKER_SPACE = "maker_space"
    NOODLE_BAR = "noodle_bar"


class Location(Model):
    """A place. Its `map`, `area` and `entry` are where you arrive, and its `floors` are the rest
    of its building."""

    id: Id
    name: str
    kind: LocationKind
    map: Key = Field(default=VILLAGE_MAP, description="The map that holds its area and entry.")
    area: TileArea = Field(description="The tiles the location covers.")
    entry: Tile = Field(description="The tile entities walk to when they go there.")
    floors: list[MapArea] = Field(
        default=[],
        exclude_if=lambda floors: not floors,
        description="Its building's other floors, each on a map of its own, as on side-view maps. "
        "Left out when empty.",
    )

    @model_validator(mode="after")
    def _a_map_per_floor(self) -> Self:
        maps = [self.map, *(floor.map for floor in self.floors)]
        if len(set(maps)) < len(maps):
            raise ValueError("each floor is on a map of its own")
        return self


class DoorKind(StrEnum):
    """How a link between maps is crossed: a door, or stairs, a ladder or a lift between floors."""

    DOOR = "door"
    STAIRS = "stairs"
    LADDER = "ladder"
    LIFT = "lift"


class Door(Model):
    """A link between two maps: taking it from either tile puts you on the other one. A door joins
    the village or a street (`outside`) and a building's ground floor (`inside`). Stairs, a ladder
    or a lift join two floors' maps, `outside` the lower and `inside` the upper."""

    id: Id
    kind: DoorKind = Field(
        default=DoorKind.DOOR,
        exclude_if=lambda kind: kind == DoorKind.DOOR,
        description="How it's crossed. Left out for a door.",
    )
    outside: MapTile = Field(
        description="The walkable tile in front of the building's door, or the lower floor's end."
    )
    inside: MapTile = Field(
        description="The mat just inside the interior's entrance, or the upper floor's end."
    )

    @model_validator(mode="after")
    def _between_maps(self) -> Self:
        if self.outside.map == self.inside.map:
            raise ValueError("a door links two different maps")
        return self


class InteractableKind(StrEnum):
    COUNTER = "counter"
    PAINTING = "painting"
    MACHINE = "machine"


class Interactable(Model):
    """Something on an interior's map that you can use, from one of its stand tiles."""

    id: Id
    label: str = Field(min_length=1, description='What it\'s called, e.g. "3D printer".')
    kind: InteractableKind
    map: Key
    area: TileArea = Field(description="The tiles it covers.")
    stand: list[Tile] = Field(
        min_length=1, description="The tiles you use it from, on the same map."
    )
