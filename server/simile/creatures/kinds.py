"""The tunnels' kinds, and how each is placed: README.md's *The kinds*."""

import math
from dataclasses import dataclass

from simile.creatures.kind import Kind
from simile.creatures.ways import Chase, Collect, DrawnTo, Patrol, Scurry, fitted, food
from simile.schema import CreatureKind

RAT = Kind(
    CreatureKind.RAT,
    speed=2.0,
    climbs=False,
    bites=True,
    rest=6.0,
    ways=(Scurry(), DrawnTo(food, within=8.0, pace=1.4, attacks=True), Patrol()),
)
BOT = Kind(
    CreatureKind.BOT,
    speed=1.2,
    reach=0.8,
    damage=0.1,
    windup=0.6,
    rest=2.0,
    health=math.inf,
    toughness=1.0,
    ways=(
        Chase(sight=5.0, pace=1.5, memory=3.0, when=fitted),
        Collect(within=14.0, pace=0.2),
        Patrol(pause=3.0),
    ),
)


@dataclass(frozen=True)
class Placing:
    kind: Kind
    respawn: float | None = None


KINDS = {CreatureKind.RAT: Placing(RAT, respawn=120.0), CreatureKind.BOT: Placing(BOT)}
"""Each kind a map's `creatures` layer can place."""
