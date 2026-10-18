from collections.abc import Callable
from datetime import date

import pytest

from simile.casting import Bond, CastError, Pin, bind, cast, village_houses
from simile.schema import Character, HookKind, HookSide, PastMemory

type Make = Callable[..., Character]

HOUSES = [f"house_{n}" for n in range(1, 11)]


def test_homes_are_the_village_maps_houses(pool: list[Character]) -> None:
    houses = village_houses()

    made = bind(cast(pool, 10, seed=4), seed=4)

    assert len(houses) == 10
    assert all(house.startswith("house_") for house in houses)
    assert sorted(r.home for r in made.residents) == sorted(houses)


def test_a_one_way_hook_binds_to_the_opposite_side(make: Make) -> None:
    lender = make("lender", hooks=(("debt", "target", "They never paid me back."),))
    borrower = make("borrower", hooks=(("debt", "actor", "I still owe them."),))

    made = bind([lender, borrower], houses=HOUSES)

    assert made.bonds == [
        Bond(
            kind=HookKind.DEBT,
            actor="borrower",
            target="lender",
            actor_hook="I still owe them.",
            target_hook="They never paid me back.",
        )
    ]


def test_a_hook_never_binds_to_the_same_side(make: Make) -> None:
    a = make("a", hooks=(("debt", "actor"),))
    b = make("b", hooks=(("debt", "actor"),))
    c = make("c", hooks=(("old_friend", "mutual"),))

    assert bind([a, b, c], houses=HOUSES).bonds == []


def test_a_mutual_hook_binds_to_the_same_kind(make: Make) -> None:
    a = make("a", hooks=(("rival", "mutual", "Mine."),))
    b = make("b", hooks=(("rival", "mutual", "Theirs."),))

    [bond] = bind([a, b], houses=HOUSES).bonds

    assert bond.kind is HookKind.RIVAL
    assert {bond.actor_hook, bond.target_hook} == {"Mine.", "Theirs."}


def test_each_pair_bonds_once_and_each_hook_once(make: Make) -> None:
    a = make("a", hooks=(("rival", "mutual"), ("debt", "actor")))
    b = make("b", hooks=(("rival", "mutual"), ("debt", "target")))
    c = make("c", hooks=(("rival", "mutual"),))

    bonds = bind([a, b, c], seed=1, houses=HOUSES).bonds

    pairs = [frozenset((bond.actor, bond.target)) for bond in bonds]
    assert len(pairs) == len(set(pairs))
    assert sum(bond.kind is HookKind.RIVAL for bond in bonds) == 1


def test_drawn_siblings_share_an_origin_and_are_close_in_age(make: Make) -> None:
    sibling = (("estranged_sibling", "mutual"),)
    a = make("a", hooks=sibling, origin="Ghana", birth_year=1980)
    elsewhere = make("b", hooks=sibling, origin="Peru", birth_year=1982)
    older = make("c", hooks=sibling, origin="Ghana", birth_year=1950)
    close = make("d", hooks=sibling, origin="Ghana", birth_year=1975)

    assert bind([a, elsewhere, older], houses=HOUSES).bonds == []
    [bond] = bind([a, elsewhere, older, close], houses=HOUSES).bonds
    assert {bond.actor, bond.target} == {"a", "d"}


def test_pins_bind_as_given_and_use_matching_hooks(make: Make) -> None:
    a = make("a", hooks=(("saved_life", "target", "They pulled me out."),))
    b = make("b")
    c = make("c", hooks=(("saved_life", "actor", "I pulled them out."),))
    pins = [
        Pin(kind=HookKind.ESTRANGED_SIBLING, actor="a", target="b"),
        Pin(kind=HookKind.SAVED_LIFE, actor="b", target="a"),
    ]

    with pytest.raises(CastError, match="pinned twice"):
        bind([a, b, c], pins, houses=HOUSES)

    bonds = bind([a, b, c], pins[1:], houses=HOUSES).bonds

    assert bonds == [
        Bond(
            kind=HookKind.SAVED_LIFE,
            actor="b",
            target="a",
            target_hook="They pulled me out.",
            pinned=True,
        )
    ]


def test_a_pin_outside_the_cast_is_refused(make: Make) -> None:
    with pytest.raises(CastError, match="Pinned c, who isn't in the cast"):
        bind([make("a"), make("b")], [Pin(kind=HookKind.RIVAL, actor="a", target="c")])


def test_every_drawn_bond_joins_matching_hooks(pool: list[Character]) -> None:
    for seed in range(20):
        made = bind(cast(pool, 10, seed=seed, houses=10), seed=seed, houses=HOUSES)
        hooks = {r.character.id: r.character.hooks for r in made.residents}
        assert made.bonds
        for bond in made.bonds:
            actor, target = (
                (HookSide.MUTUAL, HookSide.MUTUAL)
                if bond.kind.mutual
                else (HookSide.ACTOR, HookSide.TARGET)
            )
            assert any(
                (h.kind, h.side, h.description) == (bond.kind, actor, bond.actor_hook)
                for h in hooks[bond.actor]
            )
            assert any(
                (h.kind, h.side, h.description) == (bond.kind, target, bond.target_hook)
                for h in hooks[bond.target]
            )


def test_the_cast_records_its_date_seed_and_each_characters_version(make: Make) -> None:
    a = make("a", version=3)

    made = bind([a], seed=9, game_date=date(2030, 5, 1), houses=HOUSES)

    assert made.game_date == date(2030, 5, 1)
    assert made.seed == 9
    assert (made.residents[0].character.id, made.residents[0].character.version) == ("a", 3)


def test_a_game_date_their_ages_cant_fit_is_refused(make: Make) -> None:
    past = [PastMemory(age=40, content="A move.", salience=0.5, valence=0.0)]
    a = make("a", birth_year=1980, past=past)

    with pytest.raises(CastError, match="1979-06-01 is too early for A: born in 1980"):
        bind([a], game_date=date(1979, 6, 1), houses=HOUSES)
    with pytest.raises(CastError, match="past up to age 40"):
        bind([a], game_date=date(2010, 1, 1), houses=HOUSES)
    with pytest.raises(CastError, match="2101-01-01 is too late for A"):
        bind([a], game_date=date(2101, 1, 1), houses=HOUSES)
    assert bind([a], game_date=date(2020, 1, 1), houses=HOUSES).npcs()[0].age == 40
