from enum import StrEnum
from typing import Annotated

from pydantic import AfterValidator, Field, field_validator

from simile.schema.common import PLAYER_ID, Colour, Id, Model, Unit


class CoreValue(StrEnum):
    FREEDOM = "freedom"
    INDEPENDENCE = "independence"
    SELF_RESPECT = "self_respect"
    SELF_ACTUALIZATION = "self_actualization"
    CREATIVITY = "creativity"
    HONESTY = "honesty"
    COMPASSION = "compassion"
    LOYALTY = "loyalty"
    JUSTICE = "justice"
    RESPONSIBILITY = "responsibility"
    SECURITY = "security"
    EQUALITY = "equality"
    TRADITION = "tradition"
    OBEDIENCE = "obedience"
    SUCCESS = "success"
    AMBITION = "ambition"
    DISCIPLINE = "discipline"
    KNOWLEDGE = "knowledge"
    OPEN_MINDEDNESS = "open_mindedness"
    PEACE_OF_MIND = "peace_of_mind"
    PLEASURE = "pleasure"
    CONNECTION = "connection"
    ADVENTURE = "adventure"
    OPTIMISM = "optimism"


def _every_value(values: dict[CoreValue, float]) -> dict[CoreValue, float]:
    if missing := [value.value for value in CoreValue if value not in values]:
        raise ValueError(f"missing core values: {', '.join(missing)}")
    return values


EveryValue = Annotated[dict[CoreValue, Unit], AfterValidator(_every_value)]


class HairStyle(StrEnum):
    BALD = "bald"
    BUZZ = "buzz"
    SHORT = "short"
    CURLY = "curly"
    BOB = "bob"
    LONG = "long"
    PONYTAIL = "ponytail"
    BUN = "bun"


class Build(StrEnum):
    SLIM = "slim"
    AVERAGE = "average"
    BROAD = "broad"


class Accessory(StrEnum):
    GLASSES = "glasses"
    SUNGLASSES = "sunglasses"
    CAP = "cap"
    BEANIE = "beanie"
    HEADPHONES = "headphones"
    SCARF = "scarf"
    BACKPACK = "backpack"
    APRON = "apron"


class Appearance(Model):
    """What a character looks like, for the sprite generator. Colours are #rrggbb."""

    skin: Colour
    hair_style: HairStyle
    hair_colour: Colour
    top_colour: Colour
    bottom_colour: Colour
    shoe_colour: Colour
    build: Build
    accessories: list[Accessory] = []


class Voice(Model):
    description: str = Field(description="What the voice sounds like, for the voice design model.")
    reference_line: str = Field(
        description="A neutral line in character, 5-10 seconds of speech. The clip's transcript."
    )
    reference_clip: str | None = Field(
        default=None,
        description="The recorded reference clip, relative to the repository root. "
        "Null until the voice is designed.",
    )


class Medium(StrEnum):
    WRITING = "writing"
    MURAL = "mural"


class Craft(Model):
    """What a resident makes in their own time, which can differ from their job."""

    medium: Medium
    form: str = Field(
        min_length=1,
        description='What they make, in a few words, e.g. "short poems about the river".',
    )


class Npc(Model):
    id: Id
    name: str
    age: int = Field(ge=0, le=120)
    occupation: str
    home: Id = Field(description="Location id of their house.")
    values: EveryValue = Field(
        description="How much they care about each of the 24 core values, 0-1. All are present."
    )
    backstory: str
    persona: str
    speaking_style: str
    interests: list[str]
    appearance: Appearance
    voice: Voice
    craft: Craft | None = Field(default=None, description="Null if they don't make anything.")

    @field_validator("id")
    @classmethod
    def _not_player(cls, id: str) -> str:
        if id == PLAYER_ID:
            raise ValueError(f"'{PLAYER_ID}' is reserved for the player")
        return id
