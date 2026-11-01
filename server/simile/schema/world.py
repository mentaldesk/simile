from enum import StrEnum
from typing import Self

from pydantic import Field, model_validator

from simile.schema.common import Id, Key, MapTile, Model
from simile.schema.player import Bionic, Item

VILLAGE_MAP = "village"


class Tile(Model):
    """A cell of the map grid, about 1.1 m across, counted in tiles from the top-left corner. On a
    side-view map, x runs along the street and y counts rows down from the top, and a resident
    stands on a cell with ground under it or on a climbable cell."""

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


class SideFacing(StrEnum):
    """Which way something faces or acts on a side-view map, where only right and left draw:
    `east`, to the right, or `west`, to the left."""

    EAST = "east"
    WEST = "west"


class Pose(StrEnum):
    """What someone is doing where they are. `climbing` is on stairs or a ladder, `riding` in a
    lift, and `sleeping` lying asleep in a bed, on a bed spot's cell."""

    STANDING = "standing"
    WALKING = "walking"
    SITTING = "sitting"
    READING = "reading"
    WORKING = "working"
    LOOKING = "looking"
    CLIMBING = "climbing"
    RIDING = "riding"
    SLEEPING = "sleeping"


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
    """A link between two maps: taking it from either end tile puts you on the other one. A door
    joins the village or a street (`outside`) and a building's ground floor (`inside`), or two
    streets, with `outside` on the one whose id comes first alphabetically. Stairs, a ladder or a
    lift join two floors' maps, `outside` the lower and `inside` the upper. No two links share an
    end tile, so a lift serving three floors, or two flights meeting on a landing, has a separate
    end tile on the middle floor for each link."""

    id: Id
    kind: DoorKind = Field(
        default=DoorKind.DOOR,
        exclude_if=lambda kind: kind == DoorKind.DOOR,
        description="How it's crossed. Left out for a door.",
    )
    outside: MapTile = Field(
        description="The walkable tile in front of the building's door, the lower floor's end, or "
        "the end on the street whose id comes first."
    )
    inside: MapTile = Field(
        description="The mat just inside the interior's entrance, the upper floor's end, or the "
        "end on the other street."
    )

    @model_validator(mode="after")
    def _between_maps(self) -> Self:
        if self.outside.map == self.inside.map:
            raise ValueError("a door links two different maps")
        return self


class InteractableKind(StrEnum):
    """What it is. A `plug` charges the player's lamp while they stand on one of its stand tiles.
    A `jack` is a machine only the datajack works, such as the metro's dead terminal and its lift:
    without one it's dead, and a link ending on one of its stand tiles can't be taken. A
    `searchable` is a piece of furniture or a dead appliance, searched once for what it holds."""

    COUNTER = "counter"
    PAINTING = "painting"
    MACHINE = "machine"
    PLUG = "plug"
    JACK = "jack"
    SEARCHABLE = "searchable"


HOLDS = (InteractableKind.SEARCHABLE, InteractableKind.JACK)
"""The kinds that can hold items or money or teach a recipe, found by searching them once."""


class Interactable(Model):
    """Something on an interior's map that you can use, from one of its stand tiles. A searchable
    thing is searched once for the `items` and `money` it holds and the recipe it `teaches`, and so
    is a jack that holds or teaches anything, with the datajack. The player's `searched` says
    whether it has been."""

    id: Id
    label: str = Field(min_length=1, description='What it\'s called, e.g. "3D printer".')
    kind: InteractableKind
    map: Key
    area: TileArea = Field(description="The tiles it covers.")
    stand: list[Tile] = Field(
        min_length=1, description="The tiles you use it from, on the same map."
    )
    items: list[Item] = Field(
        default=[],
        exclude_if=lambda items: not items,
        description="What searching it finds, in order: a searchable's, or a jack's. Left out "
        "while it holds nothing.",
    )
    money: float = Field(
        default=0.0,
        ge=0,
        allow_inf_nan=False,
        strict=True,
        exclude_if=lambda money: not money,
        description="Cash searching it finds, which weighs nothing: a searchable's, or a jack's. "
        "Left out while there's none.",
    )
    teaches: Bionic | None = Field(
        default=None,
        exclude_if=lambda teaches: teaches is None,
        description="The recipe searching it teaches, by the bionic it builds, such as Aris's "
        "schematic for the datajack: a searchable's, or a jack's. Left out while it teaches none.",
    )

    @model_validator(mode="after")
    def _only_searched_things_hold(self) -> Self:
        if self.kind not in HOLDS and (self.items or self.money or self.teaches is not None):
            raise ValueError("only a searchable or a jack holds items or money or teaches a recipe")
        return self
