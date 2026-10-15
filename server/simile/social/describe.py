from itertools import chain, repeat

from simile.schema import Aspect, FlagKind, Relationship
from simile.social.config import DEFAULT_CONFIG, RelationshipConfig

FEELINGS: dict[Aspect, dict[int, str]] = {
    Aspect.LIKE: {2: "like {} a lot", 1: "like {}", -1: "dislike {}", -2: "can't stand {}"},
    Aspect.TRUST: {
        2: "trust {} completely",
        1: "trust {}",
        -1: "don't trust {}",
        -2: "don't trust {} at all",
    },
    Aspect.RESPECT: {
        2: "have great respect for {}",
        1: "respect {}",
        -1: "don't think much of {}",
        -2: "have no respect for {}",
    },
}

FLAGS: dict[FlagKind, str] = {
    FlagKind.DEBT: "{name} still owes you for {description}.",
    FlagKind.GRUDGE: "You hold a grudge against {name} over {description}.",
    FlagKind.PROMISE: "{name} made you a promise they haven't kept yet: {description}.",
    FlagKind.BROKEN_PROMISE: "{name} broke a promise to you: {description}.",
    FlagKind.SAVED_LIFE: "{name} once saved your life: {description}.",
    FlagKind.SECRET: "{name} trusted you with a secret: {description}.",
}


def describe(rel: Relationship, name: str, *, config: RelationshipConfig = DEFAULT_CONFIG) -> str:
    """A second-person summary of how `rel.owner` feels about `rel.about`, whose name is `name`."""
    refer = chain([name], repeat("them"))
    clauses = [
        (level > 0, FEELINGS[aspect][level])
        for aspect in Aspect
        if (level := _level(getattr(rel, aspect.value), config))
    ]
    if clauses:
        first = clauses[0][0]
        same = [clause.format(next(refer)) for positive, clause in clauses if positive == first]
        other = [clause.format(next(refer)) for positive, clause in clauses if positive != first]
        feelings = f"You {_join(same)} but {_join(other)}." if other else f"You {_join(same)}."
    else:
        feelings = f"You have no strong feelings about {next(refer)}."

    if rel.familiarity < config.barely_known:
        familiarity = f"You barely know {next(refer)}."
    elif rel.familiarity < config.well_known:
        familiarity = f"You know {next(refer)} a little."
    else:
        familiarity = f"You know {next(refer)} well."

    flags = [
        FLAGS[flag.kind].format(name=name, description=flag.description)
        for flag in sorted(rel.flags, key=lambda flag: flag.created)
        if flag.resolved is None
    ]
    return " ".join([feelings, familiarity, *flags])


def _level(score: float, config: RelationshipConfig) -> int:
    if score >= 0.5 + config.strong_feeling:
        return 2
    if score >= 0.5 + config.mild_feeling:
        return 1
    if score <= 0.5 - config.strong_feeling:
        return -2
    if score <= 0.5 - config.mild_feeling:
        return -1
    return 0


def _join(clauses: list[str]) -> str:
    return clauses[0] if len(clauses) == 1 else f"{', '.join(clauses[:-1])} and {clauses[-1]}"
