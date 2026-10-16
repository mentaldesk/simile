from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class VoicingConfig(BaseModel):
    """Every constant of earshot voicing. Distances are in tiles, times in real seconds."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    earshot: float = Field(
        default=4.0,
        gt=0,
        description="A conversation is voiced, from its next line, once the player is this near "
        "one of its speakers. C2 draws bubbles within the same 4 tiles (`EARSHOT_TILES`), about "
        "as far as the screen shows above and below the player.",
    )
    out_of_earshot: float = Field(
        default=5.5,
        description="Voicing stops, cutting the line being said, once the player is further than "
        "this from every speaker. C3 fades an overheard voice to silence here (`SILENT_BEYOND`). "
        "The gap from `earshot` keeps lines from cutting in and out at the edge.",
    )
    max_voiced: int = Field(
        default=2,
        ge=1,
        description="Most conversations voiced at once, the player's included, since V1 voices one "
        "sentence at a time. Others in earshot stay unvoiced until there's room, and the player's "
        "own conversation silences the farthest.",
    )
    lead: float = Field(
        default=0.5,
        gt=0,
        description="How much audio is sent ahead of what the client is playing, so a cut line "
        "stops this soon after. Less risks gaps when the server is busy.",
    )
    jitter_buffer: float = Field(
        default=0.1,
        ge=0,
        description="C3's jitter buffer: the client starts a line this long after its first "
        "chunk arrives, and again after a gap.",
    )

    @model_validator(mode="after")
    def _leaving_is_further(self) -> Self:
        if self.out_of_earshot < self.earshot:
            raise ValueError("out_of_earshot must be at least earshot")
        return self


DEFAULT_CONFIG = VoicingConfig()
