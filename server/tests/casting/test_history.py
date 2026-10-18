from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

import pytest

from simile.casting import Cast, Pin, bind, history
from simile.memory import MemoryStore
from simile.schema import (
    Character,
    FlagKind,
    HookKind,
    Memory,
    MemoryKind,
    Npc,
    PastMemory,
    Relationship,
    Voice,
)
from simile.social import meet

type Make = Callable[..., Character]

HOUSES = [f"house_{n}" for n in range(1, 11)]
START = datetime(2026, 10, 18, 8, tzinfo=UTC)


@pytest.mark.parametrize(
    ("born", "game_date", "age"),
    [(1955, date(2026, 10, 18), 71), (1955, date(2031, 1, 1), 76), (2008, date(2026, 1, 1), 18)],
)
def test_ages_come_from_the_birth_year_and_the_game_date(
    make: Make, born: int, game_date: date, age: int
) -> None:
    made = bind([make("a", birth_year=born)], game_date=game_date, houses=HOUSES)

    assert made.npcs()[0].age == age


def test_an_npc_has_a_plain_voice_and_round_trips(pool: list[Character]) -> None:
    made = bind(pool[:3], houses=HOUSES)

    for npc, resident in zip(made.npcs(), made.residents, strict=True):
        assert type(npc.voice) is Voice
        assert npc.voice.reference_line == resident.character.voice.reference_line
        assert Npc.model_validate_json(npc.model_dump_json()) == npc
        assert npc.home == resident.home
    assert Cast.model_validate_json(made.model_dump_json()) == made


def test_a_hook_binds_on_both_sides(make: Make) -> None:
    lender = make("mei_lin", hooks=(("debt", "target", "They never paid me back."),))
    borrower = make("tom_hale", hooks=(("debt", "actor", "I still owe them."),))
    made = bind([lender, borrower], houses=HOUSES)

    records = history(made, START)

    relationships = {(r.owner, r.about): r for r in records if isinstance(r, Relationship)}
    memories = {m.owner: m for m in records if isinstance(m, Memory)}
    owed, owes = relationships["mei_lin", "tom_hale"], relationships["tom_hale", "mei_lin"]
    assert [(f.kind, f.owner, f.about) for f in owed.flags] == [
        (FlagKind.DEBT, "mei_lin", "tom_hale")
    ]
    assert owes.flags == []
    assert memories["mei_lin"].content == "Tom owes me money. They never paid me back."
    assert memories["tom_hale"].content == "I owe Mei money. I still owe them."
    assert memories["mei_lin"].about == ["tom_hale"]
    assert memories["tom_hale"].about == ["mei_lin"]
    assert {m.kind for m in memories.values()} == {MemoryKind.PAST}


def test_a_bond_moves_both_sides_from_their_baselines_and_holds_there(make: Make) -> None:
    traitor = make("a", hooks=(("betrayal", "actor"),))
    betrayed = make("b", hooks=(("betrayal", "target"),))
    made = bind([traitor, betrayed], houses=HOUSES)
    npcs = {npc.id: npc for npc in made.npcs()}

    records = history(made, START)

    hurt = next(r for r in records if isinstance(r, Relationship) and r.owner == "b")
    stranger = meet(npcs["b"], "a")
    assert hurt.like < stranger.like
    assert hurt.trust < stranger.trust
    assert (hurt.baseline.like, hurt.baseline.trust) == (hurt.like, hurt.trust)
    assert hurt.familiarity == 0.5
    assert hurt.flags[0].kind is FlagKind.GRUDGE


def test_a_pinned_bond_without_hooks_still_leaves_memories(make: Make) -> None:
    pin = Pin(kind=HookKind.ESTRANGED_SIBLING, actor="ana_ruiz", target="leo_ruiz")
    made = bind([make("ana_ruiz"), make("leo_ruiz")], [pin], houses=HOUSES)

    contents = sorted(m.content for m in history(made, START) if isinstance(m, Memory))

    assert contents == [
        "Ana is my sibling, and we don't speak.",
        "Leo is my sibling, and we don't speak.",
    ]


def test_the_past_is_stamped_just_before_the_start_and_surfaces_in_recall(make: Make) -> None:
    past = [
        PastMemory(age=8, content="A childhood summer.", salience=0.4, valence=0.5),
        PastMemory(age=30, content="The wedding.", salience=0.9, valence=0.8),
        PastMemory(age=55, content="A quiet loss.", salience=0.6, valence=-0.6),
    ]
    made = bind([make("a", birth_year=1956, past=past)], houses=HOUSES)
    assert made.npcs()[0].age == 70

    memories = [m for m in history(made, START) if isinstance(m, Memory)]

    assert [START - m.timestamp for m in memories] == [
        timedelta(minutes=62),
        timedelta(minutes=40),
        timedelta(minutes=15),
    ]
    with MemoryStore(":memory:") as store:
        store.add(*memories)
        recalled = store.recall("a", START, k=3)
    assert [m.content for m in recalled] == ["The wedding.", "A quiet loss.", "A childhood summer."]
