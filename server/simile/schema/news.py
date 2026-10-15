from datetime import datetime

from pydantic import Field

from simile.schema.common import Model


class NewsItem(Model):
    id: str = Field(min_length=1, description="The feed entry's guid.")
    title: str
    url: str
    summary: str = Field(description="Plain text, HTML stripped.")
    published: datetime
