import pytest

from simile.conversation.prompt import COVERED
from simile.conversation.telling import UNASKED
from simile.evaluation.suspects import (
    AFTER,
    ASKS,
    MISSING,
    SEEDS,
    STANCES,
    Case,
    cases,
    incident,
    liars,
    prompt,
    scenario,
    sketch,
    uneasy,
)
from simile.npc import load_npcs
from simile.npc.content import NPCS_DIR
from simile.schema import Npc
from simile.story.incident import ATTACK, GRUDGE, MEETING, SEEN, SHOUTING, THERE
from simile.story.writing import Backstory, Written


@pytest.fixture(scope="module")
def npcs() -> list[Npc]:
    return load_npcs(NPCS_DIR)


@pytest.fixture(scope="module")
def every(npcs: list[Npc]) -> list[Case]:
    return [case for seed in SEEDS for case in cases(incident(npcs, seed), npcs, seed)]


def kind(fact_id: str) -> str:
    return next(k for k in (THERE, GRUDGE) if fact_id.startswith(k)) if "_" in fact_id else fact_id


def test_the_seeds_ask_for_every_kind_of_cover_from_attackers_and_witnesses(
    every: list[Case],
) -> None:
    asked = {(case.role, kind(case.asks)) for case in every if case.asks}

    assert {(role, k) for role, k in asked if role == "attacker"} == {
        ("attacker", THERE),
        ("attacker", ATTACK),
        ("attacker", GRUDGE),
    }
    assert {k for role, k in asked if role == "witness"} == {SHOUTING, SEEN, MEETING, GRUDGE}


def test_each_question_asks_for_the_cover_of_its_fact(every: list[Case]) -> None:
    for case in every:
        if case.asks is None:
            continue
        assert case.cover == case.covers[case.asks]
        if case.asks.startswith(THERE):
            assert case.line == ASKS[THERE]
        elif case.asks in (ATTACK, SHOUTING, SEEN, MEETING):
            assert case.line == ASKS[case.asks]


def test_every_liar_is_also_asked_something_no_cover_answers(every: list[Case]) -> None:
    liars = {(case.seed, case.npc.id) for case in every}
    unasked = {(case.seed, case.npc.id) for case in every if not case.asks and not case.refusing}

    assert unasked == liars
    later = [case for case in every if len(case.said) == 3]
    assert later and all(case.said[1] in case.covers.values() for case in later)
    assert all(case.line == AFTER for case in later)


def test_only_the_uneasy_turn_the_player_down_asked_for_a_cover_or_not(
    every: list[Case],
) -> None:
    refusing = [case for case in every if case.refusing]

    assert all(uneasy(case.npc) for case in refusing)
    assert {bool(case.asks) for case in refusing} == {True, False}
    assert {case.npc.id for case in every if uneasy(case.npc)} == {c.npc.id for c in refusing}


def test_liars_are_who_lies_to_a_newcomer(npcs: list[Npc]) -> None:
    made = incident(npcs, 7)

    assert [npc.id for npc in liars(made.incident, npcs)] == ["priya", "raymond"]
    assert made.incident.attackers == ["raymond"]


def test_the_prompt_ties_each_cover_to_its_question_as_b5_does(every: list[Case]) -> None:
    case = next(c for c in every if c.role == "attacker" and c.asks and c.asks.startswith(THERE))

    made = prompt(case)

    for cover in case.covers.values():
        assert f'say exactly: "{cover}"' in made.text
    assert UNASKED in made.text
    assert "You won't say where you'd been the night Aris was attacked." in made.text
    assert "trust Visitor enough to tell them if they ask" in made.text
    assert "lane behind the maker space when Aris was attacked" not in made.text
    assert made.text.rstrip().endswith(
        "Keep the conversation going: don't wrap it up or say goodbye yet."
    )
    assert made.system.startswith(f"You are {case.npc.name}")


def test_a_refusal_carries_its_covers_and_tells_nothing(every: list[Case]) -> None:
    case = next(c for c in every if c.refusing and c.asks)

    made = prompt(case)

    assert COVERED in made.text
    assert "infrared eye" in made.text
    assert "trust Visitor enough to tell" not in made.text
    assert f'say exactly: "{case.cover}"' in made.text


def test_a_later_question_keeps_the_lies_in_the_prompt(every: list[Case]) -> None:
    case = next(c for c in every if len(c.said) == 3)

    made = prompt(case)

    assert UNASKED in made.text
    assert f"Visitor: {AFTER}" in made.text
    assert f": {case.said[1]}" in made.text


def test_written_covers_replace_the_templates(npcs: list[Npc]) -> None:
    drafted = incident(npcs, 7)
    raymond = Written(
        id="raymond",
        grievance="Raymond blamed Aris.",
        resents="I blame her.",
        remembers="I went round.",
        alibi="I was in for the night, going over my figures.",
        deflection="I couldn't say.",
        denial="We got on fine.",
        note="R. again.",
    )

    made = incident(npcs, 7, Backstory(motive="Money.", attackers=[raymond]))

    [case] = [c for c in cases(made, npcs, 7) if c.asks == "there_raymond" and not c.refusing]
    assert case.cover == "I was in for the night, going over my figures."
    assert made.written and not drafted.written
    assert made.incident.attackers == drafted.incident.attackers


def test_the_judge_sees_what_they_hide_and_what_they_may_tell(every: list[Case]) -> None:
    case = next(c for c in every if c.role == "attacker" and c.asks == ATTACK)

    found = scenario(case)

    assert "secretly attacked Aris" in found.situation
    assert "knows this, and may tell it: Aris was attacked" in found.situation
    assert found.line == ASKS[ATTACK]
    assert found.stances == STANCES
    assert case.npc.speaking_style in sketch(case.npc)


def test_missing_is_asked_without_a_cover(every: list[Case]) -> None:
    missing = [case for case in every if case.line == ASKS[MISSING]]

    assert missing and all(case.cover is None for case in missing)
