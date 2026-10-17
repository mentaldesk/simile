import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from simile.characters.tables.census import Skeleton
from simile.characters.tables.conditions import Context, Village, choose
from simile.characters.tables.load import Event, Tables, load_tables

MIN_EVENTS, MAX_EVENTS = 2, 6


@dataclass(frozen=True)
class Happening:
    """`impact` (1-100) and `valence` (-1 to 1) map onto a past memory's salience and valence."""

    age: int
    id: str
    text: str
    impact: int
    valence: float


def event_count(rng: random.Random, age: int) -> int:
    return rng.randint(MIN_EVENTS, min(MAX_EVENTS, MIN_EVENTS + age // 15))


def sample_events(
    rng: random.Random,
    skeleton: Skeleton,
    scores: Mapping[str, float],
    *,
    fixed: Sequence[Happening] = (),
    count: int | None = None,
    village: Village | None = None,
    tables: Tables | None = None,
) -> list[Happening]:
    """Life events in age order, each conditioned on the skeleton, the values and temperament
    in `scores` and the events before it. Implied events are always drawn; `fixed` are kept."""
    t = tables or load_tables()
    taken = village or Village()
    chosen = {happening.id: happening for happening in fixed}
    facts = skeleton.facts()
    for event in t.events:
        if event.id not in chosen and event.implied and Context(facts).allows(event.implied):
            window = _window(event, skeleton, chosen)
            if window is not None:
                chosen[event.id] = _happen(event, rng.randint(*window))
    target = event_count(rng, skeleton.age) if count is None else count
    while len(chosen) < target:
        context = Context(facts, scores, frozenset(chosen))
        options: list[tuple[Event, tuple[int, int]]] = []
        weights: list[float] = []
        for event in t.events:
            window = _window(event, skeleton, chosen)
            if event.id in chosen or window is None or _clashes(t, event, chosen):
                continue
            weight = context.weight(event, event.weight) * taken.damping(event.id, event.rare)
            if weight > 0:
                options.append((event, window))
                weights.append(weight)
        pick = choose(rng, options, weights)
        if pick is None:
            break
        event, window = pick
        chosen[event.id] = _happen(event, rng.randint(*window))
    if village is not None:
        village.drawn.update(chosen.keys())
    return sorted(chosen.values(), key=lambda happening: (happening.age, happening.id))


def _window(
    event: Event, skeleton: Skeleton, chosen: Mapping[str, Happening]
) -> tuple[int, int] | None:
    low, high = event.ages[0], min(event.ages[1], skeleton.age)
    if event.years is not None:
        low = max(low, event.years[0] - skeleton.birth_year)
        high = min(high, event.years[1] - skeleton.birth_year)
    if event.after:
        earlier = [chosen[id].age for id in event.after if id in chosen]
        if not earlier:
            return None
        low = max(low, min(earlier) + 1)
    return (low, high) if low <= high else None


def _clashes(t: Tables, event: Event, chosen: Mapping[str, Happening]) -> bool:
    return any(
        id in event.not_with or (id in t.event and event.id in t.event[id].not_with)
        for id in chosen
    )


def _happen(event: Event, age: int) -> Happening:
    return Happening(age, event.id, event.text, event.impact, event.valence)
