import itertools
import math
import random
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from simile.characters.brief import Brief
from simile.characters.tables import (
    YEAR,
    Happening,
    Skeleton,
    Tables,
    Tension,
    Village,
    load_tables,
    origins_for,
    sample_attachment,
    sample_events,
    sample_mannerisms,
    sample_skeleton,
    sample_temperament,
    sample_tension,
)
from simile.characters.tables.conditions import LEAN, choose
from simile.characters.tables.load import Job
from simile.npc import values as npc_values
from simile.schema import Build, CoreValue, HairStyle, HookKind, HookSide

type Profile = dict[CoreValue, float]

V, H, S, Hair = CoreValue, HookKind, HookSide, HairStyle

YOUNGEST, OLDEST = 18, 90
MEAN_AGE, AGE_PULL, AGE_SPREAD = 46, 20, 15
STABILITY = (V.TRADITION, V.SECURITY, V.OBEDIENCE)
NOVELTY = (V.ADVENTURE, V.FREEDOM, V.PLEASURE)
LOCAL_ACCENT_BEFORE = 12
"""Someone who arrived younger than this speaks with the local accent."""
PARTICLES = frozenset({"de", "del", "della", "dela", "di", "da", "dos", "du", "van", "von", "le"})
CONTRADICTION_SALIENCE, CONTRADICTION_VALENCE = 0.7, -0.5

PER_ROLE = 2
"""Characters a pool plans for each of the village's roles, so casts don't all share them."""
MAKER_SHARE = 0.7
"""Of the pool's other characters, the share with a job from makers.toml, as in casting."""
ELDER_FROM, ELDER_OLDEST = 60, 88
"""A pool's other characters are over `ELDER_FROM`, with a trade from occupations.toml."""
YOUNGER = 10
"""Years younger than their values alone make them for a role or maker, as elders are planned."""
INTERESTS = (
    "computer games",
    "board games",
    "a science",
    "ideas: philosophy, maths or where the world is heading",
    "making, fixing or tinkering with things",
)
"""One of these goes into each character's interests, alongside everyday ones."""

HOOK_COUNTS, HOOK_COUNT_WEIGHTS = (2, 3, 4), (2, 2, 1)
HOOK_LEANS: dict[tuple[HookKind, HookSide], tuple[CoreValue, float] | None] = {
    (H.ESTRANGED_SIBLING, S.MUTUAL): None,
    (H.EX_PARTNER, S.MUTUAL): None,
    (H.OLD_FRIEND, S.MUTUAL): (V.CONNECTION, 1),
    (H.RIVAL, S.MUTUAL): (V.AMBITION, 1),
    (H.DEBT, S.ACTOR): (V.DISCIPLINE, -1),
    (H.DEBT, S.TARGET): (V.COMPASSION, 1),
    (H.SECRET, S.ACTOR): None,
    (H.SECRET, S.TARGET): (V.HONESTY, 1),
    (H.BETRAYAL, S.ACTOR): (V.LOYALTY, -1),
    (H.BETRAYAL, S.TARGET): (V.LOYALTY, 1),
    (H.SAVED_LIFE, S.ACTOR): (V.ADVENTURE, 1),
    (H.SAVED_LIFE, S.TARGET): None,
}

HAIR: dict[str, dict[HairStyle, float]] = {
    "woman": {
        Hair.BALD: 0.1,
        Hair.BUZZ: 0.4,
        Hair.SHORT: 2,
        Hair.CURLY: 1.5,
        Hair.BOB: 2,
        Hair.LONG: 2.5,
        Hair.PONYTAIL: 1.5,
        Hair.BUN: 1.5,
    },
    "man": {
        Hair.BALD: 1,
        Hair.BUZZ: 2,
        Hair.SHORT: 4,
        Hair.CURLY: 1.5,
        Hair.BOB: 0.1,
        Hair.LONG: 0.5,
        Hair.PONYTAIL: 0.4,
        Hair.BUN: 0.2,
    },
}
BALDING_FROM, BALDING_PER_YEAR = 35, 0.08
BUILDS = {Build.SLIM: 1, Build.AVERAGE: 2, Build.BROAD: 1}
TOPS = {
    **dict.fromkeys(("night", "slate", "steel", "concrete", "pavement", "white", "cream"), 2),
    **dict.fromkeys(("sand", "tan", "brown", "umber", "espresso", "maroon", "green"), 2),
    **dict.fromkeys(("forest", "deep", "plum", "navy"), 2),
    **dict.fromkeys(("ice", "red", "orange", "amber", "yellow", "lime", "blue"), 1),
    **dict.fromkeys(("cyan", "magenta", "pink", "neon", "violet"), 1),
}
"""Palette colours for a top, muted ones twice as likely as bright ones."""


