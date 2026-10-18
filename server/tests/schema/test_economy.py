import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from simile.schema import Character, Npc, Pay, PayKind, Shift, Weekday, export

FIXTURES = Path(__file__).parents[1] / "fixtures" / "npcs"
FIELDS = ["workplace", "shifts", "pay", "money"]

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday"]
OWNER: dict[str, Any] = {
    "workplace": "coffee_shop",
    "shifts": [
        {"days": ["tuesday", "wednesday", "thursday", "friday"], "start": 6.5, "end": 15.0},
        {"days": ["saturday"], "start": 8.0, "end": 13.0},
    ],
    "pay": {"kind": "takings", "amount": None},
    "money": 1450.0,
}
REMOTE: dict[str, Any] = {
    "workplace": "house_3",
    "shifts": [{"days": WEEKDAYS, "start": 9.0, "end": 17.5}],
    "pay": {"kind": "wage", "amount": 21.5},
    "money": 800.0,
}
RETIRED: dict[str, Any] = {"pay": {"kind": "pension", "amount": 310.0}, "money": 5200.0}


def npc(name: str, **fields: Any) -> dict[str, Any]:
    return json.loads((FIXTURES / f"{name}.json").read_text()) | fields


def schema(name: str) -> Draft202012Validator:
    return Draft202012Validator(json.loads((export.JSON_DIR / f"{name}.json").read_text()))


