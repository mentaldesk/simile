from dataclasses import dataclass
from typing import TYPE_CHECKING

from simile.schema import CreatureKind

if TYPE_CHECKING:
    from simile.creatures.ways import Way


@dataclass(frozen=True)
class Kind:
    """What every creature of a kind shares: README.md has each field."""

    id: CreatureKind
    ways: "tuple[Way, ...]" = ()
    speed: float = 1.0
    think: float = 0.25
    flies: bool = False
    climbs: bool = True
    stairs: bool = True
    doors: bool = True
    drops: bool = True
    reach: float = 0.7
    bites: bool = False
    damage: float = 0.05
    windup: float = 0.3
    lunges: bool = False
    rest: float = 1.0
    stomped: bool = False
