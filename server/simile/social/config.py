from datetime import timedelta
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from simile.schema import Aspect, CoreValue, Signed

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
        description="How far a positive event of full valence and magnitude moves a stranger's "
        "score.",
    )
    negativity_bias: float = Field(
        default=2.5, ge=1, description="How many times more a negative event weighs."
    )
    dampening_floor: float = Field(
        default=0.25,
        ge=0,
        le=1,
        description="The share of an event's effect that still lands at full familiarity, so old "
        "friends can still be moved.",
    )
    familiarity_gain: float = Field(
        default=0.06,
        ge=0,
        le=1,
        description="The share of the gap to full familiarity that any event closes.",
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
