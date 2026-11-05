import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, get_args

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from simile.schema import (
    BIONIC_LEGS,
    BODY_PARTS,
    LINES,
    MODELS,
    POWER_CELLS,
    PRESENT,
    SOLD,
    SPRING_FEET,
    STASH_LIMIT,
    Bionic,
    Body,
    BodyPart,
    Corpse,
    Effect,
    EffectKind,
    Item,
    ItemKind,
    MapTile,
    Material,
    Mind,
    Pile,
    Player,
    Recipe,
    Sale,
    Stash,
    export,
    lamp,
)

HERE = Path(__file__).parent
PLAYERS: list[dict[str, Any]] = json.loads((HERE / "players.json").read_text())
(
    STARTING,
    KIDNEY_SOLD,
    DELVING,
    FITTED,
    COLLAPSED,
    SALVAGING,
    CELL_FITTED,
    HURT,
    SEARCHING,
    ARMED,
    DEAD,
) = PLAYERS
STAGE_1 = PLAYERS[:-5]
BEFORE_VITALS = PLAYERS[:-4]
BEFORE_SEARCHING = PLAYERS[:-3]
BEFORE_THE_STASH = PLAYERS[:-2]
BEFORE_CORPSES = PLAYERS[:-1]
CORPSES: list[dict[str, Any]] = json.loads((HERE / "corpses.json").read_text())
FULL_CORPSE, EMPTY_CORPSE = CORPSES
STAGE_2_SAVE = (HERE / "stage_2_player.json").read_text()
SALVAGE = DELVING["items"][1]
LAMP, PISTOL, ROUNDS, PLASTIC, SALVAGED_CELL = ARMED["items"]
RECIPES: list[dict[str, Any]] = json.loads((HERE / "recipes.json").read_text())
CELL, JACK, APEX_LEGS, EYE = RECIPES


def schema(name: str) -> Draft202012Validator:
    return Draft202012Validator(json.loads((export.JSON_DIR / f"{name}.json").read_text()))


def rejects(
    model: type[Player | Item | Body | Pile | Recipe | Mind | Effect | Sale | Stash | Corpse],
    data: dict[str, Any],
    match: str,
) -> None:
    with pytest.raises(ValidationError, match=match):
        model.model_validate(data)


