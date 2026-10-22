from datetime import UTC, datetime

import pytest

from simile.npc import load_npcs
from simile.schema import PLAYER_ID, Aspect, Bionic, CoreValue, MemoryKind, Npc
from simile.social import (
    apply_events,
    looks,
    meet,
    sighting,
    strongly_against,
    tolerance,
    unease,
)
from simile.social.bionics import level, seen_in

NOW = datetime(2026, 1, 1, 10, tzinfo=UTC)
TEMPLATE = load_npcs()[0]
EYE, LEGS, JACK = Bionic.INFRARED_EYE, Bionic.HYDRAULIC_LEGS, Bionic.DATAJACK


def resident(id: str = "ana", **values: float) -> Npc:
    scores = {value: values.get(value.value, 0.5) for value in CoreValue}
    return TEMPLATE.model_copy(update={"id": id, "values": scores})


def test_tradition_and_security_count_against_and_adventure_ambition_and_openness_for() -> None:
    assert tolerance(resident().values) == 0
    for value in ("tradition", "security"):
        assert tolerance(resident(**{value: 0.9}).values) < 0
        assert tolerance(resident(**{value: 0.1}).values) > 0
    for value in ("adventure", "ambition", "open_mindedness"):
        assert tolerance(resident(**{value: 0.9}).values) > 0
        assert tolerance(resident(**{value: 0.1}).values) < 0
    assert tolerance(resident(honesty=1.0, connection=0.0).values) == 0


def test_tolerance_runs_from_strongly_against_to_strongly_for() -> None:
    against = dict(tradition=1.0, security=1.0, adventure=0.0, ambition=0.0, open_mindedness=0.0)
    for_ = {value: 1 - score for value, score in against.items()}

    assert tolerance(resident(**against).values) == -1
    assert tolerance(resident(**for_).values) == 1
    assert [level(t) for t in (-1, -0.3, 0, 0.3, 1)] == [-2, -1, 0, 1, 2]


def test_some_of_the_village_are_strongly_against_and_some_strongly_for() -> None:
    village = {npc.id: tolerance(npc.values) for npc in load_npcs()}

    assert {npc.id for npc in load_npcs() if strongly_against(npc)} == {"tobias", "henrietta"}
    assert {id for id, t in village.items() if level(t) == 2} == {"ingrid", "kofi"}
    assert {id for id, t in village.items() if level(t) == 0} >= {"desmond", "odalys"}


def feelings(npc: Npc, *bionics: Bionic) -> tuple[float, float, float]:
    before = meet(npc, PLAYER_ID).model_copy(update={"like": 0.5, "trust": 0.5, "respect": 0.5})
    events, _ = sighting(npc, list(bionics), NOW)
    after = apply_events(before, events, NOW)
    return after.like, after.trust, after.respect


def test_a_sighting_moves_like_trust_and_respect_by_tolerance() -> None:
    hostile = resident(tradition=1.0, security=1.0)
    wary = resident(tradition=0.8, security=0.8)
    neutral = resident()
    curious = resident(adventure=1.0, open_mindedness=1.0)

    assert all(score < 0.5 for score in feelings(wary, EYE))
    assert all(a < b for a, b in zip(feelings(hostile, EYE), feelings(wary, EYE), strict=True))
    assert feelings(neutral, EYE) == (0.5, 0.5, 0.5)
    assert all(score > 0.5 for score in feelings(curious, EYE))
    assert 0.5 - feelings(wary, EYE)[0] > feelings(curious, EYE)[0] - 0.5


def test_the_eye_stands_out_most_and_the_datajack_least() -> None:
    hostile = resident(tradition=1.0, security=1.0)

    eye, legs, jack = (feelings(hostile, bionic)[0] for bionic in (EYE, LEGS, JACK))

    assert eye < legs < jack < 0.5
    assert feelings(hostile, LEGS, JACK)[0] < legs


def test_a_sighting_is_one_event_per_bionic_and_one_memory_that_records_them() -> None:
    hostile = resident(tradition=1.0, security=1.0)

    events, memory = sighting(hostile, [LEGS, EYE], NOW)

    assert [(e.actor, e.target) for e in events] == [(PLAYER_ID, "ana")] * 2
    assert all(set(e.aspects) == set(Aspect) for e in events)
    assert all(e.valence == tolerance(hostile.values) for e in events)
    assert memory.kind is MemoryKind.OBSERVATION and memory.about == [PLAYER_ID]
    assert memory.content.startswith("I saw that Visitor has hydraulic legs")
    assert "infrared eye" in memory.content and "turned my stomach" in memory.content
    assert seen_in(memory) == [LEGS, EYE]
    assert memory.salience > sighting(resident(), [LEGS], NOW)[1].salience


def test_unease_is_for_the_intolerant_and_grows_with_what_they_have_seen() -> None:
    assert unease(0.8, [EYE]) == 0
    assert unease(-0.5, []) == 0
    assert unease(-0.5, [JACK]) < unease(-0.5, [EYE]) == unease(-0.5, [EYE, LEGS])
    assert unease(-0.575, [EYE]) == pytest.approx(0.5)
    assert unease(-1, [LEGS, JACK]) == 1


def test_nobody_who_barely_minds_is_uneasy() -> None:
    assert unease(-0.15, [EYE]) == 0
    assert unease(-0.16, [EYE]) > 0
    village = {npc.id: unease(tolerance(npc.values), [EYE]) for npc in load_npcs()}
    assert {id for id, level in village.items() if level} == {
        "tobias",
        "henrietta",
        "mirela",
        "raymond",
    }


def test_what_they_see_names_each_bionic_what_is_new_and_how_they_feel() -> None:
    line = looks("Visitor", [LEGS, EYE], -1, new=[EYE])

    assert line is not None
    assert line.startswith("Visitor has hydraulic legs where their own legs were and an infrared")
    assert "The infrared eye is new since you last saw them." in line
    assert line.endswith("you'd rather keep your distance.")
    assert looks("Visitor", [], -1) is None
    assert "fascinate" in (looks("Visitor", [JACK], 1) or "")
    assert "new" not in (looks("Visitor", [JACK], 0) or "")


@pytest.mark.parametrize("bionics", [[LEGS], [JACK], [EYE], [LEGS, JACK, EYE]])
def test_every_bionic_reads_back_from_its_memory(bionics: list[Bionic]) -> None:
    _, memory = sighting(resident(), bionics, NOW)

    assert seen_in(memory) == bionics
