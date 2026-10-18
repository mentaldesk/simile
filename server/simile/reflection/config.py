from datetime import timedelta

from pydantic import BaseModel, ConfigDict, Field

from simile.llm import Model


class ReflectionConfig(BaseModel):
    """Every constant of how a finished conversation becomes memories, events and flags."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    model: str = Field(
        default=Model.HAIKU_5_5,
        description="The model that reads each conversation. See *Which model* in the L1 README.",
    )
    priority: int = Field(
        default=-1, description="L1 priority of the reflection calls, below conversations' 0."
    )
    cares_most: int = Field(
        default=5, ge=0, description="Strongest values listed for each participant."
    )
    cares_least: int = Field(
        default=3, ge=0, description="Weakest values listed for each participant."
    )
    transcript_lines: int = Field(
        default=60, ge=1, description="Latest lines of a conversation in the prompt."
    )
    events: int = Field(default=4, ge=0, description="Most events kept per NPC per conversation.")
    max_magnitude: float = Field(
        default=1.0,
        gt=0,
        le=1,
        description="Most that one NPC's events about another can weigh in a conversation, "
        "however many there are: a total magnitude above it is scaled down to it.",
    )
    flags: int = Field(default=3, ge=0, description="Most flags opened per NPC per conversation.")
    broken_promise_valence: float = Field(
        default=-0.4,
        ge=-1,
        lt=0,
        description="Valence of the trust event a broken promise adds when its owner's own "
        "events don't already lower their trust in whoever broke it.",
    )
    broken_promise_magnitude: float = Field(
        default=0.4, gt=0, le=1, description="Magnitude of that trust event."
    )
    broken_salience: float = Field(
        default=0.5,
        ge=0,
        le=1,
        description="Salience of the memories a promise left to expire leaves, the resident's and "
        "each promisee's. Their valence is `broken_promise_valence`.",
    )
    intentions: int = Field(
        default=2, ge=0, description="Most intentions kept per NPC per conversation."
    )
    description: int = Field(
        default=240, ge=1, description="Longest an intention's description is kept, in characters."
    )
    expire_now: timedelta = Field(
        default=timedelta(hours=2),
        description="How long after it's due an intention for straight after the conversation "
        "expires if it isn't kept.",
    )
    expire_later: timedelta = Field(
        default=timedelta(days=1),
        description="How long after it's due an intention for later expires if it isn't kept.",
    )
    horizon: timedelta = Field(
        default=timedelta(hours=36),
        description="Intentions due further off than this are dropped as too vague to act on.",
    )
    topics: int = Field(default=3, ge=0, description="Most topics kept per memory.")
    player_name: str = Field(
        default="Visitor", min_length=1, description="What the player is called in the prompt."
    )


DEFAULT_CONFIG = ReflectionConfig()
