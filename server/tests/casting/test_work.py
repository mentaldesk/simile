from collections.abc import Callable

import pytest

from simile.casting import bind
from simile.casting.bind import wage
from simile.casting.config import DEFAULT_CONFIG
from simile.casting.model import Cast
from simile.casting.roles import village_roles
from simile.casting.variety import of_cast
from simile.schema import Character, CoreValue, Npc, PayKind, Shift, Weekday

type Make = Callable[..., Character]

HOUSES = [f"house_{n}" for n in range(1, 11)]


def made(make: Make, *jobs: tuple[str, str], seed: int = 0) -> Cast:
    chosen = [make(id, occupation=job, birth_year=1980) for id, job in jobs]
    return bind(chosen, seed=seed, houses=HOUSES, roles=())


def test_everyone_without_a_role_works_where_their_job_does_or_from_home(make: Make) -> None:
    cast = made(
        make,
        ("roboticist", "Programmer of drone swarms"),
        ("novelist", "Science fiction novelist"),
        ("cashier", "Supermarket cashier"),
    )
    npcs = {npc.id: npc for npc in cast.npcs()}

    assert npcs["roboticist"].workplace == "maker_space"
    assert npcs["roboticist"].shifts in DEFAULT_CONFIG.hours["maker_space"]
    for id in ("novelist", "cashier"):
        npc = npcs[id]
        assert npc.workplace == npc.home
        assert npc.shifts in DEFAULT_CONFIG.hours["home"]
    for npc in npcs.values():
        assert npc.pay == wage(npc.shifts)
        assert Npc.model_validate_json(npc.model_dump_json()) == npc


def test_someone_retired_has_a_pension_and_no_workplace(make: Make) -> None:
    [npc] = made(make, ("welder", "Retired welder")).npcs()

    assert (npc.workplace, npc.shifts) == (None, [])
    assert npc.pay is not None and npc.pay.kind is PayKind.PENSION
    assert npc.pay.amount == DEFAULT_CONFIG.pension


def test_a_wage_pays_a_full_week_of_shifts_the_weekly_pay() -> None:
    days = [Weekday.MONDAY, Weekday.TUESDAY, Weekday.WEDNESDAY, Weekday.THURSDAY, Weekday.FRIDAY]
    pay = wage([Shift(days=days, start=9, end=13)])

    assert pay.kind is PayKind.WAGE
    assert pay.amount == round(DEFAULT_CONFIG.weekly_pay / 20)


def test_hosts_without_pay_in_their_role_get_a_wage() -> None:
    roles = {role.id: role for role in village_roles()}

    assert roles["gallery_host"].pay is None
    assert wage(roles["gallery_host"].shifts).kind is PayKind.WAGE


def test_everyone_starts_with_money_and_security_brings_more(make: Make) -> None:
    def money(security: float) -> float:
        values = dict.fromkeys(CoreValue, 0.5) | {CoreValue.SECURITY: security}
        chosen = [make("saver", occupation="Science fiction novelist", values=values)]
        return bind(chosen, seed=3, houses=HOUSES, roles=()).residents[0].money

    low, high = DEFAULT_CONFIG.start_money
    assert low * 0.5 <= money(0.0) <= high * 0.5
    assert money(1.0) == pytest.approx(money(0.0) * 3, abs=1)


def test_work_is_stable_for_a_seed(make: Make) -> None:
    first = made(make, ("novelist", "Science fiction novelist"), seed=4)
    again = made(make, ("novelist", "Science fiction novelist"), seed=4)

    assert first.npcs() == again.npcs()


def test_a_workplace_alone_doesnt_count_as_a_role_for_variety(make: Make) -> None:
    cast = made(
        make, ("novelist", "Science fiction novelist"), ("poet", "Science fiction novelist")
    )

    assert all(r.workplace for r in cast.residents)
    assert of_cast(cast).repeats == 1
