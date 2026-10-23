from pydantic import BaseModel, ConfigDict, Field


class VoicelibConfig(BaseModel):
    """The creator's voice step."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    elevenlabs_characters_a_day: int = Field(
        default=300,
        ge=0,
        description="Most ElevenLabs characters the greetings jobs may send each day, about two "
        "characters' worth. Past it, V1's model says them.",
    )


DEFAULT_CONFIG = VoicelibConfig()
