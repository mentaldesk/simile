from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from simile.schema import Id


class Shop(BaseModel):
    """What a shop charges, and what its keeper spends on supplies."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    drink: float = Field(
        default=0.0,
        ge=0,
        description="A drink. The café charges it when it serves someone, and any other shop "
        "when someone comes in while it's staffed, but not again within the café's `again`.",
    )
    meal: float = Field(ge=0, description="Eating there, charged when they start.")
    supplies: float = Field(
        ge=0,
        le=1,
        description="The share of what it takes that its keeper pays outside the village for "
        "supplies.",
    )
    batch: int | None = Field(
        default=None,
        ge=1,
        description="Meals its keeper cooks when they arrive for a shift. It can sell out, and "
        "what's left at closing goes off. None never runs out while it's staffed.",
    )


SHOPS: dict[Id, Shop] = {
    "coffee_shop": Shop(drink=3.0, meal=5.0, supplies=0.6),
    "noodle_bar": Shop(drink=3.0, meal=10.0, supplies=0.3, batch=6),
}
SALVAGE: dict[Id, float] = {
    "copper_wire": 6.0,
    "scrap_steel": 5.0,
    "circuit_board": 8.0,
    "brass_valve": 7.0,
    "signal_relay": 6.0,
    "servo_motor": 18.0,
    "lead_pipe": 7.0,
    "copper_coil": 7.0,
    "brass_fitting": 6.0,
    "pump_impeller": 10.0,
    "float_valve": 8.0,
    "filter_mesh": 5.0,
    "old_battery": 5.0,
    "pressure_gauge": 8.0,
    "apex_board": 14.0,
}
"""The metro's salvage, then the sewers' (`simile.street.sewers`)."""
PARTS: dict[Id, float] = {
    "lithium_cell": 10.0,
    "charge_controller": 15.0,
    "usb_c_connector": 12.0,
    "infrared_lens": 40.0,
    "apex_actuator": 30.0,
}
"""The recipes' parts that aren't salvage, which buyers keep for the player to buy back."""


class EconomyConfig(BaseModel):
    """Every price and constant of the village's money. Amounts are in the same units as `Npc`'s
    `money` and `pay`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rent: float = Field(default=30.0, ge=0, description="Each resident's rent, every midnight.")
    groceries: float = Field(
        default=2.5, ge=0, description="A meal's worth of groceries, paid outside the village."
    )
    fridge: int = Field(default=8, ge=1, description="Meals a home's fridge holds.")
    low: int = Field(
        default=2,
        ge=0,
        description="Meals left in a fridge at which someone at home orders groceries to fill it.",
    )
    shops: dict[Id, Shop] = Field(default=SHOPS, description="By location id.")
    salvage: dict[Id, Annotated[float, Field(ge=0)]] = Field(
        default=SALVAGE,
        description="What a buyer pays the player for one of each kind of salvage, by item id.",
    )
    parts: dict[Id, Annotated[float, Field(ge=0)]] = Field(
        default=PARTS,
        description="What a buyer pays the player for one of each kind of part, by item id.",
    )
    buy_back: float = Field(
        default=2.0,
        ge=1,
        description="What a buyer asks for a part the player sold it, as a multiple of what it "
        "paid.",
    )
    buyers: tuple[Id, ...] = Field(
        default=("scrap_stall", "clinic"),
        description="Where salvage and parts sell, by location id: the scrap trader's stall on "
        "the metro's platform and the clinic.",
    )
    takings: float = Field(
        default=10.0,
        ge=0,
        description="What an hour running a shop is reckoned to bring its keeper, when they "
        "weigh up going to work.",
    )
    late: float = Field(
        default=5.0, ge=0, description="Minutes after a shift starts that count as late."
    )
    pay_every: float = Field(
        default=1.0, gt=0, description="Hours of work between wages, and at the end of a stint."
    )
    every: float = Field(
        default=5.0, gt=0, description="Sim seconds between looking at who's working and eating."
    )

    @model_validator(mode="after")
    def _low_below_full(self) -> Self:
        if self.low >= self.fridge:
            raise ValueError("a fridge must hold more than `low` meals")
        return self


DEFAULT_CONFIG = EconomyConfig()
