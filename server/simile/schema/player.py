from enum import StrEnum
from typing import Final, Literal, Self

from pydantic import Field, model_validator

from simile.schema.common import Id, Model, Unit

CARRY_LIMIT = 10.0
PRESENT: Final = "present"
SOLD: Final = "sold"


class ItemKind(StrEnum):
    """What a carried thing is for: `salvage` to sell, `food` to eat, or the `lamp` to see by."""

    SALVAGE = "salvage"
    FOOD = "food"
    LAMP = "lamp"


class Item(Model):
    """Something the player carries."""

    id: Id = Field(
        description='What it is, the same for every one of its kind, e.g. "copper_wire" or '
        '"lamp". Salvage is priced by it.'
    )
    kind: ItemKind
    name: str = Field(min_length=1, description='What the player sees, e.g. "Copper wire".')
    weight: float = Field(
        ge=0, allow_inf_nan=False, description="In kg, counted against the carry limit."
    )
    charge: Unit | None = Field(
        default=None,
        description="A lamp's battery, from 0 (flat) to 1 (full). Null for anything else.",
    )

    @model_validator(mode="after")
    def _only_a_lamp_has_a_charge(self) -> Self:
        if (self.kind is ItemKind.LAMP) != (self.charge is not None):
            raise ValueError("a lamp has a charge, and nothing else does")
        return self


def lamp() -> Item:
    """The lamp the player starts with, fully charged."""
    return Item(id="lamp", kind=ItemKind.LAMP, name="Lamp", weight=1.0, charge=1.0)


class Bionic(StrEnum):
    """A part fitted in place of one of the player's own. The hydraulic legs replace their legs,
    the datajack takes a vertebra, and the infrared eye takes either eye."""

    HYDRAULIC_LEGS = "hydraulic_legs"
    DATAJACK = "datajack"
    INFRARED_EYE = "infrared_eye"

    @property
    def replaces(self) -> frozenset[str]:
        """The `Body` parts it can go in place of."""
        return _REPLACES[self]

    @property
    def humanity_cost(self) -> float:
        return _HUMANITY_COST[self]


_REPLACES = {
    Bionic.HYDRAULIC_LEGS: frozenset({"legs"}),
    Bionic.DATAJACK: frozenset({"vertebra"}),
    Bionic.INFRARED_EYE: frozenset({"left_eye", "right_eye"}),
}
_HUMANITY_COST = {Bionic.HYDRAULIC_LEGS: 0.15, Bionic.DATAJACK: 0.1, Bionic.INFRARED_EYE: 0.2}

type PartState = Literal["present", "sold"] | Bionic


class Body(Model):
    """Each part of the player's body that can be sold or replaced: still `present`, `sold`, or
    the bionic fitted in its place. A whole body has every part present."""

    legs: PartState = PRESENT
    vertebra: PartState = PRESENT
    left_eye: PartState = PRESENT
    right_eye: PartState = PRESENT
    left_kidney: PartState = PRESENT
    right_kidney: PartState = PRESENT

    @property
    def bionics(self) -> list[Bionic]:
        return [Bionic(state) for _, state in self if state not in (PRESENT, SOLD)]

    @model_validator(mode="after")
    def _bionics_fit(self) -> Self:
        for part, state in self:
            if state not in (PRESENT, SOLD) and part not in Bionic(state).replaces:
                raise ValueError(f"{state} can't replace {part}")
        return self


class Player(Model):
    """The player's state, saved with the world. Each field defaults to the starting player's, so
    a save from before the player loads with a whole body, no money and a charged lamp. Their
    humanity is derived from the bionics fitted and isn't a field, so the client never sees it."""

    money: float = Field(
        default=0.0,
        ge=0,
        allow_inf_nan=False,
        description="In the same units as the residents' money.",
    )
    items: list[Item] = Field(
        default_factory=lambda: [lamp()],
        description="What they carry. Picking things up keeps their weight within `carry_limit`.",
    )
    carry_limit: float = Field(
        default=CARRY_LIMIT, gt=0, allow_inf_nan=False, description="The most they carry, in kg."
    )
    body: Body = Field(default_factory=Body)
    hunger: Unit = Field(default=0.0, description="0 is fed and 1 is starving: they collapse.")

    @property
    def humanity(self) -> float:
        """How much of them is still them: 1 with no bionics, falling with each one fitted."""
        return 1 - sum(bionic.humanity_cost for bionic in self.body.bionics)

    @property
    def load(self) -> float:
        """What everything they carry weighs, in kg."""
        return sum(item.weight for item in self.items)
