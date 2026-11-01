import math
import zlib
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from simile.schema import Id, Pose
from simile.world.map import Spot, SpotKind

type Affinity = Callable[[Id, Id], float]


class Purpose(StrEnum):
    """What someone is at a place for, which says which spots suit them."""

    EAT = "eat"
    DRINK = "drink"
    READ = "read"
    MAKE = "make"
    LOOK = "look"
    RELAX = "relax"
    LINGER = "linger"
    SLEEP = "sleep"


BY_ACTIVITY = {
    "coffee_shop": Purpose.DRINK,
    "noodle_bar": Purpose.EAT,
    "news": Purpose.READ,
    "maker_space": Purpose.MAKE,
    "create": Purpose.MAKE,
    "gallery": Purpose.LOOK,
    "park": Purpose.RELAX,
    "square": Purpose.LINGER,
    "sleep": Purpose.SLEEP,
}
SERVING = (Purpose.EAT, Purpose.DRINK)
"""Places whose staff serve rather than take a spot."""


def indifferent(a: Id, b: Id) -> float:
    return 0.0


@dataclass(frozen=True)
class SpotConfig:
    fits: Mapping[Purpose, Mapping[SpotKind, float]] = field(
        default_factory=lambda: {
            Purpose.EAT: {SpotKind.SEAT: 0.0},
            Purpose.DRINK: {SpotKind.BAR: 0.0, SpotKind.SEAT: 0.0},
            Purpose.READ: {SpotKind.TERMINAL: 0.0},
            Purpose.MAKE: {SpotKind.DESK: 0.0, SpotKind.SEAT: -0.5},
            Purpose.LOOK: {SpotKind.VIEWING: 0.0, SpotKind.SEAT: -0.5},
            Purpose.RELAX: {SpotKind.SEAT: 0.0},
            Purpose.LINGER: {SpotKind.STANDING: 0.0, SpotKind.SEAT: 0.0},
            Purpose.SLEEP: {SpotKind.BED: 0.0},
        }
    )
    """The spots that suit each purpose, and how much each kind is preferred."""
    near: float = 3.0
    """Tiles within which someone's affinity for whoever's there counts, more the closer."""
    taste: float = 0.2
    """How much each resident's own liking for a spot counts, so regulars have their usual."""
    walk: float = 0.02
    """What each tile of walking costs, inside the place."""


DEFAULT_SPOTS = SpotConfig()


def purpose_of(activity: str, target: str | None) -> Purpose | None:
    """At work, what the place is for, since an amenity's activity is its id."""
    if activity == "work":
        purpose = BY_ACTIVITY.get(target or "")
        return None if purpose in SERVING else purpose
    return BY_ACTIVITY.get(activity)


def pose_on(spot: Spot, purpose: Purpose | None) -> Pose:
    if purpose is Purpose.MAKE and spot.kind is SpotKind.VIEWING:
        return Pose.WORKING
    return spot.pose


def taste(entity: Id, spot: Spot, place: str | None = None) -> float:
    """Each resident's own liking for a spot, 0 to 1, the same every time. It's keyed by the
    place the spot is in, or else its map: an interior's map id was its place's."""
    return zlib.crc32(f"{entity}/{place or spot.map}/{spot.id}".encode()) / 0xFFFFFFFF


def choose(
    entity: Id,
    free: Iterable[Spot],
    kinds: Mapping[SpotKind, float],
    others: Mapping[Id, tuple[float, float]],
    start: tuple[float, float] | None,
    affinity: Affinity,
    config: SpotConfig = DEFAULT_SPOTS,
    *,
    place: str | None = None,
) -> Spot | None:
    """Near friends and away from foes, then to taste, then the shortest walk."""

    liking: dict[Id, float] = {}

    def score(spot: Spot) -> float:
        value = kinds[spot.kind] + config.taste * taste(entity, spot, place)
        for other, there in others.items():
            if (gap := math.dist(spot.seat, there)) < config.near:
                if other not in liking:
                    liking[other] = affinity(entity, other)
                value += liking[other] * (1 - gap / config.near)
        if start is not None:
            value -= config.walk * math.dist(start, (spot.x, spot.y))
        return value

    suitable = [spot for spot in free if spot.kind in kinds]
    return max(suitable, key=score, default=None)
