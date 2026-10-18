import asyncio
import logging
import re
from collections.abc import Callable
from urllib.error import HTTPError, URLError

from simile.news.config import DEFAULT_CONFIG, NewsConfig
from simile.news.feed import DEADLINE, FeedRefused, get
from simile.news.store import NewsStore
from simile.schema import NewsItem

logger = logging.getLogger(__name__)

GIVE_UP = DEADLINE + 5
PAGE_TYPES = ("text/html", "application/xhtml+xml")
PAYWALLED = re.compile(
    rb"isAccessibleForFree[\"']?\s*(?::\s*|[^>]*?content\s*=\s*)[\"']?false\b", re.IGNORECASE
)

type Page = Callable[[str, str | None], str]


class NoText(Exception):
    """Why there's no article text to summarise, in words for the log and the CLI."""


def word_count(text: str) -> int:
    return len(text.split())


def enough(text: str, config: NewsConfig = DEFAULT_CONFIG) -> bool:
    return word_count(text) >= config.min_article_words


def capped(text: str, limit: int) -> str:
    """`text`'s first `limit` words, keeping its lines."""
    kept, count = [], 0
    for line in text.splitlines():
        words = line.split()
        kept.append(" ".join(words[: limit - count]))
        count += len(words)
        if count >= limit:
            break
    return "\n".join(line for line in kept if line)


def page(url: str, origin: str | None = None) -> str:
    """The main text of the article at `url`, a paragraph a line, from one request with `get`.
    `origin` is the feed that links to it. Blocks."""
    got = get(url, {"Accept": "text/html,application/xhtml+xml"}, origin=origin, what="an article")
    kind = got.headers.get_content_type()
    if kind not in PAGE_TYPES:
        raise NoText(f"The page is {kind}, not HTML")
    return main_text(got.body, url)


def main_text(html: bytes, url: str | None = None) -> str:
    """The article's text on a page, a paragraph a line. Refuses a page that says it isn't free to
    read, though it serves the whole article."""
    if PAYWALLED.search(html):
        raise NoText("Paywalled: the page says it isn't free to read")
    import trafilatura

    text = trafilatura.extract(html, url=url, include_comments=False, include_tables=False)
    if not text:
        raise NoText("No article text found on the page")
    return text


def why(error: Exception) -> str:
    if isinstance(error, HTTPError):
        return f"The site answered {error.code} {error.reason}"
    if isinstance(error, URLError):
        return f"Couldn't reach it: {error.reason}"
    return str(error) or type(error).__name__


async def read_page(
    url: str, origin: str | None = None, *, page: Page = page, give_up: float = GIVE_UP
) -> str:
    """`page` in a thread, given up on after `give_up` seconds even if the thread carries on."""
    try:
        async with asyncio.timeout(give_up):
            return await asyncio.to_thread(page, url, origin)
    except TimeoutError as error:
        raise TimeoutError(str(error) or f"It took over {give_up:g} seconds") from None


async def article_text(
    store: NewsStore,
    item: NewsItem,
    page: Page | None,
    config: NewsConfig = DEFAULT_CONFIG,
    *,
    give_up: float = GIVE_UP,
) -> str | None:
    """The text of `item`'s article to summarise: what its feed carried, or else its page's, from
    one request with `page`, which is held until the summary is written. None, with the reason
    recorded, if neither has `config.min_article_words`. Once a reason is recorded the page isn't
    asked for again. Without `page`, only what the feed carried."""
    if store.why_no_text(item.id) is not None:
        return None
    text = store.text(item.id)
    if text is not None and enough(text, config):
        return text
    if page is None:
        return None
    try:
        text = await read_page(item.url, item.source_url or None, page=page, give_up=give_up)
    except (NoText, FeedRefused, OSError) as error:
        return no_text(store, item, why(error))
    except Exception as error:
        logger.warning("Couldn't read the page of %r", item.title, exc_info=True)
        return no_text(store, item, why(error))
    if not enough(text, config):
        return no_text(store, item, f"Only {word_count(text)} words: a teaser or a paywall")
    text = capped(text, config.article_words)
    store.keep_text(item.id, text)
    return text


def no_text(store: NewsStore, item: NewsItem, reason: str) -> None:
    store.no_text(item.id, reason)
    logger.info("%r keeps its feed's summary. %s", item.title, reason)
