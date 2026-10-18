from datetime import timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from simile.schema import FlagKind, HookKind, HookSide, Signed, Unit


class Weights(BaseModel):
    """How much each part of a character counts towards the distance between two of them."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    values: float = Field(default=2.0, ge=0, description="Times their values' RMS difference.")
    origin: float = Field(default=0.5, ge=0, description="When they come from different places.")
    age: float = Field(default=0.5, ge=0, description="Times their age gap over `age_scale`.")
    occupation: float = Field(default=0.5, ge=0, description="When their job's family differs.")
    gender: float = Field(default=0.5, ge=0, description="When their genders differ.")


class Side(BaseModel):
    """How a bond leaves one side: shifts from their baseline, how well they know the other, and
    the memory they keep of it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    like: Signed = 0.0
    trust: Signed = 0.0
    respect: Signed = 0.0
    familiarity: Unit
    valence: Signed = Field(description="How they feel about the memory.")
    memory: str = Field(description="The memory's first sentence, with the other's {name}.")


class BondConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    actor: Side
    target: Side = Field(description="The same as `actor` for a mutual kind.")
    flag: FlagKind | None = Field(
        default=None, description="The flag the target opens about the actor."
    )
    flag_description: str = ""
    max_age_gap: int | None = Field(default=None, description="Years, for a drawn bond.")
    same_origin: bool = Field(default=False, description="Only for a drawn bond.")
    fit: Literal[-1, 0, 1] = Field(
        default=0, description="1 binds like-minded residents first, -1 opposed ones."
    )

    def side(self, side: HookSide) -> Side:
        return self.target if side is HookSide.TARGET else self.actor


def _mutual(side: Side, **rest: object) -> BondConfig:
    return BondConfig.model_validate({"actor": side, "target": side, **rest})


BONDS: dict[HookKind, BondConfig] = {
    HookKind.ESTRANGED_SIBLING: _mutual(
        Side(
            like=-0.2,
            trust=-0.2,
            respect=-0.1,
            familiarity=0.9,
            valence=-0.6,
            memory="{name} is my sibling, and we don't speak.",
        ),
        max_age_gap=20,
        same_origin=True,
        fit=-1,
    ),
    HookKind.EX_PARTNER: _mutual(
        Side(
            like=-0.1,
            trust=-0.2,
            familiarity=0.8,
            valence=-0.4,
            memory="{name} and I used to be together.",
        ),
        max_age_gap=15,
    ),
    HookKind.OLD_FRIEND: _mutual(
        Side(
            like=0.25,
            trust=0.2,
            respect=0.1,
            familiarity=0.7,
            valence=0.5,
            memory="{name} and I go back a long way.",
        ),
        max_age_gap=20,
        fit=1,
    ),
    HookKind.RIVAL: _mutual(
        Side(
            like=-0.15,
            trust=-0.1,
            respect=0.1,
            familiarity=0.5,
            valence=-0.4,
            memory="{name} and I have been rivals for years.",
        ),
        max_age_gap=25,
        fit=-1,
    ),
    HookKind.DEBT: BondConfig(
        actor=Side(respect=0.05, familiarity=0.4, valence=-0.3, memory="I owe {name} money."),
        target=Side(
            trust=-0.2,
            respect=-0.1,
            familiarity=0.4,
            valence=-0.4,
            memory="{name} owes me money.",
        ),
        flag=FlagKind.DEBT,
        flag_description="an old loan",
    ),
    HookKind.SECRET: BondConfig(
        actor=Side(
            trust=-0.15,
            familiarity=0.3,
            valence=-0.5,
            memory="{name} once saw me do something I want kept hidden.",
        ),
        target=Side(
            trust=-0.15,
            respect=-0.15,
            familiarity=0.3,
            valence=-0.3,
            memory="I once saw {name} do something they want kept hidden.",
        ),
        flag=FlagKind.SECRET,
        flag_description="something best kept quiet",
    ),
    HookKind.BETRAYAL: BondConfig(
        actor=Side(trust=-0.05, familiarity=0.5, valence=-0.4, memory="I once betrayed {name}."),
        target=Side(
            like=-0.3,
            trust=-0.35,
            respect=-0.2,
            familiarity=0.5,
            valence=-0.7,
            memory="{name} once betrayed me.",
        ),
        flag=FlagKind.GRUDGE,
        flag_description="an old betrayal",
        fit=-1,
    ),
    HookKind.SAVED_LIFE: BondConfig(
        actor=Side(like=0.1, familiarity=0.3, valence=0.3, memory="I once saved {name}'s life."),
        target=Side(
            like=0.3,
            trust=0.3,
            respect=0.25,
            familiarity=0.4,
            valence=0.6,
            memory="{name} once saved my life.",
        ),
        flag=FlagKind.SAVED_LIFE,
        flag_description="an accident years ago",
    ),
}


class CastingConfig(BaseModel):
    """Every tunable constant of casting."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    weights: Weights = Weights()
    age_scale: float = Field(
        default=50, gt=0, description="An age gap of this many years or more counts in full."
    )
    conflict: Unit = Field(
        default=0.45, description="Values this far apart (RMS) make two residents a conflict."
    )
    affinity: Unit = Field(
        default=0.3, description="Values this close (RMS) make two residents an affinity."
    )
    conflict_share: Unit = Field(
        default=0.2, description="The share of a drawn cast picked to clash with someone's values."
    )
    affinity_share: Unit = Field(
        default=0.2, description="The share of a drawn cast picked to share someone's values."
    )
    choices: int = Field(
        default=3, ge=1, description="Each draw picks at random among this many best candidates."
    )
    maker_share: Unit = Field(
        default=0.7,
        description="Of the residents not filling one of the village's roles, the share with a "
        "job from makers.toml.",
    )
    elders: int = Field(
        default=2,
        ge=0,
        description="Residents over `elder_age` with a trade from occupations.toml in a cast of "
        "10, scaled to the cast's size.",
    )
    elder_age: int = Field(default=60, ge=0, description="Elders are older than this.")
    bonds: dict[HookKind, BondConfig] = BONDS
    bond_salience: Unit = Field(default=0.8, description="Of the memory each side keeps of a bond.")
    past_spacing: timedelta = Field(
        default=timedelta(minutes=1),
        ge=timedelta(0),
        description="How long before the start a past memory is stamped, per year ago.",
    )


DEFAULT_CONFIG = CastingConfig()
