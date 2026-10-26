from datetime import timedelta
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from simile.schema import (
    BIONIC_LEGS,
    LEGS,
    POWER_CELLS,
    SPRING_FEET,
    Aspect,
    Bionic,
    CoreValue,
    Signed,
    Unit,
)

BASELINE_WEIGHTS: dict[Aspect, dict[CoreValue, float]] = {
    Aspect.LIKE: {
        CoreValue.CONNECTION: 0.2,
        CoreValue.COMPASSION: 0.15,
        CoreValue.OPTIMISM: 0.15,
        CoreValue.OPEN_MINDEDNESS: 0.1,
    },
    Aspect.TRUST: {
        CoreValue.OPTIMISM: 0.15,
        CoreValue.COMPASSION: 0.1,
        CoreValue.OPEN_MINDEDNESS: 0.05,
        CoreValue.SECURITY: -0.15,
        CoreValue.INDEPENDENCE: -0.05,
    },
    Aspect.RESPECT: {
        CoreValue.EQUALITY: 0.1,
        CoreValue.OBEDIENCE: 0.1,
        CoreValue.TRADITION: 0.05,
        CoreValue.AMBITION: -0.1,
        CoreValue.SUCCESS: -0.05,
    },
}


class RelationshipConfig(BaseModel):
    """Every tunable constant of the relationship model. Scores run from 0 to 1, neutral at 0.5."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    baseline_weights: dict[Aspect, dict[CoreValue, Signed]] = Field(
        default=BASELINE_WEIGHTS,
        description="How each core value moves a newcomer's baseline away from neutral: "
        "0.5 + sum(weight * (value - 0.5)), clamped to [0, 1].",
    )
    max_shift: float = Field(
        default=0.3,
        gt=0,
        le=1,
        description="How far a positive event of full valence and magnitude moves a neutral "
        "score. An encounter's events add up per aspect before they move it.",
    )
    negativity_bias: float = Field(
        default=2.5, ge=1, description="How many times more a negative event weighs."
    )
    negativity_bias_spread: float = Field(
        default=2.0,
        ge=1,
        description="How far the owner's negativity_bias trait moves negativity_bias: times "
        "this at 1, divided by it at 0, and never below 1.",
    )
    first_impressions_spread: float = Field(
        default=2.0,
        ge=1,
        description="How far the owner's first_impressions trait swings their first encounter "
        "with someone: its shifts times this at 1, divided by it at 0.",
    )
    resistance_step: float = Field(
        default=0.15,
        ge=0.05,
        le=0.5,
        description="Each this much further from neutral a score is, moving it further away is "
        "ten times harder: the encounter that takes 0.5 to 0.65 has to happen 10 more times to "
        "reach 0.8 and 100 more to reach 0.95. Moving toward neutral isn't resisted.",
    )
    familiarity_gain: float = Field(
        default=0.06,
        ge=0,
        le=1,
        description="The share of the gap to full familiarity that each encounter closes.",
    )
    like_half_life: timedelta = Field(
        default=timedelta(days=2),
        gt=timedelta(0),
        description="Time without contact for like to get halfway back to its baseline.",
    )
    respect_half_life: timedelta = Field(
        default=timedelta(days=4),
        gt=timedelta(0),
        description="Time without contact for respect to get halfway back to its baseline.",
    )
    trust_half_life: timedelta = Field(
        default=timedelta(days=8),
        gt=timedelta(0),
        description="Longer than like_half_life: trust decays more slowly.",
    )
    forgiveness_spread: float = Field(
        default=3.0,
        ge=1,
        description="How far the owner's forgiveness trait speeds up a grudge, a score below its "
        "baseline, fading: its half-lives divided by this at 1, times it at 0.",
    )
    familiarity_half_life: timedelta = Field(
        default=timedelta(days=90),
        gt=timedelta(0),
        description="Time without contact for familiarity to halve. Long, as it rarely decreases.",
    )
    mild_feeling: float = Field(
        default=0.1,
        gt=0,
        lt=0.5,
        description="How far from neutral a score must be for describe to mention it.",
    )
    strong_feeling: float = Field(
        default=0.3,
        gt=0,
        le=0.5,
        description="How far from neutral a score must be for describe to call it strong.",
    )
    barely_known: float = Field(
        default=0.2, gt=0, lt=1, description="Below this familiarity, you barely know them."
    )
    well_known: float = Field(
        default=0.6, gt=0, le=1, description="From this familiarity up, you know them well."
    )

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.trust_half_life <= self.like_half_life:
            raise ValueError("trust_half_life must be longer than like_half_life")
        if self.strong_feeling <= self.mild_feeling:
            raise ValueError("strong_feeling must be more than mild_feeling")
        if self.well_known <= self.barely_known:
            raise ValueError("well_known must be more than barely_known")
        return self


DEFAULT_CONFIG = RelationshipConfig()


TOLERANCE_WEIGHTS: dict[CoreValue, float] = {
    CoreValue.TRADITION: -1.0,
    CoreValue.SECURITY: -1.0,
    CoreValue.ADVENTURE: 2 / 3,
    CoreValue.AMBITION: 2 / 3,
    CoreValue.OPEN_MINDEDNESS: 2 / 3,
}

STANDS_OUT: dict[Bionic, float] = {
    Bionic.INFRARED_EYE: 1.0,
    **dict.fromkeys(LEGS + BIONIC_LEGS, 0.75),
    Bionic.DATAJACK: 0.5,
    **dict.fromkeys(SPRING_FEET, 0.5),
    **dict.fromkeys(POWER_CELLS, 0.25),
}


class BionicsConfig(BaseModel):
    """Every constant of how residents take to the player's bionics."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tolerance_weights: dict[CoreValue, float] = Field(
        default=TOLERANCE_WEIGHTS,
        description="How each core value moves a resident's tolerance for bionics: "
        "sum(weight * (value - 0.5)), clamped to [-1, 1]. The two against weigh 2 in all, as do "
        "the three for.",
    )
    mildly: float = Field(
        default=0.15, gt=0, lt=1, description="How far from 0 a tolerance is against or for."
    )
    strongly: float = Field(
        default=0.5, gt=0, le=1, description="How far from 0 a tolerance is strongly so."
    )
    stands_out: dict[Bionic, Unit] = Field(
        default=STANDS_OUT,
        description="How much each bionic catches the eye: the eye most, the power cell least.",
    )
    sighting: float = Field(
        default=0.3,
        gt=0,
        le=1,
        description="The magnitude of R1's event for seeing a bionic that stands out fully. Its "
        "valence is the resident's tolerance, and it moves like, trust and respect.",
    )
    salience: float = Field(
        default=0.3, ge=0, le=1, description="The salience of the memory of a sighting."
    )
    salience_feeling: float = Field(
        default=0.6,
        ge=0,
        le=1,
        description="Salience added per unit of |tolerance| times how much the most eye-catching "
        "bionic seen stands out, so strong feelings get talked about.",
    )
    sight: float = Field(
        default=6.0, gt=0, description="How far a resident sees the player from, in tiles."
    )
    look_every: float = Field(
        default=5, gt=0, description="Sim seconds between looks for residents who can see them."
    )
    new_for: timedelta = Field(
        default=timedelta(hours=1),
        ge=timedelta(0),
        description="How long after first seeing a bionic a resident's prompt calls it new.",
    )
    player_name: str = Field(default="Visitor", min_length=1)

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.strongly <= self.mildly:
            raise ValueError("strongly must be more than mildly")
        return self


DEFAULT_BIONICS = BionicsConfig()
