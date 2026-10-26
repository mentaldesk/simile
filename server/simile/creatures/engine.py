"""The creatures in the sim: README.md."""

import logging
import math
from collections import deque
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import NamedTuple

from starlette.applications import Starlette

from simile.creatures.grid import Cell, Edge, Grid, sees
from simile.creatures.kind import Kind
from simile.creatures.ways import Aim, Senses
from simile.player.kick import Hit, Kick
from simile.protocol import Creature as Shown
from simile.protocol import CreatureGoneMessage, CreatureMovedMessage, Position, ServerMessage
from simile.schema import CreatureState, MapTile, Player, SideFacing, TileArea
from simile.sim import Clock
from simile.world.map import TownMap
from simile.world.movement import Point

logger = logging.getLogger(__name__)

THINK = 0.25
"""Sim seconds between a creature's choices of where to go."""
SEND = 0.2
"""Sim seconds between `creature_moved`s while one moves; a change of state goes at once."""
FALL_SPEED = 8.0
KNOCK_SPEED = 6.0
KICK_SLACK = 0.3
"""Tiles either side of a kick's reach that still hit, for the client's lag."""
KICK_HEIGHT = 1.2
"""Tiles above the player's feet a kick reaches: a bat lower than that is in it."""
JUMPS_OVER = 0.8
"""Tiles above a walking creature the player's feet are out of its reach."""


class Leg(NamedTuple):
    """A stretch of a path; a new path can start only where a leg `ends`."""

    to: Cell
    falls: bool = False
    ends: bool = True


def legs(edges: Iterable[Edge]) -> Iterable[Leg]:
    for edge in edges:
        if edge.via is not None:
            yield Leg(edge.via, ends=False)
            yield Leg(edge.to, falls=True)
        else:
            yield Leg(edge.to)


@dataclass
class Creature:
    """`y` is the row a walking kind stands on, or a flying kind is in."""

    id: str
    kind: Kind
    grid: Grid
    home: Cell
    x: float
    y: float
    route: tuple[Cell, ...] = ()
    roost: Cell | None = None
    respawn: float | None = None
    facing: SideFacing = SideFacing.EAST
    state: CreatureState = CreatureState.IDLE
    health: float = 1.0
    path: deque[Leg] = field(default_factory=deque)
    goal: Cell | None = None
    aim: Aim | None = None
    leg: int = 0
    paused: float | None = None
    seen: tuple[tuple[float, float], float] | None = None
    thinks: float = 0.0
    strikes: float | None = None
    rested: float = 0.0
    hurt: float = 0.0
    down: float | None = None
    """When it went down, while it's gone."""
    sent: Shown | None = None
    sent_at: float = -math.inf

    @property
    def map(self) -> str:
        return self.grid.town.id

    @property
    def position(self) -> tuple[float, float]:
        return (self.x, self.y)

    @property
    def cell(self) -> Cell:
        return (math.floor(self.x + 0.5), math.floor(self.y + 0.5))

    @property
    def resting(self) -> bool:
        return not self.path

    def finishing(self) -> list[Leg]:
        """What's left of the move it's in the middle of."""
        kept = []
        for leg in self.path:
            kept.append(leg)
            if leg.ends:
                break
        return kept

    def sees(self, target: tuple[float, float], sight: float) -> bool:
        eye = (self.x, self.y - 0.5)
        return math.dist(eye, target) <= sight and sees(self.grid.town, eye, target)

    def shown(self) -> Shown:
        """As the protocol has it: a bat's position is its middle, or the ceiling it hangs from."""
        y = self.y
        if self.kind.flies:
            y -= 1.0 if self.state is CreatureState.ROOSTING else 0.5
        position = Position(x=round(self.x, 2), y=round(y, 2), map=self.map)
        return Shown(
            id=self.id, kind=self.kind.id, position=position, facing=self.facing, state=self.state
        )


@dataclass(frozen=True)
class Sight:
    """The player as the creatures sense them: there only while a client is in the game."""

    player: Player | None = None
    at: Point | None = None


