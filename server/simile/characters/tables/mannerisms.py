import random
from collections.abc import Mapping

from simile.characters.tables.conditions import Context, Village
from simile.characters.tables.load import Tables, load_tables

COUNT = 2


def sample_mannerisms(
    rng: random.Random,
    scores: Mapping[str, float],
    *,
    count: int = COUNT,
    village: Village | None = None,
    tables: Tables | None = None,
) -> list[str]:
    """Mannerisms that fit their temperament, none already used in `village`."""
    t = tables or load_tables()
    taken = village or Village()
    context = Context(scores=scores)
    pool = [
        (item, context.weight(group) * taken.damping(item, rare=True))
        for group in t.mannerisms.group
        for item in group.items
    ]
    picked: list[str] = []
    while len(picked) < count and (pool := [(i, w) for i, w in pool if w > 0 and i not in picked]):
        picked.append(rng.choices([i for i, _ in pool], [w for _, w in pool])[0])
    if village is not None:
        village.drawn.update(picked)
    return picked
