from datetime import timedelta

from pydantic import BaseModel, ConfigDict, Field

from simile.llm import Model


class WorksConfig(BaseModel):
    """Every constant of how residents make, read and see works, and how the player does."""

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
        description="The salience of the player's memory of reading a work or seeing a mural. "
        "They don't react to it, so its valence is 0.",
    )
    svg_chars: int = Field(default=60_000, ge=1, description="The longest a mural's SVG may be.")
    svg_elements: int = Field(
        default=2_000, ge=1, description="The most elements a mural's SVG may have."
    )
    render_timeout: float = Field(
        default=5.0,
        gt=0,
        description="Real seconds a mural's child process gets to draw it, once it has started.",
    )
    render_memory: int = Field(
        default=1024, ge=1, description="Megabytes a mural's child process may use to draw it."
    )
    aspect_tolerance: float = Field(
        default=0.1,
        ge=0,
        description="How far a mural's viewBox may stray from its wall's aspect ratio, as a "
        "fraction of it. What doesn't fit is cropped.",
    )
    mural_age: timedelta = Field(
        default=timedelta(days=2),
        description="The age at which a mural is as ready to be painted over as age makes it.",
    )
    age_weight: float = Field(
        default=1.0, ge=0, description="Readiness to paint over a mural `mural_age` old or older."
    )
    own_mural: float = Field(
        default=0.3, description="Readiness to paint over one's own mural, on top of its age."
    )
    boldness_weight: float = Field(
        default=1.0,
        ge=0,
        description="Readiness to paint over someone else's mural per unit of boldness above "
        "0.5. Boldness is the mean of 1 - Tradition, 1 - Obedience and Freedom.",
    )
    fondness_weight: float = Field(
        default=0.5,
        ge=0,
        description="Readiness lost per unit of B1's affinity for the mural's artist.",
    )
    friend: float = Field(
        default=0.4, description="B1's affinity for an artist at which they're a friend."
    )
    friend_boldness: float = Field(
        default=0.75,
        ge=0,
        le=1,
        description="Painters less bold than this never paint over a friend's mural.",
    )
    min_readiness: float = Field(
        default=0.5, description="Walls less ready than this to be painted over are left alone."
    )
    reach: float = Field(
        default=3.0,
        gt=0,
        description="How far in front of a mural, in tiles, a passer-by sees it. The client's "
        "MURAL_REACH_TILES.",
    )
    look_every: float = Field(
        default=1.0, gt=0, description="Sim seconds between looks at who's passing a mural."
    )
    look_again: timedelta = Field(
        default=timedelta(hours=1),
        description="Sim time before a resident tries again to say how a mural lands, after "
        "the call failed.",
    )
    painted_over_salience: float = Field(
        default=0.7,
        ge=0,
        le=1,
        description="The least salience of an artist's memory of finding their mural painted over.",
    )


DEFAULT_CONFIG = WorksConfig()
