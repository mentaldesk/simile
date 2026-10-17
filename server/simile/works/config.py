from datetime import timedelta

from pydantic import BaseModel, ConfigDict, Field

from simile.llm import Model


class WorksConfig(BaseModel):
    """Every constant of how residents make their works."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    model: str = Field(default=Model.SONNET, description="The model that writes a work.")
    priority: int = Field(
        default=-1, description="L1 priority of the writing call, below conversations' 0."
    )
    memories: int = Field(
        default=8,
        ge=0,
        description="The strongest memories, by salience × recency, put to the artist as what's "
        "on their mind. Their memories of making their own works are left out.",
    )
    half_life: timedelta = Field(
        default=timedelta(hours=24), description="Sim time over which a memory's pull halves."
    )
    past_works: int = Field(
        default=3,
        ge=0,
        description="The artist's latest works whose titles and statements go in the prompt, so "
        "they don't repeat themselves.",
    )
    words: int = Field(default=250, ge=1, description="The most words a piece should run to.")
    cares_most: int = Field(
        default=5, ge=0, description="Strongest values listed in the writing prompt."
    )
    cares_least: int = Field(
        default=3, ge=0, description="Weakest values listed in the writing prompt."
    )
    salience: float = Field(
        default=0.6, ge=0, le=1, description="The salience of the artist's memory of making it."
    )
    valence: float = Field(
        default=0.5, ge=-1, le=1, description="How the artist feels about having made it."
    )
    topics: int = Field(
        default=3, ge=0, description="The work's first tags kept as the memory's topics."
    )


DEFAULT_CONFIG = WorksConfig()
