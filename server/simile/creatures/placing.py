"""The creatures the maps place, from each one's `creatures` layer: README.md's *Placing them*."""

import json
from pathlib import Path
from typing import Any

from simile.creatures.engine import Creature, Creatures
from simile.creatures.kinds import KINDS
from simile.schema import CreatureKind, MapTile, TileArea
from simile.street.plan import CREATURES_LAYER, Spawn
from simile.world.map import LEVELS, MAP_DIR


def spawns(directory: Path = MAP_DIR, level: int = 0) -> list[tuple[str, Spawn]]:
    """Every creature on the streets and `level`'s maps, which are all that have any, by map id."""
    paths = [
        *sorted(directory.glob("*.tmj")),
        *sorted((directory / LEVELS / str(level)).glob("*.tmj")),
    ]
    found = []
    for path in paths:
        data = json.loads(path.read_text())
        size = data["tilewidth"]
        for layer in data["layers"]:
            if layer["name"] == CREATURES_LAYER:
                found += [(path.stem, _spawn(each, size)) for each in layer["objects"]]
    return found


def populate(creatures: Creatures, placed: list[tuple[str, Spawn]]) -> list[Creature]:
    """Spawns each on a map the creatures have."""
    made = []
    for map_id, spawn in placed:
        if map_id not in creatures.maps:
            continue
        placing = KINDS[spawn.kind]
        at = MapTile(map=map_id, x=spawn.x, y=spawn.y)
        made.append(
            creatures.spawn(placing.kind, at, id=spawn.id, area=spawn.area, respawn=placing.respawn)
        )
    return made


def _spawn(data: dict[str, Any], size: int) -> Spawn:
    props = {prop["name"]: prop["value"] for prop in data.get("properties", [])}
    area = None
    if "area" in props:
        x, y, width, height = map(int, props["area"].split(","))
        area = TileArea(x=x, y=y, width=width, height=height)
    x, y = data["x"] // size, data["y"] // size
    return Spawn(data["name"], CreatureKind(data["type"]), x, y, area)
