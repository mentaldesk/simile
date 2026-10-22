from enum import StrEnum
from typing import Any, Final

from pydantic import Field, model_validator

from simile.schema.common import CHECKED, Id, Key, Model, Timestamp, Unit

ARIS: Final = "aris"


def _field(item: Any, field: str) -> Any:
    """`field` of a model, or of the dict it's validated from."""
    return item.get(field) if isinstance(item, dict) else getattr(item, field, None)


def _strings(values: Any) -> list[str]:
    return [value for value in values if isinstance(value, str)] if isinstance(values, list) else []


def _fields(items: Any, field: str) -> list[str]:
    return _strings([_field(item, field) for item in items]) if isinstance(items, list) else []


def _repeats(values: list[str]) -> bool:
    return len(set(values)) < len(values)


class HowKnown(StrEnum):
    """How a resident knows a fact: they `did` it, `witnessed` it (saw or heard it happen), or
    were `told` it by someone."""

    DID = "did"
    WITNESSED = "witnessed"
    TOLD = "told"


class Knower(Model):
    """A resident who knows a fact, how they know it, and how willing they are to tell it."""

    model_config = CHECKED

    id: Id = Field(description="The resident.")
    how: HowKnown
    tells_from: Unit | None = Field(
        description="The least trust they need in whoever asks before they tell it: 0 tells "
        "anyone. Null if they never tell it."
    )
    cover: str | None = Field(
        min_length=1,
        description='What they say instead of telling it, when they lie, e.g. "I was home all '
        'night." Code decides when they lie, as for other lies, so the infrared eye reads it '
        "exactly. Null if they keep quiet rather than lie.",
    )


class Lead(Model):
    """Where the trail goes next: someone to ask or somewhere to look, which turns up a fact."""

    model_config = CHECKED

    fact_id: Id = Field(description="The fact following it turns up.")
    text: str = Field(
        min_length=1,
        description='For the journal, e.g. "Kofi paints in the lane at night. Ask him what he '
        'saw."',
    )


class Fact(Model):
    """Something that happened, kept in the sim. Residents only voice it: code decides who tells
    it to whom, and who lies about it."""

    model_config = CHECKED

    id: Id
    what: str = Field(
        min_length=1,
        description="What happened, in the third person, as it really did. Each knower's memory "
        "of it is in their own words.",
    )
    when: Timestamp = Field(description="Sim time.")
    where: Key = Field(
        description='A location\'s id, such as "maker_space", or a map\'s, such as "high_street".'
    )
    about: list[Id] = Field(
        description="Who it's about, even if those who know it couldn't name them."
    )
    known_by: list[Knower] = Field(description="The residents who know it, each listed once.")
    found_in: Id | None = Field(
        default=None,
        description="The clue the player can find it in instead of being told, such as Aris's "
        "notes: the interactable's id. Null if only residents can tell it.",
    )
    leads: list[Lead] = Field(
        default=[], description="Where learning it points the player next, never back to itself."
    )

    @model_validator(mode="before")
    @classmethod
    def _consistent(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if _repeats(_fields(data.get("known_by"), "id")):
                raise ValueError("each resident knows it once")
            if data.get("id") in _fields(data.get("leads"), "fact_id"):
                raise ValueError("a fact doesn't lead to itself")
        return data


class Incident(Model):
    """The night Aris was attacked, made once at world creation: who attacked her, why, and the
    facts around it."""

    model_config = CHECKED

    victim: Id = Field(default=ARIS, description="Aris, who has been missing since.")
    attackers: list[Id] = Field(
        min_length=1, max_length=3, description="The residents who attacked her, one to three."
    )
    motive: str = Field(
        min_length=1,
        description="Why they did it, written once at world creation and never rewritten.",
    )
    night: Timestamp = Field(description="When they attacked her, in sim time.")
    facts: list[Fact] = Field(
        description="Who did it, why, who saw what and who knows what. Each has its own id, and "
        "their leads go to one another."
    )

    @model_validator(mode="before")
    @classmethod
    def _consistent(cls, data: Any) -> Any:
        if isinstance(data, dict):
            attackers = _strings(data.get("attackers"))
            if _repeats(attackers):
                raise ValueError("each attacker is named once")
            if data.get("victim", ARIS) in attackers:
                raise ValueError("the victim isn't one of the attackers")
            facts = data.get("facts")
            ids = _fields(facts, "id")
            if _repeats(ids):
                raise ValueError("each fact has its own id")
            for fact in facts if isinstance(facts, list) else []:
                for target in _fields(_field(fact, "leads"), "fact_id"):
                    if target not in ids:
                        raise ValueError(f"a lead goes to {target}, which isn't one of its facts")
        return data


class SourceKind(StrEnum):
    """Where the player learned something: a `resident` told them, or they found a `clue`, such
    as Aris's notes or a terminal."""

    RESIDENT = "resident"
    CLUE = "clue"


class Source(Model):
    """Who told the player something, or the clue they found it in."""

    model_config = CHECKED

    kind: SourceKind
    id: Id = Field(description="The resident's id, or the clue's interactable's.")
    name: str = Field(
        min_length=1, description='As the journal names them, e.g. "Kofi" or "Aris\'s notes".'
    )


class JournalEntry(Model):
    """Something the player learned about the incident: a fact, or a lie told about one."""

    model_config = CHECKED

    fact_id: Id = Field(description="The fact it's about. Several entries can be about one fact.")
    text: str = Field(
        min_length=1,
        description="What they learned, as the journal puts it. A lie is written as it was told.",
    )
    source: Source = Field(description="Who told them, or the clue they found it in.")
    learned: Timestamp = Field(description="Sim time.")
    flushed: bool | None = Field(
        description="Whether the infrared eye saw the resident flush as they told it, which it "
        "shows exactly on a lie. Null if the player had no infrared eye then, and for a clue."
    )
    leads: list[Lead] = Field(
        default=[],
        description="The leads it opened that are still open. Each stays until the player learns "
        "its fact, from anyone.",
    )

    @model_validator(mode="before")
    @classmethod
    def _consistent(cls, data: Any) -> Any:
        if isinstance(data, dict):
            clue = _field(data.get("source"), "kind") == SourceKind.CLUE
            if clue and data.get("flushed") is not None:
                raise ValueError("only a resident can flush")
            if data.get("fact_id") in _fields(data.get("leads"), "fact_id"):
                raise ValueError("an entry's leads go to other facts")
        return data
