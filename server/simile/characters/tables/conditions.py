import math
import random
from collections import Counter
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field

from simile.characters.tables.load import Allowed, Between, Conditional, Except

LEAN = 2.0
"""A lean of 1 makes a score of 0.9 about five times as likely to draw as one of 0.1."""
REPEAT = 0.3


@dataclass
class Village:
    """What one cast has drawn, so rare draws go to one resident and common ones fade."""

    names: set[str] = field(default_factory=set)
    jobs: set[str] = field(default_factory=set)
    drawn: Counter[str] = field(default_factory=Counter)

    def damping(self, key: str, rare: bool = False) -> float:
        times = self.drawn[key]
        return 0.0 if rare and times else REPEAT**times


@dataclass(frozen=True)
class Context:
    facts: Mapping[str, object] = field(default_factory=dict)
    scores: Mapping[str, float] = field(default_factory=dict)
    happened: Collection[str] = frozenset()

    def allows(self, when: Mapping[str, Allowed]) -> bool:
        return all(meets(self.facts.get(key), spec) for key, spec in when.items())

    def weight(self, row: Conditional, base: float = 1.0) -> float:
        if not self.allows(row.when):
            return 0.0
        weight = base
        for key, strength in row.lean.items():
            weight *= math.exp(LEAN * strength * (self.scores.get(key, 0.5) - 0.5))
        for key, factor in row.boost.items():
            if self.holds(key):
                weight *= factor
        return weight

    def holds(self, key: str) -> bool:
        if "=" not in key:
            return key in self.happened
        name, expected = key.split("=", 1)
        actual = self.facts.get(name)
        if isinstance(actual, bool):
            return expected == str(actual).lower()
        return actual is not None and str(actual) == expected


def meets(value: object, spec: Allowed) -> bool:
    if value is None:
        return False
    match spec:
        case bool():
            return value is spec
        case Between(min=low, max=high):
            return (
                isinstance(value, int)
                and (low is None or value >= low)
                and (high is None or value <= high)
            )
        case Except(excluded=excluded):
            return value not in excluded
        case _:
            return value in spec


def choose[T](rng: random.Random, items: Sequence[T], weights: Sequence[float]) -> T | None:
    """A weighted pick, or None when nothing has any weight."""
    if not items or sum(weights) <= 0:
        return None
    return rng.choices(items, weights)[0]


def fresh(rng: random.Random, options: Sequence[str], taken: Collection[str]) -> str:
    return rng.choice([option for option in options if option not in taken] or options)
