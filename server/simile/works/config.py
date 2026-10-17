from datetime import timedelta

from pydantic import BaseModel, ConfigDict, Field

from simile.llm import Model


class WorksConfig(BaseModel):
    """Every constant of how residents make and read their works, and how the player reads them."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    model: str = Field(default=Model.SONNET, description="The model that writes a work.")
    reaction_model: str = Field(
        default=Model.HAIKU_5_5, description="The model that says how a work lands with a reader."
    )
    priority: int = Field(
        default=-1,
        description="L1 priority of the writing and reading calls, below conversations' 0.",
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
        default=3, ge=0, description="The work's first tags kept as a memory's topics."
    )
    candidates: int = Field(
        default=30, ge=1, description="The newest pieces of writing considered for reading."
    )
    artist_weight: float = Field(
        default=0.5,
        ge=0,
        description="Interest per unit of the reader's B1 affinity for the artist, added to the "
        "piece's interest as if it were an article.",
    )
    min_interest: float = Field(
        default=0.5, ge=0, description="Works less interesting than this aren't read."
    )
    listed: int = Field(
        default=20, ge=0, description="The newest pieces of writing listed for the player."
    )
    player_salience: float = Field(
        default=0.5,
        ge=0,
        le=1,
        description="The salience of the player's memory of reading a work. They don't react to "
        "it, so its valence is 0.",
    )


DEFAULT_CONFIG = WorksConfig()
