import math
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from simile.behaviour.config import DEFAULT_CONFIG, Activity, BehaviourConfig, Curve, Need
from simile.schema import CoreValue, Id, Location, LocationKind, Relationship
from simile.world.map import WALKING_SPEED, TownMap
from simile.world.movement import Point, inside

PLACES: dict[Activity, LocationKind] = {
    Activity.COFFEE_SHOP: LocationKind.COFFEE_SHOP,
    Activity.SQUARE: LocationKind.SQUARE,
    Activity.NEWS: LocationKind.TERMINAL,
}
AMENITIES = (Activity.PARK, Activity.NOODLE_BAR, Activity.MAKER_SPACE)


@dataclass(frozen=True)
class Goal:
    activity: Activity
    target: str | None = None
    """A location id, or for `seek` and `talk` the entity's id."""

    def __str__(self) -> str:
        return self.activity if self.target is None else f"{self.activity} {self.target}"


class Places:
    def __init__(self, town: TownMap) -> None:
        self.town = town
        self.by_activity: dict[Activity, list[Location]] = {
            activity: [loc for loc in town.locations if loc.kind is kind]
            for activity, kind in PLACES.items()
        }
        ids = {loc.id: loc for loc in town.locations}
        for activity in AMENITIES:
            self.by_activity[activity] = [ids[activity]] if activity in ids else []
        self._by_size = sorted(town.locations, key=lambda loc: loc.area.width * loc.area.height)

    def location(self, location_id: str) -> Location:
        return self.town.location(location_id)

    def at(self, point: Point) -> Location | None:
        """The smallest location the point is in, so a terminal wins over the square around it."""
        cell = (math.floor(point.x + 0.5), math.floor(point.y + 0.5))
        return next((loc for loc in self._by_size if inside(loc, cell)), None)


@dataclass(frozen=True)
class Other:
    id: Id
    position: Point
    affinity: float
    place: str | None = None
    """The location they're at or heading for."""
    available: bool = True
    """Whether they can be sought out: not asleep, at home, talking or recently refused."""


@dataclass(frozen=True)
class Situation:
    values: Mapping[CoreValue, float]
    needs: Mapping[Need, float]
    hour: float
    position: Point
    home: Id
    bedtime: float
    others: Sequence[Other] = ()
    last: Goal | None = None
    news: float = 0.0
    """How interesting the best article they haven't read is, 0-1. 0 if nothing's worth reading,
    and then the terminals aren't an option."""


AFFINITY = ("like", "trust", "respect")


def affinity(rel: Relationship, config: BehaviourConfig = DEFAULT_CONFIG) -> float:
    """How much the owner wants to be around them: positive for friends, negative to avoid."""
    weights = config.affinity_weights
    return (
        sum(weights.get(aspect, 0.0) * (getattr(rel, aspect) - 0.5) for aspect in AFFINITY)
        + weights.get("familiarity", 0.0) * rel.familiarity
    )


def curve(points: Curve, hour: float) -> float:
    if not points or not points[0][0] <= hour <= points[-1][0]:
        return 0.0
    for (x0, y0), (x1, y1) in zip(points, points[1:], strict=False):
        if x0 <= hour <= x1:
            return y0 if x1 == x0 else y0 + (y1 - y0) * (hour - x0) / (x1 - x0)
    return 0.0


def personal_hour(
    base: float,
    weights: Mapping[CoreValue, float],
    bounds: tuple[float, float],
    values: Mapping[CoreValue, float],
) -> float:
    hour = base + sum(weight * (values[value] - 0.5) for value, weight in weights.items())
    return min(max(hour, bounds[0]), bounds[1])


def bedtime(values: Mapping[CoreValue, float], config: BehaviourConfig = DEFAULT_CONFIG) -> float:
    return personal_hour(config.bedtime, config.bedtime_values, config.bedtime_range, values)


def wake(values: Mapping[CoreValue, float], config: BehaviourConfig = DEFAULT_CONFIG) -> float:
    return personal_hour(config.wake, config.wake_values, config.wake_range, values)


def asleep(hour: float, bed: float, up: float) -> bool:
    return hour >= bed or hour < up


def sociability(values: Mapping[CoreValue, float], config: BehaviourConfig) -> float:
    return max(0.0, 1 + config.sociability * (values[CoreValue.CONNECTION] - 0.5))


def walk_minutes(a: Point, b: Point) -> float:
    return math.dist(a, b) / WALKING_SPEED / 60


