from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AmbientConfig(BaseModel):
    """Every constant of the ambient director. Distances are in tiles, times in sim seconds."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    enabled: bool = Field(default=True, description="Whether the director nudges anyone.")
    quiet: float = Field(
        default=180,
        ge=0,
        description="How long the player goes without an NPC conversation in earshot before the "
        "director nudges a pair near them.",
    )
    retry: float = Field(
        default=60, ge=0, description="How long after a nudge before it may nudge again."
    )
    look_every: float = Field(default=5, gt=0, description="Time between looks at the village.")
    earshot: float = Field(
        default=8.0,
        gt=0,
        description="A conversation comes into earshot once the player is this near one of its "
        "speakers, as I1 voices it and C2 draws its bubbles.",
    )
    out_of_earshot: float = Field(
        default=11.0,
        description="It stays in earshot until the player is further than this from all of them.",
    )
    reach: float = Field(
        default=16.0, gt=0, description="Furthest a seeker may be from the one they're nudged to."
    )
    accept_bar: float = Field(
        default=0.0,
        description="Both must score above this on B2's acceptance of the other to be nudged.",
    )
    bonus: float = Field(
        default=0.6,
        ge=0,
        description="Added to the seeker's score for seeking the other out, at their next "
        "decision.",
    )

    @model_validator(mode="after")
    def _leaving_is_further(self) -> Self:
        if self.out_of_earshot < self.earshot:
            raise ValueError("out_of_earshot must be at least earshot")
        return self


DEFAULT_CONFIG = AmbientConfig()
