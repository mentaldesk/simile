from pydantic import BaseModel, ConfigDict, Field

from simile.llm import Model


class ReflectionConfig(BaseModel):
    """Every constant of how a finished conversation becomes memories, events and flags."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    model: str = Field(default=Model.HAIKU, description="The model that reads each conversation.")
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
    events: int = Field(
        default=4, ge=0, description="Most events kept per participant per conversation."
    )
    flags: int = Field(
        default=3, ge=0, description="Most flags opened per participant per conversation."
    )
    topics: int = Field(default=3, ge=0, description="Most topics kept per memory.")
    player_name: str = Field(
        default="Visitor", min_length=1, description="What the player is called in the prompt."
    )


DEFAULT_CONFIG = ReflectionConfig()
