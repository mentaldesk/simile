import asyncio
import math
from collections import deque
from collections.abc import Callable, Generator
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, NamedTuple

from starlette.applications import Starlette

from simile.schema import Id, Location, Tile
from simile.sim import EntityMoved, EventBus, world_of
from simile.world.map import WALKING_SPEED, TownMap, load_map
from simile.world.paths import Cell, find_path, nearby, path_length

type Target = Tile | str

EPSILON = 1e-9


class Point(NamedTuple):
    x: float
    y: float


class Outcome(StrEnum):
    ARRIVED = "arrived"
    UNREACHABLE = "unreachable"
    CANCELLED = "cancelled"
    SUPERSEDED = "superseded"


class Walk:
    """One walk_to. Await it, poll `outcome` or add a callback to find out how it ended."""

    def __init__(self, entity: Id, target: Target) -> None:
        self.entity = entity
        self.target = target
        self.destination: Tile | None = None
        self.distance = 0.0
        self.outcome: Outcome | None = None
        self._callbacks: list[Callable[[Walk], None]] = []

    @property
    def done(self) -> bool:
        return self.outcome is not None

    def add_done_callback(self, callback: Callable[["Walk"], None]) -> None:
        if self.done:
            callback(self)
        else:
            self._callbacks.append(callback)

    def finish(self, outcome: Outcome) -> None:
        if self.done:
            return
        self.outcome = outcome
        callbacks, self._callbacks = self._callbacks, []
        for callback in callbacks:
            callback(self)

    def __await__(self) -> Generator[Any, None, Outcome]:
        if self.outcome is None:
            future: asyncio.Future[Outcome] = asyncio.get_running_loop().create_future()

            def resolve(walk: Walk) -> None:
                if not future.done() and walk.outcome is not None:
                    future.set_result(walk.outcome)

            self.add_done_callback(resolve)
            return (yield from future.__await__())
        return self.outcome

    def __repr__(self) -> str:
        return f"Walk({self.entity!r} to {self.target!r}, {self.outcome or 'walking'})"


@dataclass
class Body:
    tile: Cell
    position: Point
    path: deque[Cell] = field(default_factory=deque)
    walk: Walk | None = None

    @property
    def stepping(self) -> bool:
        return bool(self.path) and self.position != self.tile

    @property
    def heading(self) -> Cell:
        return self.path[0] if self.stepping else self.tile

    @property
    def claim(self) -> Cell:
        return self.path[-1] if self.path else self.tile


def cell_of(point: Point) -> Cell:
    return math.floor(point.x + 0.5), math.floor(point.y + 0.5)


def inside(location: Location, cell: Cell) -> bool:
    area = location.area
    return area.x <= cell[0] < area.x + area.width and area.y <= cell[1] < area.y + area.height


