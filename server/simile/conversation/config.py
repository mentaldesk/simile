from datetime import timedelta
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
        default=2,
        ge=0,
        description="Conversations between NPCs going on at once. Requests beyond it decline. "
        "The player's conversation doesn't count; I1's max_voiced caps what's voiced.",
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
    accept_urgent: float = Field(
        default=5.0,
        ge=0,
        description="Taken off the accept score while one of the target's needs is at or past "
        "B1's critical level for it: enough to decline even a friend they were looking for.",
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
        "brings into the conversation for the first time matter to them, from -1 to 1.",
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
        description="A backstop: most lines in a conversation, goodbyes included. Engagement, "
        "or the scene's plan, ends them long before this.",
    )
    farewell: bool = Field(default=True, description="Whether the other answers a goodbye.")

    long_talk: int = Field(
        default=30,
        ge=2,
        description="Lines before someone as keen as can be wants to wrap up a scripted "
        "conversation. Someone at `leave_below` or less wants to after `min_lines`.",
    )
    keen_social: float = Field(
        default=0.3, description="Keenness per unit of social need above or below 0.5."
    )
    keen_topics: float = Field(
        default=0.2,
        description="Keenness per unit of topic interest: how much the values of what each side "
        "is likely to bring up matter to them, from -1 to 1.",
    )
    keen_goal: float = Field(
        default=0.3,
        description="Keenness per unit of what they were doing's accept score "
        "(`accept_goals`, or `seeking_them`).",
    )
    keen_pressing: float = Field(
        default=0.6,
        description="Keenness lost per unit of their most pressing need over `pressing`.",
    )
    pressing: float = Field(
        default=0.6,
        ge=0,
        le=1,
        description="Rest, curiosity or news above this is mentioned in the direction and makes "
        "them less keen.",
    )
    urgent_need: float = Field(
        default=0.95,
        ge=0,
        le=1,
        description="Rest, curiosity or news rising past this during a scripted conversation "
        "pulls them away from it, as does a need rising past B1's critical level for it.",
    )
    drain_from: float = Field(
        default=0.75,
        ge=0,
        le=1,
        description="A need with a critical level in B1 (hunger, the bladder) drains engagement "
        "faster from here, and the goodbye says what it sends them off to do.",
    )
    need_drain: float = Field(
        default=3.0,
        ge=0,
        description="How much faster engagement drains at a need's critical level: 1 + "
        "need_drain times as fast, in a straight line up from `drain_from`.",
    )

    borrow_from: float = Field(
        default=0.6,
        gt=0,
        le=1,
        description="Finances (how far below their savings target someone's money is, as a share "
        "of it) from which a resident asks a friend for a loan. They pay one back once doing so "
        "leaves them below it.",
    )
    ask_like: float = Field(
        default=0.6,
        ge=0,
        le=1,
        description="How much a resident must like someone to ask them for a loan.",
    )
    lend_trust: float = Field(
        default=0.6,
        ge=0,
        le=1,
        description="How much a resident must trust someone to lend them money.",
    )
    max_loan: int = Field(
        default=100,
        ge=10,
        description="Most a resident asks to borrow. They ask for what takes them back to their "
        "savings target, in tens, and a lender lends what they have above their own, in tens.",
    )
    ask_again: timedelta = Field(
        default=timedelta(hours=24),
        description="Sim time before a resident asks someone who turned them down again.",
    )

    words_per_minute: float = Field(
        default=200,
        gt=0,
        description="Speaking pace for a voice without a measured rate (see the voice README's "
        "*Speaking rates*), and for the player: 0.3 s a word. C2's SECONDS_PER_WORD matches it.",
    )
    min_line_seconds: float = Field(default=1.0, ge=0, description="Shortest a line takes.")
    voice_wait: float = Field(
        default=3.0,
        ge=0,
        description="Longest the next line waits, past the end of a voiced line, for I1 to make "
        "and play that line's audio, so a slow generation can't stall a conversation.",
    )
    turn_gap: float = Field(default=0.5, ge=0, description="Sim seconds between two lines.")

    model: str = Field(
        default=Model.HAIKU_4_5,
        description="The model that writes scenes. Haiku 4.5 rather than Haiku 5.5, whose "
        "thinking can't be turned off and held some scenes' first line back over 20 s. See "
        "*Which model* in the L1 README.",
    )
    line_timeout: float = Field(
        default=30,
        gt=0,
        description="Real seconds a line may take to write, or a script's next line to stream "
        "after its first, before the call counts as failed.",
    )
    first_line_timeout: float = Field(
        default=10,
        gt=0,
        description="Real seconds a script's first line may take to stream. A script with no "
        "line by then is asked for once more, and if that one misses too, the conversation ends "
        "before anyone speaks.",
    )
    continue_below: float = Field(
        default=0.5,
        ge=0,
        le=1,
        description="Share of its planned length a script must stop short of, without a "
        "goodbye in its last two lines, to get one more call for the rest.",
    )
    max_words: int = Field(
        default=40,
        ge=1,
        description="Longest line asked for. A longer one is cut at the first sentence boundary "
        "past it.",
    )
    memories_about: int = Field(
        default=3, ge=0, description="Memories of the other person in a speaker's prompt."
    )
    memories_recent: int = Field(
        default=3, ge=0, description="Other recent or salient memories in a speaker's prompt."
    )
    history: int = Field(default=5, ge=0, description="Shared events in a speaker's prompt.")
    topics: int = Field(default=3, ge=0, description="News topics from B4 in a speaker's prompt.")
    works: int = Field(
        default=2,
        ge=0,
        description="Works a speaker might bring up: their strongest memories of works they made, "
        "read or saw, those of the other's works first. In a scene each side also gets the works "
        "of theirs the other might bring up.",
    )
    works_half_life: timedelta = Field(
        default=timedelta(hours=24),
        description="Sim time over which a work memory's pull as a topic halves.",
    )
    works_min_score: float = Field(
        default=0.05,
        ge=0,
        description="Work memories scoring less than this (salience × recency) aren't raised.",
    )
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
