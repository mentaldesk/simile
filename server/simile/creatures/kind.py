from dataclasses import dataclass
from typing import TYPE_CHECKING

from simile.schema import CreatureKind

if TYPE_CHECKING:
    from simile.creatures.ways import Way


@dataclass(frozen=True)
class Kind:
    """Everything every creature of a kind shares: how it gets about, how it decides where to go,
    what it does to the player on contact and what a kick does to it. Speeds are in tiles a sim
    second, times in sim seconds and distances in tiles."""

    id: CreatureKind
    ways: "tuple[Way, ...]" = ()
    """Its ways of moving, first first: the first with somewhere to go decides. With none, it
    stays where it is."""
    speed: float = 1.0
    flies: bool = False
    """Through any open cell, rather than along floors."""
    climbs: bool = True
    """Up and down ladders. Every walking kind takes stairs."""
    doors: bool = True
    """Onto a door's tile, at the end of a link on its map. No creature takes a link."""
    drops: bool = True
    """Off a ledge or through a hole, falling to the floor below."""
    reach: float = 0.7
    """How near the player it hurts them."""
    bites: bool = False
    """It hurts by biting, which can turn infected, rather than by `damage`."""
    damage: float = 0.05
    windup: float = 0.3
    """How long it shows its attack before it lands, on the player if they're still in reach."""
    rest: float = 1.0
    """How long after an attack before its next."""
    health: float = 1.0
    """How hard it has to be kicked to go down: 1 is a kick on the player's own legs."""
    toughness: float = 0.0
    """How much of each kick's strength it shrugs off."""
    knock: float = 1.0
    """How far a kick of strength 1 sends it."""
    stagger: float = 0.6
    """How long it's hurt after a kick, doing nothing else."""
