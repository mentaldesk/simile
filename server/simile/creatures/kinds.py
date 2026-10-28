"""The tunnels' kinds, and how each is placed: README.md's *The kinds*."""

from dataclasses import dataclass

from simile.creatures.kind import Kind
from simile.creatures.ways import (
    Chase,
    Collect,
    DrawnTo,
    Patrol,
    Roost,
    Scurry,
    fitted,
    food,
    lamp_on,
)
from simile.schema import CreatureKind

RAT = Kind(
    CreatureKind.RAT,
    speed=2.0,
    climbs=False,
    bites=True,
    damage=0.14,
    rest=6.0,
    stomped=True,
    ways=(Scurry(), DrawnTo(food, within=8.0, pace=1.4, attacks=True, floor=True), Patrol()),
)
BOT = Kind(
    CreatureKind.BOT,
    speed=1.2,
    climbs=False,
    stairs=False,
    drops=False,
    reach=1.2,
    damage=0.35,
    windup=0.3,
    lunges=True,
    rest=2.0,
    ways=(
        Chase(sight=5.0, pace=1.5, memory=3.0, when=fitted, floor=True),
        Collect(within=14.0, pace=0.2),
        Patrol(pause=3.0),
    ),
)
DOG = Kind(
    CreatureKind.DOG,
    speed=4.0,
    think=0.1,
    climbs=False,
    doors=False,
    reach=1.2,
    lunges=True,
    damage=0.1,
    rest=0.9,
    ways=(Chase(sight=10.0, pace=4.0, memory=3.0), Patrol(pause=2.0)),
)
BAT = Kind(
    CreatureKind.BAT,
    speed=3.0,
    think=0.15,
    flies=True,
    reach=0.8,
    damage=0.03,
    lunges=True,
    rest=2.0,
    ways=(Chase(sight=8.0, pace=4.0, memory=2.0, when=lamp_on), Roost()),
)


@dataclass(frozen=True)
class Placing:
    kind: Kind
    respawn: float | None = None


KINDS = {
    CreatureKind.RAT: Placing(RAT, respawn=120.0),
    CreatureKind.BOT: Placing(BOT),
    CreatureKind.DOG: Placing(DOG),
    CreatureKind.BAT: Placing(BAT),
}
"""Each kind a map's `creatures` layer can place."""
