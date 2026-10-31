import tomllib
from functools import cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from simile.schema import Id, Key

STORY = Path(__file__).resolve().parents[3] / "content" / "story" / "story.toml"


class Authored(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Aris(Authored):
    name: str
    workshop: Id = Field(description="Her workshop's location id.")
    street: Key = Field(description="The street outside it, a map id.")
    last_seen: Key = Field(description="The street she was last seen on, a map id.")
    description: str


class Clue(Authored):
    """Something in Aris's workshop the player can find a fact in: a fact's `found_in`."""

    id: Id
    label: str = Field(description="As the journal names it.")
    map: Key
    x: int
    y: int
    pages: list[str] = Field(default=[], description="What it says besides the fact, if anything.")


class Memories(Authored):
    """What a knower remembers, in their own words."""

    distrusted: str = Field(description="A distruster's memory of saying what they thought.")
    heard: str = Field(description="A bystander's memory of hearing them, with `{name}`.")
    saw: str = Field(description="The last sighting, with `{time}` and the passer's `{name}`.")
    passed: str = Field(description="The passer's memory of passing her.")


class Texts(Authored):
    relieved: str = Field(description="How a distruster ends their memory of her going.")
    denial: str = Field(description="A dishonest distruster's lie about how they got on with her.")
    not_seen: str = Field(description="A dishonest passer's lie about passing her.")
    notes: list[str] = Field(
        min_length=2, description="What Aris wrote about a distruster, with their `{initial}`."
    )
    memories: Memories
    covers: dict[Id, str] = Field(
        description="What a witness who'd rather lie says instead, by the fact they know."
    )


class StoryContent(Authored):
    aris: Aris
    clues: list[Clue]
    texts: Texts

    def clue(self, clue_id: Id) -> Clue:
        return next(clue for clue in self.clues if clue.id == clue_id)


NOTES = "aris_notes"
"""The clue that holds Aris's notes."""
TERMINAL = "metro_terminal"
"""The metro's dead terminal, a clue only the datajack reads."""
HATCH = "sewers_hatch"
"""The sewers' maintenance hatch, in every level: a clue only the datajack reads."""


@cache
def load_story(path: Path = STORY) -> StoryContent:
    with path.open("rb") as file:
        return StoryContent.model_validate(tomllib.load(file))
