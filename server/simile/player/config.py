from pydantic import BaseModel, ConfigDict, Field

from simile.schema import Id, Item, ItemKind


class Salvage(BaseModel):
    """What lies at a salvage pickup whose map doesn't say, and how soon another lies there."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    item: Item
    respawn: float | None = Field(
        default=None,
        gt=0,
        description="Sim hours after it's taken that another lies there, in place of "
        "`PlayerConfig.respawn`.",
    )


def salvage(id: Id, name: str, weight: float) -> Salvage:
    return Salvage(item=Item(id=id, kind=ItemKind.SALVAGE, name=name, weight=weight))


SALVAGE: dict[Id, Salvage] = {
    "metro_salvage_1": salvage("copper_wire", "Copper wire", 1.5),
    "metro_salvage_2": salvage("scrap_steel", "Scrap steel", 4.5),
    "metro_salvage_3": salvage("circuit_board", "Circuit board", 0.5),
    "metro_salvage_4": salvage("brass_valve", "Brass valve", 2.0),
    "metro_salvage_5": salvage("signal_relay", "Signal relay", 1.0),
    "metro_salvage_6": salvage("servo_motor", "Servo motor", 3.0),
}


class PlayerConfig(BaseModel):
    """How the player gets hungry, eats and collapses, and what lies about for them to pick up."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    home: Id = Field(
        default="maker_space",
        description="Where they live: a meal there is free, and they wake there after "
        "collapsing. The village has no house for them, so it's Aris's workshop.",
    )
    rise: float = Field(
        default=0.25,
        gt=0,
        description="How much hungrier they get each sim hour while someone's playing: from fed "
        "to collapsing in four hours.",
    )
    waking: float = Field(
        default=0.75, ge=0, lt=1, description="Their hunger when they wake after collapsing."
    )
    home_meal: float = Field(default=1.0, gt=0, description="How much a meal at home relieves.")
    meals: dict[Id, float] = Field(
        default={"coffee_shop": 0.5, "noodle_bar": 1.0},
        description="How much a meal at each shop relieves, by location id. Only these shops "
        "feed the player, at the economy's meal price, and only while they'd feed a resident.",
    )
    food: float = Field(default=0.4, gt=0, description="How much a food item they carry relieves.")
    reach: float = Field(
        default=1.5, gt=0, description="How far from a pile, in tiles, they can pick it up."
    )
    salvage: dict[Id, Salvage] = Field(
        default=SALVAGE,
        description="What lies at the maps' salvage pickups that don't name an item, as the "
        "metro's don't, by pickup id. The economy prices salvage by item id.",
    )
    respawn: float = Field(
        default=24.0,
        gt=0,
        description="Sim hours after salvage is taken that another lies at its pickup, unless "
        "`salvage` gives the pickup its own.",
    )
    step: float = Field(
        default=0.01,
        gt=0,
        description="How far hunger, power or a lamp's charge moves before a change to it alone "
        "is sent.",
    )


DEFAULT_CONFIG = PlayerConfig()
