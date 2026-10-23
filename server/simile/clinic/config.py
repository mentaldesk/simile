from pydantic import BaseModel, ConfigDict, Field

from simile.llm import Model
from simile.schema import Bionic, Id, Item
from simile.street.sewers import APEX_ACTUATOR


class Offer(BaseModel):
    """A bionic the doctor fits: what it's called, what it costs, what it does and what it takes."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    price: float = Field(ge=0, allow_inf_nan=False)
    does: str = Field(min_length=1, description="What it lets them do, for the doctor to say.")
    after: tuple[Bionic, ...] = Field(
        default=(),
        description="The legs it goes in place of, which the doctor takes back, so it's stocked "
        "only once one of them is fitted. Empty for a bionic in place of a part still theirs.",
    )
    needs: Item | None = Field(
        default=None, description="A part they bring for it, used up in the fitting."
    )


OFFERS: dict[Bionic, Offer] = {
    Bionic.HYDRAULIC_LEGS: Offer(
        name="Hydraulic legs", price=80.0, does="jump two rows higher, up to ledges out of reach"
    ),
    Bionic.SPRINT_LEGS: Offer(
        name="Sprint legs", price=80.0, does="run half as fast again, and jump further"
    ),
    Bionic.SPRING_LEGS: Offer(
        name="Spring legs",
        price=240.0,
        does="jump two rows higher than the hydraulic legs",
        after=(Bionic.HYDRAULIC_LEGS,),
    ),
    Bionic.BLADE_LEGS: Offer(
        name="Blade legs",
        price=240.0,
        does="run twice as fast as their own legs, and jump further still",
        after=(Bionic.SPRINT_LEGS,),
    ),
    Bionic.PREMIUM_LEGS: Offer(
        name="Premium legs",
        price=600.0,
        does="jump as high as the spring legs and run as fast as the blades",
        after=(Bionic.SPRING_LEGS, Bionic.BLADE_LEGS),
        needs=APEX_ACTUATOR,
    ),
    Bionic.DATAJACK: Offer(
        name="Datajack",
        price=150.0,
        does="plug into basic machines, like the maintenance lift down to the sewers",
    ),
    Bionic.INFRARED_EYE: Offer(
        name="Infrared eye", price=200.0, does="see the flush on someone's face when they lie"
    ),
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
    offers: dict[Bionic, Offer] = Field(default=OFFERS, description="The bionics they fit.")
    stock: dict[Bionic, int] = Field(
        default=dict.fromkeys(Bionic, 1),
        description="How many of each bionic the doctor had, counting any fitted in the player. "
        "With 0 they don't fit it.",
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


DEFAULT_CONFIG = ClinicConfig()
