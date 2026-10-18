from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from simile.cafe.config import CafeConfig, Nudge
from simile.schema import Aspect, Id, InteractionEvent, Memory, MemoryKind, Npc, Relationship
from simile.sim import Event
from simile.social import apply_events, as_of, meet


@dataclass(frozen=True)
class Ordered(Event):
    customer: Id
    barista: Id
    drink: str
    menu: str | None
    """The menu item it's made as, or None for something improvised."""


@dataclass(frozen=True)
class Served(Event):
    customer: Id
    barista: Id
    drink: str
    waited: float
    """Sim seconds from joining the queue, or from ordering for the player."""
    wrong: bool


@dataclass(frozen=True)
class GaveUp(Event):
    customer: Id
    barista: Id
    waited: float


class Store(Protocol):
    def relationship(self, owner: str, about: str) -> Relationship | None: ...

    def add(self, *records: InteractionEvent | Memory | Relationship) -> None: ...


def event(
    actor: Id, target: Id, action: str, aspect: Aspect, nudge: Nudge, now: datetime
) -> InteractionEvent:
    return InteractionEvent(
        actor=actor,
        target=target,
        action=action,
        aspects=[aspect],
        valence=nudge.valence,
        magnitude=nudge.magnitude,
        timestamp=now,
    )


def served(
    barista: Npc,
    customer: Npc,
    drink: str,
    waited: float,
    wrong: bool,
    config: CafeConfig,
    now: datetime,
) -> tuple[list[InteractionEvent], list[Memory]]:
    """What an order meant to each of them: the customer was served, perhaps slowly or wrongly,
    and the barista served them."""
    name, them = barista.name.split()[0], customer.name.split()[0]
    slow = waited > config.slow
    events = [
        event(barista.id, customer.id, f"made my {drink}", Aspect.LIKE, config.served, now),
        event(customer.id, barista.id, f"came in for a {drink}", Aspect.LIKE, config.serving, now),
    ]
    if slow:
        events.append(
            event(barista.id, customer.id, "kept me waiting", Aspect.LIKE, config.waited, now)
        )
    if wrong:
        events.append(
            event(barista.id, customer.id, "got my order wrong", Aspect.RESPECT, config.wrong, now)
        )
    how = ", though I waited ages" if slow else ""
    how += ", once they'd remade it after getting it wrong" if wrong else ""
    memories = [
        Memory(
            owner=customer.id,
            kind=MemoryKind.OBSERVATION,
            content=f"Had a {drink} at the Daily Grind, made by {name}{how}.",
            salience=config.salience * (2 if slow or wrong else 1),
            valence=-0.3 if slow or wrong else 0.3,
            timestamp=now,
            about=[barista.id],
        )
    ]
    if wrong:
        memories.append(
            Memory(
                owner=barista.id,
                kind=MemoryKind.OBSERVATION,
                content=f"Got {them}'s {drink} wrong and had to make it again.",
                salience=config.salience * 2,
                valence=-0.3,
                timestamp=now,
                about=[customer.id],
            )
        )
    return events, memories


def gave_up(
    barista: Npc, customer: Npc, config: CafeConfig, now: datetime
) -> tuple[list[InteractionEvent], list[Memory]]:
    name = barista.name.split()[0]
    events = [
        event(
            barista.id,
            customer.id,
            "kept me waiting so long I gave up",
            Aspect.LIKE,
            config.gave_up,
            now,
        )
    ]
    memory = Memory(
        owner=customer.id,
        kind=MemoryKind.OBSERVATION,
        content=f"Gave up waiting for a coffee from {name} at the Daily Grind.",
        salience=config.salience * 2,
        valence=-0.5,
        timestamp=now,
        about=[barista.id],
    )
    return events, [memory]


def record(
    store: Store,
    npcs: Mapping[Id, Npc],
    events: Sequence[InteractionEvent],
    memories: Sequence[Memory],
    now: datetime,
) -> list[Relationship]:
    """Apply each event to how its target feels about its actor, as B3 applies a conversation's,
    and store the events, the memories and the relationships after."""
    by_pair: dict[tuple[Id, Id], list[InteractionEvent]] = defaultdict(list)
    for item in events:
        by_pair[item.target, item.actor].append(item)
    after = []
    for (owner, about), happened in by_pair.items():
        stored = store.relationship(owner, about)
        before = as_of(stored, now) if stored else meet(npcs[owner], about)
        after.append(apply_events(before, happened, now))
    store.add(*events, *memories, *after)
    return after
