import heapq
import math
from collections.abc import Callable, Iterator, Sequence

from simile.protocol import Entity, EntityKind, Position, SnapshotMessage
from simile.sim import EntityMoved
from simile.world.map import WALKING_SPEED, TownMap

type Cell = tuple[int, int]

ERRANDS = (
    ("coffee_shop", "square"),
    ("square", "park"),
    ("terminal_1", "coffee_shop"),
)
PAUSE = 4.0
STAGGER = 3.0
STEPS = [(dx, dy) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dx or dy]


def neighbours(town: TownMap, cell: Cell) -> Iterator[Cell]:
    x, y = cell
    for dx, dy in STEPS:
        if not town.walkable(x + dx, y + dy):
            continue
        if dx and dy and not (town.walkable(x + dx, y) and town.walkable(x, y + dy)):
            continue
        yield x + dx, y + dy


def route(town: TownMap, start: Cell, goal: Cell) -> list[Cell]:
    """The shortest walk from start to goal, diagonals included, without start itself."""
    came_from: dict[Cell, Cell] = {}
    best = {start: 0.0}
    frontier = [(0.0, start)]
    while frontier:
        cost, cell = heapq.heappop(frontier)
        if cell == goal:
            break
        if cost > best[cell]:
            continue
        for step in neighbours(town, cell):
            step_cost = cost + math.dist(cell, step)
            if step_cost < best.get(step, math.inf):
                best[step], came_from[step] = step_cost, cell
                heapq.heappush(frontier, (step_cost, step))
    else:
        raise ValueError(f"no way from {start} to {goal}")
    path = [goal]
    while path[-1] != start:
        path.append(came_from[path[-1]])
    return path[-2::-1]


class Walker:
    """Walks one entity round its stops forever, publishing each tile it reaches, as W2 does."""

    def __init__(
        self,
        entity: str,
        stops: Sequence[Cell],
        town: TownMap,
        publish: Callable[[EntityMoved], None],
        wait: float = 0.0,
    ) -> None:
        self.entity = entity
        self.stops = list(stops)
        self.town = town
        self.publish = publish
        self.wait = wait
        self.at = self.stops[0]
        self.stop = 0
        self.path: list[Cell] = []
        self.progress = 0.0

    def tick(self, dt: float) -> None:
        while dt > 0:
            if self.wait > 0:
                waited = min(self.wait, dt)
                self.wait -= waited
                dt -= waited
            elif not self.path:
                self.stop = (self.stop + 1) % len(self.stops)
                self.path = route(self.town, self.at, self.stops[self.stop])
                self.wait = 0 if self.path else PAUSE
            else:
                dt = self._walk(dt)

    def _walk(self, dt: float) -> float:
        left = math.dist(self.at, self.path[0]) - self.progress
        if left > WALKING_SPEED * dt:
            self.progress += WALKING_SPEED * dt
            return 0
        self.at = self.path.pop(0)
        self.progress = 0
        self.publish(EntityMoved(self.entity, float(self.at[0]), float(self.at[1])))
        if not self.path:
            self.wait = PAUSE
        return dt - left / WALKING_SPEED


class Demo:
    """Sends every NPC from its doorstep on errands and back home, in a loop."""

    def __init__(
        self, town: TownMap, entities: Sequence[Entity], publish: Callable[[EntityMoved], None]
    ) -> None:
        npcs = sorted((e for e in entities if e.kind == EntityKind.NPC), key=lambda e: e.id)
        self.walkers = {
            npc.id: Walker(
                npc.id,
                [
                    cell_of(npc.position),
                    *(entry(town, place) for place in ERRANDS[i % len(ERRANDS)]),
                ],
                town,
                publish,
                wait=1 + STAGGER * i,
            )
            for i, npc in enumerate(npcs)
        }

    def tick(self, dt: float) -> None:
        for walker in self.walkers.values():
            walker.tick(dt)

    def snapshot(self, base: SnapshotMessage) -> SnapshotMessage:
        entities = [
            e.model_copy(update={"position": Position(x=w.at[0], y=w.at[1])})
            if (w := self.walkers.get(e.id))
            else e
            for e in base.entities
        ]
        return base.model_copy(update={"entities": entities})


def cell_of(position: Position) -> Cell:
    return round(position.x), round(position.y)


def entry(town: TownMap, location_id: str) -> Cell:
    tile = town.location(location_id).entry
    return tile.x, tile.y