class Movement:
    """Where every entity is, and their walks around the town. Tick it on the sim loop."""

    def __init__(self, town: TownMap, bus: EventBus) -> None:
        self.town = town
        self.bus = bus
        self._bodies: dict[Id, Body] = {}

    def place(self, entity: Id, target: Target) -> Tile:
        """Put an entity on the target, or the nearest free tile to it, ending any walk."""
        body = self._bodies.get(entity)
        cell = self._resolve(entity, target, body.heading if body else None)
        if cell is None:
            raise ValueError(f"{entity} can't stand on {target!r}")
        self._replace(entity, Body(cell, Point(*cell)))
        self._publish(entity, cell)
        return Tile(x=cell[0], y=cell[1])

    def track(self, entity: Id, position: Point) -> None:
        """Record where something the client moves, like the player, is. Publishes nothing."""
        self._replace(entity, Body(cell_of(position), position))

    def position(self, entity: Id) -> Point:
        return self._bodies[entity].position

    def entities(self) -> dict[Id, Point]:
        return {entity: body.position for entity, body in self._bodies.items()}

    def distance(self, a: Id, b: Id) -> float:
        return math.dist(self.position(a), self.position(b))

    def walk_to(self, entity: Id, target: Target) -> Walk:
        """Walk to the target, or the nearest free tile to it, ending any walk already going."""
        body = self._bodies[entity]
        previous, walk = body.walk, Walk(entity, target)
        start = body.heading
        cell = self._resolve(entity, target, start)
        path = None if cell is None else find_path(self.town, start, cell)
        body.walk = walk
        body.path = deque(path or [start])
        if not body.stepping:
            body.path.popleft()
        if path is None:
            self._end(body, Outcome.UNREACHABLE)
        else:
            walk.destination = Tile(x=path[-1][0], y=path[-1][1])
            walk.distance = path_length([body.position, *body.path])
            if not body.path:
                self._end(body, Outcome.ARRIVED)
        if previous:
            previous.finish(Outcome.SUPERSEDED)
        return walk

    def stop(self, entity: Id) -> None:
        """Cancel the entity's walk. It stops on the next tile."""
        self._end(self._bodies[entity], Outcome.CANCELLED)

    def tick(self, dt: float) -> None:
        for entity, body in tuple(self._bodies.items()):
            if body.path:
                self._advance(entity, body, WALKING_SPEED * dt)

    def _advance(self, entity: Id, body: Body, budget: float) -> None:
        while body.path:
            x, y = body.path[0]
            gap = math.dist(body.position, (x, y))
            if gap > budget + EPSILON:
                share = budget / gap
                body.position = Point(
                    body.position.x + (x - body.position.x) * share,
                    body.position.y + (y - body.position.y) * share,
                )
                return
            budget -= gap
            body.tile, body.position = (x, y), Point(x, y)
            body.path.popleft()
            if body.walk and body.claim in self._claims(entity):
                self._reroute(entity, body, body.walk)
            self._publish(entity, body.tile)
            if not body.path:
                self._end(body, Outcome.ARRIVED)
                return

    def _reroute(self, entity: Id, body: Body, walk: Walk) -> None:
        cell = self._resolve(entity, walk.target, body.tile)
        path = None if cell is None else find_path(self.town, body.tile, cell)
        if path:
            walk.distance += path_length(path) - path_length([body.tile, *body.path])
            walk.destination = Tile(x=path[-1][0], y=path[-1][1])
            body.path = deque(path[1:])

    def _replace(self, entity: Id, body: Body) -> None:
        old = self._bodies.get(entity)
        self._bodies[entity] = body
        if old and old.walk:
            old.walk.finish(Outcome.CANCELLED)

    def _end(self, body: Body, outcome: Outcome) -> None:
        body.path = deque([body.path[0]]) if body.stepping else deque()
        walk, body.walk = body.walk, None
        if walk:
            walk.finish(outcome)

    def _claims(self, entity: Id) -> set[Cell]:
        return {body.claim for other, body in self._bodies.items() if other != entity}

    def _resolve(self, entity: Id, target: Target, start: Cell | None) -> Cell | None:
        """The free tile nearest the target, in its location if there's room, nearest the start."""
        claimed = self._claims(entity)
        if isinstance(target, Tile):
            origin, location = (target.x, target.y), None
        else:
            location = self.town.location(target)
            if start is not None and inside(location, start) and start not in claimed:
                return start
            origin = (location.entry.x, location.entry.y)
        best: tuple[tuple[bool, int, float], Cell] | None = None
        for cell, depth in nearby(self.town, origin):
            if best and not best[0][0] and depth > best[0][1]:
                break
            if cell not in claimed:
                outside = location is not None and not inside(location, cell)
                rank = (outside, depth, math.dist(cell, start or origin))
                if best is None or rank < best[0]:
                    best = (rank, cell)
        return best[1] if best else None

    def _publish(self, entity: Id, cell: Cell) -> None:
        self.bus.publish(EntityMoved(entity, float(cell[0]), float(cell[1])))


def movement_of(app: Starlette) -> Movement:
    if not hasattr(app.state, "movement"):
        app.state.movement = Movement(load_map(), world_of(app).bus)
    return app.state.movement