@dataclass(frozen=True)
class Sheet:
    """Everything decided in code before Claude writes the character."""

    skeleton: Skeleton
    country: str
    accent: str | None
    """The accent their voice is designed or recorded with, or None for the local one."""
    values: Profile
    temperament: dict[str, float]
    attachment: str
    events: list[Happening]
    tension: Tension
    mannerisms: list[str]
    hooks: list[tuple[HookKind, HookSide]]
    look: "Look | None" = None
    interest: str | None = None
    """What one of their interests is about."""

    def seeds(self) -> list["Seed"]:
        """What happened to them in age order, each to become one past memory."""
        seeds = [Seed(e.age, e.text, e.impact / 100, e.valence) for e in self.events]
        if c := self.tension.contradiction:
            against = f"{c.text}, against their own {c.value.replace('_', ' ')}"
            seeds.append(Seed(c.age, against, CONTRADICTION_SALIENCE, CONTRADICTION_VALENCE))
        return sorted(seeds, key=lambda seed: seed.age)


@dataclass(frozen=True)
class Seed:
    age: int
    text: str
    salience: float
    valence: float


@dataclass(frozen=True)
class Slot:
    """What a slot in a pool's plan is for: one of the village's roles, a job from makers.toml,
    or someone over 60 with a trade from occupations.toml."""

    kind: Literal["role", "maker", "elder"]
    role: str | None = None


@dataclass(frozen=True)
class Look:
    """The parts of their appearance drawn in code, so the pool doesn't all look alike."""

    build: Build
    hair_style: HairStyle
    top: str
    """A palette colour name."""


def draw(
    rng: random.Random,
    brief: Brief | None = None,
    *,
    village: Village | None = None,
    tables: Tables | None = None,
    slot: Slot | None = None,
) -> Sheet:
    """The code stages in order, each sampling only what `brief` doesn't lock. A `slot` says
    which jobs they can have."""
    brief = brief or Brief()
    t = tables or load_tables()
    values = sample_values(rng, brief.values, brief.latent)
    age = YEAR - brief.birth_year if brief.birth_year is not None else sample_age(rng, values)
    fixed, country = _fixed(rng, brief, t)
    jobs = None if slot is None or "occupation" in fixed else _slot_jobs(slot, t)
    if jobs and brief.birth_year is None:
        youngest, oldest = min(j.ages[0] for j in jobs), max(j.ages[1] for j in jobs)
        age = min(max(age - YOUNGER, youngest, YOUNGEST), oldest)
    elder = slot is not None and slot.kind == "elder"
    if elder and brief.birth_year is None and age <= ELDER_FROM:
        age = rng.randint(ELDER_FROM + 1, ELDER_OLDEST)
    skeleton = sample_skeleton(rng, age, village=village, tables=t, jobs=jobs, trade=elder, **fixed)
    origin = t.origin[skeleton.origin]
    country = country or origin.country.removeprefix("the ")
    accent = origin.accent if country == origin.country.removeprefix("the ") else f"from {country}"
    arrived = skeleton.arrived_at
    if skeleton.born_here or (arrived is not None and arrived < LOCAL_ACCENT_BEFORE):
        accent = None
    scores = {value.value: score for value, score in values.items()}
    temperament = sample_temperament(rng, scores, tables=t)
    scores |= temperament
    events = (
        []
        if brief.locked("past")
        else sample_events(rng, skeleton, scores, village=village, tables=t)
    )
    attachment = sample_attachment(rng, skeleton, scores, events, tables=t)
    tension = sample_tension(rng, skeleton, scores, events, attachment, village=village, tables=t)
    mannerisms = (
        list(brief.mannerisms or [])
        if brief.locked("mannerisms")
        else sample_mannerisms(rng, temperament, village=village, tables=t)
    )
    hooks = [] if brief.locked("hooks") else sample_hooks(rng, skeleton, values, village=village)
    look = None if brief.locked("appearance") else sample_look(rng, skeleton, village=village)
    interest = None if brief.locked("interests") else sample_interest(rng, village=village)
    return Sheet(
        skeleton,
        country,
        accent,
        values,
        temperament,
        attachment,
        events,
        tension,
        mannerisms,
        hooks,
        look,
        interest,
    )


