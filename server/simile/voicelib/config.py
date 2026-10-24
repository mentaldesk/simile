import os
from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict, Field

DAILY = "SIMILE_ELEVENLABS_DAILY"


class VoicelibConfig(BaseModel):
    """The creator's voice step."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    elevenlabs_characters_a_day: int = Field(
        default=300,
        ge=0,
        description="Most ElevenLabs characters the greetings jobs may send each day, about two "
        f"characters' worth. Past it, V1's model says them. `{DAILY}` sets it.",
    )


DEFAULT_CONFIG = VoicelibConfig()


def from_environment(environ: Mapping[str, str] = os.environ) -> VoicelibConfig:
    """`DEFAULT_CONFIG`, with `SIMILE_ELEVENLABS_DAILY` if it's set."""
    daily = environ.get(DAILY, "").strip()
    if not daily:
        return DEFAULT_CONFIG
    if not daily.isdigit():
        raise ValueError(f"{DAILY} has to be a whole number of characters, not {daily!r}")
    return VoicelibConfig(elevenlabs_characters_a_day=int(daily))
