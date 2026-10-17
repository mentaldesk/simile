"""Build the demo village in a fresh database: the article, the rest of the news, who has read
the article, everyone's acquaintance with everyone else, and where each resident is at the start.

    cd server && uv run python ../demo/prepare.py --db data/demo.db
"""

import argparse
import json
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from simile.memory import MemoryStore
from simile.news.bundled import BUNDLED, bundled
from simile.news.config import DEFAULT_CONFIG
from simile.news.interest import interest
from simile.news.reactions import Reaction, remember
from simile.news.store import NewsStore
from simile.npc import load_npcs
from simile.persistence.state import SavedWorld
from simile.persistence.store import WorldStore
from simile.schema import Memory, NewsItem, Npc, Relationship
from simile.social import meet
from simile.world.map import load_map

HERE = Path(__file__).resolve().parent
ARTICLE = (
    "https://www.scientificamerican.com/article/"
    "what-would-it-take-to-terraform-mars-erika-debenedictis-has-ideas/"
)


def prepare(db: Path) -> None:
    """Replace whatever is at `db` with the demo village."""
    scenario = json.loads((HERE / "scenario.json").read_text())
    news = bundled()
    article = next(item for item in news if item.id == ARTICLE)
    others = [item for item in news if item.id != ARTICLE]
    world = SavedWorld.model_validate({"now": scenario["now"], "npcs": scenario["residents"]})
    npcs = {npc.id: npc for npc in load_npcs()}
    validate(world, npcs.keys(), scenario["read"].keys())
    validate_news(article, others, [npc for npc in npcs.values() if npc.id not in scenario["read"]])

    memories = [news_memory(npcs[npc], article, read) for npc, read in scenario["read"].items()]
    relationships = [
        Relationship.model_validate(
            meet(npcs[owner], about).model_dump() | {"familiarity": scenario["familiarity"]}
        )
        for owner in npcs
        for about in npcs
        if owner != about
    ]

    for suffix in ("", "-journal", "-wal", "-shm"):
        Path(f"{db}{suffix}").unlink(missing_ok=True)
    with NewsStore(db) as news:
        news.add([article, *others])
    with MemoryStore(db) as memory, WorldStore(memory) as store:
        memory.add(*relationships, *memories)
        store.save(world)


def news_memory(npc: Npc, article: NewsItem, read: dict) -> Memory:
    reaction = Reaction.model_validate({key: read[key] for key in Reaction.model_fields})
    return remember(npc, article, reaction, datetime.fromisoformat(read["at"]), DEFAULT_CONFIG)


def validate(world: SavedWorld, npcs: Iterable[str], readers: Iterable[str]) -> None:
    town = load_map()
    if missing := sorted(set(npcs) - set(world.npcs)):
        raise SystemExit(f"scenario.json has no place for {', '.join(missing)}")
    if unknown := sorted((set(world.npcs) | set(readers)) - set(npcs)):
        raise SystemExit(f"scenario.json names residents not in content/npcs: {unknown}")
    tiles = {}
    for npc, saved in world.npcs.items():
        tile = (saved.position.x, saved.position.y)
        if not town.walkable(*tile):
            raise SystemExit(f"{npc} starts on {tile}, which isn't walkable")
        if tile in tiles:
            raise SystemExit(f"{npc} and {tiles[tile]} both start on {tile}")
        tiles[tile] = npc


def validate_news(article: NewsItem, others: list[NewsItem], unread: Iterable[Npc]) -> None:
    """Every article is listed at the terminals and needs no analysis call, and whoever hasn't
    read the article will read it before any of the others."""
    if (total := len(others) + 1) > DEFAULT_CONFIG.articles:
        raise SystemExit(f"A terminal lists {DEFAULT_CONFIG.articles} articles, not {total}")
    if unanalysed := [item.title for item in others if not item.analysed]:
        raise SystemExit(f"{BUNDLED} has articles with no analysis: {unanalysed}")
    for npc in unread:
        rather = [item.title for item in others if interest(npc, item) >= interest(npc, article)]
        if rather:
            raise SystemExit(f"{npc.id} would read {rather} before {article.title!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the demo village in a fresh database.")
    parser.add_argument("--db", type=Path, required=True, help="The database to replace.")
    args = parser.parse_args()
    prepare(args.db)
    print(f"Prepared the demo village in {args.db}")


if __name__ == "__main__":
    main()
