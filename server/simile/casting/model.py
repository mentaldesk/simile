from datetime import date
from typing import Self

from pydantic import Field, model_validator

from simile.schema import Character, HookKind, Id, Model, Npc, Voice


class CastError(ValueError):
    """A cast that can't be made as asked."""


class Pin(Model):
    """A bond the player chose: `actor` did it to `target`, or for a mutual kind, they share it."""

    kind: HookKind
    actor: Id
    target: Id

    @model_validator(mode="after")
    def _two_residents(self) -> Self:
        if self.actor == self.target:
            raise ValueError("a bond is between two residents")
        return self


class Bond(Model):
    """A hook bound between two residents. For a mutual kind, either one is the actor."""

    kind: HookKind
    actor: Id
    target: Id
    actor_hook: str | None = Field(default=None, description="The actor's own words for it.")
    target_hook: str | None = Field(default=None, description="The target's own words for it.")
    pinned: bool = False


class Resident(Model):
    character: Character = Field(description="As it was when cast, with its id and version.")
    home: Id


class Cast(Model):
    """A village's residents, made from library characters."""

    game_date: date = Field(description="The day the village starts, which sets their ages.")
    seed: int
    residents: list[Resident]
    bonds: list[Bond] = []

    def age(self, character: Character) -> int:
        return self.game_date.year - character.birth_year

    def npcs(self) -> list[Npc]:
        return [self.npc(resident) for resident in self.residents]

    def npc(self, resident: Resident) -> Npc:
        character = resident.character
        return Npc(
            id=character.id,
            name=character.name,
            age=self.age(character),
            occupation=character.occupation,
            home=resident.home,
            values=character.values,
            backstory=character.backstory,
            persona=character.persona,
            speaking_style=character.speaking_style,
            mannerisms=character.mannerisms,
            interests=character.interests,
            appearance=character.appearance,
            voice=Voice.model_validate(character.voice.model_dump(exclude={"needs_recording"})),
            craft=character.craft,
        )

    def unvoiced(self) -> list[Character]:
        """Residents with no reference clip yet."""
        return [r.character for r in self.residents if r.character.voice.reference_clip is None]
