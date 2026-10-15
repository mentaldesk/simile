from pydantic import Field

from simile.schema.common import Key, Model, Timestamp


class NewsItem(Model):
    id: Key = Field(description="The feed entry's guid.")
    title: str
    url: str
    summary: str = Field(description="Plain text, HTML stripped.")
    published: Timestamp
