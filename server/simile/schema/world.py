from enum import StrEnum
from typing import Self

from pydantic import Field, model_validator

from simile.schema.common import Id, Key, Model

VILLAGE_MAP = "village"


class Tile(Model):
    """A cell of the map grid, counted in tiles from the top-left corner."""

    x: int = Field(ge=0)
    y: int = Field(ge=0)


class MapTile(Model):
    """A tile on a given map: the village or an interior."""

    map: Key
    x: int = Field(ge=0)
    y: int = Field(ge=0)


class TileArea(Model):
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
    id: Id
    name: str
    kind: LocationKind
    map: Key = Field(default=VILLAGE_MAP, description="The map that holds its area and entry.")
    area: TileArea = Field(description="The tiles the location covers.")
    entry: Tile = Field(description="The tile entities walk to when they go there.")


class Door(Model):
    """A way into a building. Stepping onto either tile puts you on the other one."""

    id: Id
    outside: MapTile = Field(description="The walkable tile in front of the building's door.")
    inside: MapTile = Field(description="The mat just inside the interior's entrance.")

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
