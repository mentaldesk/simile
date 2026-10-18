import math
from collections.abc import Iterable
from datetime import datetime, timedelta

from simile.schema import Aspect, Baseline, Flag, InteractionEvent, Npc, Relationship, Traits
from simile.social.config import DEFAULT_CONFIG, RelationshipConfig
from simile.social.traits import trait_factor, traits_of

NEUTRAL = 0.5


def meet(owner: Npc, about: str, *, config: RelationshipConfig = DEFAULT_CONFIG) -> Relationship:
    """How `owner` feels about someone new: at a baseline set by their own core values."""
    baseline = Baseline.model_validate(
        {aspect.value: _baseline(owner, aspect, config) for aspect in Aspect}
    )
    return Relationship(
        owner=owner.id, about=about, **baseline.model_dump(), familiarity=0.0, baseline=baseline
    )


def as_of(
    rel: Relationship,
    now: datetime,
    *,
    config: RelationshipConfig = DEFAULT_CONFIG,
    traits: Traits | None = None,
) -> Relationship:
    """`rel` decayed from its last interaction to `now`. Read through this but don't store it:
    store `apply_event(as_of(rel, now), event, now)`, so each stretch of time decays once."""
    if rel.last_interaction is None:
        return rel
    return decay(rel, max(now - rel.last_interaction, timedelta(0)), config=config, traits=traits)


def apply_event(
    rel: Relationship,
    event: InteractionEvent,
    now: datetime,
    *,
    config: RelationshipConfig = DEFAULT_CONFIG,
    traits: Traits | None = None,
) -> Relationship:
    """How `rel.owner` feels about `rel.about` after `event`, something `rel.about` did to them."""
    return apply_events(rel, [event], now, config=config, traits=traits)


def apply_events(
    rel: Relationship,
    events: Iterable[InteractionEvent],
    now: datetime,
    *,
    config: RelationshipConfig = DEFAULT_CONFIG,
    traits: Traits | None = None,
) -> Relationship:
    """How `rel.owner` feels about `rel.about` after one encounter, such as a conversation, in
    which `rel.about` did `events` to them. The events add up per aspect and move it once, so
    splitting one in two changes nothing. Familiarity grows once, events or not. The owner's
    traits, from the cast unless given, weigh bad events and swing a first encounter."""
    traits = traits_of(rel.owner) if traits is None else traits
    negative = max(
        config.negativity_bias
        * trait_factor(traits.negativity_bias, config.negativity_bias_spread),
        1.0,
    )
    first = (
        trait_factor(traits.first_impressions, config.first_impressions_spread)
        if rel.familiarity == 0
        else 1.0
    )
    shifts: dict[Aspect, float] = {}
    for event in events:
        if (event.actor, event.target) != (rel.about, rel.owner):
            raise ValueError(
                f"{event.actor}'s event for {event.target} doesn't change how {rel.owner} "
                f"feels about {rel.about}"
            )
        bias = negative if event.valence < 0 else 1.0
        for aspect in set(event.aspects):
            shifts[aspect] = shifts.get(aspect, 0.0) + (
                event.valence * event.magnitude * config.max_shift * bias
            )
    scores = {
        aspect.value: _moved(getattr(rel, aspect.value), shift * first, config.resistance_step)
        for aspect, shift in shifts.items()
    }
    familiarity = rel.familiarity + config.familiarity_gain * (1 - rel.familiarity)
    last = now if rel.last_interaction is None else max(rel.last_interaction, now)
    return _with(rel, **scores, familiarity=_clamp(familiarity), last_interaction=last)


def decay(
    rel: Relationship,
    elapsed: timedelta,
    *,
    config: RelationshipConfig = DEFAULT_CONFIG,
    traits: Traits | None = None,
) -> Relationship:
    """Drift toward the baseline after `elapsed` without contact. Flags are untouched. A score
    below its baseline, a grudge, fades as fast as the owner's forgiveness, from the cast unless
    given."""
    if elapsed < timedelta(0):
        raise ValueError(f"elapsed must not be negative, not {elapsed}")
    traits = traits_of(rel.owner) if traits is None else traits
    forgiving = trait_factor(traits.forgiveness, config.forgiveness_spread)

    def toward(score: float, target: float, half_life: timedelta) -> float:
        if score < target:
            half_life = half_life / forgiving
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


def _moved(score: float, shift: float, step: float) -> float:
    """`score` after a shift that would move a neutral score by `shift`. From neutral or toward it,
    it moves the whole way. Away from it, 10 ** (distance / step) grows as much as from neutral."""
    offset = score - NEUTRAL
    if offset * shift <= 0:
        return _clamp(score + shift)
    # A shift of 1 already crosses the whole scale, and much more would overflow.
    distance, push = abs(offset) / step, min(abs(shift), 1.0) / step
    further = step * math.log10(10**distance + 10**push - 1) - abs(offset)
    return _clamp(score + math.copysign(max(further, 0.0), shift))


def _baseline(owner: Npc, aspect: Aspect, config: RelationshipConfig) -> float:
    weights = config.baseline_weights.get(aspect, {})
    return _clamp(0.5 + sum(weight * (owner.values[v] - 0.5) for v, weight in weights.items()))


def _clamp(value: float, a: float = 0.0, b: float = 1.0) -> float:
    return min(max(value, min(a, b)), max(a, b))


def _with(rel: Relationship, **changes: object) -> Relationship:
    return Relationship.model_validate(rel.model_dump() | changes)
