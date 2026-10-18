import random
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from simile.casting import Cast, Resident, write_cast
from simile.characters.pool import load_pool
from simile.schema import Aspect, InteractionEvent, Relationship, Traits
from simile.social import (
    DEFAULT_CONFIG,
    RelationshipConfig,
    apply_events,
    as_of,
    cast_traits,
    decay,
    trait_factor,
    traits_of,
)

NOW = datetime(2026, 3, 14, 9, tzinfo=UTC)
NEUTRAL = Traits()
SWITCHED_OFF = RelationshipConfig(
    negativity_bias_spread=1, forgiveness_spread=1, first_impressions_spread=1
)


def relationship(**changes: Any) -> Relationship:
    return Relationship.model_validate(
        {
            "owner": "mei",
            "about": "viktor",
            "like": 0.5,
            "trust": 0.5,
            "respect": 0.5,
            "familiarity": 0.5,
            "baseline": {"like": 0.5, "trust": 0.5, "respect": 0.5},
        }
        | changes
    )


def event(**changes: Any) -> InteractionEvent:
    return InteractionEvent.model_validate(
        {
            "actor": "viktor",
            "target": "mei",
            "action": "snapped at her",
            "aspects": ["like"],
            "valence": -0.4,
            "magnitude": 0.2,
            "timestamp": NOW,
        }
        | changes
    )


def test_trait_factor_is_one_at_neutral_and_the_spread_at_either_end() -> None:
    assert trait_factor(0.5, 3.0) == 1.0
    assert trait_factor(1.0, 3.0) == pytest.approx(3.0)
    assert trait_factor(0.0, 3.0) == pytest.approx(1 / 3)


def test_neutral_traits_reproduce_todays_scores() -> None:
    stranger, friend, wronged = (
        relationship(familiarity=0.0),
        relationship(like=0.8),
        relationship(like=0.2),
    )
    good = event(valence=1.0, magnitude=0.5)

    for traits in (None, NEUTRAL):
        first = apply_events(stranger, [good], NOW, traits=traits)
        snub = apply_events(friend, [event()], NOW, traits=traits)
        grudge = decay(wronged, DEFAULT_CONFIG.like_half_life, traits=traits)

        assert first.like == pytest.approx(0.65)
        assert snub.like == pytest.approx(0.8 - 0.4 * 0.2 * 0.3 * 2.5)
        assert grudge.like == pytest.approx(0.35)


def test_neutral_traits_score_as_if_traits_were_switched_off() -> None:
    rng = random.Random(0)
    extreme = Traits(sociability=1, negativity_bias=1, forgiveness=0, first_impressions=1)
    neutral = off = relationship(familiarity=0.0)
    when = NOW
    for _ in range(200):
        when += timedelta(hours=rng.uniform(0, 48))
        events = [
            event(
                valence=rng.uniform(-1, 1),
                magnitude=rng.uniform(0, 1),
                aspects=rng.sample(list(Aspect), rng.randint(0, 3)),
                timestamp=when,
            )
            for _ in range(rng.randint(0, 3))
        ]
        neutral = apply_events(as_of(neutral, when, traits=NEUTRAL), events, when, traits=NEUTRAL)
        off = apply_events(
            as_of(off, when, config=SWITCHED_OFF, traits=extreme),
            events,
            when,
            config=SWITCHED_OFF,
            traits=extreme,
        )
        assert neutral == off


@pytest.mark.parametrize("trait", [0.0, 0.25, 0.75, 1.0])
def test_negativity_bias_sets_how_much_more_a_bad_turn_weighs(trait: float) -> None:
    rel = relationship(like=0.8)
    spread = DEFAULT_CONFIG.negativity_bias_spread

    neutral = rel.like - apply_events(rel, [event()], NOW, traits=NEUTRAL).like
    drop = rel.like - apply_events(rel, [event()], NOW, traits=Traits(negativity_bias=trait)).like
    rise = apply_events(rel, [event(valence=0.4)], NOW, traits=Traits(negativity_bias=trait))

    assert drop == pytest.approx(neutral * spread ** (2 * trait - 1))
    assert rise == apply_events(rel, [event(valence=0.4)], NOW, traits=NEUTRAL)


