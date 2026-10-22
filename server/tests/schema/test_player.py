import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from simile.schema import (
    MODELS,
    PRESENT,
    SOLD,
    Bionic,
    Body,
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
STARTING, KIDNEY_SOLD, DELVING, FITTED, COLLAPSED = PLAYERS
SALVAGE = DELVING["items"][1]


def schema(name: str) -> Draft202012Validator:
    return Draft202012Validator(json.loads((export.JSON_DIR / f"{name}.json").read_text()))


def rejects(model: type[Player | Item | Body | Pile], data: dict[str, Any], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        model.model_validate(data)


@pytest.mark.parametrize(
    "data", PLAYERS, ids=["starting", "kidney_sold", "delving", "fitted", "collapsed"]
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
        (Bionic.HYDRAULIC_LEGS, {"legs"}),
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


def changes(model: Player | Item | Body | Pile, field: str, value: Any, match: str) -> None:
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

    assert player.items == []
    assert player.load == 0
    assert [pile.at for pile in player.left] == [MapTile(map="kapok_walk", x=12, y=15)]
    assert [item.id for item in player.left[0].items] == ["lamp", "copper_wire"]


def test_a_player_who_left_nothing_dumps_without_piles() -> None:
    assert "left" not in json.loads(Player(left=[]).model_dump_json())
    assert "left" not in schema("Player").schema["required"]


@pytest.mark.parametrize(
    ("update", "match"),
    [
        ({"items": []}, "at least 1 item"),
        ({"at": {"map": "kapok_walk", "x": -1, "y": 15}}, "greater than or equal to 0"),
        ({"at": None}, "at"),
        ({"weight": 3}, "Extra inputs are not permitted"),
    ],
)
def test_rejects_invalid_piles(update: dict[str, Any], match: str) -> None:
    rejects(Pile, COLLAPSED["left"][0] | update, match)


def test_rejects_an_empty_pile_left_on_a_player() -> None:
    player = Player.model_validate(COLLAPSED)

    changes(player.left[0], "items", [], "at least 1 item")