@pytest.mark.parametrize(
    "data",
    PLAYERS,
    ids=[
        "starting",
        "kidney_sold",
        "delving",
        "fitted",
        "collapsed",
        "salvaging",
        "cell_fitted",
        "hurt",
        "searching",
        "armed",
        "dead",
    ],
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
    assert Body.model_validate({"legs": "bionic_legs"}).left_kidney == PRESENT


def test_a_new_player_carries_15_kg() -> None:
    assert Player().carry_limit == 15


def test_a_save_holding_the_old_10_kg_limit_loads_at_15() -> None:
    def loaded(carry_limit: float) -> float:
        saved = json.dumps(STARTING | {"carry_limit": carry_limit})
        return Player.model_validate_json(saved).carry_limit

    assert loaded(10) == 15
    assert loaded(12) == 12
    assert Player(carry_limit=10).carry_limit == 10


def test_humanity_falls_with_each_bionic_fitted() -> None:
    humanity = [Player.model_validate(data).humanity for data in PLAYERS]

    assert humanity[0] == humanity[1] == 1
    assert humanity[0] > humanity[2] > humanity[3] > 0
    assert Player.model_validate(FITTED).body.bionics == [
        Bionic.BIONIC_LEGS,
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
        *((legs, {"legs"}) for legs in BIONIC_LEGS),
        *((cell, {"stomach"}) for cell in POWER_CELLS),
        *((feet, {"feet"}) for feet in SPRING_FEET),
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
    assert {bionic for bionic in Bionic if bionic.replaces == {"legs"}} == set(BIONIC_LEGS)
    assert len({legs.humanity_cost for legs in BIONIC_LEGS}) == 1


@pytest.mark.parametrize(
    ("legs", "body"),
    [
        ("hydraulic_legs", Body(feet=Bionic.SPRING_FEET)),
        ("spring_legs", Body(feet=Bionic.SPRING_FEET_2)),
        ("sprint_legs", Body(legs=Bionic.BIONIC_LEGS)),
        ("blade_legs", Body(legs=Bionic.BIONIC_LEGS_2)),
        ("premium_legs", Body(legs=Bionic.BIONIC_LEGS_3, feet=Bionic.SPRING_FEET_2)),
    ],
)
def test_stage_1s_legs_load_as_the_lines(legs: str, body: Body) -> None:
    saved = FITTED | {"body": FITTED["body"] | {"legs": legs}}
    player = Player.model_validate(saved)

    assert player.body == body.model_copy(
        update={"vertebra": Bionic.DATAJACK, "right_eye": Bionic.INFRARED_EYE, "left_kidney": SOLD}
    )
    assert Player.model_validate_json(player.model_dump_json()) == player
    assert legs not in Bionic


def test_stage_1s_legs_keep_higher_feet_already_fitted() -> None:
    body = Body.model_validate({"legs": "hydraulic_legs", "feet": "spring_feet_2"})

    assert body == Body(feet=Bionic.SPRING_FEET_2)
    assert Body.model_validate({"legs": "sprint_legs", "feet": "spring_feet"}) == Body(
        legs=Bionic.BIONIC_LEGS, feet=Bionic.SPRING_FEET
    )


def test_a_part_is_an_item_found_for_the_doctor_to_fit() -> None:
    part = Item(id="apex_actuator", kind=ItemKind.PART, name="Apex actuator", weight=2.0)

    assert Item.model_validate(part.model_dump()) == part
    assert part.charge is None and part.on is None
    schema("Item").validate(part.model_dump(mode="json"))


def test_a_body_part_names_each_part_of_the_body() -> None:
    assert get_args(BodyPart.__value__) == BODY_PARTS == tuple(Body.model_fields)
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
    model: Player | Item | Body | Pile | MapTile | Mind | Effect,
    field: str,
    value: Any,
    match: str,
) -> None:
    before = model.model_dump()
    with pytest.raises(ValidationError, match=match):
        setattr(model, field, value)
    assert model.model_dump() == before


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("hunger", 1.02, "less than or equal to 1"),
        ("power", -0.01, "greater than or equal to 0"),
        ("health", 1.5, "less than or equal to 1"),
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


@pytest.mark.parametrize("data", STAGE_1)
def test_a_stage_1_save_loads_knowing_nothing_with_its_own_stomach_and_feet(
    data: dict[str, Any],
) -> None:
    player = Player.model_validate(data)

    assert (player.body.stomach, player.body.feet) == (PRESENT, PRESENT)
    assert player.mind == Mind()
    assert json.loads(player.model_dump_json()) == data


def test_a_stomach_and_feet_still_theirs_and_an_empty_mind_are_left_out() -> None:
    dumped = json.loads(Player(body=Body(stomach=SOLD)).model_dump_json())

    assert "mind" not in dumped
    assert dumped["body"]["stomach"] == SOLD
    assert "feet" not in dumped["body"]
    assert not {"stomach", "feet"} & set(schema("Player").schema["$defs"]["Body"]["required"])
    assert "mind" not in schema("Player").schema["required"]


def test_a_fitted_cell_legs_and_feet_count_as_bionics() -> None:
    player = Player.model_validate(CELL_FITTED)

    assert player.body.bionics == [
        Bionic.BIONIC_LEGS,
        Bionic.DATAJACK,
        Bionic.POWER_CELL,
        Bionic.SPRING_FEET,
    ]
    assert player.humanity == pytest.approx(1 - 0.15 - 0.1 - 0.1 - 0.1)


def test_each_line_comes_in_grades_of_one_part() -> None:
    assert LINES == (POWER_CELLS, BIONIC_LEGS, SPRING_FEET)
    for line in LINES:
        assert len(line) > 1
        assert len({bionic.replaces for bionic in line}) == 1
        assert len({bionic.humanity_cost for bionic in line}) == 1
        assert all(bionic.line == line for bionic in line)
    assert Bionic.DATAJACK.line == (Bionic.DATAJACK,)


def test_a_higher_grade_counts_as_having_a_lower_one() -> None:
    body = Body(stomach=Bionic.POWER_CELL_2, vertebra=Bionic.DATAJACK)

    assert body.has(Bionic.POWER_CELL) and body.has(Bionic.POWER_CELL_2)
    assert not body.has(Bionic.POWER_CELL_3)
    assert body.has(Bionic.DATAJACK)
    assert not body.has(Bionic.BIONIC_LEGS)


@pytest.mark.parametrize("data", RECIPES, ids=lambda data: data["bionic"])
def test_recipe_fixture_round_trips_through_json(data: dict[str, Any]) -> None:
    recipe = Recipe.model_validate_json(json.dumps(data))

    assert json.loads(recipe.model_dump_json()) == data
    schema("Recipe").validate(data)


def test_recipes_are_exported_with_every_field_required() -> None:
    assert Recipe in MODELS
    assert set(schema("Recipe").schema["required"]) == set(Recipe.model_fields)


def test_a_recipe_left_without_what_it_replaces_takes_its_bionics() -> None:
    def without_replaces(data: dict[str, Any]) -> Recipe:
        return Recipe.model_validate({k: v for k, v in data.items() if k != "replaces"})

    assert without_replaces(EYE).replaces == ["left_eye", "right_eye"]
    assert without_replaces(CELL).replaces == ["stomach"]


def test_a_recipe_is_ready_once_what_comes_before_it_is_fitted() -> None:
    cell, legs = Recipe.model_validate(CELL), Recipe.model_validate(APEX_LEGS)

    assert cell.ready(Body())
    assert not legs.ready(Body(stomach=Bionic.POWER_CELL))
    assert legs.ready(Body(stomach=Bionic.POWER_CELL_2))
    assert legs.ready(Body(stomach=Bionic.POWER_CELL_3))


@pytest.mark.parametrize(
    ("update", "match"),
    [
        ({"replaces": ["left_eye"]}, "datajack replaces vertebra"),
        ({"replaces": ["vertebra", "vertebra"]}, "datajack replaces vertebra"),
        ({"replaces": ["tail"]}, "replaces"),
        ({"after": ["datajack"]}, "never itself"),
        ({"after": ["power_cell", "power_cell"]}, "once each"),
        ({"parts": {"copper_wire": 0}}, "greater than or equal to 1"),
        ({"parts": {"": 1}}, "at least 1 character"),
        ({"credits": -1}, "greater than or equal to 0"),
        ({"credits": float("inf")}, "finite number"),
        ({"name": ""}, "at least 1 character"),
        ({"bionic": "jetpack"}, "bionic"),
        ({"price": 100}, "Extra inputs are not permitted"),
    ],
)
def test_rejects_invalid_recipes(update: dict[str, Any], match: str) -> None:
    rejects(Recipe, JACK | update, match)


def test_a_mind_keeps_what_it_learned_and_sold_in_order() -> None:
    mind = Player.model_validate(CELL_FITTED).mind

    assert mind.recipes[:2] == [Bionic.POWER_CELL, Bionic.DATAJACK]
    assert mind.sold == [Bionic.POWER_CELL]
    assert "sold" not in json.loads(Mind(recipes=[Bionic.DATAJACK]).model_dump_json())


@pytest.mark.parametrize(
    ("data", "match"),
    [
        ({"recipes": ["datajack", "datajack"]}, "knows each recipe once"),
        ({"recipes": ["datajack"], "sold": ["datajack", "datajack"]}, "sells it once"),
        ({"recipes": ["datajack"], "sold": ["power_cell"]}, "only sell a recipe they know"),
        ({"sold": ["datajack"]}, "only sell a recipe they know"),
        ({"recipes": ["jetpack"]}, "recipes"),
        ({"recipes": "datajack"}, "valid list"),
        ({"recipes": [{}]}, "recipes"),
    ],
)
def test_rejects_invalid_minds(data: dict[str, Any], match: str) -> None:
    rejects(Mind, data, match)


def test_rejects_selling_a_recipe_they_never_learned_or_forgetting_one_sold() -> None:
    mind = Mind(recipes=[Bionic.DATAJACK])

    changes(mind, "sold", [Bionic.POWER_CELL], "only sell a recipe they know")
    mind.sold = [Bionic.DATAJACK]
    changes(mind, "recipes", [], "only sell a recipe they know")
    assert mind.sold == [Bionic.DATAJACK]


BITE = HURT["effects"][0]


@pytest.mark.parametrize("data", BEFORE_VITALS)
def test_a_save_from_before_vitals_loads_at_full_health_and_power_with_no_effects(
    data: dict[str, Any],
) -> None:
    player = Player.model_validate(data)

    assert (player.health, player.power) == (1, 1)
    assert player.effects == []
    assert player.sales == []
    assert json.loads(player.model_dump_json()) == data


def test_full_vitals_no_effects_and_no_sales_are_left_out() -> None:
    required = schema("Player").schema["required"]

    for field in ("power", "health", "effects", "sales"):
        assert field not in json.loads(Player().model_dump_json())
        assert field in Player.model_fields
        assert field not in required
    assert json.loads(Player(health=0.99).model_dump_json())["health"] == 0.99


def test_a_hurt_player_has_their_vitals_effects_and_what_they_can_buy_back() -> None:
    player = Player.model_validate(HURT)

    assert (player.hunger, player.power, player.health) == (0.3, 0.65, 0.5)
    assert [effect.kind for effect in player.effects] == [EffectKind.RAT_BITE, EffectKind.INFECTION]
    bite, infection = player.effects
    assert (bite.strength, bite.fades) == (0.2, 0.05)
    assert bite.since == datetime(2026, 3, 15, 11, 20, tzinfo=UTC)
    assert infection.fades is None
    assert [(sale.item.id, sale.place, sale.price) for sale in player.sales] == [
        ("copper_wire", "scrap_stall", 6),
        ("copper_wire", "scrap_stall", 5),
    ]


def test_an_effect_lasting_until_treated_says_so_with_null() -> None:
    assert json.loads(Effect.model_validate(HURT["effects"][1]).model_dump_json())["fades"] is None
    assert "fades" in schema("Player").schema["$defs"]["Effect"]["required"]


@pytest.mark.parametrize(
    ("update", "match"),
    [
        ({"kind": "snake_bite"}, "rat_bite"),
        ({"strength": 0}, "greater than 0"),
        ({"strength": 1.1}, "less than or equal to 1"),
        ({"fades": 0}, "greater than 0"),
        ({"fades": float("inf")}, "finite"),
        ({"since": "2026-03-15T11:20:00"}, "timezone"),
    ],
)
def test_rejects_invalid_effects(update: dict[str, Any], match: str) -> None:
    rejects(Effect, BITE | update, match)


def test_rejects_an_effect_without_how_it_fades() -> None:
    rejects(Effect, {key: value for key, value in BITE.items() if key != "fades"}, "fades")


def test_they_have_each_kind_of_effect_once() -> None:
    rejects(Player, HURT | {"effects": [BITE, BITE | {"strength": 0.5}]}, "each kind of effect")
    player = Player.model_validate(HURT)
    changes(player, "effects", [*player.effects, Effect.model_validate(BITE)], "each kind")
    assert len(player.effects) == 2


@pytest.mark.parametrize(
    ("update", "match"),
    [
        ({"place": "Scrap stall"}, "pattern"),
        ({"price": -1}, "greater than or equal to 0"),
    ],
)
def test_rejects_invalid_sales(update: dict[str, Any], match: str) -> None:
    rejects(Sale, HURT["sales"][0] | update, match)


@pytest.mark.parametrize("data", BEFORE_SEARCHING)
def test_a_save_from_before_searching_has_searched_nothing(data: dict[str, Any]) -> None:
    player = Player.model_validate(data)

    assert player.searched == []
    assert json.loads(player.model_dump_json()) == data


def test_a_stage_2_save_loads_as_it_was() -> None:
    player = Player.model_validate_json(STAGE_2_SAVE)

    assert player.stash == Stash()
    assert all(item.amount == 1 for item in player.items)
    assert player.load == pytest.approx(6.2)
    assert player.left[0].items[0].amount == 1
    assert player.sales[0].item.amount == 1
    assert player.corpses == []
    assert player.repaired == []
    assert json.loads(player.model_dump_json()) == json.loads(STAGE_2_SAVE)


@pytest.mark.parametrize("data", BEFORE_THE_STASH)
def test_a_save_from_before_the_stash_has_an_empty_one_at_the_starting_limit(
    data: dict[str, Any],
) -> None:
    player = Player.model_validate(data)

    assert player.stash.items == []
    assert player.stash.limit == STASH_LIMIT == 20
    assert json.loads(player.model_dump_json()) == data


def test_a_stack_weighs_each_one_by_its_amount() -> None:
    assert Item.model_validate(ROUNDS).load == pytest.approx(0.6)
    assert Item.model_validate(SALVAGE).load == SALVAGE["weight"]
    assert Player.model_validate(ARMED).load == pytest.approx(6.1)


def test_the_stash_counts_against_its_own_limit_and_not_what_they_carry() -> None:
    player = Player.model_validate(ARMED)

    assert player.stash.load == 9.5
    assert player.load == pytest.approx(6.1)


def test_a_stash_that_holds_something_or_has_been_fitted_out_is_saved() -> None:
    assert "stash" not in Player().model_dump(mode="json")
    stocked = Player(stash=Stash(items=[Item.model_validate(PLASTIC)]))
    fitted_out = Player(stash=Stash(limit=40))

    for player in (stocked, fitted_out):
        assert Player.model_validate_json(player.model_dump_json()) == player


def test_plastic_is_a_material_by_kind_and_amount() -> None:
    plastic = Item.model_validate(PLASTIC)

    assert (plastic.kind, plastic.material, plastic.amount) == (
        ItemKind.MATERIAL,
        Material.PLASTIC,
        2.5,
    )


def test_a_weapon_has_its_rounds_loaded_its_capacity_and_its_condition() -> None:
    pistol = Item.model_validate(PISTOL)

    assert (pistol.kind, pistol.rounds, pistol.capacity, pistol.condition) == (
        ItemKind.WEAPON,
        4,
        6,
        0.8,
    )
    assert pistol.amount == 1


def test_a_weapon_can_be_full() -> None:
    assert Item.model_validate(PISTOL | {"rounds": 6}).rounds == 6


def test_an_empty_worn_out_weapon_is_still_a_weapon() -> None:
    pistol = Item.model_validate(PISTOL | {"rounds": 0, "condition": 0.0})

    assert json.loads(pistol.model_dump_json()) == PISTOL | {"rounds": 0, "condition": 0.0}


@pytest.mark.parametrize("bionic", list(Bionic))
def test_any_grade_of_any_bionic_can_be_salvaged(bionic: Bionic) -> None:
    item = Item.model_validate(SALVAGED_CELL | {"id": bionic.value, "bionic": bionic.value})

    assert item.bionic is bionic


def test_a_pile_and_a_sale_hold_stacks_and_weapons() -> None:
    pile = Pile(
        at=MapTile(map="sewers", x=1, y=2),
        items=[Item.model_validate(ROUNDS), Item.model_validate(PISTOL)],
    )

    assert Pile.model_validate_json(pile.model_dump_json()) == pile
    assert json.loads(pile.model_dump_json())["items"] == [ROUNDS, PISTOL]


@pytest.mark.parametrize(
    ("data", "match"),
    [
        (SALVAGE | {"rounds": 6}, "a weapon has a magazine, and nothing else has one"),
        (SALVAGE | {"capacity": 6}, "a weapon has a capacity, and nothing else has one"),
        (SALVAGE | {"condition": 1.0}, "a weapon has a condition, and nothing else has one"),
        (SALVAGE | {"bionic": "datajack"}, "a bionic has a grade, and nothing else has one"),
        (SALVAGE | {"material": "plastic"}, "nothing else does"),
        (LAMP | {"material": "plastic"}, "nothing else does"),
        (PISTOL | {"rounds": None}, "a weapon has a magazine,"),
        (PISTOL | {"capacity": None}, "a weapon has a capacity,"),
        (PISTOL | {"condition": None}, "a weapon has a condition,"),
        (PISTOL | {"material": None}, "nothing else does"),
        (ROUNDS | {"material": None}, "nothing else does"),
        (PLASTIC | {"material": None}, "nothing else does"),
        (SALVAGED_CELL | {"bionic": None}, "a bionic has a grade,"),
        (PISTOL | {"rounds": -1}, "greater than or equal to 0"),
        (PISTOL | {"rounds": 7}, "no more rounds than its capacity"),
        (PISTOL | {"rounds": "7"}, "valid integer"),
        (PISTOL | {"capacity": 3}, "no more rounds than its capacity"),
        (PISTOL | {"rounds": 0, "capacity": 0}, "greater than or equal to 1"),
        (PISTOL | {"capacity": "6"}, "valid integer"),
        (PISTOL | {"condition": 1.5}, "less than or equal to 1"),
        (PLASTIC | {"material": "wood", "id": "wood"}, "material"),
        (PLASTIC | {"id": "carbon_fibre"}, "a material's id is its material"),
        (SALVAGED_CELL | {"bionic": "power_cell"}, "a bionic's id is its bionic"),
        (SALVAGED_CELL | {"id": "kidney", "bionic": "kidney"}, "bionic"),
        (SALVAGE | {"amount": 2.0}, "only material and rounds stack"),
        (LAMP | {"amount": 2.0}, "only material and rounds stack"),
        (PISTOL | {"amount": 2.0}, "only material and rounds stack"),
        (SALVAGED_CELL | {"amount": 2.0}, "only material and rounds stack"),
        (ROUNDS | {"amount": 2.5}, "rounds come whole"),
        (ROUNDS | {"amount": 0}, "greater than 0"),
        (PLASTIC | {"amount": -1}, "greater than 0"),
        (PLASTIC | {"amount": float("inf")}, "finite number"),
        (ROUNDS | {"amount": "2.5"}, "valid number"),
    ],
)
def test_rejects_invalid_stacks_weapons_and_salvaged_bionics(
    data: dict[str, Any], match: str
) -> None:
    rejects(Item, data, match)


@pytest.mark.parametrize(
    ("data", "field", "value", "match"),
    [
        (PISTOL, "rounds", None, "a weapon has a magazine"),
        (PISTOL, "rounds", 7, "no more rounds than its capacity"),
        (PISTOL, "capacity", 3, "no more rounds than its capacity"),
        (PISTOL, "capacity", None, "a weapon has a capacity"),
        (PISTOL, "condition", -0.1, "greater than or equal to 0"),
        (PISTOL, "amount", 3.0, "only material and rounds stack"),
        (ROUNDS, "amount", 1.5, "rounds come whole"),
        (PLASTIC, "amount", 0.0, "greater than 0"),
        (SALVAGE, "amount", 2.0, "only material and rounds stack"),
    ],
)
def test_rejects_invalid_changes_to_stacks_and_weapons(
    data: dict[str, Any], field: str, value: Any, match: str
) -> None:
    changes(Item.model_validate(data), field, value, match)


@pytest.mark.parametrize(
    ("update", "match"),
    [
        ({"limit": 0}, "greater than 0"),
        ({"limit": float("inf")}, "finite number"),
        ({"items": [SALVAGE | {"amount": 2.0}]}, "only material and rounds stack"),
    ],
)
def test_rejects_invalid_stashes(update: dict[str, Any], match: str) -> None:
    rejects(Stash, update, match)


def test_they_keep_what_they_have_searched_in_order() -> None:
    player = Player.model_validate(SEARCHING)

    assert player.searched == ["maker_space_drawers", "aris_bench", "metro_vending_machine"]
    assert "searched" not in schema("Player").schema["required"]


def test_they_search_each_thing_once() -> None:
    rejects(
        Player, SEARCHING | {"searched": ["aris_bench", "aris_bench"]}, "search each thing once"
    )
    rejects(Player, SEARCHING | {"searched": ["Aris bench"]}, "pattern")
    player = Player.model_validate(SEARCHING)
    changes(player, "searched", [*player.searched, "aris_bench"], "search each thing once")
    assert len(player.searched) == 3


@pytest.mark.parametrize("data", BEFORE_CORPSES)
def test_a_save_from_before_corpses_has_none_and_nothing_repaired(data: dict[str, Any]) -> None:
    player = Player.model_validate(data)
    dumped = json.loads(player.model_dump_json())

    assert player.corpses == []
    assert player.repaired == []
    assert "corpses" not in dumped
    assert "repaired" not in dumped


def test_a_dead_players_corpses_and_repairs_are_saved_on_them() -> None:
    player = Player.model_validate(DEAD)

    assert player.corpses[0].bionics == [Bionic.POWER_CELL, Bionic.DATAJACK]
    assert player.corpses[0].at == MapTile(map="sewers", x=14, y=9)
    assert player.repaired == ["printer_3d"]
    assert player.body == Body()


@pytest.mark.parametrize("data", CORPSES, ids=["full", "empty"])
def test_corpse_fixture_round_trips_through_json(data: dict[str, Any]) -> None:
    parsed = Corpse.model_validate_json(json.dumps(data))

    assert json.loads(parsed.model_dump_json()) == data
    schema("Corpse").validate(data)
    assert Corpse in MODELS


def test_a_corpse_keeps_its_stacks_weapons_and_salvaged_bionics() -> None:
    corpse = Corpse.model_validate(FULL_CORPSE)

    assert [item.kind for item in corpse.items] == [
        ItemKind.LAMP,
        ItemKind.MATERIAL,
        ItemKind.WEAPON,
        ItemKind.BIONIC,
    ]
    assert corpse.items[1].amount == 2.5
    assert corpse.items[2].rounds == 2
    assert corpse.bionics == [Bionic.POWER_CELL, Bionic.DATAJACK, Bionic.BIONIC_LEGS_2]


def test_a_corpse_stays_as_it_is_emptied_unlike_a_pile() -> None:
    corpse = Corpse.model_validate(FULL_CORPSE)

    corpse.money = 0
    corpse.items = []
    corpse.bionics = []

    assert (corpse.money, corpse.items, corpse.bionics) == (0, [], [])


def test_two_corpses_can_lie_on_one_tile() -> None:
    player = Player(corpses=[Corpse.model_validate(data) for data in CORPSES])

    assert player.corpses[0].at == player.corpses[1].at


@pytest.mark.parametrize(
    ("update", "match"),
    [
        ({"money": -1}, "greater than or equal to 0"),
        ({"money": float("inf")}, "finite"),
        ({"bionics": ["wings"]}, "Input should be"),
        ({"id": "Corpse 1"}, "should match pattern"),
        ({"owner": ""}, "should match pattern"),
        ({"at": {"x": 1, "y": 1}}, "map"),
    ],
)
def test_rejects_invalid_corpses(update: dict[str, Any], match: str) -> None:
    rejects(Corpse, FULL_CORPSE | update, match)


@pytest.mark.parametrize(
    ("update", "match"),
    [
        ({"corpses": [FULL_CORPSE, FULL_CORPSE]}, "each corpse has its own id"),
        ({"repaired": ["printer_3d", "printer_3d"]}, "repair each machine once"),
        ({"repaired": ["Printer 3D"]}, "should match pattern"),
    ],
)
def test_rejects_invalid_corpses_and_repairs_on_a_player(
    update: dict[str, Any], match: str
) -> None:
    rejects(Player, STARTING | update, match)