def candidates(situation: Situation, places: Places) -> list[Goal]:
    goals = [Goal(Activity.HOME, situation.home)]
    for activity, locations in places.by_activity.items():
        if activity is Activity.NEWS and situation.news <= 0:
            continue
        goals.extend(Goal(activity, location.id) for location in locations)
    goals += [Goal(Activity.WANDER), Goal(Activity.IDLE)]
    goals.extend(Goal(Activity.SEEK, o.id) for o in situation.others if o.available)
    return goals


def score(
    goal: Goal, situation: Situation, places: Places, config: BehaviourConfig = DEFAULT_CONFIG
) -> float:
    activity, values, needs = goal.activity, situation.values, situation.needs
    total = config.base.get(activity, 0.0)
    total += sum(w * (values[v] - 0.5) for v, w in config.value_weights.get(activity, {}).items())
    total += sum(w * needs[n] for n, w in config.need_weights.get(activity, {}).items())
    on_offer = situation.news if activity is Activity.NEWS else 1.0
    total += sum(
        urgency.weight
        * relief(needs[need], on_offer * promised(activity, need, config), urgency.power)
        for need, urgency in config.urgency.items()
    )
    total += curve(config.daily.get(activity, ()), situation.hour)
    if situation.last is not None and activity is situation.last.activity:
        total -= config.repeat_penalty
    if activity is Activity.HOME:
        until_bed = situation.bedtime - situation.hour
        total += config.evening_weight * min(max(1 - until_bed / config.evening_hours, 0.0), 1.0)
    if activity is Activity.SEEK:
        other = next(o for o in situation.others if o.id == goal.target)
        total += config.seek_weight * sociability(values, config) * other.affinity
        total -= config.travel_weight * walk_minutes(situation.position, other.position)
    elif goal.target is not None:
        location = places.location(goal.target)
        entry = Point(location.entry.x, location.entry.y)
        total -= config.travel_weight * walk_minutes(situation.position, entry)
        if activity is not Activity.HOME:
            total += company(location.id, situation, config)
    return total


def company(location_id: str, situation: Situation, config: BehaviourConfig) -> float:
    present = [o for o in situation.others if o.place == location_id]
    liked = sum(max(o.affinity, 0.0) for o in present)
    disliked = sum(min(o.affinity, 0.0) for o in present)
    crowd = min(len(present), config.crowd_cap)
    connection = situation.values[CoreValue.CONNECTION] - 0.5
    return (
        config.company_weight * sociability(situation.values, config) * liked
        + config.avoid_weight * disliked
        + config.crowd_weight * connection * crowd
    )


def relief(need: float, change: float, power: float) -> float:
    """What changing a need by `change` is worth: the area under its urgency curve,
    `need ** power`, between where it is and where it ends up. Positive for relief."""
    after = min(max(need + change, 0.0), 1.0)
    return (need ** (power + 1) - after ** (power + 1)) / (power + 1)


def promised(activity: Activity, need: Need, config: BehaviourConfig = DEFAULT_CONFIG) -> float:
    """How a typical stay at `activity` changes `need`. Seeking someone out promises a talk."""
    if activity is Activity.SEEK:
        return config.effects.get(Activity.TALK, {}).get(need, 0.0) * config.talk_minutes / 60
    low, high = config.dwell.get(activity, (0.0, 0.0))
    return config.effects.get(activity, {}).get(need, 0.0) * (low + high) / 2 / 60


def scores(
    situation: Situation, places: Places, config: BehaviourConfig = DEFAULT_CONFIG
) -> dict[Goal, float]:
    return {goal: score(goal, situation, places, config) for goal in candidates(situation, places)}


def best_per_activity(options: Mapping[Goal, float]) -> dict[Activity, tuple[Goal, float]]:
    """The best goal of each activity, so three terminals don't make the news three times as
    likely as the park."""
    best: dict[Activity, tuple[Goal, float]] = {}
    for goal, value in options.items():
        if goal.activity not in best or value > best[goal.activity][1]:
            best[goal.activity] = (goal, value)
    return best


def choose(options: Mapping[Goal, float], rng: random.Random, temperature: float) -> Goal:
    """Softmax over each activity's best goal. A temperature of 0 always picks the best."""
    best = list(best_per_activity(options).values())
    top = max(value for _, value in best)
    if temperature <= 0:
        return next(goal for goal, value in best if value == top)
    weights = [math.exp((value - top) / temperature) for _, value in best]
    return rng.choices([goal for goal, _ in best], weights)[0]
