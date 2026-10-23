import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, get_args

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from simile.schema import (
    LEGS,
    MODELS,
    PRESENT,
    SOLD,
    Bionic,
    Body,
    BodyPart,
    Item,
    ItemKind,
    MapTile,
    Pile,
    Player,
    export,
    lamp,
)

HERE = Path(__file__).parent
PLAYERS: list[dict[str, Any]] = json.loads((HERE / "players.json").read_text())
STARTING, KIDNEY_SOLD, DELVING, FITTED, COLLAPSED, SALVAGING = PLAYERS
SALVAGE = DELVING["items"][1]


def schema(name: str) -> Draft202012Validator:
    return Draft202012Validator(json.loads((export.JSON_DIR / f"{name}.json").read_text()))


def rejects(model: type[Player | Item | Body | Pile], data: dict[str, Any], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        model.model_validate(data)


@pytest.mark.parametrize(
    "data", PLAYERS, ids=["starting", "kidney_sold", "delving", "fitted", "collapsed", "salvaging"]
)
def test_fixture_round_trips_through_json(data: dict[str, Any]) -> None:
    parsed = Player.model_validate_json(json.dumps(data))
    dumped = parsed.model_dump_json()

    assert json.loads(dumped) == data
    assert Player.model_validate_json(dumped) == parsed


def test_it_is_exported_and_the_schema_accepts_the_fixtures() -> None:
    assert {Player, Item} <= set(MODELS)
    for data in PLAYERS:
        schema("Player").validate(data)
    schema("Item").validate(SALVAGE)
    assert not schema("Player").is_valid(STARTING | {"humanity": 1.0})


def test_the_starting_player_is_whole_with_no_money_and_a_charged_lamp() -> None:
    player = Player()

    assert player.money == 0
    assert player.items == [lamp()]
    assert player.items[0].charge == 1
    assert all(state == PRESENT for _, state in player.body)
    assert player.body.bionics == []
    assert player.hunger == 0
    assert player.left == []
    assert player.humanity == 1
    assert json.loads(player.model_dump_json()) == STARTING


def test_anything_left_out_is_the_starting_players() -> None:
    assert Player.model_validate({}) == Player()
    assert Player.model_validate(FITTED).left == []
    assert Player.model_validate({"money": 40}).items == [lamp()]
    assert Body.model_validate({"legs": "hydraulic_legs"}).left_kidney == PRESENT


def test_humanity_falls_with_each_bionic_fitted() -> None:
    humanity = [Player.model_validate(data).humanity for data in PLAYERS]

    assert humanity[0] == humanity[1] == 1
    assert humanity[0] > humanity[2] > humanity[3] > 0
    assert Player.model_validate(FITTED).body.bionics == [
        Bionic.HYDRAULIC_LEGS,
        Bionic.DATAJACK,
        Bionic.INFRARED_EYE,
    ]


def test_the_eye_costs_the_most_humanity() -> None:
    costs = {bionic: bionic.humanity_cost for bionic in Bionic}

    assert max(costs, key=costs.__getitem__) is Bionic.INFRARED_EYE
    assert all(0 < cost < 1 for cost in costs.values())


def test_all_three_bionics_still_leave_some_humanity() -> None:
    assert Player.model_validate(FITTED).humanity == pytest.approx(0.55)


def test_humanity_is_never_saved() -> None:
    assert "humanity" not in Player.model_fields
    assert "humanity" not in json.loads(Player.model_validate(FITTED).model_dump_json())


@pytest.mark.parametrize(
    ("bionic", "parts"),
    [
        *((legs, {"legs"}) for legs in LEGS),
        (Bionic.DATAJACK, {"vertebra"}),
        (Bionic.INFRARED_EYE, {"left_eye", "right_eye"}),
    ],
)
def test_each_bionic_fits_only_in_place_of_its_part(bionic: Bionic, parts: set[str]) -> None:
    assert bionic.replaces == parts
    for part in Body.model_fields:
        if part in parts:
            assert Body.model_validate({part: bionic.value}).bionics == [bionic]
        else:
            rejects(Body, {part: bionic.value}, f"{bionic} can't replace {part}")


def test_every_grade_of_legs_is_a_bionic_that_takes_the_legs() -> None:
    assert LEGS[0] is Bionic.HYDRAULIC_LEGS, "today's legs are the first grade, so saves keep them"
    assert {bionic for bionic in Bionic if bionic.replaces == {"legs"}} == set(LEGS)
    assert len({legs.humanity_cost for legs in LEGS}) == 1
    assert Body.model_validate({"legs": "spring_legs"}).bionics == [Bionic.SPRING_LEGS]


def test_a_part_is_an_item_found_for_the_doctor_to_fit() -> None:
    part = Item(id="apex_actuator", kind=ItemKind.PART, name="Apex actuator", weight=2.0)

    assert Item.model_validate(part.model_dump()) == part
    assert part.charge is None and part.on is None
    schema("Item").validate(part.model_dump(mode="json"))


def test_a_body_part_names_each_part_of_the_body() -> None:
    assert get_args(BodyPart.__value__) == tuple(Body.model_fields)
    assert all(bionic.replaces <= set(Body.model_fields) for bionic in Bionic)


@pytest.mark.parametrize("eye", ["left_eye", "right_eye"])
def test_the_infrared_eye_goes_in_either_eye(eye: str) -> None:
    assert Body.model_validate({eye: "infrared_eye"}).bionics == [Bionic.INFRARED_EYE]


def test_there_is_only_one_infrared_eye() -> None:
    rejects(
        Body,
        {"left_eye": "infrared_eye", "right_eye": "infrared_eye"},
        "there's only one infrared eye",
    )


def test_any_part_can_be_sold() -> None:
    body = Body.model_validate(dict.fromkeys(Body.model_fields, SOLD))

    assert body.bionics == []
    assert Player(body=body).humanity == 1


def test_bionics_set_in_python_count_as_fitted() -> None:
    player = Player()
    player.body.vertebra = "datajack"

    assert player.body.bionics == [Bionic.DATAJACK]


@pytest.mark.parametrize(
    ("data", "match"),
    [
        ({"legs": "gone"}, "legs"),
        ({"legs": None}, "legs"),
        ({"tail": SOLD}, "Extra inputs are not permitted"),
    ],
)
def test_rejects_invalid_bodies(data: dict[str, Any], match: str) -> None:
    rejects(Body, data, match)


def test_the_starting_lamp_is_charged_and_switched_off() -> None:
    assert (lamp().charge, lamp().on) == (1, False)


@pytest.mark.parametrize(
    ("field", "value", "what"), [("charge", 0.5, "charge"), ("on", True, "switch")]
)
def test_only_a_lamp_has_a_charge_and_a_switch(field: str, value: Any, what: str) -> None:
    rejects(Item, lamp().model_dump() | {field: None}, f"a lamp has a {what},")
    rejects(Item, SALVAGE | {field: value}, f"a lamp has a {what}, and nothing else has one")
    assert Item.model_validate(SALVAGE).kind is ItemKind.SALVAGE


@pytest.mark.parametrize(
    ("update", "match"),
    [
        ({"charge": 1.5}, "less than or equal to 1"),
        ({"charge": -0.1}, "greater than or equal to 0"),
        ({"weight": -1}, "greater than or equal to 0"),
        ({"weight": float("inf")}, "finite number"),
        ({"name": ""}, "at least 1 character"),
        ({"id": "Lamp"}, "String should match pattern"),
        ({"kind": "torch"}, "kind"),
        ({"on": "dim"}, "valid boolean"),
    ],
)
def test_rejects_invalid_items(update: dict[str, Any], match: str) -> None:
    rejects(Item, lamp().model_dump() | update, match)


@pytest.mark.parametrize(
    ("update", "match"),
    [
        ({"money": -1}, "greater than or equal to 0"),
        ({"money": float("nan")}, "finite number"),
        ({"hunger": 1.1}, "less than or equal to 1"),
        ({"hunger": -0.1}, "greater than or equal to 0"),
        ({"carry_limit": 0}, "greater than 0"),
        ({"humanity": 0.5}, "Extra inputs are not permitted"),
    ],
)
def test_rejects_invalid_players(update: dict[str, Any], match: str) -> None:
    rejects(Player, STARTING | update, match)


def test_load_is_what_everything_carried_weighs() -> None:
    assert Player().load == 1
    assert Player.model_validate(DELVING).load == 7.5
    assert Player(items=[]).load == 0


def changes(
    model: Player | Item | Body | Pile | MapTile, field: str, value: Any, match: str
) -> None:
    before = model.model_dump()
    with pytest.raises(ValidationError, match=match):
        setattr(model, field, value)
    assert model.model_dump() == before


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("hunger", 1.02, "less than or equal to 1"),
        ("money", -5, "greater than or equal to 0"),
        ("carry_limit", 0, "greater than 0"),
    ],
)
def test_rejects_invalid_changes_to_the_player(field: str, value: Any, match: str) -> None:
    changes(Player(), field, value, match)


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("charge", -0.01, "greater than or equal to 0"),
        ("charge", None, "a lamp has a charge"),
        ("on", None, "a lamp has a switch"),
        ("kind", "salvage", "nothing else has one"),
    ],
)
def test_rejects_invalid_changes_to_the_lamp(field: str, value: Any, match: str) -> None:
    changes(lamp(), field, value, match)


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("legs", Bionic.DATAJACK, "datajack can't replace legs"),
        ("right_eye", Bionic.INFRARED_EYE, "there's only one infrared eye"),
        ("vertebra", "gone", "vertebra"),
    ],
)
def test_rejects_invalid_changes_to_the_body(field: str, value: Any, match: str) -> None:
    changes(Body(left_eye=Bionic.INFRARED_EYE), field, value, match)


