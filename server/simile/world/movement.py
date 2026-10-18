import asyncio
import logging
import math
from collections import deque
from collections.abc import Callable, Generator, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Self

from starlette.applications import Starlette

from simile.schema import VILLAGE_MAP, Facing, Id, Location, MapTile, Pose, Tile
from simile.sim import EntityMoved, EventBus, world_of
from simile.world.map import WALKING_SPEED, TownMap, load_maps, with_every_location
from simile.world.map import Spot as MapSpot
from simile.world.paths import DOOR, Cell, Spot, door_ends, find_route, nearby, route_length
from simile.world.spots import (
    DEFAULT_SPOTS,
    Affinity,
    Purpose,
    SpotConfig,
    choose,
    indifferent,
    pose_on,
)

logger = logging.getLogger(__name__)

type Target = Tile | MapTile | str

EPSILON = 1e-9
FACINGS = tuple(Facing)


class Point(tuple[float, float]):
    """Where an entity is, in tiles, and on which map. It unpacks and measures as `(x, y)`."""

    map: str

    def __new__(cls, x: float, y: float, map: str = VILLAGE_MAP) -> Self:
        point = super().__new__(cls, (x, y))
        point.map = map
        return point

    @property
    def x(self) -> float:
        return self[0]

    @property
    def y(self) -> float:
        return self[1]

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Point) and other.map != self.map:
            return False
        return tuple.__eq__(self, other)

    def __ne__(self, other: object) -> bool:
        equal = self.__eq__(other)
        return equal if equal is NotImplemented else not equal

    __hash__ = tuple.__hash__

    def __getnewargs__(self) -> tuple[Any, ...]:
        return (*self, self.map)

    def __repr__(self) -> str:
        return f"Point({self[0]!r}, {self[1]!r}, {self.map!r})"


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
        self.destination: MapTile | None = None
        self.distance = 0.0
        self.outcome: Outcome | None = None
        self._callbacks: list[Callable[[Walk], None]] = []

    @property
    def done(self) -> bool:
        return self.outcome is not None

    def add_done_callback(self, callback: Callable[["Walk"], None]) -> None:
        if self.done:
            self._call(callback)
        else:
            self._callbacks.append(callback)

    def finish(self, outcome: Outcome) -> None:
        if self.done:
            return
        self.outcome = outcome
        callbacks, self._callbacks = self._callbacks, []
        for callback in callbacks:
            self._call(callback)

    def _call(self, callback: Callable[["Walk"], None]) -> None:
        try:
            callback(self)
        except Exception:
            logger.exception("%r failed to handle %r", callback, self)

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


def point_of(spot: Spot) -> Point:
    return Point(spot.x, spot.y, spot.map)


def map_tile(spot: Spot) -> MapTile:
    return MapTile(map=spot.map, x=spot.x, y=spot.y)


def facing_of(dx: float, dy: float) -> Facing:
    """The way a step goes, to the nearest of the eight."""
    return FACINGS[round(math.atan2(dy, dx) / (math.pi / 4)) % 8]


@dataclass
class Body:
    tile: Spot
    position: Point
    path: deque[Spot] = field(default_factory=deque)
    walk: Walk | None = None
    through: float = 0.0
    """How far through a door it's got, in tiles."""
    pose: Pose = Pose.STANDING
    facing: Facing = Facing.SOUTH_EAST

    @property
    def stepping(self) -> bool:
        return bool(self.path) and (
            (self.path[0].map != self.tile.map and self.through > 0)
            or self.position != (self.tile.x, self.tile.y)
        )

    @property
    def heading(self) -> Spot:
        return self.path[0] if self.stepping else self.tile

    @property
    def claim(self) -> Spot:
        return self.path[-1] if self.path else self.tile


def cell_of(point: tuple[float, float]) -> Cell:
    return math.floor(point[0] + 0.5), math.floor(point[1] + 0.5)


def spot_of(point: Point) -> Spot:
    return Spot(point.map, *cell_of(point))


def inside(location: Location, where: Cell | Spot | Point) -> bool:
    """Whether a tile, or a point's tile, is in the location's area. A plain `(x, y)` cell is
    taken to be on the location's map; a `Spot` or `Point` on another map is never inside."""
    if isinstance(where, Point):
        where = spot_of(where)
    if isinstance(where, Spot):
        if where.map != location.map:
            return False
        where = (where.x, where.y)
    area, (x, y) = location.area, where
    return area.x <= x < area.x + area.width and area.y <= y < area.y + area.height


