import math
import random
from collections.abc import Mapping, Sequence

from simile.characters.tables.census import Skeleton
from simile.characters.tables.conditions import Context, choose
from simile.characters.tables.events import Happening
from simile.characters.tables.load import Tables, load_tables

GAIN = 1.6
NOISE = 0.7
FACET_NOISE = 0.5


def sample_temperament(
    rng: random.Random,
    values: Mapping[str, float],
    *,
    fixed: Mapping[str, float] | None = None,
    tables: Tables | None = None,
) -> dict[str, float]:
    """HEXACO scores, 0-1: domains pulled by the core values, facets scattered around them."""
    t = tables or load_tables()
    scores = dict(fixed or {})
    for domain in t.temperament.domain:
        if domain.id not in scores:
            norm = math.sqrt(sum(s * s for s in domain.values.values()))
            pull = sum(s * (2 * values.get(v, 0.5) - 1) for v, s in domain.values.items()) / norm
            scores[domain.id] = round(_logistic(GAIN * pull + rng.gauss(0, NOISE)), 2)
        centre = _logit(scores[domain.id])
        for facet in domain.facet:
            if facet.id not in scores:
                scores[facet.id] = round(_logistic(centre + rng.gauss(0, FACET_NOISE)), 2)
    return scores


def describe_temperament(
    scores: Mapping[str, float], *, threshold: float = 0.25, tables: Tables | None = None
) -> list[str]:
    """The facets furthest from average, most extreme first, in plain words."""
    t = tables or load_tables()
    facets = [facet for domain in t.temperament.domain for facet in domain.facet]
    extreme = [f for f in facets if abs(scores.get(f.id, 0.5) - 0.5) >= threshold]
    extreme.sort(key=lambda f: -abs(scores[f.id] - 0.5))
    return [f.high if scores[f.id] > 0.5 else f.low for f in extreme]


def sample_attachment(
    rng: random.Random,
    skeleton: Skeleton,
    scores: Mapping[str, float],
    events: Sequence[Happening],
    *,
    tables: Tables | None = None,
) -> str:
    """An attachment style, conditioned on temperament and on how they grew up."""
    t = tables or load_tables()
    context = Context(skeleton.facts(), scores, frozenset(e.id for e in events))
    styles = t.temperament.attachment
    picked = choose(rng, [s.id for s in styles], [context.weight(s, s.weight) for s in styles])
    return picked or styles[0].id


def _logistic(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def _logit(p: float) -> float:
    p = min(max(p, 0.01), 0.99)
    return math.log(p / (1 - p))
