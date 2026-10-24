import tomllib
from functools import cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from simile.schema import CoreValue, Id, Key

STORY = Path(__file__).resolve().parents[3] / "content" / "story" / "story.toml"


class Authored(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Aris(Authored):
    name: str
    workshop: Id = Field(description="Her workshop's location id.")
    street: Key = Field(description="The street outside it, a map id.")
    description: str


class Clue(Authored):
    """Something in Aris's workshop the player can find a fact in: a fact's `found_in`."""

    id: Id
    label: str = Field(description="As the journal names it.")
    map: Key
    x: int
    y: int
    pages: list[str] = Field(default=[], description="What it says besides the fact, if anything.")


class Place(Authored):
    id: Id
    name: str


class Grievance(Authored):
    """Something Aris did that an attacker can't forgive, and the values that make it rankle."""

    values: dict[CoreValue, float]
    told: str = Field(description="What it is, for whoever writes the motive.")
    grievance: str = Field(description="In the third person, with `{name}`.")
    resents: str = Field(description="In the attacker's own words.")
    note: str = Field(description="What Aris wrote about it, with the attacker's `{initial}`.")


class Texts(Authored):
    """What stands in when nobody wrote it."""

    remembers: str = Field(description="An attacker's memory of the night, with `{with}`.")
    alibi: str
    deflection: str
    denial: str
    alone: str = Field(description="The motive's end for one attacker, with `{name}`.")
    together: str = Field(description="The motive's end for several.")
    relieved: str = Field(description="How a hostile resident ends their memory of her going.")
    covers: dict[Id, str] = Field(
        description="What a witness who'd rather lie says instead, by the fact they saw."
    )


class StoryContent(Authored):
    aris: Aris
    clues: list[Clue]
    meeting_places: list[Place] = Field(min_length=1)
    grievances: dict[Id, Grievance] = Field(min_length=1)
    texts: Texts

    def clue(self, clue_id: Id) -> Clue:
        return next(clue for clue in self.clues if clue.id == clue_id)


NOTES = "aris_notes"
"""The clue that holds Aris's notes."""
DOOR = "door_frame"
"""The clue the attackers left behind."""
TERMINAL = "metro_terminal"
"""The metro's dead terminal, a clue only the datajack reads."""
HATCH = "sewers_hatch"
"""The sewers' maintenance hatch, in every level: a clue only the datajack reads."""


@cache
def load_story(path: Path = STORY) -> StoryContent:
    with path.open("rb") as file:
        return StoryContent.model_validate(tomllib.load(file))
