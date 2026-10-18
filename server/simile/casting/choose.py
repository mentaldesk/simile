import math
import random
from collections.abc import Sequence
from functools import cache
from itertools import combinations

from simile.casting.config import DEFAULT_CONFIG, CastingConfig
from simile.casting.model import CastError, Pin
from simile.npc.values import distance as profile_distance
from simile.schema import Character, CoreValue, Id


def value_distance(a: Character, b: Character) -> float:
    """The RMS difference of their core values, 0-1."""
    return profile_distance(a.values, b.values) / math.sqrt(len(CoreValue))


def distance(a: Character, b: Character, config: CastingConfig = DEFAULT_CONFIG) -> float:
    """How different two characters are, across values, origin, age, occupation and gender."""
    w = config.weights
    return (
        w.values * value_distance(a, b)
        + w.origin * (a.origin != b.origin)
        + w.age * min(abs(a.birth_year - b.birth_year) / config.age_scale, 1.0)
        + w.occupation * (_category(a.occupation) != _category(b.occupation))
        + w.gender * (a.gender != b.gender)
    )


def spread(characters: Sequence[Character], config: CastingConfig = DEFAULT_CONFIG) -> float:
    """The mean distance between two of them."""
    pairs = list(combinations(characters, 2))
    return sum(distance(a, b, config) for a, b in pairs) / len(pairs) if pairs else 0.0


def conflicts(
    characters: Sequence[Character], config: CastingConfig = DEFAULT_CONFIG
) -> list[tuple[Character, Character]]:
    return [
        (a, b) for a, b in combinations(characters, 2) if value_distance(a, b) >= config.conflict
    ]


def affinities(
    characters: Sequence[Character], config: CastingConfig = DEFAULT_CONFIG
) -> list[tuple[Character, Character]]:
    return [
        (a, b) for a, b in combinations(characters, 2) if value_distance(a, b) <= config.affinity
    ]


def cast(
    characters: Sequence[Character],
    count: int | None = None,
    picks: Sequence[Id] = (),
    pins: Sequence[Pin] = (),
    seed: int = 0,
    *,
    houses: int | None = None,
    config: CastingConfig = DEFAULT_CONFIG,
) -> list[Character]:
    """The picks and everyone pinned, as given, then drawn residents up to `count`. Draws spread
    the cast out, and some of them clash with or share a resident's values on purpose."""
    library = {character.id: character for character in characters}
    wanted = list(dict.fromkeys([*picks, *(id for pin in pins for id in (pin.actor, pin.target))]))
    if unknown := [id for id in wanted if id not in library]:
        raise CastError(f"No character {', '.join(unknown)} in the library")
    count = len(wanted) if count is None else count
    if count < max(len(wanted), 1):
        raise CastError(f"A cast of {count} can't hold the {len(wanted)} picked and pinned")
    if houses is None:
        from simile.casting.bind import village_houses

        houses = len(village_houses())
    if count > houses:
        raise CastError(f"The village has {houses} houses, too few for {count} residents")
    if count > len(library):
        raise CastError(f"The library has {len(library)} characters, too few for {count}")

    chosen = [library[id] for id in wanted]
    clips: dict[str, Id] = {}
    for character in chosen:
        if (clip := character.voice.reference_clip) is not None:
            if clip in clips:
                raise CastError(f"{clips[clip]} and {character.id} share the voice clip {clip}")
            clips[clip] = character.id

    rng = random.Random(seed)
    candidates = [character for character in characters if character.id not in wanted]
    for kind in _draws(count, len(chosen), rng, config):
        free = [c for c in candidates if c.voice.reference_clip not in clips]
        if not free:
            raise CastError(f"Too few characters with a voice clip of their own for {count}")
        pick = rng.choice(free) if not chosen else _best(free, chosen, kind, rng, config)
        chosen.append(pick)
        candidates.remove(pick)
        if pick.voice.reference_clip is not None:
            clips[pick.voice.reference_clip] = pick.id
    return chosen


def _draws(count: int, given: int, rng: random.Random, config: CastingConfig) -> list[str]:
    slots = count - given
    clash = min(round(count * config.conflict_share), slots)
    share = min(round(count * config.affinity_share), slots - clash)
    kinds = ["conflict"] * clash + ["affinity"] * share + ["spread"] * (slots - clash - share)
    rng.shuffle(kinds)
    if given == 0 and kinds:
        kinds.remove("spread" if "spread" in kinds else kinds[0])
        kinds.insert(0, "first")
    return kinds


def _best(
    free: list[Character],
    chosen: list[Character],
    kind: str,
    rng: random.Random,
    config: CastingConfig,
) -> Character:
    if kind == "spread":
        ranked = sorted(free, key=lambda c: -min(distance(c, m, config) for m in chosen))
        return rng.choice(ranked[: config.choices])
    apart = {c.id: [value_distance(c, m) for m in chosen] for c in free}
    if kind == "conflict":
        ranked = sorted(free, key=lambda c: -max(apart[c.id]))
        fits = [c for c in ranked if max(apart[c.id]) >= config.conflict]
    else:
        ranked = sorted(free, key=lambda c: min(apart[c.id]))
        fits = [c for c in ranked if min(apart[c.id]) <= config.affinity]
    return rng.choice(fits[: config.choices] or ranked[:1])


@cache
def _category(occupation: str) -> str:
    from simile.characters.pool import occupation_category

    return occupation_category(occupation)
