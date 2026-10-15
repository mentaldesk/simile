import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from simile.schema import Aspect, Flag, FlagKind, InteractionEvent, Relationship
from simile.social import (
    DEFAULT_CONFIG,
    RelationshipConfig,
    apply_event,
    as_of,
    decay,
    describe,
    open_flag,
    resolve_flag,
)

FIXTURES = Path(__file__).parents[1] / "fixtures"
NOW = datetime(2026, 3, 14, 9, tzinfo=UTC)


def relationship(**changes: Any) -> Relationship:
    return Relationship.model_validate(
        {
            "owner": "mei",
            "about": "viktor",
            "like": 0.5,
            "trust": 0.5,
            "respect": 0.5,
            "familiarity": 0.0,
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
            "valence": -0.5,
            "magnitude": 0.5,
            "timestamp": NOW,
        }
        | changes
    )


def flag(**changes: Any) -> Flag:
    return Flag.model_validate(
        {
            "id": "flag_1",
            "kind": "grudge",
            "owner": "mei",
            "about": "viktor",
            "description": "the bridge incident",
            "created": NOW,
        }
        | changes
    )


def test_a_strangers_rude_act_moves_scores_more_than_a_friends() -> None:
    stranger = relationship(familiarity=0.0)
    friend = relationship(familiarity=0.9)

    stranger_drop = stranger.like - apply_event(stranger, event(), NOW).like
    friend_drop = friend.like - apply_event(friend, event(), NOW).like

    assert stranger_drop > friend_drop > 0


def test_an_old_friend_can_still_be_moved() -> None:
    stranger = relationship(familiarity=0.0)
    friend = relationship(familiarity=1.0)

    stranger_drop = stranger.like - apply_event(stranger, event(), NOW).like
    friend_drop = friend.like - apply_event(friend, event(), NOW).like

    assert friend_drop == pytest.approx(stranger_drop * DEFAULT_CONFIG.dampening_floor)
    assert friend_drop > 0


@pytest.mark.parametrize("bias", [2.0, 2.5, 3.0])
def test_a_negative_event_outweighs_a_positive_one_of_equal_magnitude(bias: float) -> None:
    config = RelationshipConfig(negativity_bias=bias)
    rel = relationship()

    rise = apply_event(rel, event(valence=0.4), NOW, config=config).like - rel.like
    drop = rel.like - apply_event(rel, event(valence=-0.4), NOW, config=config).like

    assert drop == pytest.approx(bias * rise)
    assert rise > 0


def test_an_event_moves_only_its_aspects() -> None:
    rel = relationship()

    after = apply_event(rel, event(aspects=["trust", "respect"], valence=0.8), NOW)

    assert after.like == rel.like
    assert after.trust > rel.trust
    assert after.respect == after.trust


def test_an_event_without_aspects_only_builds_familiarity() -> None:
    rel = relationship(familiarity=0.3)

    after = apply_event(rel, event(aspects=[]), NOW)

    assert (after.like, after.trust, after.respect) == (rel.like, rel.trust, rel.respect)
    assert after.familiarity > rel.familiarity


@pytest.mark.parametrize("valence", [-1.0, -0.2, 0.0, 0.7])
def test_familiarity_grows_with_any_interaction(valence: float) -> None:
    rel = relationship(familiarity=0.4)

    assert apply_event(rel, event(valence=valence), NOW).familiarity > rel.familiarity


def test_a_big_event_can_push_a_score_only_as_far_as_the_end_of_the_scale() -> None:
    rel = relationship(like=0.1)

    after = apply_event(rel, event(valence=-1.0, magnitude=1.0), NOW)

    assert after.like == 0.0


def test_apply_event_records_the_interaction_time() -> None:
    rel = relationship(last_interaction=NOW)

    assert apply_event(rel, event(), NOW + timedelta(minutes=5)).last_interaction == (
        NOW + timedelta(minutes=5)
    )
    assert apply_event(rel, event(), NOW - timedelta(minutes=5)).last_interaction == NOW


def test_apply_event_leaves_its_input_alone() -> None:
    rel = relationship(flags=[flag()])
    before = rel.model_copy(deep=True)

    apply_event(rel, event(), NOW)

    assert rel == before


@pytest.mark.parametrize(
    ("actor", "target"), [("mei", "viktor"), ("suki", "mei"), ("viktor", "suki")]
)
def test_apply_event_rejects_an_event_for_another_relationship(actor: str, target: str) -> None:
    with pytest.raises(ValueError, match="doesn't change how mei feels about viktor"):
        apply_event(relationship(), event(actor=actor, target=target), NOW)


def test_decay_approaches_the_baseline() -> None:
    rel = relationship(
        like=0.9,
        trust=0.1,
        respect=0.8,
        baseline={"like": 0.55, "trust": 0.6, "respect": 0.65},
    )

    day = decay(rel, timedelta(days=1))
    year = decay(rel, timedelta(days=365))

    for aspect in Aspect:
        start, target = getattr(rel, aspect), getattr(rel.baseline, aspect)
        assert abs(getattr(day, aspect) - target) < abs(start - target)
        assert getattr(year, aspect) == pytest.approx(target, abs=1e-6)


def test_decay_halves_the_gap_to_the_baseline_every_half_life() -> None:
    rel = relationship(like=0.9)

    after = decay(rel, DEFAULT_CONFIG.like_half_life)

    assert after.like - rel.baseline.like == pytest.approx((rel.like - rel.baseline.like) / 2)


def test_trust_decays_more_slowly_than_like() -> None:
    rel = relationship(like=0.9, trust=0.9)

    after = decay(rel, timedelta(days=1))

    assert rel.trust - after.trust < rel.like - after.like


