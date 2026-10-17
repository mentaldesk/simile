from pathlib import Path

from pydantic import TypeAdapter

from simile.news.store import NewsStore
from simile.schema import NewsItem

BUNDLED = Path(__file__).resolve().parents[3] / "content" / "news" / "articles.json"


def bundled(path: Path = BUNDLED) -> list[NewsItem]:
    """The real articles that ship in `content/news/`, analysed already."""
    return TypeAdapter(list[NewsItem]).validate_json(path.read_bytes())


def fall_back(store: NewsStore, path: Path = BUNDLED) -> list[NewsItem]:
    """Store the bundled articles if no news is stored yet, and return those stored."""
    return [] if store.latest(1) else store.add(bundled(path))