def rejects(data: dict[str, Any], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        Npc.model_validate(data)


@pytest.mark.parametrize("name", ["mei", "suki", "viktor"])
def test_without_work_they_have_none_and_it_is_left_out(name: str) -> None:
    parsed = Npc.model_validate(npc(name))

    assert (parsed.workplace, parsed.shifts, parsed.pay, parsed.money) == (None, [], None, 0)
    assert not set(FIELDS) & set(json.loads(parsed.model_dump_json()))
    assert not set(FIELDS) & set(parsed.model_dump())


@pytest.mark.parametrize(("name", "work"), [("mei", OWNER), ("suki", REMOTE), ("viktor", RETIRED)])
def test_work_round_trips_after_the_home(name: str, work: dict[str, Any]) -> None:
    parsed = Npc.model_validate(npc(name, **work))

    dumped = json.loads(parsed.model_dump_json())
    keys = list(dumped)

    assert {key: dumped[key] for key in work} == work
    assert keys[keys.index("home") + 1 : keys.index("values")] == list(work)
    assert Npc.model_validate_json(parsed.model_dump_json()) == parsed


def test_characters_have_no_work() -> None:
    premade = json.loads((Path(__file__).parent / "characters" / "premade.json").read_text())

    assert not set(FIELDS) & set(Character.model_fields)
    assert not set(FIELDS) & set(schema("Character").schema["properties"])
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Character.model_validate(premade | {"workplace": "coffee_shop"})


@pytest.mark.parametrize(
    ("shift", "match"),
    [
        ({"days": ["friday"], "start": 22.0, "end": 2.0}, "split one past midnight"),
        ({"days": ["friday"], "start": 9.0, "end": 9.0}, "doesn't end after it starts"),
        ({"days": ["friday"], "start": -1.0, "end": 9.0}, "greater than or equal to 0"),
        ({"days": ["friday"], "start": 20.0, "end": 26.0}, "less than or equal to 24"),
        ({"days": [], "start": 9.0, "end": 17.0}, "at least 1 item"),
        ({"days": ["friday", "friday"], "start": 9.0, "end": 17.0}, "each day once"),
        ({"days": ["fri"], "start": 9.0, "end": 17.0}, "monday"),
    ],
)
def test_a_shift_is_on_some_days_and_ends_after_it_starts(
    shift: dict[str, Any], match: str
) -> None:
    with pytest.raises(ValidationError, match=match):
        Shift.model_validate(shift)


def test_a_late_shift_runs_to_midnight_and_the_rest_is_the_next_day() -> None:
    shifts = [
        {"days": ["friday"], "start": 18.0, "end": 24.0},
        {"days": ["saturday"], "start": 0.0, "end": 1.5},
    ]

    parsed = Npc.model_validate(npc("suki", **REMOTE | {"shifts": shifts}))

    assert [(shift.start, shift.end) for shift in parsed.shifts] == [(18, 24), (0, 1.5)]


@pytest.mark.parametrize(
    "shifts",
    [
        [
            {"days": WEEKDAYS, "start": 9.0, "end": 17.0},
            {"days": ["friday"], "start": 16.0, "end": 20.0},
        ],
        [
            {"days": ["monday"], "start": 9.0, "end": 17.0},
            {"days": ["monday"], "start": 10.0, "end": 11.0},
        ],
    ],
)
def test_shifts_on_the_same_day_do_not_overlap(shifts: list[dict[str, Any]]) -> None:
    rejects(npc("suki", **REMOTE | {"shifts": shifts}), "shifts overlap on")


def test_overlaps_name_the_first_shared_day() -> None:
    shifts = [
        {"days": ["sunday", "wednesday"], "start": 9.0, "end": 17.0},
        {"days": ["wednesday", "sunday"], "start": 12.0, "end": 14.0},
    ]

    rejects(npc("suki", **REMOTE | {"shifts": shifts}), "overlap on wednesday: 9-17 and 12-14")


def test_shifts_can_meet_and_repeat_on_other_days() -> None:
    shifts = [
        {"days": ["monday"], "start": 7.0, "end": 11.0},
        {"days": ["monday"], "start": 11.0, "end": 15.0},
        {"days": ["tuesday"], "start": 7.0, "end": 15.0},
    ]

    assert len(Npc.model_validate(npc("suki", **REMOTE | {"shifts": shifts})).shifts) == 3


@pytest.mark.parametrize(
    ("when", "covered"),
    [
        (datetime(2026, 3, 16, 9, 0, tzinfo=UTC), True),
        (datetime(2026, 3, 16, 17, 29, tzinfo=UTC), True),
        (datetime(2026, 3, 16, 17, 30, tzinfo=UTC), False),
        (datetime(2026, 3, 16, 8, 59, tzinfo=UTC), False),
        (datetime(2026, 3, 21, 12, 0, tzinfo=UTC), False),
    ],
)
def test_a_shift_covers_its_hours_on_its_days(when: datetime, covered: bool) -> None:
    assert Shift.model_validate(REMOTE["shifts"][0]).covers(when) is covered


def test_a_shift_to_midnight_covers_the_last_minute() -> None:
    shift = Shift(days=[Weekday.SUNDAY], start=20, end=24)

    assert shift.covers(datetime(2026, 3, 22, 23, 59, 59, tzinfo=UTC))
    assert not shift.covers(datetime(2026, 3, 23, 0, 0, tzinfo=UTC))


def test_weekdays_follow_the_calendar() -> None:
    monday = datetime(2026, 3, 16, tzinfo=UTC)

    assert [Weekday.of(monday.replace(day=16 + n)) for n in range(7)] == list(Weekday)


@pytest.mark.parametrize(
    ("pay", "match"),
    [
        ({"kind": "wage"}, "a wage needs an amount per hour worked"),
        ({"kind": "pension", "amount": None}, "a pension needs an amount per week"),
        ({"kind": "takings", "amount": 40.0}, "so no amount"),
        ({"kind": "wage", "amount": 0}, "greater than 0"),
        ({"kind": "wage", "amount": float("inf")}, "finite number"),
        ({"kind": "salary", "amount": 20.0}, "'wage', 'takings' or 'pension'"),
    ],
)
def test_pay_has_an_amount_that_fits_its_kind(pay: dict[str, Any], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        Pay.model_validate(pay)


def test_takings_load_without_an_amount() -> None:
    assert Pay.model_validate({"kind": "takings"}) == Pay(kind=PayKind.TAKINGS)


@pytest.mark.parametrize(
    ("money", "match"),
    [(-0.01, "greater than or equal to 0"), (float("inf"), "finite number"), ("lots", "number")],
)
def test_money_is_a_finite_amount_of_at_least_0(money: Any, match: str) -> None:
    rejects(npc("viktor", money=money), match)


@pytest.mark.parametrize(
    ("work", "match"),
    [
        ({"shifts": REMOTE["shifts"]}, "shifts need a workplace"),
        ({"workplace": "house_3"}, "a workplace needs shifts"),
        ({"pay": REMOTE["pay"]}, "wage pay needs a workplace"),
        ({"pay": OWNER["pay"]}, "takings pay needs a workplace"),
    ],
)
def test_work_needs_a_workplace_and_shifts(work: dict[str, Any], match: str) -> None:
    rejects(npc("suki", **work), match)


def test_a_pension_needs_no_workplace_but_allows_one() -> None:
    working = RETIRED | {"workplace": "gallery", "shifts": [OWNER["shifts"][1]]}

    assert Npc.model_validate(npc("viktor", **RETIRED)).workplace is None
    assert Npc.model_validate(npc("viktor", **working)).workplace == "gallery"


@pytest.mark.parametrize(("name", "work"), [("mei", OWNER), ("suki", REMOTE), ("viktor", RETIRED)])
def test_the_exported_schema_allows_but_does_not_require_work(
    name: str, work: dict[str, Any]
) -> None:
    assert schema("Npc").is_valid(npc(name))
    assert schema("Npc").is_valid(npc(name, **work))


@pytest.mark.parametrize(
    "work",
    [
        {"money": -1},
        {"pay": {"kind": "salary", "amount": 20.0}},
        {"pay": {"kind": "wage", "amount": 0}},
        {"shifts": [{"days": ["fri"], "start": 9.0, "end": 17.0}]},
        {"shifts": [{"days": [], "start": 9.0, "end": 17.0}]},
        {"shifts": [{"days": ["friday"], "start": 9.0, "end": 25.0}]},
        {"workplace": "Coffee Shop"},
    ],
)
def test_the_exported_schema_checks_work(work: dict[str, Any]) -> None:
    assert not schema("Npc").is_valid(npc("suki", **REMOTE | work))
