import sys

from simile.memory import MemoryStore
from simile.news.config import DEFAULT_CONFIG, NewsConfig
from simile.news.reactions import read_in
from simile.news.store import NewsStore
from simile.protocol import NewsArticle, NewsMessage
from simile.schema import PLAYER_ID, Memory, MemoryKind, NewsItem
from simile.sim import Clock


class PlayerNews:
    """The player at a news terminal: `list_news` and `read_news` each get the `news` to send
    back, and reading an article stores it as the player's own `news` memory. No LLM call."""

    def __init__(
        self,
        news: NewsStore,
        memory: MemoryStore,
        clock: Clock,
        *,
        config: NewsConfig = DEFAULT_CONFIG,
    ) -> None:
        self.news = news
        self.memory = memory
        self.clock = clock
        self.config = config

    def listing(self) -> NewsMessage:
        read = self._read()
        return NewsMessage(
            articles=[
                NewsArticle(
                    news_id=item.id,
                    title=item.title,
                    source=item.source,
                    summary=item.summary,
                    long_summary=item.long_summary,
                    url=item.url,
                    read=item.id in read,
                )
                for item in self.news.latest(self.config.articles)
            ]
        )

    def read(self, news_id: str) -> NewsMessage:
        item = self.news.get(news_id)
        if item is not None and news_id not in self._read():
            self.memory.add(self._remember(item))
        return self.listing()

    def _read(self) -> set[str]:
        memories = self.memory.recall(
            PLAYER_ID, self.clock.now, kind=MemoryKind.NEWS, k=sys.maxsize
        )
        return {memory.news_id for memory in memories if memory.news_id}

    def _remember(self, item: NewsItem) -> Memory:
        return Memory(
            owner=PLAYER_ID,
            kind=MemoryKind.NEWS,
            content=f'I read "{item.title}"{read_in(item)} on the news terminal.',
            salience=self.config.player_salience,
            valence=0,
            timestamp=self.clock.now,
            topics=item.tags[: self.config.topics],
            news_id=item.id,
        )
