import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from pydantic import Field, ValidationError

from simile.persistence import SavedWorld
from simile.schema import MODELS, PRESENT, SOLD, Bionic, Body, Item, ItemKind, Player, export, lamp

HERE = Path(__file__).parent
PLAYERS: list[dict[str, Any]] = json.loads((HERE / "players.json").read_text())
STARTING, KIDNEY_SOLD, DELVING, FITTED = PLAYERS
OLD_SAVE: dict[str, Any] = json.loads((HERE / "save_before_the_player.json").read_text())
SALVAGE = DELVING["items"][1]


class SavedWorldWithPlayer(SavedWorld):
    """`SavedWorld` once it saves the player, as the task that wires it in will add it."""

    player: Player = Field(default_factory=Player)


def schema(name: str) -> Draft202012Validator:
    return Draft202012Validator(json.loads((export.JSON_DIR / f"{name}.json").read_text()))


def rejects(model: type[Player | Item | Body], data: dict[str, Any], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        model.model_validate(data)


@pytest.mark.parametrize("data", PLAYERS, ids=["starting", "kidney_sold", "delving", "fitted"])
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
    assert player.humanity == 1
    assert json.loads(player.model_dump_json()) == STARTING


def test_anything_left_out_is_the_starting_players() -> None:
    assert Player.model_validate({}) == Player()
    assert Player.model_validate({"money": 40}).items == [lamp()]
    assert Body.model_validate({"legs": "hydraulic_legs"}).left_kidney == PRESENT


def test_a_save_from_before_the_player_loads_with_the_starting_player() -> None:
    assert "player" not in OLD_SAVE
    assert json.loads(SavedWorld.model_validate(OLD_SAVE).model_dump_json()) == OLD_SAVE

    loaded = SavedWorldWithPlayer.model_validate_json(json.dumps(OLD_SAVE))

    assert loaded.player == Player()
    assert loaded.npcs.keys() == {"desmond", "henrietta"}


def test_the_player_saves_and_loads_with_the_world() -> None:
    world = SavedWorldWithPlayer.model_validate(OLD_SAVE | {"player": DELVING})

    loaded = SavedWorldWithPlayer.model_validate_json(world.model_dump_json())

    assert loaded.player == Player.model_validate(DELVING)


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


def test_every_bionic_there_is_room_for_still_leaves_some_humanity() -> None:
    everything = Body(
        legs=Bionic.HYDRAULIC_LEGS,
        vertebra=Bionic.DATAJACK,
        left_eye=Bionic.INFRARED_EYE,
        right_eye=Bionic.INFRARED_EYE,
    )

    assert 0 < Player(body=everything).humanity < Player.model_validate(FITTED).humanity


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


def test_only_a_lamp_has_a_charge() -> None:
    rejects(Item, lamp().model_dump() | {"charge": None}, "a lamp has a charge")
    rejects(Item, SALVAGE | {"charge": 0.5}, "nothing else does")
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