def test_a_valid_change_is_kept() -> None:
    player = Player()
    player.hunger = 0.4
    player.items[0].on = True
    player.body.left_kidney = SOLD

    assert (player.hunger, player.items[0].on, player.body.left_kidney) == (0.4, True, SOLD)


def test_what_they_left_where_they_collapsed_is_kept_in_piles() -> None:
    player = Player.model_validate(COLLAPSED)

    assert [item.id for item in player.items] == ["lamp"]
    assert player.load == 1
    assert [pile.at for pile in player.left] == [MapTile(map="kapok_walk", x=12, y=15)]
    assert [item.id for item in player.left[0].items] == ["copper_wire", "servo_motor"]


def test_a_player_who_left_nothing_dumps_without_piles() -> None:
    assert "left" not in json.loads(Player(left=[]).model_dump_json())
    assert "left" not in schema("Player").schema["required"]


def test_when_they_took_from_each_pickup_is_kept_by_its_id() -> None:
    player = Player.model_validate(SALVAGING)

    assert player.taken == {
        "metro_secret_stairwell": datetime(2026, 3, 14, 9, 40, tzinfo=UTC),
        "metro_salvage_2": datetime(2026, 3, 14, 10, 5, 30, tzinfo=UTC),
        "metro_salvage_4": datetime(2026, 3, 14, 10, 12, tzinfo=UTC),
    }
    assert [item.id for item in player.left[0].items] == ["copper_wire", "brass_valve"]


