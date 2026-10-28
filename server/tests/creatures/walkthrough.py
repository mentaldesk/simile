"""A scripted player past a map's creatures, as the server hears them."""

import math
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field

from simile.creatures.engine import Creature, Creatures, Sight
from simile.creatures.kind import Kind
from simile.creatures.placing import populate
from simile.schema import DoorKind, Player
from simile.sim import STEP as TICK
from simile.street.jump import JUMP, Jump
from simile.street.moves import possible
from simile.street.plan import Spawn
from simile.world.map import TownMap
from simile.world.movement import Point

FRAME = 0.05
"""Seconds of the client's that each step of the player's moves takes."""
THROTTLE = 0.2
"""Real seconds between the client's `player_move`s; it sends one at once as it lands."""
CLIMB = 1.5
"""Tiles a second up or down a ladder, as the client climbs."""
WALK = JUMP.run / 2
FALL_GRAVITY = 1.3
FOOT, BODY = 0.25, 1.7
LONGEST = 900.0


@dataclass(frozen=True)
class Walk:
    """Along the row they're on to `x`, or until `until` holds of the walkthrough, or they react
    to something."""

    x: float
    pace: float = WALK
    until: "Callable[[Walkthrough], bool] | None" = None


@dataclass(frozen=True)
class Climb:
    """Up or down the ladder they're on, or at the foot or top of, to `row`."""

    row: int


@dataclass(frozen=True)
class Leap:
    """A running jump through the air to stand at (`x`, `row`), rising `rise` tiles first: none
    to step off a ledge, and the jump's full rise by default."""

    x: float
    row: int
    rise: float | None = None


@dataclass(frozen=True)
class Wait:
    """Standing still until `until` holds of the walkthrough, or for `seconds`."""

    seconds: float = math.inf
    until: "Callable[[Walkthrough], bool] | None" = None
    timeout: float = 120.0


type Step = Walk | Climb | Leap | Wait
type Plan = Callable[["Walkthrough"], Iterable["Step | Plan"]]
"""Steps worked out when they're reached, from where everything is then."""
type React = Callable[["Walkthrough", Step], "Iterable[Step | Plan] | None"]
"""What the player does before going on with a step, if anything: dodging what's coming."""


class Stuck(AssertionError):
    pass


