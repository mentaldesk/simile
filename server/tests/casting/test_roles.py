from collections import Counter
from collections.abc import Callable
from statistics import mean

import pytest

from simile.casting import bind, cast
from simile.casting.bind import wage
from simile.casting.choose import elder, family
from simile.casting.roles import holders, village_roles
from simile.characters.jobs import maker
from simile.schema import Character, Npc, PayKind, Weekday
from simile.world.map import load_maps

type Make = Callable[..., Character]

YEAR = 2026
HOUSES = [f"house_{n}" for n in range(1, 11)]
LIBRARY = [
    ("barista_one", "Barista", 1995),
    ("barista_two", "Barista", 1990),
    ("cook", "Cook", 1980),
    ("chef", "Chef", 1985),
    ("roboticist", "Programmer of drone swarms", 1992),
    ("mason", "Stonemason restoring old bridges", 1988),
    ("animator", "Stop-motion animator", 1990),
    ("typographer", "Typeface designer", 1975),
    ("physicist", "Theoretical physicist working on dark matter", 1970),
    ("novelist", "Science fiction novelist", 1983),
    ("drummer", "Session drummer", 1999),
    ("philosopher", "Philosopher of mind", 1979),
    ("welder", "Retired welder", 1950),
    ("clerk", "Retired court clerk", 1955),
    ("driver", "Retired bus driver", 1948),
    ("cashier", "Supermarket cashier", 2001),
]


@pytest.fixture
def library(make: Make) -> list[Character]:
    return [make(id, occupation=job, birth_year=born) for id, job, born in LIBRARY]


@pytest.mark.parametrize("seed", range(20))
def test_roles_are_filled_first_by_characters_whose_jobs_fit(
    library: list[Character], seed: int
) -> None:
    chosen = cast(library, 10, seed=seed, houses=10, year=YEAR)
    held = holders(chosen, village_roles())

    assert [role.id for role in held.values()] == [
        "barista",
        "cook",
        "maker_space_host",
        "gallery_host",
    ]
    assert list(held) == [c.id for c in chosen[:4]]
    assert chosen[0].occupation == "Barista"
    assert chosen[1].occupation in ("Cook", "Chef")
    assert chosen[2].id in ("roboticist", "mason")
    assert chosen[3].id in ("animator", "typographer")


def test_a_small_cast_fills_the_roles_in_order(library: list[Character]) -> None:
    chosen = cast(library, 2, seed=1, houses=10, year=YEAR)

    assert [c.occupation for c in chosen][0] == "Barista"
    assert chosen[1].occupation in ("Cook", "Chef")


def test_a_pick_whose_job_fits_holds_the_role_and_nobody_else_does_that_job(
    library: list[Character],
) -> None:
    for seed in range(20):
        chosen = cast(library, 10, picks=["barista_two"], seed=seed, houses=10, year=YEAR)

        assert chosen[0].id == "barista_two"
        assert holders(chosen, village_roles())["barista_two"].id == "barista"
        assert [c.occupation for c in chosen].count("Barista") == 1


def test_a_role_nobody_fits_stays_open(library: list[Character]) -> None:
    unfit = [c for c in library if c.occupation != "Barista"]

    chosen = cast(unfit, 10, seed=2, houses=10, year=YEAR)

    assert len(chosen) == 10
    assert "barista" not in {role.id for role in holders(chosen, village_roles()).values()}


def test_nobody_retired_holds_a_role(make: Make) -> None:
    retired = make("retired_barista", occupation="Retired barista", birth_year=1950)

    assert holders([retired], village_roles()) == {}


def test_without_roles_a_cast_is_drawn_as_before(library: list[Character]) -> None:
    chosen = cast(library, 4, seed=3, houses=10, roles=(), year=YEAR)

    assert len(chosen) == 4
    assert holders(chosen, ()) == {}


def test_role_holders_work_at_the_role_with_its_shifts_and_pay(library: list[Character]) -> None:
    made = bind(cast(library, 10, seed=5, houses=10, year=YEAR), seed=5, houses=HOUSES)
    npcs = {npc.id: npc for npc in made.npcs()}
    held = holders([r.character for r in made.residents], village_roles())

    assert sorted(role.id for role in held.values()) == sorted(r.id for r in village_roles())
    for id, role in held.items():
        npc = npcs[id]
        assert (npc.workplace, npc.shifts) == (role.workplace, role.shifts)
        assert npc.pay == (role.pay or wage(role.shifts))
        assert Npc.model_validate_json(npc.model_dump_json()) == npc


def test_the_barista_and_cook_take_their_shops_takings() -> None:
    roles = {role.id: role for role in village_roles()}

    for id in ("barista", "cook"):
        pay = roles[id].pay
        assert pay is not None and pay.kind is PayKind.TAKINGS
    [cafe] = roles["barista"].shifts
    assert (cafe.days, cafe.start, cafe.end) == (list(Weekday), 7, 17)


def test_every_roles_workplace_is_an_interior_on_the_map() -> None:
    interiors = load_maps()

    for role in village_roles():
        assert role.workplace in interiors
        assert interiors[role.workplace].location(role.workplace).map == role.workplace


def test_a_cast_from_the_pool_fills_every_role(pool: list[Character]) -> None:
    for seed in range(20):
        chosen = cast(pool, 10, seed=seed, year=YEAR)

        assert len(holders(chosen, village_roles())) == len(village_roles())


def test_over_many_casts_seven_in_ten_outside_the_roles_make_or_think_and_elders_stay(
    pool: list[Character],
) -> None:
    shares = []
    for seed in range(50):
        chosen = cast(pool, 10, seed=seed, year=YEAR)
        held = holders(chosen, village_roles())
        others = [c for c in chosen if c.id not in held]
        shares.append(sum(maker(c.occupation) for c in others) / len(others))
        ages = [YEAR - c.birth_year for c in chosen]

        assert sum(elder(c, YEAR) for c in chosen) >= 2
        assert max(ages) - min(ages) >= 40
        assert max(Counter(family(c) for c in others).values()) == 1
    assert mean(shares) == pytest.approx(0.7, abs=0.05)