def test_familiarity_fades_far_more_slowly_than_feelings() -> None:
    rel = relationship(like=1.0, familiarity=1.0, baseline={"like": 0, "trust": 0, "respect": 0})

    after = decay(rel, timedelta(days=1))

    assert 1 - after.familiarity < (1 - after.like) / 10


def test_decay_over_no_time_changes_nothing() -> None:
    rel = relationship(like=0.9, trust=0.2, familiarity=0.4)

    assert decay(rel, timedelta(0)) == rel


def test_decay_rejects_negative_time() -> None:
    with pytest.raises(ValueError, match="must not be negative"):
        decay(relationship(), timedelta(seconds=-1))


def test_flags_survive_score_recovery() -> None:
    rel = relationship(familiarity=0.5)
    rel = apply_event(rel, event(action="broke her window", valence=-0.9, magnitude=0.9), NOW)
    rel = open_flag(rel, flag(description="the broken window"))
    hurt = rel.like

    for hour in range(1, 30):
        rel = apply_event(
            rel, event(action="bought her a coffee", valence=0.8), NOW + timedelta(hours=hour)
        )
    rel = decay(rel, timedelta(days=30))

    assert rel.like > hurt
    assert rel.like == pytest.approx(rel.baseline.like, abs=0.01)
    assert [f.id for f in rel.flags if f.resolved is None] == ["flag_1"]
    assert "You hold a grudge against Viktor over the broken window." in describe(rel, "Viktor")


def test_open_flag_adds_the_flag() -> None:
    rel = open_flag(relationship(), flag())

    assert rel.flags == [flag()]


def test_open_flag_rejects_a_duplicate_id() -> None:
    rel = open_flag(relationship(), flag())

    with pytest.raises(ValueError, match="already has flag flag_1"):
        open_flag(rel, flag(kind="debt"))


def test_open_flag_rejects_a_flag_for_another_relationship() -> None:
    with pytest.raises(ValidationError, match="belongs to another relationship"):
        open_flag(relationship(), flag(owner="viktor", about="mei"))


def test_resolve_flag_closes_only_that_flag() -> None:
    rel = relationship(flags=[flag(), flag(id="flag_2", kind=FlagKind.DEBT)])
    later = NOW + timedelta(days=2)

    resolved = resolve_flag(rel, "flag_2", later)

    assert [f.resolved for f in resolved.flags] == [None, later]
    assert rel.flags[1].resolved is None


def test_resolving_a_resolved_flag_keeps_its_time() -> None:
    rel = resolve_flag(relationship(flags=[flag()]), "flag_1", NOW)

    assert resolve_flag(rel, "flag_1", NOW + timedelta(days=1)).flags[0].resolved == NOW


def test_resolve_flag_rejects_an_unknown_flag() -> None:
    with pytest.raises(KeyError, match="no flag flag_9"):
        resolve_flag(relationship(flags=[flag()]), "flag_9", NOW)


def test_times_must_be_timezone_aware() -> None:
    naive = datetime(2026, 3, 14, 9)

    with pytest.raises(ValidationError):
        apply_event(relationship(), event(), naive)
    with pytest.raises(ValidationError):
        resolve_flag(relationship(flags=[flag()]), "flag_1", naive)


def test_the_fixture_events_apply_to_the_fixture_relationships() -> None:
    rels = TypeAdapter(list[Relationship]).validate_json(
        (FIXTURES / "relationships.json").read_bytes()
    )
    events = TypeAdapter(list[InteractionEvent]).validate_json(
        (FIXTURES / "interaction_events.json").read_bytes()
    )
    by_pair = {(rel.owner, rel.about): rel for rel in rels}

    for item in events:
        rel = by_pair[(item.target, item.actor)]
        after = apply_event(rel, item, item.timestamp)
        assert after.familiarity > rel.familiarity
        for aspect in item.aspects:
            moved = getattr(after, aspect) - getattr(rel, aspect)
            assert moved * item.valence > 0


def test_the_config_keeps_trust_slower_than_like() -> None:
    with pytest.raises(ValidationError, match="trust_half_life must be longer"):
        RelationshipConfig(like_half_life=timedelta(days=3), trust_half_life=timedelta(days=3))


def test_the_config_loads_from_json() -> None:
    config = RelationshipConfig.model_validate_json(
        json.dumps({"negativity_bias": 3, "like_half_life": "P1D"})
    )

    assert config.negativity_bias == 3
    assert config.like_half_life == timedelta(days=1)
    assert config.trust_half_life == DEFAULT_CONFIG.trust_half_life


def test_as_of_decays_from_the_last_interaction() -> None:
    rel = relationship(like=0.9, trust=0.1, familiarity=0.5, last_interaction=NOW)

    assert as_of(rel, NOW + timedelta(days=3)) == decay(rel, timedelta(days=3))


def test_as_of_leaves_a_relationship_without_interactions_alone() -> None:
    rel = relationship(like=0.9)

    assert as_of(rel, NOW) == rel


def test_as_of_never_decays_backwards() -> None:
    rel = relationship(like=0.9, last_interaction=NOW)

    assert as_of(rel, NOW - timedelta(days=1)) == rel


def test_storing_only_after_an_event_decays_each_stretch_once() -> None:
    stored = relationship(like=0.9, last_interaction=NOW)
    later, latest = NOW + timedelta(days=1), NOW + timedelta(days=3)

    stored = apply_event(as_of(stored, later), event(aspects=[]), later)

    assert as_of(stored, latest).like == pytest.approx(
        decay(relationship(like=0.9), latest - NOW).like
    )
