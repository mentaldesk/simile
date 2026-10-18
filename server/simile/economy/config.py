from pydantic import BaseModel, ConfigDict, Field

from simile.schema import Id


class Shop(BaseModel):
    """What a shop charges, and what its keeper spends on supplies."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    drink: float = Field(
        default=0.0, ge=0, description="A drink. The café charges it when it serves someone."
    )
    meal: float = Field(ge=0, description="Eating there, charged when they start.")
    supplies: float = Field(
        ge=0,
        le=1,
        description="The share of what it takes that its keeper pays outside the village for "
        "supplies.",
    )


SHOPS: dict[Id, Shop] = {
    "coffee_shop": Shop(drink=3.0, meal=5.0, supplies=0.6),
    "noodle_bar": Shop(meal=8.0, supplies=0.45),
}


class EconomyConfig(BaseModel):
    """Every price and constant of the village's money. Amounts are in the same units as `Npc`'s
    `money` and `pay`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rent: float = Field(default=30.0, ge=0, description="Each resident's rent, every midnight.")
    groceries: float = Field(
        default=2.5, ge=0, description="A meal at home, paid outside the village."
    )
    shops: dict[Id, Shop] = Field(default=SHOPS, description="By location id.")
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


DEFAULT_CONFIG = EconomyConfig()
