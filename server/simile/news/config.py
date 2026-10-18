from datetime import timedelta

from pydantic import BaseModel, ConfigDict, Field

from simile.llm import Model


class NewsConfig(BaseModel):
    """Every constant of how articles are taken in and analysed, how NPCs pick, read and bring up
    the news, and how the player reads it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_feeds: int = Field(
        default=12,
        ge=1,
        description="The most feeds the saved list takes. Each one switched on adds up to 10 "
        "analysis calls when its new stories come in.",
    )
    min_summary_words: int = Field(
        default=3,
        ge=0,
        description="Feed items whose summary has fewer words than this, like a section header "
        "with none, aren't taken in: there's too little to react to.",
    )
    model: str = Field(
        default=Model.HAIKU_5_5, description="The model that analyses and rates articles."
    )
    priority: int = Field(
        default=-1,
        description="L1 priority of the analysis and rating calls, below conversations' 0.",
    )
    candidates: int = Field(
        default=60, ge=1, description="The newest articles analysed and considered for reading."
    )
    analyse_every: timedelta = Field(
        default=timedelta(minutes=1), description="Sim time between checks for new articles."
    )
    analyse_backoff: timedelta = Field(
        default=timedelta(hours=1),
        description="The longest wait between checks while analysis calls keep failing. The "
        "wait doubles with each failure in a row.",
    )
    value_decay: float = Field(
        default=2.0,
        ge=1,
        description="How many times less each value's pull on an NPC counts than the stronger "
        "one before it. A pull is `2 * value - 1` (or 0) times the article's relatedness.",
    )
    value_weight: float = Field(
        default=1.0, ge=0, description="Interest per unit of those pulls, added up."
    )
    tag_weight: float = Field(
        default=0.15,
        ge=0,
        description="Interest when one of the article's tags shares a word with their interests.",
    )
    sentiment_weight: float = Field(
        default=0.1,
        description="Interest per unit of the article's sentiment times `2 * optimism - 1`, so "
        "optimists lean to good news and pessimists to bad.",
    )
    min_interest: float = Field(
        default=0.5, ge=0, description="Articles less interesting than this aren't read."
    )
    cares_most: int = Field(
        default=5, ge=0, description="Strongest values listed in the reading prompt."
    )
    cares_least: int = Field(
        default=3, ge=0, description="Weakest values listed in the reading prompt."
    )
    topics: int = Field(default=3, ge=0, description="Most topics kept per reaction.")
    half_life: timedelta = Field(
        default=timedelta(hours=24),
        description="Sim time over which a reaction's pull as a topic halves.",
    )
    min_score: float = Field(
        default=0.05,
        ge=0,
        description="Reactions scoring less than this (intensity × recency) aren't raised.",
    )
    articles: int = Field(
        default=20, ge=0, description="The newest articles listed for the player at a terminal."
    )
    player_salience: float = Field(
        default=0.5,
        ge=0,
        le=1,
        description="The salience of the player's memory of reading an article. They don't "
        "react to it, so its valence is 0.",
    )
    mention_words: int = Field(
        default=2,
        ge=1,
        description="Words the player's latest lines must share with an article an NPC read, "
        "its title, tags, summary or the NPC's topics, to bring it to the NPC's mind. One will "
        "do only if they name the news too and it's in the title or a one-word tag or topic.",
    )
    mentions: int = Field(
        default=2,
        ge=0,
        description="Most articles the player's latest lines bring to an NPC's mind for a reply.",
    )


DEFAULT_CONFIG = NewsConfig()
