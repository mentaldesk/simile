import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from simile.schema import CoreValue, Id, Npc
from simile.story.config import DEFAULT_CONFIG, StoryConfig
from simile.story.content import Grievance


@dataclass(frozen=True)
class Suspect:
    npc: Npc
    grievance: Id
    hostility: float


def lean(npc: Npc, weights: Mapping[CoreValue, float]) -> float:
    """How far `npc`'s values lean the way `weights` point, from -0.5 to 0.5."""
    total = sum(abs(weight) for weight in weights.values()) or 1.0
    return sum(weight * (npc.values[value] - 0.5) for value, weight in weights.items()) / total


def fit(npc: Npc, grievance: Grievance) -> float:
    """How much `npc`'s values make `grievance` rankle, from -0.5 to 0.5."""
    return lean(npc, grievance.values)


def hostility(
    npc: Npc, grievances: Mapping[Id, Grievance], config: StoryConfig = DEFAULT_CONFIG
) -> float:
    """How hostile `npc` is to Aris: their best grievance's fit, plus `harm` from low Compassion."""
    best = max(fit(npc, grievance) for grievance in grievances.values())
    return best + config.harm * (0.5 - npc.values[CoreValue.COMPASSION])


def suspect(
    npc: Npc,
    grievances: Mapping[Id, Grievance],
    rng: random.Random,
    config: StoryConfig = DEFAULT_CONFIG,
) -> Suspect:
    """`npc` with a grievance drawn from those that fit them within `grievance_spread`."""
    fits = {kind: fit(npc, grievance) for kind, grievance in sorted(grievances.items())}
    best = max(fits.values())
    near = [kind for kind, score in fits.items() if score >= best - config.grievance_spread]
    return Suspect(npc, rng.choice(near), hostility(npc, grievances, config))


def attackers(
    npcs: Sequence[Npc],
    grievances: Mapping[Id, Grievance],
    rng: random.Random,
    config: StoryConfig = DEFAULT_CONFIG,
) -> list[Suspect]:
    """One to three hostile residents drawn by hostility, or the most hostile alone."""
    ranked = sorted(
        (suspect(npc, grievances, rng, config) for npc in sorted(npcs, key=lambda n: n.id)),
        key=lambda found: -found.hostility,
    )
    hostile = [found for found in ranked if found.hostility >= config.hostile_from]
    if not hostile:
        return ranked[:1]
    counts = sorted(config.attackers)
    count = min(rng.choices(counts, [config.attackers[n] for n in counts])[0], len(hostile))
    chosen: list[Suspect] = []
    pool = list(hostile)
    while len(chosen) < count:
        weights = [found.hostility - config.hostile_from + 0.05 for found in pool]
        pick = rng.choices(pool, weights)[0]
        chosen.append(pick)
        pool.remove(pick)
    return chosen
