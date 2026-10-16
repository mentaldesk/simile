import asyncio
import logging
from collections import Counter
from collections.abc import Callable, Iterable

from pydantic import BaseModel, Field, create_model

from simile.llm import LLMClient, StructuredOutputError
from simile.news.config import DEFAULT_CONFIG, NewsConfig
from simile.news.store import NewsStore
from simile.schema import CoreValue, NewsItem

logger = logging.getLogger(__name__)

SCALE = 10
MAX_TAGS = 10
TAG_LENGTH = 40

MEANINGS: dict[CoreValue, str] = {
    CoreValue.FREEDOM: "the right to live, think and act freely",
    CoreValue.INDEPENDENCE: "relying on yourself; self-sufficiency",
    CoreValue.SELF_RESPECT: "pride in who you are and how you act",
    CoreValue.SELF_ACTUALIZATION: "becoming the best version of yourself",
    CoreValue.CREATIVITY: "expressing new ideas and original thought",
    CoreValue.HONESTY: "telling the truth and being transparent",
    CoreValue.COMPASSION: "caring for others and their well-being",
    CoreValue.LOYALTY: "standing by people and commitments",
    CoreValue.JUSTICE: "treating people fairly and upholding rights",
    CoreValue.RESPONSIBILITY: "being accountable for your actions",
    CoreValue.SECURITY: "physical, financial and emotional safety",
    CoreValue.EQUALITY: "fair treatment regardless of identity",
    CoreValue.TRADITION: "respecting customs and cultural continuity",
    CoreValue.OBEDIENCE: "following rules and authority",
    CoreValue.SUCCESS: "accomplishing goals and excelling",
    CoreValue.AMBITION: "striving to achieve more",
    CoreValue.DISCIPLINE: "controlling impulses to reach long-term goals",
    CoreValue.KNOWLEDGE: "seeking truth and understanding",
    CoreValue.OPEN_MINDEDNESS: "being receptive to different views",
    CoreValue.PEACE_OF_MIND: "inner calm and lack of anxiety",
    CoreValue.PLEASURE: "enjoying life's moments",
    CoreValue.CONNECTION: "feeling close to others",
    CoreValue.ADVENTURE: "seeking novelty and challenge",
    CoreValue.OPTIMISM: "expecting good things and seeing the bright side",
}

SYSTEM = (
    "You analyse news articles for a village simulation whose residents each care about these "
    "values to different degrees:\n"
    + "\n".join(f"- {value.value}: {meaning}" for value, meaning in MEANINGS.items())
    + f"\n\nFor the article you're given, score how closely it relates to each value, from 0 "
    f"(not at all) to {SCALE} (it's what the article is about). A score has no direction: an "
    "article that threatens or argues against a value relates to it as much as one that "
    "upholds it. Most articles relate closely to only a few values, so most scores should be 0 "
    f"or low. Also give up to {MAX_TAGS} short lowercase topic tags, and the article's overall "
    f"tone from 0 (very negative) to {SCALE} (very positive)."
)


class Analysis(BaseModel):
    tags: list[str] = Field(description=f"Up to {MAX_TAGS} tags of one to three words.")
    sentiment: float = Field(ge=0, le=SCALE, description="The article's overall tone.")


Reply = create_model(
    "Analysis",
    __base__=Analysis,
    **{value.value: (float, Field(ge=0, le=SCALE)) for value in CoreValue},
)


def article_prompt(item: NewsItem) -> str:
    source = f" ({item.source})" if item.source else ""
    return f"{item.title}{source}\n\n{item.summary}"


def clean_tags(tags: Iterable[str]) -> list[str]:
    cleaned = (" ".join(tag.lower().split()) for tag in tags)
    return list(dict.fromkeys(tag for tag in cleaned if 0 < len(tag) <= TAG_LENGTH))[:MAX_TAGS]


async def analyse(llm: LLMClient, item: NewsItem, config: NewsConfig = DEFAULT_CONFIG) -> NewsItem:
    """`item` with its relatedness to every core value, tags and sentiment from one LLM call.
    Raises `StructuredOutputError` if the reply doesn't fit, and `LLMError` if the call fails."""
    reply = await llm.structured(
        article_prompt(item),
        Reply,
        system=SYSTEM,
        model=config.model,
        purpose="news-analysis",
        priority=config.priority,
    )
    return NewsItem.model_validate(
        {
            **item.model_dump(),
            "values": {value: getattr(reply, value.value) / SCALE for value in CoreValue},
            "tags": clean_tags(reply.tags),
            "sentiment": reply.sentiment / SCALE * 2 - 1,
        }
    )


class NewsAnalyser:
    """Analyses each new article once, off the tick, for every NPC to share. Every
    `config.analyse_every` of sim time it looks for articles among the newest
    `config.candidates` that aren't analysed yet. One the provider can't analyse is remembered
    and left unanalysed. While calls keep failing it checks less and less often, and tries the
    articles that have failed least first."""

    def __init__(
        self,
        store: NewsStore,
        llm: Callable[[], LLMClient | None],
        *,
        config: NewsConfig = DEFAULT_CONFIG,
    ) -> None:
        self.store = store
        self.llm = llm
        self.config = config
        self.task: asyncio.Task[list[NewsItem]] | None = None
        self.warned = False
        self.failed: Counter[str] = Counter()
        self.failing = 0
        self.since = self.wait

    @property
    def wait(self) -> float:
        """Sim seconds between checks: `analyse_every`, doubled for each failure in a row."""
        every = self.config.analyse_every.total_seconds() * 2**self.failing
        return min(every, self.config.analyse_backoff.total_seconds())

    def tick(self, dt: float) -> None:
        self.since += dt
        if self.task is None and self.since >= self.wait:
            self.since = 0.0
            self.task = asyncio.create_task(self._run())

    async def _run(self) -> list[NewsItem]:
        try:
            return await self.analyse_pending()
        finally:
            self.task = None

    async def analyse_pending(self) -> list[NewsItem]:
        """Analyse the articles waiting, one at a time, and store each. Returns them. Those that
        have failed least go first, newest first among them. Stops at the first call that fails,
        to try again next time."""
        llm = self.llm()
        if llm is None:
            return []
        provider = llm.provider.name
        waiting = self.store.unanalysed(self.config.candidates, provider)
        analysed = []
        for item in sorted(waiting, key=lambda item: self.failed[item.id]):
            try:
                result = await analyse(llm, item, self.config)
            except StructuredOutputError:
                self.store.unanalysable(item.id, provider)
                level = logging.DEBUG if self.warned else logging.WARNING
                self.warned = True
                logger.log(level, "%s couldn't analyse %r, so left it out", provider, item.title)
                continue
            except Exception as error:
                self.failed[item.id] += 1
                self.failing += 1
                logger.warning(
                    "Couldn't analyse %r (%d failures in a row): %s",
                    item.title,
                    self.failing,
                    error,
                    exc_info=self.failing == 1,
                )
                break
            self.failing = 0
            self.store.update(result)
            analysed.append(result)
            logger.info("Analysed %r: %s", item.title, ", ".join(result.tags))
        return analysed

    async def stop(self) -> None:
        if self.task is not None:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
