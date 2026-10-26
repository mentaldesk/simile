from enum import StrEnum
from typing import Annotated, Any, Final, Literal, Self, get_args

from pydantic import Field, field_validator, model_validator

from simile.schema.common import CHECKED, Id, Key, MapTile, Model, Timestamp, Unit

CARRY_LIMIT = 10.0
PRESENT: Final = "present"
SOLD: Final = "sold"


class ItemKind(StrEnum):
    """What it's for: `salvage` to sell, `food` to eat, the `lamp` to see by, or a `part` to fit."""

    SALVAGE = "salvage"
    FOOD = "food"
    LAMP = "lamp"
    PART = "part"


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
        description="A lamp's battery, from 0 (flat) to 1 (full). It runs down while the lamp is "
        "on, and at a plug it charges, on or off. Null for anything else.",
    )
    on: bool | None = Field(
        default=None,
        description="Whether a lamp is switched on, running its battery down. The player switches "
        "it, and it goes off by itself when it's flat. Null for anything else.",
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
    """Items, money or both lying `at` a tile in the world for the player to pick up, such as
    salvage, a secret's cash, or what they left when they collapsed."""

    model_config = CHECKED

    at: MapTile
    items: list[Item]
    money: float = Field(
        default=0.0,
        ge=0,
        allow_inf_nan=False,
        strict=True,
        exclude_if=lambda money: not money,
        description="Cash lying there, which weighs nothing. Left out while there's none.",
    )

    @model_validator(mode="before")
    @classmethod
    def _something_lies_there(cls, data: Any) -> Any:
        # `money` is strict, so a string can't pass this as cash and turn into 0 after it.
        if isinstance(data, dict) and not data.get("items") and not data.get("money"):
            raise ValueError("a pile holds at least one item or some money")
        return data


class Bionic(StrEnum):
    """A part fitted in place of the player's own: a grade of the power cell, the legs or the
    feet, the datajack, the eye, or one of stage 1's grades of legs."""

    HYDRAULIC_LEGS = "hydraulic_legs"
    DATAJACK = "datajack"
    INFRARED_EYE = "infrared_eye"
    SPRING_LEGS = "spring_legs"
    SPRINT_LEGS = "sprint_legs"
    BLADE_LEGS = "blade_legs"
    PREMIUM_LEGS = "premium_legs"
    POWER_CELL = "power_cell"
    POWER_CELL_2 = "power_cell_2"
    POWER_CELL_3 = "power_cell_3"
    BIONIC_LEGS = "bionic_legs"
    BIONIC_LEGS_2 = "bionic_legs_2"
    BIONIC_LEGS_3 = "bionic_legs_3"
    SPRING_FEET = "spring_feet"
    SPRING_FEET_2 = "spring_feet_2"

    @property
    def replaces(self) -> frozenset[str]:
        """The `Body` parts it can go in place of."""
        return _REPLACES[self]

    @property
    def humanity_cost(self) -> float:
        return _HUMANITY_COST[self]

    @property
    def line(self) -> tuple["Bionic", ...]:
        """Its grades, lowest first: one of `LINES`, or just itself."""
        return next((line for line in LINES if self in line), (self,))


LEGS: Final = (
    Bionic.HYDRAULIC_LEGS,
    Bionic.SPRING_LEGS,
    Bionic.SPRINT_LEGS,
    Bionic.BLADE_LEGS,
    Bionic.PREMIUM_LEGS,
)
"""Stage 1's grades of legs."""
POWER_CELLS: Final = (Bionic.POWER_CELL, Bionic.POWER_CELL_2, Bionic.POWER_CELL_3)
"""The power cell's grades, in place of the stomach: it runs every other bionic, and a bigger cell
runs more of them."""
BIONIC_LEGS: Final = (Bionic.BIONIC_LEGS, Bionic.BIONIC_LEGS_2, Bionic.BIONIC_LEGS_3)
"""The legs' grades, for speed and kick."""
SPRING_FEET: Final = (Bionic.SPRING_FEET, Bionic.SPRING_FEET_2)
"""The feet's grades, for jump height."""
LINES: Final = (POWER_CELLS, BIONIC_LEGS, SPRING_FEET)
"""Each bionic that comes in grades, lowest first."""
_REPLACES = {
    **dict.fromkeys(LEGS + BIONIC_LEGS, frozenset({"legs"})),
    **dict.fromkeys(POWER_CELLS, frozenset({"stomach"})),
    **dict.fromkeys(SPRING_FEET, frozenset({"feet"})),
    Bionic.DATAJACK: frozenset({"vertebra"}),
    Bionic.INFRARED_EYE: frozenset({"left_eye", "right_eye"}),
}
_HUMANITY_COST = {
    **dict.fromkeys(LEGS + BIONIC_LEGS, 0.15),
    **dict.fromkeys(POWER_CELLS + SPRING_FEET, 0.1),
    Bionic.DATAJACK: 0.1,
    Bionic.INFRARED_EYE: 0.2,
}

type PartState = Literal["present", "sold"] | Bionic
type BodyPart = Literal[
    "legs", "vertebra", "left_eye", "right_eye", "left_kidney", "right_kidney", "stomach", "feet"
]


def _full(vital: float) -> bool:
    return vital == 1


def _theirs(state: PartState) -> bool:
    return state == PRESENT


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
    stomach: PartState = Field(
        default=PRESENT,
        exclude_if=_theirs,
        description="Left out while it's still theirs, as in a save from before it could go.",
    )
    feet: PartState = Field(
        default=PRESENT,
        exclude_if=_theirs,
        description="Left out while they're still theirs, as in a save from before they could go.",
    )

    @property
    def bionics(self) -> list[Bionic]:
        return [state for _, state in self if isinstance(state, Bionic)]

    def has(self, bionic: Bionic) -> bool:
        """Whether `bionic` is fitted, or a higher grade of its line."""
        line = bionic.line
        return any(fitted in line[line.index(bionic) :] for fitted in self.bionics)

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


BODY_PARTS: Final[tuple[BodyPart, ...]] = get_args(BodyPart.__value__)


def _replaced(data: dict[str, Any]) -> list[BodyPart]:
    bionic = data.get("bionic")
    return [part for part in BODY_PARTS if bionic is not None and part in bionic.replaces]


class Recipe(Model):
    """How to build a `bionic`, which the clinic needs before it fits one. It's known by the
    bionic it builds."""

    bionic: Bionic
    name: str = Field(
        min_length=1, description='The bionic as the player sees it, e.g. "Datajack".'
    )
    parts: dict[Key, Annotated[int, Field(ge=1)]] = Field(
        description="The items the fitting uses up, how many of each by item `id`, e.g. "
        '`{"copper_wire": 3, "usb_c_connector": 1}`.'
    )
    credits: float = Field(
        ge=0, allow_inf_nan=False, description="What the fitting costs, from their money."
    )
    replaces: list[BodyPart] = Field(
        default_factory=_replaced,
        description="The parts of their body it can go in place of, any one of which they give "
        "up for it, or a lower grade of its line fitted there: the bionic's own, filled in from it "
        "when left out.",
    )
    after: list[Bionic] = Field(
        default=[],
        description="What must be fitted first, each of them or a higher grade of its line: a "
        "power cell for everything but a cell.",
    )

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if len(set(self.replaces)) != len(self.replaces) or set(self.replaces) != set(
            self.bionic.replaces
        ):
            raise ValueError(f"{self.bionic} replaces {', '.join(sorted(self.bionic.replaces))}")
        if self.bionic in self.after or len(set(self.after)) != len(self.after):
            raise ValueError("a recipe names what comes before it once each, never itself")
        return self

    def ready(self, body: Body) -> bool:
        """Whether everything that must be fitted first is."""
        return all(body.has(bionic) for bionic in self.after)


class Mind(Model):
    """What the player knows, which they keep when they collapse, and later when they die. Left
    out of `Player` while they know no recipe."""

    model_config = CHECKED

    recipes: list[Bionic] = Field(
        default=[],
        description="The recipes they know, by the bionic each builds, in the order they learned "
        "them.",
    )
    sold: list[Bionic] = Field(
        default=[],
        exclude_if=lambda sold: not sold,
        description="The recipes they've sold to the clinic, in the order they sold them. They "
        "still know each, and can't sell it again. Left out while there's none.",
    )

    @model_validator(mode="before")
    @classmethod
    def _sells_what_it_knows_once(cls, data: Any) -> Any:
        if isinstance(data, dict):
            recipes, sold = data.get("recipes", []), data.get("sold", [])
            lists = isinstance(recipes, list) and isinstance(sold, list)
            if not lists or not all(isinstance(name, str) for name in [*recipes, *sold]):
                return data
            if len(set(recipes)) != len(recipes) or len(set(sold)) != len(sold):
                raise ValueError("a mind knows each recipe once, and sells it once")
            if not set(sold) <= set(recipes):
                raise ValueError("they can only sell a recipe they know")
        return data


class EffectKind(StrEnum):
    """An ailment and its cause: a `rat_bite`, the `infection` an untreated bite can turn into, or
    a dose of `radiation`."""

    RAT_BITE = "rat_bite"
    INFECTION = "infection"
    RADIATION = "radiation"


class Effect(Model):
    """An ailment the player has, which fades on its own or lasts until it's treated."""

    model_config = CHECKED

    kind: EffectKind
    strength: Annotated[float, Field(gt=0, le=1)] = Field(
        description="How bad it is, up to 1. It's gone once it fades to 0."
    )
    fades: Annotated[float, Field(gt=0, allow_inf_nan=False)] | None = Field(
        description="The strength it loses each sim hour, or null while it lasts until it's "
        "treated, at the clinic or with medicine."
    )
    since: Timestamp = Field(description="When they got it, in sim time.")


class Sale(Model):
    """Something the player sold that its buyer keeps for them to buy back."""

    model_config = CHECKED

    item: Item
    place: Id = Field(description='The buyer that has it, by its place, e.g. "scrap_stall".')
    price: float = Field(ge=0, allow_inf_nan=False, description="What it fetched.")


class Player(Model):
    """The player's state, saved with the world. Each field defaults to the starting player's, so
    a save from before the player loads with a whole body, no money, a charged lamp, nothing known,
    full health, no effects and nothing searched. Their humanity is derived from the bionics
    fitted and isn't a field, so the client never sees it."""

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
    mind: Mind = Field(default_factory=Mind, exclude_if=lambda mind: not mind.recipes)
    hunger: Unit = Field(default=0.0, description="0 is fed and 1 is starving: they collapse.")
    power: Unit = Field(
        default=1.0,
        exclude_if=_full,
        description="Their power cell's charge, from 1 (full) to 0 (flat: they collapse), which "
        "they run on in place of hunger once a cell is in their stomach. It stays full without "
        "one. Left out while it's full.",
    )
    health: Unit = Field(
        default=1.0,
        exclude_if=_full,
        description="From 1, unhurt, to 0, when they collapse. Left out while it's full.",
    )
    effects: list[Effect] = Field(
        default=[],
        exclude_if=lambda effects: not effects,
        description="Their ailments, in the order they got them, each kind once. Left out while "
        "there's none.",
    )
    left: list[Pile] = Field(
        default=[],
        exclude_if=lambda left: not left,
        description="What they left lying in the world, oldest first: what they carried when they "
        "collapsed, on the tile they fell on or the ground below it, and anything of a pickup that "
        "didn't fit when they took from it. Left out while there's none.",
    )
    taken: dict[Key, Timestamp] = Field(
        default={},
        exclude_if=lambda taken: not taken,
        description="When they last took from each pickup in the world, in sim time, by pickup "
        "id. Salvage lies there again a while after it was taken, but a secret, cash or a ration, "
        "stays taken for good. Left out while there's none.",
    )
    sales: list[Sale] = Field(
        default=[],
        exclude_if=lambda sales: not sales,
        description="What they've sold that its buyer keeps for them to buy back, oldest first. "
        "Left out while there's none.",
    )
    searched: list[Id] = Field(
        default=[],
        exclude_if=lambda searched: not searched,
        description="The searchable things and jacks they've searched, by interactable id, in the "
        "order they searched them. Each is searched once, and holds nothing after. Left out while "
        "there's none.",
    )

    @field_validator("effects")
    @classmethod
    def _each_kind_once(cls, effects: list[Effect]) -> list[Effect]:
        if len({effect.kind for effect in effects}) != len(effects):
            raise ValueError("they have each kind of effect once")
        return effects

    @field_validator("searched")
    @classmethod
    def _each_searched_once(cls, searched: list[str]) -> list[str]:
        if len(set(searched)) != len(searched):
            raise ValueError("they search each thing once")
        return searched

    @property
    def humanity(self) -> float:
        """How much of them is still them: 1 with no bionics, falling with each one fitted."""
        return 1 - sum(bionic.humanity_cost for bionic in self.body.bionics)

    @property
    def load(self) -> float:
        """What everything they carry weighs, in kg."""
        return sum(item.weight for item in self.items)