def plan(count: int, seed: int, *, tables: Tables | None = None) -> list[Sheet]:
    """A pool's sheets: values spread across the pool, nothing rare drawn twice, and jobs as
    `slots` gives them. The first `n` sheets are the same for any count of `n` or more, so a pool
    can grow."""
    t = tables or load_tables()
    profiles = npc_values.sample_values(count, random.Random(seed))
    village = Village()
    return [
        draw(
            random.Random(f"{seed}:{n}"),
            Brief(values=profile),
            village=village,
            tables=t,
            slot=slot,
        )
        for n, (profile, slot) in enumerate(zip(profiles, slots(t), strict=False))
    ]


def slots(tables: Tables | None = None) -> Iterator[Slot]:
    """`PER_ROLE` slots for each of the village's roles, then slots for jobs from makers.toml
    and for elders, `MAKER_SHARE` of them makers, spread evenly."""
    t = tables or load_tables()
    for _ in range(PER_ROLE):
        for role in t.roles:
            yield Slot("role", role.id)
    others = 1 - MAKER_SHARE
    for n in itertools.count():
        elder = math.floor((n + 1) * others + 0.5) > math.floor(n * others + 0.5)
        yield Slot("elder") if elder else Slot("maker")


def sample_values(
    rng: random.Random, locked: Mapping[CoreValue, float], latent: Mapping[str, float]
) -> Profile:
    """`simile.npc.values`' model, with any latent trait or core value the player locked."""
    traits = [latent[name] if name in latent else rng.gauss(0, 1) for name in npc_values.TRAITS]
    profile = {}
    for value, loadings in npc_values.LOADINGS.items():
        pull = npc_values.GAIN * _dot(loadings, traits) + rng.gauss(0, npc_values.NOISE)
        profile[value] = round(_logistic(pull), 2)
    return profile | dict(locked)


def sample_age(rng: random.Random, values: Profile) -> int:
    """Older for those who value stability over novelty."""
    settled = (sum(values[v] for v in STABILITY) - sum(values[v] for v in NOVELTY)) / 3
    age = round(rng.gauss(MEAN_AGE + AGE_PULL * settled, AGE_SPREAD))
    return min(OLDEST, max(YOUNGEST, age))


def sample_hooks(
    rng: random.Random,
    skeleton: Skeleton,
    values: Profile,
    *,
    village: Village | None = None,
) -> list[tuple[HookKind, HookSide]]:
    """Two to four open ties of different kinds, leaning on their values. A village spreads
    kinds and sides, so casting finds an actor for each target."""
    taken = village or Village()
    count = rng.choices(HOOK_COUNTS, HOOK_COUNT_WEIGHTS)[0]
    options = list(HOOK_LEANS)
    hooks: list[tuple[HookKind, HookSide]] = []
    while len(hooks) < count:
        weights = [
            0.0
            if kind in {k for k, _ in hooks}
            else _hook_weight(kind, side, skeleton, values) * taken.damping(_hook_key(kind, side))
            for kind, side in options
        ]
        pick = choose(rng, options, weights)
        if pick is None:
            break
        hooks.append(pick)
    if village is not None:
        village.drawn.update(_hook_key(kind, side) for kind, side in hooks)
    return hooks


def sample_interest(rng: random.Random, *, village: Village | None = None) -> str:
    """One of `INTERESTS`, the ones neighbours already have less likely."""
    taken = village or Village()
    interest = rng.choices(INTERESTS, [taken.damping(f"interest:{i}") for i in INTERESTS])[0]
    if village is not None:
        village.drawn[f"interest:{interest}"] += 1
    return interest


