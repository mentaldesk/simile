from datetime import datetime, timedelta

from simile.schema import Flag, InteractionEvent, Relationship
from simile.social.config import DEFAULT_CONFIG, RelationshipConfig


def apply_event(
    rel: Relationship,
    event: InteractionEvent,
    now: datetime,
    *,
    config: RelationshipConfig = DEFAULT_CONFIG,
) -> Relationship:
    """How `rel.owner` feels about `rel.about` after `event`, something `rel.about` did to them."""
    if (event.actor, event.target) != (rel.about, rel.owner):
        raise ValueError(
            f"{event.actor}'s event for {event.target} doesn't change how {rel.owner} "
            f"feels about {rel.about}"
        )
    bias = config.negativity_bias if event.valence < 0 else 1.0
    dampening = max(config.dampening_floor, 1 - rel.familiarity)
    shift = event.valence * event.magnitude * config.max_shift * bias * dampening
    scores = {aspect.value: _clamp(getattr(rel, aspect.value) + shift) for aspect in event.aspects}
    familiarity = rel.familiarity + config.familiarity_gain * (1 - rel.familiarity)
    last = now if rel.last_interaction is None else max(rel.last_interaction, now)
    return _with(rel, **scores, familiarity=_clamp(familiarity), last_interaction=last)


def decay(
    rel: Relationship, elapsed: timedelta, *, config: RelationshipConfig = DEFAULT_CONFIG
) -> Relationship:
    """Drift toward the baseline after `elapsed` without contact. Flags are untouched."""
    if elapsed < timedelta(0):
        raise ValueError(f"elapsed must not be negative, not {elapsed}")

    def toward(score: float, target: float, half_life: timedelta) -> float:
        kept = 0.5 ** (elapsed / half_life)
        return _clamp(score * kept + target * (1 - kept), score, target)

    return _with(
        rel,
        like=toward(rel.like, rel.baseline.like, config.like_half_life),
        trust=toward(rel.trust, rel.baseline.trust, config.trust_half_life),
        respect=toward(rel.respect, rel.baseline.respect, config.respect_half_life),
        familiarity=toward(rel.familiarity, 0.0, config.familiarity_half_life),
    )


def open_flag(rel: Relationship, flag: Flag) -> Relationship:
    if any(existing.id == flag.id for existing in rel.flags):
        raise ValueError(f"{rel.owner} already has flag {flag.id} about {rel.about}")
    return _with(rel, flags=[*rel.flags, flag])


def resolve_flag(rel: Relationship, flag_id: str, when: datetime) -> Relationship:
    """Close an open flag, e.g. a debt repaid. A flag that's already resolved keeps its time."""
    if all(flag.id != flag_id for flag in rel.flags):
        raise KeyError(f"{rel.owner} has no flag {flag_id} about {rel.about}")
    flags = [
        Flag.model_validate(flag.model_dump() | {"resolved": when})
        if flag.id == flag_id and flag.resolved is None
        else flag
        for flag in rel.flags
    ]
    return _with(rel, flags=flags)


def _clamp(value: float, a: float = 0.0, b: float = 1.0) -> float:
    return min(max(value, min(a, b)), max(a, b))


def _with(rel: Relationship, **changes: object) -> Relationship:
    return Relationship.model_validate(rel.model_dump() | changes)
