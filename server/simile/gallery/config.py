from datetime import timedelta

from pydantic import BaseModel, ConfigDict, Field

from simile.llm import Model


class GalleryConfig(BaseModel):
    """Every constant of how residents visit the gallery and how the player sees it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    look_every: float = Field(
        default=1.0, gt=0, description="Sim seconds between looks at who's in the gallery."
    )
    linger: tuple[float, float] = Field(
        default=(2.0, 5.0), description="Sim minutes a visitor spends in front of each painting."
    )
    reaction_model: str = Field(
        default=Model.HAIKU_5_5, description="The model that says how a painting lands."
    )
    priority: int = Field(
        default=-1, description="L1 priority of the reaction calls, below conversations' 0."
    )
    topics: int = Field(
        default=3, ge=0, description="The painting's first tags kept as a memory's topics."
    )
    player_salience: float = Field(
        default=0.5,
        ge=0,
        le=1,
        description="The salience of the player's memory of seeing a painting. They don't react "
        "to it, so its valence is 0.",
    )
    murals_per_canvas: int = Field(
        default=2,
        ge=1,
        description="Murals in a row after which a muralist paints a canvas for the gallery.",
    )
    look_again: timedelta = Field(
        default=timedelta(hours=1),
        description="Sim time before a visitor tries again to say how a painting lands, after the "
        "call failed.",
    )


DEFAULT_CONFIG = GalleryConfig()
