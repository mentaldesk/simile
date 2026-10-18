from typing import Any

from pydantic import Field, field_validator

from simile.characters.tables.census import FIELDS
from simile.npc.values import TRAITS
from simile.schema import (
    Appearance,
    Arrival,
    Character,
    CharacterSource,
    CharacterVoice,
    CoreValue,
    Craft,
    Gender,
    Hook,
    PastMemory,
    Traits,
    Unit,
)
from simile.schema import Model as Schema
from simile.schema.npc import Mannerism

LOCKABLE = (
    "name",
    "birth_year",
    "gender",
    "origin",
    "arrival",
    "occupation",
    "values",
    "backstory",
    "persona",
    "speaking_style",
    "mannerisms",
    "interests",
    "past",
    "hooks",
    "traits",
    "appearance",
    "voice",
    "craft",
)

SECTIONS: dict[str, tuple[str, ...]] = {
    "name": ("name",),
    "identity": ("birth_year", "gender", "origin", "arrival", "occupation"),
    "values": ("values", "traits"),
    "past": ("past",),
    "biography": ("backstory", "persona", "speaking_style", "mannerisms", "interests", "craft"),
    "hooks": ("hooks",),
    "voice": ("voice",),
    "appearance": ("appearance",),
}


class Brief(Schema):
    """A partial character: whatever the player fixed. A `Character` field is locked when it's
    set, even to null, and every stage samples or writes only the fields that aren't."""

    source: CharacterSource = CharacterSource.PREMADE
    name: str | None = Field(default=None, min_length=1)
    birth_year: int | None = None
    gender: Gender | None = None
    origin: str | None = Field(default=None, min_length=1)
    arrival: Arrival | None = None
    occupation: str | None = Field(default=None, min_length=1)
    values: dict[CoreValue, Unit] = Field(
        default={}, description="Locked core values. The rest are sampled."
    )
    latent: dict[str, float] = Field(
        default={},
        description="Locked latent traits behind the values (openness, transcendence, outlook, "
        "rigour), each a z-score where 0 is average.",
    )
    facts: dict[str, str | int | bool | None] = Field(
        default={},
        description="Locked census fields that aren't on Character, such as family or education.",
    )
    backstory: str | None = None
    persona: str | None = None
    speaking_style: str | None = None
    mannerisms: list[Mannerism] | None = Field(default=None, max_length=3)
    interests: list[str] | None = None
    past: list[PastMemory] | None = None
    hooks: list[Hook] | None = None
    traits: Traits | None = None
    appearance: Appearance | None = None
    voice: CharacterVoice | None = None
    craft: Craft | None = None

    @field_validator("latent")
    @classmethod
    def _known_traits(cls, latent: dict[str, float]) -> dict[str, float]:
        if unknown := set(latent) - set(TRAITS):
            raise ValueError(f"not latent traits: {', '.join(sorted(unknown))}")
        return latent

    @field_validator("facts")
    @classmethod
    def _census_fields(cls, facts: dict[str, Any]) -> dict[str, Any]:
        if unknown := set(facts) - FIELDS:
            raise ValueError(f"not census fields: {', '.join(sorted(unknown))}")
        return facts

    def locked(self, field: str) -> bool:
        if field == "values":
            return len(self.values) == len(CoreValue)
        return field in LOCKABLE and field in self.model_fields_set

    def locks(self) -> dict[str, Any]:
        return {field: getattr(self, field) for field in LOCKABLE if self.locked(field)}

    @classmethod
    def keeping(cls, character: Character, *sections: str) -> "Brief":
        """Everything about `character` locked except the fields in `sections`."""
        if unknown := set(sections) - set(SECTIONS):
            raise ValueError(f"no such section: {', '.join(sorted(unknown))}")
        free = {field for section in sections for field in SECTIONS[section]}
        kept = {field: getattr(character, field) for field in LOCKABLE if field not in free}
        return cls(source=character.source, **kept)
