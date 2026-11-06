from collections.abc import Mapping, Sequence
from datetime import datetime

from simile.schema import (
    PLAYER_ID,
    Aspect,
    CoreValue,
    InteractionEvent,
    Item,
    ItemKind,
    Npc,
    Relationship,
)
from simile.social.bionics import level
from simile.social.config import DEFAULT_BIONICS, BionicsConfig
from simile.social.relationship import apply_events

FEELS: dict[int, str] = {
    -2: "Guns have no place in this village: you don't trust anyone who goes about with one, and "
    "you'd rather keep your distance.",
    -1: "A gun on someone makes you wary, and you trust them less for it.",
    0: "You notice it, but it doesn't much bother you.",
}


def armed(items: Sequence[Item]) -> bool:
    return any(item.kind is ItemKind.WEAPON for item in items)


def wariness(values: Mapping[CoreValue, float], config: BionicsConfig = DEFAULT_BIONICS) -> float:
    """How far a resident distrusts a weapon, from 0 to 1. Only scores above the middle count, so
    a low one doesn't excuse a high one and nobody warms to it."""
    weights = config.weapon_weights
    return min(sum(w * max(values[value] - 0.5, 0.0) for value, w in weights.items()), 1.0)


def wary(npc: Npc, config: BionicsConfig = DEFAULT_BIONICS) -> bool:
    return level(-wariness(npc.values, config), config) < 0


def carrying(name: str, npc: Npc, config: BionicsConfig = DEFAULT_BIONICS) -> str:
    """What a resident sees of the player's pistol and feels about it, for a prompt."""
    feeling = FEELS[level(-wariness(npc.values, config), config)]
    return f"{name} is carrying a pistol. {feeling}"


def noticed(npc: Npc, now: datetime, config: BionicsConfig = DEFAULT_BIONICS) -> InteractionEvent:
    """An R1 event for `npc` seeing the player armed, on trust alone."""
    return InteractionEvent(
        actor=PLAYER_ID,
        target=npc.id,
        action="turned up carrying a pistol",
        aspects=[Aspect.TRUST],
        valence=-wariness(npc.values, config),
        magnitude=config.sighting,
        timestamp=now,
    )


def dented(
    rel: Relationship, npc: Npc, now: datetime, config: BionicsConfig = DEFAULT_BIONICS
) -> Relationship:
    """`rel`, as of `now`, after `npc` sees the player armed: trust falls, but not past the first
    dent from their baseline, and nothing else moves."""
    event = noticed(npc, now, config)
    hit = apply_events(rel, [event], now)
    fresh = rel.model_copy(update={"trust": rel.baseline.trust, "familiarity": 0.0})
    floor = apply_events(fresh, [event], now).trust
    trust = max(hit.trust, min(floor, rel.trust))
    return hit.model_copy(update={"trust": trust, "familiarity": rel.familiarity})
