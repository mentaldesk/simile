from datetime import timedelta
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RelationshipConfig(BaseModel):
    """Every tunable constant of the relationship model. Scores run from 0 to 1, neutral at 0.5."""

    model_config = ConfigDict(frozen=True, extra="forbid")

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
    respect_half_life: timedelta = Field(default=timedelta(days=4), gt=timedelta(0))
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