def test_a_bad_turn_never_weighs_less_than_a_good_one() -> None:
    config = RelationshipConfig(negativity_bias_spread=10)
    rel = relationship()
    trusting = Traits(negativity_bias=0.0)

    drop = rel.like - apply_events(rel, [event()], NOW, config=config, traits=trusting).like
    rise = apply_events(rel, [event(valence=0.4)], NOW, config=config, traits=trusting).like

    assert drop == pytest.approx(rise - rel.like)


def test_first_impressions_set_how_far_a_first_encounter_swings() -> None:
    stranger = relationship(familiarity=0.0)
    good = event(valence=0.6, magnitude=0.5)

    def liked(trait: float, rel: Relationship = stranger) -> float:
        return apply_events(rel, [good], NOW, traits=Traits(first_impressions=trait)).like

    assert liked(0.0) < liked(0.25) < liked(0.5) < liked(0.75) < liked(1.0)
    assert liked(1.0) - 0.5 == pytest.approx(2 * (liked(0.5) - 0.5))


def test_only_the_first_encounter_swings() -> None:
    met = apply_events(relationship(familiarity=0.0), [], NOW)
    good = event(valence=0.6, magnitude=0.5)

    second = {
        trait: apply_events(met, [good], NOW, traits=Traits(first_impressions=trait))
        for trait in (0.0, 0.5, 1.0)
    }

    assert met.familiarity > 0
    assert second[0.0] == second[0.5] == second[1.0]


def test_a_slow_fading_grudge_lasts_longer_than_a_fast_one() -> None:
    grudge = relationship(like=0.1, trust=0.1, respect=0.1)

    def after(days: float, forgiveness: float) -> Relationship:
        return decay(grudge, timedelta(days=days), traits=Traits(forgiveness=forgiveness))

    for days in (1, 4, 16):
        slow, fast = after(days, 0.1), after(days, 0.9)
        for aspect in Aspect:
            assert getattr(slow, aspect) < getattr(after(days, 0.5), aspect) < getattr(fast, aspect)
    forgiving = decay(grudge, DEFAULT_CONFIG.like_half_life / 3, traits=Traits(forgiveness=1.0))
    assert forgiving.like == pytest.approx(0.3)


def test_forgiveness_leaves_warm_feelings_fading_as_ever() -> None:
    warm = relationship(like=0.9, trust=0.8, respect=0.7, familiarity=0.6)

    for forgiveness in (0.0, 1.0):
        assert decay(warm, timedelta(days=3), traits=Traits(forgiveness=forgiveness)) == decay(
            warm, timedelta(days=3), traits=NEUTRAL
        )


def test_as_of_fades_a_grudge_by_the_owners_forgiveness() -> None:
    grudge = relationship(like=0.1, last_interaction=NOW)
    later = NOW + timedelta(days=2)

    slow = as_of(grudge, later, traits=Traits(forgiveness=0.0))

    assert slow == decay(grudge, timedelta(days=2), traits=Traits(forgiveness=0.0))
    assert slow.like < as_of(grudge, later).like


def test_outside_a_cast_everyone_is_neutral(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert traits_of("mei") == NEUTRAL
    monkeypatch.setenv("SIMILE_DB", str(tmp_path / "simile.db"))
    assert traits_of("mei") == NEUTRAL
    assert dict(cast_traits()) == {}


def test_traits_come_from_the_cast(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pool = load_pool()
    gloomy = max(pool, key=lambda c: c.traits.negativity_bias)
    forgiving = max(pool, key=lambda c: c.traits.forgiveness)
    made = Cast(
        game_date=date(2026, 1, 1),
        seed=0,
        residents=[
            Resident(character=gloomy, home="house_1"),
            Resident(character=forgiving, home="house_2"),
        ],
    )
    write_cast(made, tmp_path / "world")
    monkeypatch.setenv("SIMILE_DB", str(tmp_path / "world" / "simile.db"))
    rel = relationship(owner=gloomy.id, about=forgiving.id, like=0.8)
    snub = event(actor=forgiving.id, target=gloomy.id)

    assert traits_of(gloomy.id) == gloomy.traits
    assert traits_of(forgiving.id) == forgiving.traits
    assert traits_of("someone_else") == NEUTRAL
    assert apply_events(rel, [snub], NOW) == apply_events(rel, [snub], NOW, traits=gloomy.traits)
    assert apply_events(rel, [snub], NOW).like < apply_events(rel, [snub], NOW, traits=NEUTRAL).like