@dataclass
class Walkthrough:
    """The player on `town` with its creatures from `placed`, from (`x`, `row`), moving a `frame`
    at a time and heard as the client sends their moves, the creatures ticking at the sim's rate."""

    town: TownMap
    placed: Sequence[tuple[str, Spawn]]
    x: float
    row: int
    player: Player = field(default_factory=Player)
    jump: Jump = JUMP
    react: React | None = None
    frame: float = FRAME
    now: float = 0.0
    harmed: list[Kind] = field(default_factory=list)
    log: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.y = float(self.row)
        self.heard = Point(self.x, self.y, self.town.id)
        self.said = 0.0
        self.reactions = 0
        self.ticked = 0.0
        self.creatures = Creatures(
            {self.town.id: self.town},
            sense=lambda: Sight(self.player, self.heard),
            harm=self._harm,
        )
        populate(self.creatures, list(self.placed))
        self.gravity = 2 * self.jump.rise / self.jump.rise_seconds**2

    def _harm(self, kind: Kind) -> None:
        self.harmed.append(kind)
        self.log.append(f"{self.now:.2f} a {kind.id} hurts them at {self.x:.2f}, {self.y:.2f}")

    def _reacted(self, step: Step) -> bool:
        steps = self.react(self, step) if self.react is not None else None
        if steps is None:
            return False
        self.reactions += 1
        self.go(steps)
        return True

    def creature(self, creature_id: str) -> Creature:
        return self.creatures.all[creature_id]

    def go(self, steps: Iterable["Step | Plan"]) -> "Walkthrough":
        for step in steps:
            if not callable(step):
                self.log.append(f"{self.now:.2f} at {self.x:.2f}, {self.y:.2f}: {step}")
            if callable(step):
                self.go(step(self))
            elif isinstance(step, Walk):
                self._walk(step)
            elif isinstance(step, Climb):
                self._climb(step)
            elif isinstance(step, Leap):
                self._leap(step)
            else:
                self._wait(step)
        return self

    def _tick(self, landed: bool = False) -> None:
        self.now += self.frame
        if self.now > LONGEST:
            raise Stuck(f"still going after {LONGEST} s")
        if landed or self.now - self.said >= THROTTLE - 1e-9:
            last = (self.heard.x, self.heard.y)
            if not possible(self.town, self.x, self.y, last, self.jump):
                raise Stuck(f"the server keeps no move to {self.x:.2f}, {self.y:.2f}")
            self.heard, self.said = Point(self.x, self.y, self.town.id), self.now
        while self.now - self.ticked >= TICK - 1e-9:
            self.ticked += TICK
            self.creatures.tick(TICK)

    def _walk(self, step: Walk) -> None:
        row = round(self.y)
        while not math.isclose(self.x, step.x):
            if step.until is not None and step.until(self):
                return
            gap = step.x - self.x
            if self._reacted(step):
                return
            x = self.x + math.copysign(min(abs(gap), step.pace * self.frame), gap)
            if not (self._on(x, row) or self.town.walkable(math.floor(x + 0.5), row)):
                raise Stuck(f"nowhere to walk at {x:.2f}, {row}")
            if self._blocked(x, row):
                raise Stuck(f"no room to stand at {x:.2f}, {row}")
            self.x = x
            self._tick()

    def _climb(self, step: Climb) -> None:
        cx, start = round(self.x), round(self.y)
        rows = range(min(start, step.row), max(start, step.row))
        if not all(self.town.climb(cx, r) is DoorKind.LADDER for r in rows):
            raise Stuck(f"no ladder at {cx} from row {start} to {step.row}")
        self.x = float(cx)
        while not math.isclose(self.y, step.row):
            if self._reacted(step):
                continue
            gap = step.row - self.y
            self.y += math.copysign(min(abs(gap), CLIMB * self.frame), gap)
            self._tick()

    def _leap(self, step: Leap) -> None:
        """As the client jumps: along at a run, up at `gravity` with Space held, and down at
        `FALL_GRAVITY` times it, landing on whatever's under the feet as they come down past it."""
        if not self.town.standing(round(step.x), step.row):
            raise Stuck(f"nowhere to land at {step.x}, {step.row}")
        while self._reacted(step):
            pass
        rise = self.jump.rise if step.rise is None else step.rise
        vy = -math.sqrt(2 * self.gravity * rise)
        start = self.now
        while True:
            gap = step.x - self.x
            dt = self.frame
            x = self.x + math.copysign(min(abs(gap), self.jump.run * dt), gap)
            if self._blocked(x, self.y):
                raise Stuck(f"the body meets a wall at {x:.2f}, {self.y:.2f}")
            self.x = x
            gravity = self.gravity * (1 if vy < 0 else FALL_GRAVITY)
            y = self.y + vy * dt + gravity * dt * dt / 2
            vy += gravity * dt
            if vy < 0 and self._blocked(self.x, y):
                vy, y = 0.0, self.y
            crossed = range(math.ceil(self.y - 1e-9), math.floor(y + 1e-9) + 1) if vy >= 0 else ()
            row = next((r for r in crossed if self._on(self.x, r)), None)
            landed = row is not None
            if row is not None:
                y, vy = float(row), 0.0
            self.y = y
            if landed and math.isclose(self.x, step.x):
                if row != step.row:
                    raise Stuck(f"lands on row {row}, not {step.row}")
                self._tick(landed=True)
                return
            self._tick()
            if self.now - start > 5:
                raise Stuck(f"never lands at {step.x}, {step.row}")

    def _on(self, x: float, row: int) -> bool:
        """Whether feet at `x` stand on something at the bottom of `row`."""
        return any(self.town.solid(cx, row + 1) for cx in self._columns(x))

    def _columns(self, x: float) -> range:
        return range(math.floor(x - FOOT + 0.5), math.floor(x + FOOT + 0.5) + 1)

    def _blocked(self, x: float, y: float) -> bool:
        rows = range(math.ceil(y - BODY + 1e-6), math.ceil(y - 1e-6) + 1)
        return any(self.town.solid(cx, cy) for cx in self._columns(x) for cy in rows)

    def _wait(self, step: Wait) -> None:
        start = self.now
        while self.now - start < step.seconds - 1e-9:
            if step.until is not None and step.until(self):
                return
            if self.now - start > step.timeout:
                raise Stuck(f"waited {step.timeout} s at {self.x}, {self.y}")
            if not self._reacted(step):
                self._tick()