class Movement:
    """Where every entity is, and their walks around the village and through its doors. Tick it
    on the sim loop."""

    def __init__(self, maps: TownMap | Mapping[str, TownMap], bus: EventBus) -> None:
        self.maps = {maps.id: maps} if isinstance(maps, TownMap) else dict(maps)
        self.home = VILLAGE_MAP if VILLAGE_MAP in self.maps else next(iter(self.maps))
        self.town = with_every_location(self.maps, self.home)
        self.doors = door_ends(self.maps)
        self.bus = bus
        self.affinity: Affinity = indifferent
        """How much one entity likes being near another, for choosing a spot."""
        self.spot_config: SpotConfig = DEFAULT_SPOTS
        self._bodies: dict[Id, Body] = {}
        self._purposes: dict[Id, Purpose] = {}
        self._spots: dict[Spot, MapSpot] = {
            Spot(spot.map, spot.x, spot.y): spot
            for town in self.maps.values()
            for spot in town.spots
        }
        self._spots_in: dict[str, list[MapSpot]] = {}

    def place(self, entity: Id, target: Target) -> MapTile:
        """Put an entity on the target, or the nearest free tile to it, ending any walk."""
        old = self._bodies.get(entity)
        spot = self._resolve(entity, target, old.heading if old else None)
        if spot is None:
            raise ValueError(f"{entity} can't stand on {target!r}")
        body = Body(spot, point_of(spot), facing=old.facing if old else Facing.SOUTH_EAST)
        self._rest(entity, body)
        self._replace(entity, body)
        self._publish(entity, body)
        return map_tile(spot)

    def intend(self, entity: Id, purpose: Purpose | None) -> None:
        """What they'll be at their next place for, which says which spots there suit them."""
        if purpose is None:
            self._purposes.pop(entity, None)
        else:
            self._purposes[entity] = purpose

    def posture(self, entity: Id) -> tuple[Pose, Facing]:
        body = self._bodies[entity]
        return body.pose, body.facing

    def on_spot(self, entity: Id) -> MapSpot | None:
        """The spot they're staying on, if they've stopped on one."""
        body = self._bodies[entity]
        return None if body.path else self._spots.get(body.tile)

    def track(self, entity: Id, position: Point) -> None:
        """Record where something the client moves, like the player, is. Publishes nothing."""
        self._replace(entity, Body(spot_of(position), position))

    def position(self, entity: Id) -> Point:
        return self._bodies[entity].position

    def entities(self) -> dict[Id, Point]:
        return {entity: body.position for entity, body in self._bodies.items()}

    def distance(self, a: Id, b: Id) -> float:
        here, there = self.position(a), self.position(b)
        return math.dist(here, there) if here.map == there.map else math.inf

    def walk_to(self, entity: Id, target: Target) -> Walk:
        """Walk to the target, or the nearest free tile to it, ending any walk already going."""
        body = self._bodies[entity]
        previous, walk = body.walk, Walk(entity, target)
        start = body.heading
        goal = self._resolve(entity, target, start)
        path = None if goal is None else find_route(self.maps, start, goal, self.doors)
        body.walk = walk
        body.path = deque(path or [start])
        if not body.stepping:
            body.path.popleft()
        if path is None:
            self._end(body, Outcome.UNREACHABLE)
        else:
            walk.destination = map_tile(path[-1])
            walk.distance = route_length([body.position, *body.path]) - body.through
            if not body.path:
                self._end(body, Outcome.ARRIVED)
        if not body.path:
            self._settle(entity, body)
        if previous:
            previous.finish(Outcome.SUPERSEDED)
        return walk

    def stop(self, entity: Id) -> None:
        """Cancel the entity's walk. It stops on the next tile."""
        body = self._bodies[entity]
        self._end(body, Outcome.CANCELLED)
        if not body.path:
            self._settle(entity, body)

    def tick(self, dt: float) -> None:
        for entity, body in tuple(self._bodies.items()):
            if body.path:
                self._advance(entity, body, WALKING_SPEED * dt)

    def _advance(self, entity: Id, body: Body, budget: float) -> None:
        while body.path:
            spot = body.path[0]
            if spot.map != body.tile.map:
                gap = DOOR - body.through
                if gap > budget + EPSILON:
                    body.through += budget
                    return
                body.through = 0.0
            else:
                gap = math.dist(body.position, (spot.x, spot.y))
                if gap > budget + EPSILON:
                    share = budget / gap
                    body.position = Point(
                        body.position.x + (spot.x - body.position.x) * share,
                        body.position.y + (spot.y - body.position.y) * share,
                        spot.map,
                    )
                    return
            budget -= gap
            if spot.map == body.tile.map:
                body.facing = facing_of(spot.x - body.tile.x, spot.y - body.tile.y)
            body.tile, body.position = spot, point_of(spot)
            body.path.popleft()
            if body.claim in self._claims(entity):
                self._reroute(entity, body)
            if body.path:
                body.pose = Pose.WALKING
            else:
                self._rest(entity, body)
            self._publish(entity, body)
            if not body.path:
                self._end(body, Outcome.ARRIVED)
                return

    def _reroute(self, entity: Id, body: Body) -> None:
        walk, tile = body.walk, body.tile
        target = walk.target if walk else MapTile(map=tile.map, x=tile.x, y=tile.y)
        goal = self._resolve(entity, target, tile)
        path = None if goal is None else find_route(self.maps, tile, goal, self.doors)
        if path:
            if walk:
                walk.distance += route_length(path) - route_length([tile, *body.path])
                walk.destination = map_tile(path[-1])
            body.path = deque(path[1:])

    def _replace(self, entity: Id, body: Body) -> None:
        old = self._bodies.get(entity)
        self._bodies[entity] = body
        if old:
            old.path.clear()
            self._end(old, Outcome.CANCELLED)

    def _end(self, body: Body, outcome: Outcome) -> None:
        body.path = deque([body.path[0]]) if body.stepping else deque()
        walk, body.walk = body.walk, None
        if walk:
            walk.finish(outcome)

    def _claims(self, entity: Id) -> set[Spot]:
        return {body.claim for other, body in self._bodies.items() if other != entity}

    def _resolve(self, entity: Id, target: Target, start: Spot | None) -> Spot | None:
        """The free tile nearest the target, in its location if there's room, nearest the start.
        A plain `Tile` is on the village."""
        claimed = self._claims(entity)
        location = None
        if isinstance(target, MapTile):
            origin = Spot(target.map, target.x, target.y)
        elif isinstance(target, Tile):
            origin = Spot(self.home, target.x, target.y)
        else:
            location = self.town.location(target)
            if (taken := self._take_spot(entity, location, start, claimed)) is not None:
                return taken
            if (
                start is not None
                and inside(location, start)
                and start not in claimed
                and start not in self._spots
            ):
                return start
            origin = Spot(location.map, location.entry.x, location.entry.y)
        near = start if start is not None and start.map == origin.map else origin
        best: tuple[tuple[bool, bool, int, float], Spot] | None = None
        for cell, depth in nearby(self.maps[origin.map], (origin.x, origin.y)):
            if best and not best[0][0] and not best[0][1] and depth > best[0][2]:
                break
            spot = Spot(origin.map, *cell)
            if spot not in claimed:
                outside = location is not None and not inside(location, spot)
                on_spot = location is not None and spot in self._spots
                rank = (outside, on_spot, depth, math.dist(cell, (near.x, near.y)))
                if best is None or rank < best[0]:
                    best = (rank, spot)
        return best[1] if best else None

    def _take_spot(
        self, entity: Id, location: Location, start: Spot | None, claimed: set[Spot]
    ) -> Spot | None:
        """A free spot in the location that suits what they're there for, or the one they're on."""
        purpose = self._purposes.get(entity)
        kinds = self.spot_config.fits.get(purpose) if purpose else None
        if not kinds:
            return None
        here = self._spots.get(start) if start is not None else None
        if here and here.kind in kinds and inside(location, start) and start not in claimed:
            return start
        if location.id not in self._spots_in:
            spots = self.maps[location.map].spots
            self._spots_in[location.id] = [
                spot for spot in spots if inside(location, Spot(spot.map, spot.x, spot.y))
            ]
        free = [s for s in self._spots_in[location.id] if Spot(s.map, s.x, s.y) not in claimed]
        others = {
            other: self._seat(body.claim)
            for other, body in self._bodies.items()
            if other != entity and body.claim.map == location.map
        }
        entry = (location.entry.x, location.entry.y)
        near = (start.x, start.y) if start is not None and start.map == location.map else entry
        spot = choose(entity, free, kinds, others, near, self.affinity, self.spot_config)
        return None if spot is None else Spot(spot.map, spot.x, spot.y)

    def _seat(self, tile: Spot) -> tuple[float, float]:
        spot = self._spots.get(tile)
        return spot.seat if spot else (tile.x, tile.y)

    def _rest(self, entity: Id, body: Body) -> None:
        """Stopped: the pose and facing of the spot they're on, or standing as they were."""
        spot = self._spots.get(body.tile)
        if spot is None:
            body.pose = Pose.STANDING
        else:
            body.pose, body.facing = pose_on(spot, self._purposes.get(entity)), spot.facing

    def _settle(self, entity: Id, body: Body) -> None:
        before = body.pose, body.facing
        self._rest(entity, body)
        if (body.pose, body.facing) != before:
            self._publish(entity, body)

    def _publish(self, entity: Id, body: Body) -> None:
        tile = body.tile
        moved = EntityMoved(entity, float(tile.x), float(tile.y), tile.map, body.pose, body.facing)
        self.bus.publish(moved)


def movement_of(app: Starlette) -> Movement:
    if not hasattr(app.state, "movement"):
        app.state.movement = Movement(load_maps(), world_of(app).bus)
    return app.state.movement
