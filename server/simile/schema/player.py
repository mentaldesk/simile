from enum import StrEnum
from typing import Any, Final, Literal

from pydantic import Field, model_validator

from simile.schema.common import CHECKED, Id, Model, Unit
from simile.schema.world import MapTile

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

    model_config = CHECKED

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
    on: bool | None = Field(
        default=None,
        description="Whether a lamp is switched on, running its battery down. Null for anything "
        "else.",
    )

    @model_validator(mode="before")
    @classmethod
    def _only_a_lamp_has_a_charge_and_a_switch(cls, data: Any) -> Any:
        if isinstance(data, dict):
            lamp = data.get("kind") == ItemKind.LAMP
            for field, what in (("charge", "charge"), ("on", "switch")):
                if lamp == (data.get(field) is None):
                    raise ValueError(f"a lamp has a {what}, and nothing else has one")
        return data


def lamp() -> Item:
    """The lamp the player starts with, fully charged and switched off."""
    return Item(id="lamp", kind=ItemKind.LAMP, name="Lamp", weight=1.0, charge=1.0, on=False)


class Pile(Model):
    """What the player carried when they collapsed, left where they fell for them to go back
    for. It lies `at` the cell they fell on, or the ground below it."""

    model_config = CHECKED

    at: MapTile
    items: list[Item] = Field(min_length=1)


class Bionic(StrEnum):
    """A part fitted in place of one of the player's own. The hydraulic legs replace their legs,
    the datajack takes a vertebra, and the one infrared eye takes either eye."""

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

    model_config = CHECKED

    legs: PartState = PRESENT
    vertebra: PartState = PRESENT
    left_eye: PartState = PRESENT
    right_eye: PartState = PRESENT
    left_kidney: PartState = PRESENT
    right_kidney: PartState = PRESENT

    @property
    def bionics(self) -> list[Bionic]:
        return [state for _, state in self if isinstance(state, Bionic)]

    @model_validator(mode="before")
    @classmethod
    def _bionics_fit(cls, data: Any) -> Any:
        if isinstance(data, dict):
            for part, state in data.items():
                fitted = Bionic(state) if isinstance(state, str) and state in Bionic else None
                if fitted and part not in fitted.replaces:
                    raise ValueError(f"{fitted} can't replace {part}")
            if data.get("left_eye") == data.get("right_eye") == Bionic.INFRARED_EYE:
                raise ValueError("there's only one infrared eye")
        return data


class Player(Model):
    """The player's state, saved with the world. Each field defaults to the starting player's, so
    a save from before the player loads with a whole body, no money and a charged lamp. Their
    humanity is derived from the bionics fitted and isn't a field, so the client never sees it."""

    model_config = CHECKED

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
    left: list[Pile] = Field(
        default=[],
        exclude_if=lambda left: not left,
        description="What they've left where they collapsed, oldest first. Left out while there's "
        "none.",
    )

    @property
    def humanity(self) -> float:
        """How much of them is still them: 1 with no bionics, falling with each one fitted."""
        return 1 - sum(bionic.humanity_cost for bionic in self.body.bionics)

    @property
    def load(self) -> float:
        """What everything they carry weighs, in kg."""
        return sum(item.weight for item in self.items)
