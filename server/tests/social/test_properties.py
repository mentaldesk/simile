from datetime import UTC, datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from simile.schema import Aspect, Baseline, FlagKind, InteractionEvent, Relationship
from simile.social import DEFAULT_CONFIG, RelationshipConfig, apply_event, decay

PEOPLE = ["mei", "viktor", "suki", "player"]
UNITS = st.floats(0, 1)
TIMES = st.datetimes(datetime(2026, 1, 1), datetime(2027, 1, 1), timezones=st.just(UTC))
HALF_LIVES = st.timedeltas(timedelta(minutes=1), timedelta(days=365))


@st.composite
def relationships(draw: st.DrawFn) -> Relationship:
    owner, about = draw(st.lists(st.sampled_from(PEOPLE), min_size=2, max_size=2, unique=True))
    flags = draw(
        st.lists(
            st.fixed_dictionaries(
                {
                    "kind": st.sampled_from(FlagKind),
                    "description": st.text(min_size=1, max_size=20),
                    "created": TIMES,
                    "resolved": st.none() | TIMES,
                }
            ),
            max_size=3,
        )
    )
    return Relationship(
        owner=owner,
        about=about,
        like=draw(UNITS),
        trust=draw(UNITS),
        respect=draw(UNITS),
        familiarity=draw(UNITS),
        baseline=Baseline(like=draw(UNITS), trust=draw(UNITS), respect=draw(UNITS)),
        flags=[
            {"id": f"flag_{index}", "owner": owner, "about": about, **flag}
            for index, flag in enumerate(flags)
        ],
        last_interaction=draw(st.none() | TIMES),
    )


@st.composite
def events_for(draw: st.DrawFn, rel: Relationship) -> InteractionEvent:
    return InteractionEvent(
        actor=rel.about,
        target=rel.owner,
        action="something",
        aspects=draw(st.lists(st.sampled_from(Aspect), unique=True)),
        valence=draw(st.floats(-1, 1)),
        magnitude=draw(UNITS),
        timestamp=draw(TIMES),
    )


@st.composite
def configs(draw: st.DrawFn) -> RelationshipConfig:
    like, trust = sorted(draw(st.lists(HALF_LIVES, min_size=2, max_size=2, unique=True)))
    return RelationshipConfig(
        max_shift=draw(st.floats(0.01, 1)),
        negativity_bias=draw(st.floats(1, 5)),
        dampening_floor=draw(UNITS),
        familiarity_gain=draw(UNITS),
        like_half_life=like,
        trust_half_life=trust,
        respect_half_life=draw(HALF_LIVES),
        familiarity_half_life=draw(HALF_LIVES),
    )


def scores(rel: Relationship) -> list[float]:
    return [rel.like, rel.trust, rel.respect, rel.familiarity]


@given(st.data(), relationships(), st.just(DEFAULT_CONFIG) | configs(), TIMES)
def test_apply_event_keeps_every_score_in_range(
    data: st.DataObject, rel: Relationship, config: RelationshipConfig, now: datetime
) -> None:
    after = apply_event(rel, data.draw(events_for(rel)), now, config=config)

    assert all(0 <= score <= 1 for score in scores(after))


@given(st.data(), relationships(), configs(), st.lists(TIMES, min_size=1, max_size=20))
def test_a_run_of_events_and_decay_keeps_every_score_in_range(
    data: st.DataObject, rel: Relationship, config: RelationshipConfig, times: list[datetime]
) -> None:
    for now in times:
        rel = apply_event(rel, data.draw(events_for(rel)), now, config=config)
        rel = decay(rel, data.draw(st.timedeltas(timedelta(0), timedelta(days=30))), config=config)
        assert all(0 <= score <= 1 for score in scores(rel))


@given(st.data(), relationships(), configs(), TIMES)
def test_apply_event_moves_only_its_aspects_and_only_with_its_valence(
    data: st.DataObject, rel: Relationship, config: RelationshipConfig, now: datetime
) -> None:
    event = data.draw(events_for(rel))

    after = apply_event(rel, event, now, config=config)

    assert after.familiarity >= rel.familiarity
    assert after.flags == rel.flags
    for aspect in Aspect:
        moved = getattr(after, aspect) - getattr(rel, aspect)
        if aspect not in event.aspects:
            assert moved == 0
        else:
            assert moved * event.valence >= 0


@given(relationships(), configs(), st.timedeltas(timedelta(0), timedelta(days=3650)))
def test_decay_keeps_every_score_in_range_and_never_overshoots(
    rel: Relationship, config: RelationshipConfig, elapsed: timedelta
) -> None:
    after = decay(rel, elapsed, config=config)

    assert all(0 <= score <= 1 for score in scores(after))
    assert after.familiarity <= rel.familiarity
    assert after.flags == rel.flags
    for aspect in Aspect:
        start, end, target = (
            getattr(rel, aspect),
            getattr(after, aspect),
            getattr(rel.baseline, aspect),
        )
        assert min(start, target) <= end <= max(start, target)


@given(
    relationships(),
    configs(),
    st.timedeltas(timedelta(0), timedelta(days=30)),
    st.timedeltas(timedelta(0), timedelta(days=30)),
)
def test_decay_in_steps_matches_decay_in_one_go(
    rel: Relationship, config: RelationshipConfig, first: timedelta, second: timedelta
) -> None:
    stepped = decay(decay(rel, first, config=config), second, config=config)
    at_once = decay(rel, first + second, config=config)

    assert scores(stepped) == pytest.approx(scores(at_once), abs=1e-9)


@given(relationships(), configs(), st.timedeltas(timedelta(seconds=1), timedelta(days=30)))
def test_trust_always_decays_more_slowly_than_like(
    rel: Relationship, config: RelationshipConfig, elapsed: timedelta
) -> None:
    rel = Relationship.model_validate(
        rel.model_dump()
        | {"like": 1.0, "trust": 1.0, "baseline": {"like": 0.0, "trust": 0.0, "respect": 0.0}}
    )

    after = decay(rel, elapsed, config=config)

    assert after.trust >= after.like