def test_a_player_who_took_nothing_dumps_without_taken() -> None:
    assert Player.model_validate(COLLAPSED).taken == {}
    assert "taken" not in json.loads(Player(taken={}).model_dump_json())
    assert "taken" not in schema("Player").schema["required"]


@pytest.mark.parametrize(
    ("taken", "match"),
    [
        ({"metro_salvage_1": "2026-03-14T10:05:30"}, "timezone"),
        ({"metro_salvage_1": "yesterday"}, "valid datetime"),
        ({"": "2026-03-14T10:05:30Z"}, "at least 1 character"),
        (["metro_salvage_1"], "valid dictionary"),
    ],
    ids=["naive", "not_a_time", "no_id", "a_list"],
)
def test_rejects_an_invalid_time_taken(taken: Any, match: str) -> None:
    rejects(Player, SALVAGING | {"taken": taken}, match)


def test_times_taken_are_utc() -> None:
    later = SALVAGING | {"taken": {"metro_salvage_1": "2026-03-14T21:05:30+11:00"}}

    dumped = json.loads(Player.model_validate(later).model_dump_json())

    assert dumped["taken"] == {"metro_salvage_1": "2026-03-14T10:05:30Z"}


def test_a_pile_can_hold_money_and_no_items() -> None:
    cash = Pile(at=MapTile(map="metro", x=8, y=7), items=[], money=25)

    assert json.loads(cash.model_dump_json()) == {
        "at": {"map": "metro", "x": 8, "y": 7},
        "items": [],
        "money": 25.0,
    }
    assert Player(left=[cash]).left[0].money == 25


def test_a_pile_without_money_dumps_without_it() -> None:
    pile = Pile.model_validate(COLLAPSED["left"][0])

    assert pile.money == 0
    assert "money" not in json.loads(pile.model_dump_json())
    assert "money" not in schema("Player").schema["$defs"]["Pile"]["required"]


@pytest.mark.parametrize(
    ("update", "match"),
    [
        ({"items": []}, "at least one item or some money"),
        ({"items": [], "money": 0}, "at least one item or some money"),
        ({"money": -1}, "greater than or equal to 0"),
        ({"money": float("inf")}, "finite number"),
        ({"items": [], "money": "0"}, "valid number"),
        ({"items": [], "money": "25"}, "valid number"),
        ({"at": {"map": "kapok_walk", "x": -1, "y": 15}}, "greater than or equal to 0"),
        ({"at": None}, "at"),
        ({"weight": 3}, "Extra inputs are not permitted"),
    ],
)
def test_rejects_invalid_piles(update: dict[str, Any], match: str) -> None:
    rejects(Pile, COLLAPSED["left"][0] | update, match)


def test_rejects_an_empty_pile_left_on_a_player() -> None:
    player = Player.model_validate(COLLAPSED)

    changes(player.left[0], "items", [], "at least one item or some money")


@pytest.mark.parametrize("money", [0, "0", "25"])
def test_rejects_taking_the_money_from_a_pile_of_only_money(money: Any) -> None:
    cash = Pile(at=MapTile(map="metro", x=8, y=7), items=[], money=25)

    changes(cash, "money", money, "at least one item or some money|valid number")


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [("x", -1, "greater than or equal to 0"), ("y", 1.5, "valid integer"), ("map", "", "at least")],
)
def test_rejects_moving_a_pile_off_its_map(field: str, value: Any, match: str) -> None:
    player = Player.model_validate(COLLAPSED)

    changes(player.left[0].at, field, value, match)
    assert Player.model_validate_json(player.model_dump_json()) == player
