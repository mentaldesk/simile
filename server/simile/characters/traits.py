from collections.abc import Mapping

from simile.schema import CoreValue, Traits

STRETCH = 1.25
"""Averaging pulls scores towards 0.5, so each trait is pushed back out by this much."""

RECIPES: dict[str, tuple[tuple[str, float], ...]] = {
    "sociability": (("sociability", 0.5), ("liveliness", 0.2), ("connection", 0.3)),
    "negativity_bias": (("anxiety", 0.4), ("fearfulness", 0.2), ("optimism", -0.4)),
    "forgiveness": (("forgivingness", 0.6), ("gentleness", 0.2), ("compassion", 0.2)),
    "first_impressions": (("prudence", -0.4), ("patience", -0.3), ("open_mindedness", -0.3)),
}
"""Each trait from temperament facets and core values. A negative weight counts the low end."""


def derive_traits(values: Mapping[CoreValue, float], temperament: Mapping[str, float]) -> Traits:
    scores = {value.value: score for value, score in values.items()} | dict(temperament)
    traits = {}
    for trait, recipe in RECIPES.items():
        mix = sum(abs(w) * (scores[key] if w > 0 else 1 - scores[key]) for key, w in recipe)
        traits[trait] = round(min(1.0, max(0.0, 0.5 + STRETCH * (mix - 0.5))), 2)
    return Traits(**traits)
