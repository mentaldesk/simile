from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from simile.behaviour import Activity
from simile.llm import Model
from simile.schema import CoreValue

V = CoreValue
A = Activity

ACCEPT_VALUES: dict[CoreValue, float] = {
    V.CONNECTION: 0.8,
    V.COMPASSION: 0.2,
    V.OPEN_MINDEDNESS: 0.2,
    V.INDEPENDENCE: -0.3,
    V.PEACE_OF_MIND: -0.2,
}

ACCEPT_GOALS: dict[Activity, float] = {
    A.COFFEE_SHOP: 0.1,
    A.SQUARE: 0.1,
    A.NOODLE_BAR: 0.1,
    A.IDLE: 0.1,
    A.NEWS: -0.3,
    A.MAKER_SPACE: -0.3,
    A.SEEK: -0.3,
}


class ConversationConfig(BaseModel):
    """Every constant of the conversation engine. Engagement runs from 0 (wants to leave) to 1."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_conversations: int = Field(
        default=2, ge=0, description="Conversations going on at once. Requests beyond it decline."
    )

    accept_base: float = Field(default=0.2, description="Base score for accepting a request.")
    accept_weights: dict[str, float] = Field(
        default={"like": 1.5, "trust": 0.5, "respect": 0.3, "familiarity": 0.3},
        description="How the target's relationship with the requester enters the accept score: "
        "weight * (score - 0.5) for like, trust and respect, weight * familiarity.",
    )
    accept_values: dict[CoreValue, float] = Field(
        default=ACCEPT_VALUES, description="Accept score per unit of the target's `value - 0.5`."
    )
    accept_social: float = Field(
        default=1.5, description="Accept score per unit of the target's `social need - 0.5`."
    )
    accept_goals: dict[Activity, float] = Field(
        default=ACCEPT_GOALS, description="Accept score by what the target is busy with."
    )
    seeking_them: float = Field(
        default=1.0, description="Accept score when the target was out looking for the requester."
    )
    accept_temperature: float = Field(
        default=0.1,
        ge=0,
        description="Randomness of accepting: the chance is logistic(score / temperature). "
        "0 accepts whenever the score is positive.",
    )

    start_engagement: float = Field(default=0.6, ge=0, le=1, description="Engagement at hello.")
    start_like: float = Field(
        default=0.6, description="Engagement at hello per unit of `like - 0.5` for the other."
    )
    start_values: dict[CoreValue, float] = Field(
        default={V.CONNECTION: 0.3}, description="Engagement at hello per unit of `value - 0.5`."
    )
    fatigue: float = Field(default=0.07, ge=0, description="Engagement lost every line.")
    topic_weight: float = Field(
        default=0.1,
        ge=0,
        description="Engagement per line per unit of topic match: how much the values the line "
        "touches matter to them, from -1 to 1.",
    )
    like_weight: float = Field(
        default=0.1, ge=0, description="Engagement per line per unit of `like - 0.5`."
    )
    leave_below: float = Field(
        default=0.3, ge=0, le=1, description="Someone whose turn it is says goodbye below this."
    )
    min_lines: int = Field(default=2, ge=1, description="Lines before anyone may say goodbye.")
    max_lines: int = Field(
        default=60,
        ge=2,
        description="A backstop: most lines, goodbyes included, before a conversation ends. "
        "Engagement ends them long before this.",
    )
    farewell: bool = Field(default=True, description="Whether the other answers a goodbye.")

    words_per_minute: float = Field(
        default=200,
        gt=0,
        description="Speaking pace: 0.3 s a word, so lines take about as long as V1 takes to say "
        "them. C2's SECONDS_PER_WORD matches it.",
    )
    min_line_seconds: float = Field(default=1.0, ge=0, description="Shortest a line takes.")
    turn_gap: float = Field(default=0.5, ge=0, description="Sim seconds between two lines.")

    model: str = Field(
        default=Model.HAIKU_5_5,
        description="The model that writes lines. See *Which model* in the L1 README.",
    )
    line_timeout: float = Field(
        default=30,
        gt=0,
        description="Real seconds a line may take to write before it counts as failed, which "
        "ends the conversation.",
    )
    max_words: int = Field(default=40, ge=1, description="Longest line asked for.")
    memories_about: int = Field(
        default=3, ge=0, description="Memories of the other person in a speaker's prompt."
    )
    memories_recent: int = Field(
        default=3, ge=0, description="Other recent or salient memories in a speaker's prompt."
    )
    history: int = Field(default=5, ge=0, description="Shared events in a speaker's prompt.")
    topics: int = Field(default=3, ge=0, description="News topics from B4 in a speaker's prompt.")
    transcript_lines: int = Field(
        default=12, ge=1, description="Latest lines of the conversation in a speaker's prompt."
    )

    cooldown: float = Field(
        default=60, ge=0, description="Minutes after a conversation before either seeks the other."
    )
    keep_finished: int = Field(
        default=50, ge=0, description="Finished conversations kept for `conversation(id)`."
    )

    @model_validator(mode="after")
    def _room_to_talk(self) -> Self:
        if self.max_lines < self.min_lines + (2 if self.farewell else 1):
            raise ValueError("max_lines must leave room for min_lines and the goodbyes")
        return self


DEFAULT_CONFIG = ConversationConfig()