class Creatures:
    """Every creature, ticked on the sim loop."""

    def __init__(
        self,
        maps: Mapping[str, TownMap],
        *,
        clock: Clock | None = None,
        sense: Callable[[], Sight] = Sight,
        harm: Callable[[Kind], None] = lambda kind: None,
        send: Callable[[ServerMessage], None] = lambda message: None,
        salvage: Callable[[TownMap], Mapping[Cell, str]] = lambda town: {},
        collect: Callable[[str], None] = lambda pickup: None,
    ) -> None:
        self.maps = maps
        self.clock = clock
        self.sense = sense
        self.harm = harm
        self.send = send
        self.salvage = salvage
        """What lies at a map's salvage pickups now, by cell: README.md's *Collecting*."""
        self.collect = collect
        self.now = 0.0
        self.all: dict[str, Creature] = {}
        self.numbers: dict[str, int] = {}

    def spawn(
        self,
        kind: Kind,
        at: MapTile,
        *,
        id: str | None = None,
        area: TileArea | None = None,
        route: Iterable[tuple[int, int]] | None = None,
        span: int = 5,
        roost: tuple[int, int] | None = None,
        respawn: float | None = None,
    ) -> Creature:
        """README.md's *Placing them*."""
        town = self.maps[at.map]
        if town.kind is None:
            raise ValueError(f"creatures are only on side-view maps, not {at.map}")
        grid = Grid(town, kind, area)
        home = grid.ground(at.x, at.y) if not kind.flies else (at.x, at.y)
        if home is None or not grid.allowed(home):
            raise ValueError(f"a {kind.id} can't be at {at.map} {at.x},{at.y}")
        if id is None:
            id = f"{kind.id}_{self._number(kind)}"
        creature = Creature(
            id=id,
            kind=kind,
            grid=grid,
            home=home,
            x=home[0],
            y=home[1],
            route=tuple(route) if route is not None else _route(grid, home, span),
            roost=roost if roost is not None else _roost(grid, home),
            respawn=respawn,
            health=kind.health,
        )
        if creature.id in self.all:
            raise ValueError(f"there's already a creature {creature.id}")
        self.all[creature.id] = creature
        self._send(creature)
        return creature

    def _number(self, kind: Kind) -> int:
        number = self.numbers.get(kind.id, 0) + 1
        while f"{kind.id}_{number}" in self.all:
            number += 1
        self.numbers[kind.id] = number
        return number

    def remove(self, creature_id: str) -> None:
        if self.all.pop(creature_id, None) is not None:
            self.send(CreatureGoneMessage(creature_id=creature_id))

    def shown(self) -> list[Shown]:
        """Every creature in the world, for the snapshot."""
        return [creature.shown() for creature in self.all.values() if creature.down is None]

    def tick(self, dt: float) -> None:
        self.now += dt
        sight = self.sense()
        senses: dict[str, Senses] = {}
        for creature in self.all.values():
            if creature.down is not None:
                self._come_back(creature)
                continue
            town = creature.grid.town
            if town.id not in senses:
                at = sight.at if sight.at is not None and sight.at.map == town.id else None
                player = sight.player if at is not None else None
                salvage = self.salvage(town) if at is not None else {}
                senses[town.id] = Senses(self.now, town, player, at, salvage)
            self._step(creature, senses[town.id], dt)

    def kickable(self, kick: Kick) -> Hit | None:
        """The nearest creature the player's kick would hit, for `kickables_of(app)`."""
        ahead = 1 if kick.facing is SideFacing.EAST else -1
        hits = []
        for creature in self.all.values():
            if creature.down is not None or creature.map != kick.at.map:
                continue
            along = (creature.x - kick.at.x) * ahead
            low = creature.y - 0.5 if creature.kind.flies else creature.y
            if creature.state is CreatureState.ROOSTING or not (
                -KICK_SLACK <= along <= kick.reach + KICK_SLACK
                and kick.at.y - KICK_HEIGHT <= low <= kick.at.y + 0.5
            ):
                continue
            hits.append((abs(along), creature))
        if not hits:
            return None
        distance, creature = min(hits, key=lambda hit: hit[0])
        return Hit(distance, lambda: self.kicked(creature, kick))

    def kicked(self, creature: Creature, kick: Kick) -> None:
        damage = kick.strength - creature.kind.toughness
        if damage <= 0 or creature.down is not None:
            return
        creature.health -= damage
        if creature.health <= 1e-9:
            self._go_down(creature)
            return
        away = 1 if kick.facing is SideFacing.EAST else -1
        kept = creature.finishing()
        start = kept[-1].to if kept else creature.cell
        cells = creature.grid.run(start, away, round(creature.kind.knock * kick.strength))
        creature.path = deque([*kept, *(Leg(cell) for cell in cells)])
        creature.goal = creature.aim = creature.strikes = None
        creature.hurt = self.now + creature.kind.stagger
        creature.facing = SideFacing.WEST if away > 0 else SideFacing.EAST
        creature.state = CreatureState.HURT
        self._log("A %s is kicked", creature)
        self._send(creature)

    def _step(self, creature: Creature, senses: Senses, dt: float) -> None:
        kind = creature.kind
        if self.now < creature.hurt:
            self._move(creature, dt, KNOCK_SPEED)
            self._settle(creature, CreatureState.HURT)
            return
        if self.now >= creature.thinks:
            creature.thinks = self.now + THINK
            self._think(creature, senses)
        aim, at = creature.aim, senses.at
        if creature.strikes is not None:
            if self.now >= creature.strikes:
                creature.strikes = None
                creature.rested = self.now + kind.rest
                if at is not None and _touches(creature, at):
                    self._log("A %s hurts the player", creature)
                    self.harm(kind)
            self._settle(creature, CreatureState.ATTACKING)
            return
        if aim and aim.attacks and at and self.now >= creature.rested and _touches(creature, at):
            creature.strikes = self.now + kind.windup
            creature.facing = SideFacing.EAST if at.x >= creature.x else SideFacing.WEST
            self._settle(creature, CreatureState.ATTACKING)
            return
        self._move(creature, dt, kind.speed * (aim.pace if aim else 1.0))
        if aim and aim.collects and creature.resting and creature.cell == aim.target:
            self._take(creature, senses)
        if not creature.resting:
            state = aim.state if aim else CreatureState.MOVING
        elif aim is not None and creature.cell == aim.target:
            state = aim.still
        else:
            state = CreatureState.IDLE
        self._settle(creature, state)

    def _think(self, creature: Creature, senses: Senses) -> None:
        aim = next(
            (aim for way in creature.kind.ways if (aim := way.aim(creature, senses)) is not None),
            None,
        )
        creature.aim = aim
        goal = aim.target if aim is not None else None
        if goal == creature.goal:
            return
        creature.goal = goal
        kept = creature.finishing()
        if goal is None:
            creature.path = deque(kept)
            return
        start = kept[-1].to if kept else creature.cell
        creature.path = deque([*kept, *legs(creature.grid.path(start, goal))])

    def _move(self, creature: Creature, dt: float, speed: float) -> None:
        budget = dt
        while creature.path and budget > 1e-9 and speed > 0:
            leg = creature.path[0]
            tx, ty = leg.to
            pace = FALL_SPEED if leg.falls else speed
            if not leg.falls and not math.isclose(tx, creature.x):
                creature.facing = SideFacing.EAST if tx > creature.x else SideFacing.WEST
            gap = math.dist(creature.position, leg.to)
            if gap <= pace * budget:
                creature.x, creature.y = float(tx), float(ty)
                budget -= gap / pace
                creature.path.popleft()
            else:
                share = pace * budget / gap
                creature.x += (tx - creature.x) * share
                creature.y += (ty - creature.y) * share
                budget = 0

    def _take(self, creature: Creature, senses: Senses) -> None:
        pickup = senses.salvage.get(creature.cell)
        if pickup is not None:
            self._log("A %s collects salvage", creature)
            self.collect(pickup)

    def _settle(self, creature: Creature, state: CreatureState) -> None:
        creature.state = state
        self._send(creature)

    def _send(self, creature: Creature) -> None:
        shown, sent = creature.shown(), creature.sent
        if sent is not None and (shown.state, shown.facing) == (sent.state, sent.facing):
            if shown.position == sent.position:
                return
            if not creature.resting and self.now - creature.sent_at < SEND - 1e-9:
                return
        creature.sent, creature.sent_at = shown, self.now
        self.send(CreatureMovedMessage(creature=shown))

    def _go_down(self, creature: Creature) -> None:
        creature.down = self.now
        creature.path.clear()
        creature.goal = creature.aim = creature.strikes = creature.seen = None
        creature.sent = None
        self._log("A %s goes down", creature)
        self.send(CreatureGoneMessage(creature_id=creature.id))
        if creature.respawn is None:
            del self.all[creature.id]

    def _come_back(self, creature: Creature) -> None:
        if creature.down is None or creature.respawn is None:
            return
        if self.now - creature.down < creature.respawn:
            return
        creature.down = None
        creature.x, creature.y = map(float, creature.home)
        creature.health = creature.kind.health
        creature.state, creature.leg, creature.paused = CreatureState.IDLE, 0, None
        creature.hurt = creature.rested = creature.thinks = 0.0
        self._send(creature)

    def _log(self, text: str, creature: Creature) -> None:
        logger.info("%s  " + text + " on %s", self.clock or "", creature.kind.id, creature.map)


def _touches(creature: Creature, at: Point) -> bool:
    if abs(creature.x - at.x) > creature.kind.reach:
        return False
    if creature.kind.flies:
        return at.y - 2.0 <= creature.y - 0.5 <= at.y + 0.3
    return -0.5 <= creature.y - at.y <= JUMPS_OVER


def _route(grid: Grid, home: Cell, span: int) -> tuple[Cell, ...]:
    """The ends of the floor, or the air, `span` cells either side of `home` along its row."""
    ends = [home]
    for dx in (-1, 1):
        along = grid.run(home, dx, span)
        if along:
            ends.append(along[-1])
    return tuple(ends[1:]) if len(ends) > 1 else ()


def _roost(grid: Grid, home: Cell) -> Cell | None:
    if not grid.kind.flies:
        return None
    x, y = home
    while grid.allowed((x, y - 1)):
        y -= 1
    return (x, y) if grid.town.solid(x, y - 1) else None


def creatures_of(app: Starlette) -> Creatures:
    """The creatures, made on first use, so any module can spawn them from its lifespan."""
    if not hasattr(app.state, "creatures"):
        from simile.world import movement_of

        app.state.creatures = Creatures(movement_of(app).maps)
    return app.state.creatures
