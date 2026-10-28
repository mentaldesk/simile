from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from simile.llm import Model
from simile.schema import Bionic, EffectKind, Id, Recipe
from simile.street.sewers import APEX_ACTUATOR


class Procedure(BaseModel):
    """A bionic the doctor builds from its recipe, for a player who knows it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    recipe: Recipe
    does: str = Field(min_length=1, description="What it lets them do, for the doctor to say.")
    buys: float | None = Field(
        default=None,
        ge=0,
        allow_inf_nan=False,
        description="What the doctor pays for the recipe, once. None if she won't buy it.",
    )


CELL: list[Bionic] = [Bionic.POWER_CELL]


def _procedure(
    bionic: Bionic,
    name: str,
    parts: dict[str, int],
    credits: float,
    does: str,
    buys: float | None,
    after: list[Bionic] = CELL,
) -> Procedure:
    recipe = Recipe(bionic=bionic, name=name, parts=parts, credits=credits, after=after)
    return Procedure(recipe=recipe, does=does, buys=buys)


PROCEDURES: dict[Bionic, Procedure] = {
    procedure.recipe.bionic: procedure
    for procedure in (
        _procedure(
            Bionic.POWER_CELL,
            "Power cell",
            {"lithium_cell": 3, "charge_controller": 1},
            100.0,
            "run every other bionic, charging at a plug instead of eating",
            None,
            after=[],
        ),
        _procedure(
            Bionic.DATAJACK,
            "Datajack",
            {"copper_wire": 3, "usb_c_connector": 1},
            100.0,
            "plug into basic machines, like the maintenance lift down to the sewers",
            15.0,
        ),
        _procedure(
            Bionic.BIONIC_LEGS,
            "Bionic legs",
            {"pump_impeller": 2, "copper_coil": 1},
            150.0,
            "run faster and jump further",
            25.0,
        ),
        _procedure(
            Bionic.SPRING_FEET,
            "Spring feet",
            {"brass_fitting": 2, "float_valve": 1},
            150.0,
            "jump higher, up to ledges out of reach",
            25.0,
        ),
        _procedure(
            Bionic.INFRARED_EYE,
            "Infrared eye",
            {"infrared_lens": 1},
            200.0,
            "see the flush on someone's face when they lie, and see in the dark without a lamp",
            30.0,
        ),
        _procedure(
            Bionic.POWER_CELL_2,
            "Power cell, grade 2",
            {"old_battery": 4, "copper_coil": 2},
            250.0,
            "run more bionics at once than the first cell",
            40.0,
            after=[],
        ),
        _procedure(
            Bionic.BIONIC_LEGS_2,
            "Bionic legs, grade 2",
            {"pump_impeller": 2, "servo_motor": 2},
            300.0,
            "run faster and jump further than the first bionic legs",
            45.0,
        ),
        _procedure(
            Bionic.SPRING_FEET_2,
            "Spring feet, grade 2",
            {"pressure_gauge": 2, "brass_fitting": 3},
            300.0,
            "jump higher than the first spring feet",
            45.0,
        ),
        _procedure(
            Bionic.POWER_CELL_3,
            "Power cell, grade 3",
            {"old_battery": 6, "apex_board": 1},
            600.0,
            "run more bionics still",
            90.0,
            after=[],
        ),
        _procedure(
            Bionic.BIONIC_LEGS_3,
            "Bionic legs, grade 3",
            {APEX_ACTUATOR.id: 1, "servo_motor": 2},
            700.0,
            "run the fastest and jump the furthest of any legs",
            105.0,
        ),
    )
}


class Cure(BaseModel):
    """How the doctor treats an effect, by `treat`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1, description="As the player sees it.")
    price: float = Field(ge=0, allow_inf_nan=False)


CURES: dict[EffectKind, Cure] = {
    EffectKind.RAT_BITE: Cure(name="Clean the bite", price=5.0),
    EffectKind.INFECTION: Cure(name="Treat the infection", price=25.0),
}


class ClinicConfig(BaseModel):
    """What the doctor buys and fits, at prices the doctor only voices, and how they talk."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    place: Id = Field(default="clinic", description="The clinic's location id.")
    spot: Id = Field(default="clinic_doctor", description="Where the doctor stands.")
    kidney: float = Field(
        default=100.0,
        ge=0,
        allow_inf_nan=False,
        description="What the doctor pays for a kidney. They buy one, never the last.",
    )
    procedures: dict[Bionic, Procedure] = Field(
        default=PROCEDURES,
        description="Each bionic, built from its recipe for a player who knows it, after "
        "the recipe's `after`: the power cell, for everything but a cell.",
    )
    stock: dict[Bionic, int] = Field(
        default=dict.fromkeys(Bionic, 1),
        description="How many of each bionic the doctor had, counting any fitted in the player. "
        "With 0 they don't fit it.",
    )
    patch_up: float = Field(
        default=30.0,
        ge=0,
        allow_inf_nan=False,
        description="What patching them up from no health to full costs. Less hurt costs less, "
        "rounded up to a whole credit.",
    )
    patch_name: str = Field(default="Patch up", min_length=1)
    cures: dict[EffectKind, Cure] = Field(
        default=CURES, description="The effects the doctor treats, and for how much."
    )
    model: str = Field(default=Model.HAIKU_4_5, description="The model that writes the doctor.")
    greet_every: float = Field(
        default=2.0,
        gt=0,
        description="Sim hours before the doctor greets the player again as they walk in.",
    )
    silence: float = Field(
        default=60.0, gt=0, description="Sim seconds of silence before the doctor stops talking."
    )
    gap: float = Field(default=0.5, ge=0, description="Sim seconds between two lines.")
    timeout: float = Field(
        default=30.0, gt=0, description="Real seconds a reply may take before it's dropped."
    )

    @model_validator(mode="after")
    def _each_bionic_once(self) -> Self:
        if wrong := [b for b, p in self.procedures.items() if p.recipe.bionic is not b]:
            raise ValueError(f"a procedure is keyed by its recipe's bionic: {wrong}")
        return self

    @property
    def recipes(self) -> dict[Bionic, Recipe]:
        return {bionic: procedure.recipe for bionic, procedure in self.procedures.items()}


DEFAULT_CONFIG = ClinicConfig()
