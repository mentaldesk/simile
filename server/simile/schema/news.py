from pydantic import Field

from simile.schema.common import Key, Model, Timestamp


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
