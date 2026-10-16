"""Build the demo village in a fresh database: the article, who has read it, everyone's
acquaintance with everyone else, and where each resident is at the start.

    cd server && uv run python ../demo/prepare.py --db data/demo.db
"""

import argparse
import json
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from simile.memory import MemoryStore
from simile.news.config import DEFAULT_CONFIG
from simile.news.reactions import Reaction, remember
from simile.news.store import NewsStore
from simile.npc import load_npcs
from simile.persistence.state import SavedWorld
from simile.persistence.store import WorldStore
from simile.schema import Memory, NewsItem, Npc, Relationship
from simile.social import meet
from simile.world.map import load_map

HERE = Path(__file__).resolve().parent


def prepare(db: Path) -> None:
    """Replace whatever is at `db` with the demo village."""
    scenario = json.loads((HERE / "scenario.json").read_text())
    article = NewsItem.model_validate_json((HERE / "article.json").read_text())
    world = SavedWorld.model_validate({"now": scenario["now"], "npcs": scenario["residents"]})
    npcs = {npc.id: npc for npc in load_npcs()}
    validate(world, npcs.keys(), scenario["read"].keys())

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
        news.add([article])
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the demo village in a fresh database.")
    parser.add_argument("--db", type=Path, required=True, help="The database to replace.")
    args = parser.parse_args()
    prepare(args.db)
    print(f"Prepared the demo village in {args.db}")


if __name__ == "__main__":
    main()