def sample_look(rng: random.Random, skeleton: Skeleton, *, village: Village | None = None) -> Look:
    """A build, a hair style for their gender and age, and a top colour neighbours seldom wear."""
    taken = village or Village()
    if skeleton.gender in HAIR:
        hair = dict(HAIR[skeleton.gender])
    else:
        hair = {style: (HAIR["woman"][style] + HAIR["man"][style]) / 2 for style in HairStyle}
    if skeleton.gender == "man":
        hair[Hair.BALD] *= 1 + BALDING_PER_YEAR * max(0, skeleton.age - BALDING_FROM)
    tops = list(TOPS)
    top = rng.choices(tops, [TOPS[c] * taken.damping(f"top:{c}") for c in tops])[0]
    if village is not None:
        village.drawn[f"top:{top}"] += 1
    return Look(
        build=rng.choices(list(BUILDS), list(BUILDS.values()))[0],
        hair_style=rng.choices(list(hair), list(hair.values()))[0],
        top=top,
    )


def split_name(name: str) -> tuple[str, str]:
    words = name.split()
    if len(words) < 2:
        return name.strip(), ""
    cut = -2 if len(words) > 2 and words[-2].casefold() in PARTICLES else -1
    return " ".join(words[:cut]), " ".join(words[cut:])


def _fixed(rng: random.Random, brief: Brief, t: Tables) -> tuple[dict[str, object], str | None]:
    """The census fields `brief` locks, and the country when it's locked."""
    fixed: dict[str, object] = dict(brief.facts)
    if brief.birth_year is not None:
        fixed["birth_year"] = brief.birth_year
    if brief.gender is not None:
        fixed["gender"] = brief.gender.value
    if brief.name is not None:
        fixed["given"], fixed["family"] = split_name(brief.name)
    country = None
    if brief.origin is not None:
        country = brief.origin
        try:
            ids = origins_for(country, tables=t)
        except ValueError:
            if brief.name is None:
                raise
            ids = _named(t, str(fixed["given"]), str(fixed["family"])) or [o.id for o in t.origins]
        else:
            country = None
    elif brief.name is not None:
        ids = _named(t, str(fixed["given"]), str(fixed["family"]))
    else:
        ids = []
    if ids and "origin" not in fixed:
        fixed["origin"] = choose(rng, ids, [t.origin[id].weight for id in ids])
    if brief.locked("arrival"):
        fixed["born_here"] = brief.arrival is None
        if brief.arrival is not None:
            fixed["arrived_at"] = brief.arrival.age
            reason = brief.arrival.reason
            fixed["arrival"] = next(
                (a.id for a in t.census.arrival if a.text.removeprefix("came ") == reason), reason
            )
    if brief.occupation is not None:
        fixed["occupation"] = brief.occupation[0].lower() + brief.occupation[1:]
    return fixed, country


def _slot_jobs(slot: Slot, t: Tables) -> list[Job] | None:
    if slot.kind == "maker":
        return t.maker_jobs
    if slot.kind == "role":
        return t.role_jobs(next(role for role in t.roles if role.id == slot.role))
    return None


def _named(t: Tables, given: str, family: str) -> list[str]:
    """The origins whose name lists hold the most of this given name and surname."""
    scores = {
        origin.id: (
            given in {n for era in (*origin.women.values(), *origin.men.values()) for n in era}
        )
        + (family in origin.surnames)
        for origin in t.origins
    }
    best = max(scores.values())
    return [id for id, score in scores.items() if score == best] if best else []


def _hook_weight(kind: HookKind, side: HookSide, skeleton: Skeleton, values: Profile) -> float:
    if kind is H.ESTRANGED_SIBLING and skeleton.siblings == 0:
        return 0.0
    if kind is H.EX_PARTNER and skeleton.age < 20:
        return 0.0
    lean = HOOK_LEANS[(kind, side)]
    if lean is None:
        return 1.0
    value, strength = lean
    return math.exp(LEAN * strength * (values[value] - 0.5))


def _hook_key(kind: HookKind, side: HookSide) -> str:
    return f"hook:{kind}:{side}"


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def _logistic(x: float) -> float:
    return 1 / (1 + math.exp(-x))
