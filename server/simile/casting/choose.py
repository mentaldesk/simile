import math
import random
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from functools import cache
from itertools import combinations
from typing import Literal

from simile.casting.config import DEFAULT_CONFIG, CastingConfig
from simile.casting.model import CastError, Pin
from simile.casting.roles import fits, holders, village_roles
from simile.characters import jobs
from simile.characters.tables.load import Role
from simile.npc.values import distance as profile_distance
from simile.schema import Character, CoreValue, Id, Medium

type Source = Literal["maker", "elder", "other"]


def value_distance(a: Character, b: Character) -> float:
    """The RMS difference of their core values, 0-1."""
    return profile_distance(a.values, b.values) / math.sqrt(len(CoreValue))


def distance(a: Character, b: Character, config: CastingConfig = DEFAULT_CONFIG) -> float:
    """How different two characters are, across values, origin, age, job family and gender."""
    w = config.weights
    return (
        w.values * value_distance(a, b)
        + w.origin * (a.origin != b.origin)
        + w.age * min(abs(a.birth_year - b.birth_year) / config.age_scale, 1.0)
        + w.occupation * (family(a) != family(b))
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
    roles: Sequence[Role] | None = None,
    year: int | None = None,
    config: CastingConfig = DEFAULT_CONFIG,
) -> list[Character]:
    """The picks and everyone pinned, as given, then a resident for each of the village's
    `roles` that's still open, then one for each of `crafts` nobody has yet, then drawn residents
    up to `count`. Draws spread the cast out, some of them clash with or share a resident's values
    on purpose, `maker_share` of those outside a role have a job from makers.toml, and the cast
    has its `elders`. Ages are as of `year`, this one by default."""
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

    roles = village_roles() if roles is None else list(roles)
    year = year or datetime.now(UTC).year
    rng = random.Random(seed)
    candidates = [character for character in characters if character.id not in wanted]

    def free() -> list[Character]:
        return [c for c in candidates if c.voice.reference_clip not in clips]

    def take(pick: Character) -> None:
        chosen.append(pick)
        candidates.remove(pick)
        if pick.voice.reference_clip is not None:
            clips[pick.voice.reference_clip] = pick.id

    held = holders(chosen, roles)
    for role in roles:
        if len(chosen) >= count or role in held.values():
            continue
        if fitting := [c for c in free() if fits(role, c)]:
            pick = (
                rng.choice(fitting) if not chosen else _best(fitting, chosen, "spread", rng, config)
            )
            take(pick)
            held[pick.id] = role

    for medium in config.crafts:
        if len(chosen) >= count or any(_medium(c) is medium for c in chosen):
            continue
        if crafted := [c for c in free() if _medium(c) is medium]:
            crafted = _narrow(crafted, "maker", chosen, held, year, config)
            pick = (
                rng.choice(crafted) if not chosen else _best(crafted, chosen, "spread", rng, config)
            )
            take(pick)

    kinds = _draws(count, len(chosen), rng, config)
    sources = _sources(count, len(kinds), chosen, held, year, rng, config)
    for kind, source in zip(kinds, sources, strict=True):
        if not (options := free()):
            raise CastError(f"Too few characters with a voice clip of their own for {count}")
        options = _narrow(options, source, chosen, held, year, config)
        take(rng.choice(options) if not chosen else _best(options, chosen, kind, rng, config))
    return chosen


def _medium(character: Character) -> Medium | None:
    return character.craft.medium if character.craft else None


def elder(character: Character, year: int, config: CastingConfig = DEFAULT_CONFIG) -> bool:
    """Over `elder_age`, with a trade from occupations.toml, working or retired."""
    return year - character.birth_year > config.elder_age and _trade(character.occupation)


def _sources(
    count: int,
    slots: int,
    chosen: Sequence[Character],
    held: dict[Id, Role],
    year: int,
    rng: random.Random,
    config: CastingConfig,
) -> list[Source]:
    """Where each draw comes from: elders until the cast has its `elders`, makers until
    `maker_share` of those outside a role have a job from makers.toml, and the rest someone
    without one."""
    others = [c for c in chosen if c.id not in held]
    makers = _rounded(config.maker_share * (len(others) + slots))
    makers -= sum(_maker(c.occupation) for c in others)
    elders = _rounded(config.elders * count / 10) - sum(elder(c, year, config) for c in chosen)
    elders = min(max(elders, 0), slots)
    makers = min(max(makers, 0), slots - elders)
    sources: list[Source] = ["elder"] * elders + ["maker"] * makers
    sources += ["other"] * (slots - len(sources))
    rng.shuffle(sources)
    return sources


def _narrow(
    free: list[Character],
    source: Source,
    chosen: Sequence[Character],
    held: dict[Id, Role],
    year: int,
    config: CastingConfig,
) -> list[Character]:
    """Those from `source` in a job family nobody has yet, relaxing that until someone fits.
    Nobody else has a job a role names once it's filled, like a second barista."""
    named = {title.casefold() for role in held.values() for title in role.jobs}
    families = {family(c) for c in chosen}
    sourced: dict[Source, Callable[[Character], bool]] = {
        "maker": lambda c: _maker(c.occupation),
        "elder": lambda c: elder(c, year, config),
        "other": lambda c: not _maker(c.occupation),
    }
    unnamed = [c for c in free if c.occupation.casefold() not in named]
    from_source = [c for c in unnamed if sourced[source](c)]
    for options in ([c for c in from_source if family(c) not in families], from_source, unnamed):
        if options:
            return options
    return free


def _rounded(x: float) -> int:
    return math.floor(x + 0.5)


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


def family(character: Character) -> str:
    """The family of their job, as in makers.toml, or occupations.toml's group."""
    return _family(character.occupation)


_family = cache(jobs.family)
_maker = cache(jobs.maker)
_trade = cache(jobs.trade)
