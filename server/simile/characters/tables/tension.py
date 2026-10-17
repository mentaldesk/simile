import random
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, replace

from simile.characters.tables.census import Skeleton
from simile.characters.tables.conditions import Context, Village, choose
from simile.characters.tables.events import Happening
from simile.characters.tables.load import Secret, Tables, Want, Wound, load_tables

TOP_VALUE_POWER = 4
"""Contradictions weigh by value score to this power, so they almost always betray a top value."""


@dataclass(frozen=True)
class Contradiction:
    id: str
    value: str
    text: str
    age: int


@dataclass(frozen=True)
class Drawn:
    id: str
    text: str


@dataclass(frozen=True)
class WantNeed:
    id: str
    want: str
    need: str


@dataclass(frozen=True)
class Tension:
    contradiction: Contradiction | None
    wound: Drawn | None
    secret: Drawn | None
    want: WantNeed | None


def tension_context(
    skeleton: Skeleton,
    scores: Mapping[str, float],
    events: Sequence[Happening],
    attachment: str | None = None,
) -> Context:
    facts = {**skeleton.facts(), "attachment": attachment}
    return Context(facts, scores, frozenset(e.id for e in events))


def sample_contradiction(
    rng: random.Random,
    context: Context,
    *,
    village: Village | None = None,
    tables: Tables | None = None,
) -> Contradiction | None:
    """Something they once did against one of the values they care most about."""
    t = tables or load_tables()
    taken = village or Village()
    age = context.facts["age"]
    assert isinstance(age, int)
    rows = [row for row in t.tension.contradiction if row.ages[0] <= age]
    weights = [
        context.weight(row, row.weight)
        * context.scores.get(row.value.value, 0.5) ** TOP_VALUE_POWER
        * taken.damping(row.id)
        for row in rows
    ]
    row = choose(rng, rows, weights)
    if row is None:
        return None
    _record(village, row.id)
    return Contradiction(
        row.id, row.value.value, row.text, rng.randint(row.ages[0], min(row.ages[1], age))
    )


def sample_wound(
    rng: random.Random,
    context: Context,
    *,
    village: Village | None = None,
    tables: Tables | None = None,
) -> Drawn | None:
    t = tables or load_tables()
    return _pick(rng, context, t.tension.wound, village, lambda row: Drawn(row.id, row.text))


def sample_secret(
    rng: random.Random,
    context: Context,
    *,
    village: Village | None = None,
    tables: Tables | None = None,
) -> Drawn | None:
    t = tables or load_tables()
    return _pick(rng, context, t.tension.secret, village, lambda row: Drawn(row.id, row.text))


def sample_want(
    rng: random.Random,
    context: Context,
    *,
    village: Village | None = None,
    tables: Tables | None = None,
) -> WantNeed | None:
    """A want that isn't their need, conditioned on their values and their wound."""
    t = tables or load_tables()
    return _pick(rng, context, t.tension.want, village, lambda r: WantNeed(r.id, r.want, r.need))


def sample_tension(
    rng: random.Random,
    skeleton: Skeleton,
    scores: Mapping[str, float],
    events: Sequence[Happening],
    attachment: str | None,
    *,
    fixed: Tension | None = None,
    village: Village | None = None,
    tables: Tables | None = None,
) -> Tension:
    """All four, wound before want so the want can lean on it. Parts set in `fixed` are kept."""
    context = tension_context(skeleton, scores, events, attachment)
    kept = fixed or Tension(None, None, None, None)
    options = {"village": village, "tables": tables}
    contradiction = kept.contradiction or sample_contradiction(rng, context, **options)
    wound = kept.wound or sample_wound(rng, context, **options)
    context = _with(context, [part.id for part in (contradiction, wound) if part])
    secret = kept.secret or sample_secret(rng, context, **options)
    want = kept.want or sample_want(rng, context, **options)
    return Tension(contradiction, wound, secret, want)


def _pick[R: (Wound, Secret, Want), T](
    rng: random.Random,
    context: Context,
    rows: Sequence[R],
    village: Village | None,
    make: Callable[[R], T],
) -> T | None:
    taken = village or Village()
    rows = [row for row in rows if not row.after or any(i in context.happened for i in row.after)]
    weights = [context.weight(row, row.weight) * taken.damping(row.id, row.rare) for row in rows]
    row = choose(rng, rows, weights)
    if row is None:
        return None
    _record(village, row.id)
    return make(row)


def _with(context: Context, ids: Collection[str]) -> Context:
    return replace(context, happened=frozenset(context.happened) | set(ids))


def _record(village: Village | None, id: str) -> None:
    if village is not None:
        village.drawn[id] += 1
