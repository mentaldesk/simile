from datetime import timedelta

from pydantic import BaseModel, ConfigDict, Field

from simile.llm import Model
from simile.schema import Id

WRITING_GENRES = (
    "a fable",
    "a ghost story",
    "a love story",
    "a tall tale",
    "a letter from somewhere imaginary",
    "a monologue",
    "a small mystery",
    "a myth of how something came to be",
    "a comedy of errors",
    "a lullaby",
    "a story told backwards",
    "a dialogue between two unlikely speakers",
)
PICTURE_GENRES = (
    "a portrait",
    "a landscape",
    "a street scene",
    "a still life",
    "a night scene",
    "a dream",
    "a map",
    "a festival",
    "a creature",
    "a crowd",
    "an interior",
    "a weather study",
)
SUBJECTS = (
    "someone the village overlooks",
    "a stranger passing through",
    "something lost and found",
    "a childhood memory",
    "the weather turning",
    "an animal",
    "a first meeting",
    "a promise",
    "an old object with a story",
    "a meal",
    "a journey",
    "a secret",
    "a celebration",
    "water",
    "the night",
    "work done well",
    "a mistake",
    "the far future",
    "a door",
    "a gift",
    "a machine",
    "the sky",
)
MOODS = (
    "tender",
    "playful",
    "eerie",
    "wistful",
    "comic",
    "hopeful",
    "uneasy",
    "fierce",
    "serene",
    "bittersweet",
    "mischievous",
    "solemn",
)


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
    recalled: int = Field(
        default=40,
        ge=0,
        description="The strongest memories weighed for what's on the artist's mind, before "
        "`others_works` weighs others' works down.",
    )
    others_works: float = Field(
        default=0.4,
        ge=0,
        description="What a memory of someone else's work counts for among what's on the artist's "
        "mind, as a share of any other memory as strong and as recent, so one striking piece "
        "doesn't become everyone's theme.",
    )
    past_works: int = Field(
        default=3,
        ge=0,
        description="The artist's latest works whose titles and statements go in the prompt, so "
        "they don't repeat themselves.",
    )
    village_works: int = Field(
        default=8,
        ge=0,
        description="The village's latest works by others, a title and a few words on each, put "
        "in the prompt so the new one is unlike them.",
    )
    writing_genres: tuple[str, ...] = Field(
        default=WRITING_GENRES,
        min_length=1,
        description="Genres a piece of writing's seed draws from, one at random.",
    )
    picture_genres: tuple[str, ...] = Field(
        default=PICTURE_GENRES,
        min_length=1,
        description="Genres a mural's or painting's seed draws from, one at random.",
    )
    subjects: tuple[str, ...] = Field(
        default=SUBJECTS, min_length=1, description="Subjects a work's seed draws from."
    )
    moods: tuple[str, ...] = Field(
        default=MOODS, min_length=1, description="Moods a work's seed draws from."
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
        default=timedelta(hours=8),
        description="The age at which a mural is as ready to be painted over as age makes it.",
    )
    fresh: timedelta = Field(
        default=timedelta(hours=2),
        description="Murals younger than this are never painted over, even by their artist.",
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
        description="Sim time before a resident tries again to say how a mural lands, or a "
        "shopkeeper to put up a notice, after the call failed.",
    )
    painted_over_salience: float = Field(
        default=0.7,
        ge=0,
        le=1,
        description="The least salience of an artist's memory of finding their mural painted over.",
    )

    shopkeepers: tuple[Id, ...] = Field(
        default=("priya", "odalys", "mirela"),
        description="Residents of today's village who put up notices for their business. In a "
        "new world, whoever holds one of the village's roles does.",
    )
    notice_model: str = Field(
        default=Model.HAIKU_5_5, description="The model that writes a notice."
    )
    notice_every: timedelta = Field(
        default=timedelta(hours=12),
        description="Sim time between a shopkeeper's notices. They put one up once they're awake.",
    )
    notice_check: float = Field(
        default=60.0, gt=0, description="Sim seconds between looks at whose notice is due."
    )
    notice_words: int = Field(default=50, ge=1, description="The most words a notice may run to.")
    notice_life: timedelta = Field(
        default=timedelta(days=1), description="How long a notice stays up on the board."
    )
    notices_listed: int = Field(
        default=6, ge=0, description="The most notices on the board, newest first."
    )

    starters: int = Field(
        default=8,
        ge=0,
        description="The most starter works a new world makes in the background, one each for "
        "its most creative residents with a craft.",
    )
    starters_newest: timedelta = Field(
        default=timedelta(hours=3),
        description="How long before a save's first work, or before it starts if it has none, the "
        "newest of today's village's starter works was made. The rest keep their spacing before "
        "it.",
    )


DEFAULT_CONFIG = WorksConfig()
