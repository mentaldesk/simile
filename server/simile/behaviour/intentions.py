from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime

from simile.behaviour.config import DEFAULT_CONFIG, Activity, BehaviourConfig
from simile.behaviour.scoring import Goal
from simile.schema import PLAYER_ID, CoreValue, Id, Intention, IntentionKind, Medium

GOING = (
    Activity.HOME,
    Activity.COFFEE_SHOP,
    Activity.SQUARE,
    Activity.PARK,
    Activity.NOODLE_BAR,
    Activity.MAKER_SPACE,
    Activity.GALLERY,
    Activity.WORK,
    Activity.CREATE,
)
"""The activities that take someone to a location, so keep a `go` intention for it."""

PLACES = (
    Activity.COFFEE_SHOP,
    Activity.SQUARE,
    Activity.PARK,
    Activity.NOODLE_BAR,
    Activity.MAKER_SPACE,
    Activity.GALLERY,
)


@dataclass(frozen=True)
class Options:
    """What a resident could say they'll do, by the ids B1 acts on."""

    home: Id
    places: dict[Id, str]
    """Where they can go, by location id, their home included, with each place's name."""
    terminals: dict[Id, str]
    medium: Medium | None
    making: dict[Id, str]
    """Where they'd make something now: for a muralist the wall the `mural_wall` hook names, or
    their home to paint a canvas, and for anyone else with a craft their writing places. Empty
    without a craft or a wall."""


@dataclass
class Promise:
    """An open intention, and what B1 has made of it."""

    intention: Intention
    following: bool | None = None
    """Whether they'll follow it through, decided once it's due."""
    called: bool = False
    """Whether it has sent them off to decide again."""


def matches(intention: Intention, goal: Goal) -> bool:
    """Whether choosing `goal` would do what they said: any work for `create` unless it names
    where and that's on offer, any terminal for `news` unless it names one."""
    target = intention.target
    match intention.kind:
        case IntentionKind.CREATE:
            return goal.activity is Activity.CREATE
        case IntentionKind.GO:
            return goal.activity in GOING and goal.target == target
        case IntentionKind.SEEK:
            return goal == Goal(Activity.SEEK, target)
        case IntentionKind.NEWS:
            return goal.activity is Activity.NEWS and target in (None, goal.target)


def boosted(intention: Intention, goals: Iterable[Goal]) -> list[Goal]:
    """The goals among `goals` that get the intention's bonus: those that do it, and of those the
    one it names if it's there."""
    found = [goal for goal in goals if matches(intention, goal)]
    named = [goal for goal in found if goal.target == intention.target]
    return named if intention.kind is IntentionKind.CREATE and named else found


def possible(intention: Intention, options: Options, residents: Collection[Id]) -> bool:
    """Whether B1 could ever act on it: a place they can go, someone to seek, a craft, or a
    terminal."""
    target = intention.target
    match intention.kind:
        case IntentionKind.GO:
            return target in options.places
        case IntentionKind.SEEK:
            return target != intention.owner and (target == PLAYER_ID or target in residents)
        case IntentionKind.CREATE:
            return options.medium is not None
        case IntentionKind.NEWS:
            return target is None or target in options.terminals


def deed(intention: Intention) -> str:
    """What they said they'd do, to follow "said they'd"."""
    if intention.kind is IntentionKind.CREATE:
        return f"make {intention.description}"
    return intention.description


def when(due: datetime, now: datetime) -> str:
    """ "now", or "today 15:00" or "tomorrow 09:00"."""
    if due <= now:
        return "now"
    day = "today" if due.date() == now.date() else "tomorrow"
    return f"{day} {due:%H:%M}"


def same(a: Intention, b: Intention) -> bool:
    return (a.owner, a.kind, a.target) == (b.owner, b.kind, b.target)


def reliability(
    values: Mapping[CoreValue, float], config: BehaviourConfig = DEFAULT_CONFIG
) -> float:
    weights = config.reliability_values
    total = sum(weights.values())
    return sum(w * values[v] for v, w in weights.items()) / total if total else 1.0


def lapse_chance(
    values: Mapping[CoreValue, float], config: BehaviourConfig = DEFAULT_CONFIG
) -> float:
    """The chance they let an intention slide when it falls due: now and then for the least
    reliable, never from `reliable_from`."""
    short = max(config.reliable_from - reliability(values, config), 0.0)
    return config.lapse * short / config.reliable_from
