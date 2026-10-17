from enum import StrEnum
from typing import Self

from pydantic import Field, field_validator, model_validator

from simile.schema.common import PLAYER_ID, Id, Model, Signed, Timestamp, Unit
from simile.schema.npc import Appearance, Craft, EveryValue, Voice

MAX_AGE = 120


class Gender(StrEnum):
    WOMAN = "woman"
    MAN = "man"
    NONBINARY = "nonbinary"


class CharacterSource(StrEnum):
    """`premade` characters ship with the game and are read-only; `player` ones a player made."""

    PREMADE = "premade"
    PLAYER = "player"


class Arrival(Model):
    """When and why a character came to the village."""

    age: int = Field(ge=0, le=MAX_AGE)
    reason: str = Field(min_length=1, description='Why they came, e.g. "for a job".')


class PastMemory(Model):
    """A memory of their life before the game, which casting turns into a `past` Memory."""

    age: int = Field(ge=0, le=MAX_AGE, description="How old they were when it happened.")
    content: str = Field(
        min_length=1, description="The memory in their own words, ready for a prompt."
    )
    salience: Unit = Field(description="How much it matters to them, 0-1.")
    valence: Signed = Field(description="How they feel about it, from -1 to 1.")


class HookKind(StrEnum):
    """Mutual: `estranged_sibling`, `ex_partner`, `old_friend`, `rival`. One-way, where the actor
    did it to the target: `debt`, the actor borrowed money from the target and still owes it;
    `secret`, the target saw the actor do something the actor wants kept hidden; `betrayal`, the
    actor betrayed the target; `saved_life`, the actor saved the target's life."""

    ESTRANGED_SIBLING = "estranged_sibling"
    EX_PARTNER = "ex_partner"
    OLD_FRIEND = "old_friend"
    RIVAL = "rival"
    DEBT = "debt"
    SECRET = "secret"
    BETRAYAL = "betrayal"
    SAVED_LIFE = "saved_life"

    @property
    def mutual(self) -> bool:
        return self in _MUTUAL


_MUTUAL = {HookKind.ESTRANGED_SIBLING, HookKind.EX_PARTNER, HookKind.OLD_FRIEND, HookKind.RIVAL}


class HookSide(StrEnum):
    MUTUAL = "mutual"
    ACTOR = "actor"
    TARGET = "target"


class Hook(Model):
    """An open tie to another resident, which casting binds to someone in the cast."""

    kind: HookKind
    side: HookSide = Field(description="`mutual` for a mutual kind, else `actor` or `target`.")
    description: str = Field(
        min_length=1,
        description="The tie from this character's side in a sentence, without naming the other "
        "resident.",
    )

    @model_validator(mode="after")
    def _side_fits_kind(self) -> Self:
        if (self.side is HookSide.MUTUAL) != self.kind.mutual:
            sides = "mutual" if self.kind.mutual else "actor or target"
            raise ValueError(f"a {self.kind} hook's side is {sides}")
        return self


class Traits(Model):
    """The numbers social/ and behaviour/ read. Each is 0-1, and 0.5 is how residents behave
    without traits."""

    sociability: Unit = Field(
        default=0.5, description="How often they start a conversation and how long they stay."
    )
    negativity_bias: Unit = Field(
        default=0.5, description="How much more a bad turn weighs with them than a good one."
    )
    forgiveness: Unit = Field(default=0.5, description="How fast a grudge fades.")
    first_impressions: Unit = Field(
        default=0.5, description="How far a first meeting swings their opinion of someone."
    )


class CharacterVoice(Voice):
    needs_recording: bool = Field(
        default=False,
        description="True when VoiceDesign can't do the accent, so the clip has to be recorded.",
    )


class Character(Model):
    """A character in the library, apart from any village. Casting makes an Npc from it."""

    id: Id
    name: str = Field(min_length=1)
    birth_year: int
    gender: Gender
    origin: str = Field(
        min_length=1,
        description="Where they were born, or for someone born in the village where their family "
        'is from, e.g. "Vietnam".',
    )
    arrival: Arrival | None = Field(description="Null if they were born in the village.")
    occupation: str = Field(min_length=1)
    values: EveryValue = Field(
        description="How much they care about each of the 24 core values, 0-1. All are present."
    )
    backstory: str = Field(
        min_length=1, description="Their whole life in prose, for the debug UI and for assets."
    )
    persona: str = Field(min_length=1)
    speaking_style: str = Field(min_length=1)
    interests: list[str]
    past: list[PastMemory]
    hooks: list[Hook]
    traits: Traits
    appearance: Appearance
    voice: CharacterVoice
    craft: Craft | None = Field(default=None, description="Null if they don't make anything.")
    source: CharacterSource
    created: Timestamp
    updated: Timestamp
    version: int = Field(ge=1, description="Goes up by one on every edit.")

    @field_validator("id")
    @classmethod
    def _not_player(cls, id: str) -> str:
        if id == PLAYER_ID:
            raise ValueError(f"'{PLAYER_ID}' is reserved for the player")
        return id

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.updated < self.created:
            raise ValueError("updated must not be before created")
        age = self.updated.year - self.birth_year
        if not 0 <= age <= MAX_AGE:
            raise ValueError(f"born in {self.birth_year}, they'd be {age} in {self.updated.year}")
        ages = [memory.age for memory in self.past]
        if self.arrival:
            ages.append(self.arrival.age)
        if ages and max(ages) > age:
            raise ValueError(f"something happened at {max(ages)}, but they're at most {age}")
        return self
