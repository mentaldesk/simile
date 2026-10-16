from typing import Annotated

from pydantic import Field, field_validator

from simile.schema.common import Key, Model, Signed, Timestamp, Unit
from simile.schema.npc import CoreValue

Tag = Annotated[str, Field(min_length=1, max_length=40)]


class NewsItem(Model):
    id: Key = Field(description="The feed entry's guid.")
    title: str
    url: str
    summary: str = Field(description="Plain text, HTML stripped.")
    published: Timestamp
    source: str = Field(
        default="",
        description='The display name of the feed it came from, e.g. "The Atlantic". '
        "Empty for items stored before sources were recorded.",
    )
    source_url: str = Field(
        default="",
        description="The URL of the feed it came from. Empty for items stored before sources "
        "were recorded.",
    )
    values: dict[CoreValue, Unit] = Field(
        default={},
        description="How related the article is to each of the 24 core values, 0-1, with no "
        "direction: an article that clashes with a value relates to it as much as one that "
        "upholds it. Empty until analysed, then all are present.",
    )
    tags: list[Tag] = Field(
        default=[],
        max_length=10,
        description='Up to 10 short topic tags, e.g. "drones". Empty until analysed.',
    )
    sentiment: Signed | None = Field(
        default=None,
        description="The article's overall tone, from -1 (very negative) to 1 (very positive). "
        "Null until analysed.",
    )

    @property
    def analysed(self) -> bool:
        return bool(self.values)

    @field_validator("values")
    @classmethod
    def _all_or_none(cls, values: dict[CoreValue, float]) -> dict[CoreValue, float]:
        if values and (missing := [value.value for value in CoreValue if value not in values]):
            raise ValueError(f"missing core values: {', '.join(missing)}")
        return values
