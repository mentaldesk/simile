import math
import random
from collections.abc import Iterable, Sequence

from simile.schema import CoreValue

type Profile = dict[CoreValue, float]

V = CoreValue

# Openness to change vs conservation and self-transcendence vs self-enhancement are Schwartz's axes.
TRAITS = ("openness", "transcendence", "outlook", "rigour")

LOADINGS: dict[CoreValue, tuple[float, float, float, float]] = {
    V.FREEDOM: (0.85, 0.0, 0.1, -0.2),
    V.INDEPENDENCE: (0.7, -0.3, 0.0, 0.1),
    V.SELF_RESPECT: (0.2, -0.4, 0.1, 0.3),
    V.SELF_ACTUALIZATION: (0.6, 0.1, 0.2, 0.2),
    V.CREATIVITY: (0.75, 0.1, 0.2, -0.2),
    V.HONESTY: (0.0, 0.5, 0.0, 0.4),
    V.COMPASSION: (0.0, 0.85, 0.2, 0.0),
    V.LOYALTY: (-0.4, 0.5, 0.0, 0.3),
    V.JUSTICE: (0.2, 0.7, 0.0, 0.2),
    V.RESPONSIBILITY: (-0.4, 0.3, 0.0, 0.6),
    V.SECURITY: (-0.75, -0.1, -0.3, 0.2),
    V.EQUALITY: (0.3, 0.75, 0.1, -0.1),
    V.TRADITION: (-0.85, 0.2, 0.0, 0.1),
    V.OBEDIENCE: (-0.85, 0.0, 0.0, 0.3),
    V.SUCCESS: (-0.1, -0.8, 0.1, 0.3),
    V.AMBITION: (0.2, -0.8, 0.2, 0.3),
    V.DISCIPLINE: (-0.4, -0.1, 0.0, 0.75),
    V.KNOWLEDGE: (0.5, 0.2, 0.0, 0.4),
    V.OPEN_MINDEDNESS: (0.75, 0.4, 0.1, -0.1),
    V.PEACE_OF_MIND: (-0.4, 0.3, 0.2, -0.1),
    V.PLEASURE: (0.4, -0.4, 0.4, -0.6),
    V.CONNECTION: (0.0, 0.6, 0.5, 0.0),
    V.ADVENTURE: (0.8, -0.2, 0.4, -0.3),
    V.OPTIMISM: (0.1, 0.1, 0.9, 0.0),
}

GAIN = 1.2
NOISE = 0.6
POOL_SIZE = 200


def sample_profile(rng: random.Random) -> Profile:
    """Shared latent traits plus a personal quirk per value, squashed to 0-1."""
    traits = [rng.gauss(0, 1) for _ in TRAITS]
    return {
        value: round(_logistic(GAIN * _dot(loadings, traits) + rng.gauss(0, NOISE)), 2)
        for value, loadings in LOADINGS.items()
    }


def distance(a: Profile, b: Profile) -> float:
    return math.dist([a[v] for v in CoreValue], [b[v] for v in CoreValue])


def spread(pool: Sequence[Profile], count: int) -> list[Profile]:
    """Farthest-point sampling: each pick is the profile farthest from every one picked so far."""
    chosen = [pool[0]]
    nearest = [distance(p, pool[0]) for p in pool]
    while len(chosen) < count:
        pick = max(range(len(pool)), key=nearest.__getitem__)
        chosen.append(pool[pick])
        nearest = [min(d, distance(p, pool[pick])) for d, p in zip(nearest, pool, strict=True)]
    return chosen


def sample_values(count: int, rng: random.Random, pool_size: int = POOL_SIZE) -> list[Profile]:
    return spread([sample_profile(rng) for _ in range(max(pool_size, count))], count)


def ranked(profile: Profile) -> list[tuple[CoreValue, float]]:
    return sorted(profile.items(), key=lambda item: -item[1])


def format_scores(items: Iterable[tuple[CoreValue, float]]) -> str:
    return ", ".join(f"{value.value.replace('_', ' ')} {score:.2f}" for value, score in items)


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def _logistic(x: float) -> float:
    return 1 / (1 + math.exp(-x))
