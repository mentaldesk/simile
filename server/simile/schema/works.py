from typing import Self

from pydantic import Field, model_validator

from simile.schema.common import Id, Key, Model, Signed, Timestamp
from simile.schema.news import Tag
from simile.schema.npc import EveryValue, Medium


class Work(Model):
    """Something a resident made: a piece of writing, or a mural on a wall."""

    id: Key
    artist: Id = Field(description="The NPC who made it.")
    medium: Medium
    form: str = Field(min_length=1, description="The form of the artist's craft when they made it.")
    title: str = Field(min_length=1)
    created: Timestamp
    text: str = Field(
        description="The piece itself for writing, or for a mural a plain description of what "
        "it shows."
    )
    statement: str = Field(
        description="A sentence or two in the artist's voice on what it's saying."
    )
    inspired_by: list[Key] = Field(
        description="The ids of the news items, conversations and other works it came from."
    )
    values: EveryValue = Field(
        description="How related it is to each of the 24 core values, 0-1, with no direction, "
        "as for NewsItem. All are present."
    )
    tags: list[Tag] = Field(max_length=10, description='Up to 10 short topic tags, e.g. "mars".')
    sentiment: Signed = Field(description="Its overall tone, from -1 to 1.")
    wall: Id | None = Field(
        default=None, description="The wall a mural is painted on. Null for writing."
    )

    @model_validator(mode="after")
    def _wall_for_murals(self) -> Self:
        if (self.wall is not None) != (self.medium is Medium.MURAL):
            raise ValueError("a mural needs a wall, and only a mural has one")
        return self
