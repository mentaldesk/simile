from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from itertools import cycle

from simile.protocol import Entity, EntityKind, Position, SnapshotMessage
from simile.schema import Tile
from simile.world import Movement, Target, Walk

ERRANDS = (
    ("coffee_shop", "square"),
    ("square", "park"),
    ("terminal_1", "coffee_shop"),
)
REST = 4.0
STAGGER = 3.0


@dataclass
class Walker:
    entity: str
    stops: Iterator[Target]
    rest: float
    walk: Walk | None = None


class Errands:
    def __init__(self, movement: Movement, entities: Sequence[Entity]) -> None:
        self.movement = movement
        npcs = sorted((e for e in entities if e.kind == EntityKind.NPC), key=lambda e: e.id)
        self.walkers = []
        for i, npc in enumerate(npcs):
            home = movement.place(npc.id, Tile(x=round(npc.position.x), y=round(npc.position.y)))
            stops = cycle([*ERRANDS[i % len(ERRANDS)], home])
            self.walkers.append(Walker(npc.id, stops, rest=1 + STAGGER * i))

    def tick(self, dt: float) -> None:
        for walker in self.walkers:
            if walker.walk and not walker.walk.done:
                continue
            if walker.walk:
                walker.walk, walker.rest = None, REST
            walker.rest -= dt
            if walker.rest <= 0:
                walker.walk = self.movement.walk_to(walker.entity, next(walker.stops))

    def snapshot(self, base: SnapshotMessage) -> SnapshotMessage:
        positions = self.movement.entities()
        entities = [
            e.model_copy(update={"position": Position(x=p.x, y=p.y)})
            if (p := positions.get(e.id))
            else e
            for e in base.entities
        ]
        return base.model_copy(update={"entities": entities})
