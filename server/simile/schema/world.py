from enum import StrEnum

from pydantic import Field

from simile.schema.common import Id, Model


class Tile(Model):
    """A cell of the map grid, counted in tiles from the top-left corner."""

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


class Location(Model):
    id: Id
    name: str
    kind: LocationKind
    area: TileArea = Field(description="The tiles the location covers.")
    entry: Tile = Field(description="The tile entities walk to when they go there.")
