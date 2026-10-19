import random
from collections.abc import Sequence

from simile.characters.humour import key, sample_humour
from simile.characters.tables import Tables, Village, sample_temperament
from simile.schema import Character


def humoured(
    characters: Sequence[Character], seed: int = 0, *, tables: Tables | None = None
) -> list[Character]:
    """`characters`, each one without a humour given one as generation draws it, from their
    values and a temperament drawn from them. Styles others in the cast have are less likely, so
    the cast has a spread of them."""
    village = Village()
    village.drawn.update(key(c.humour.style) for c in characters if c.humour)
    given = []
    for character in characters:
        if character.humour is None:
            rng = random.Random(f"{seed}:humour:{character.id}")
            scores = {value.value: score for value, score in character.values.items()}
            scores |= sample_temperament(rng, scores, tables=tables)
            humour = sample_humour(rng, scores, village=village)
            character = character.model_copy(update={"humour": humour})
        given.append(character)
    return given
