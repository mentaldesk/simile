import random

import pytest

from simile.cafe.config import DEFAULT_CONFIG, CafeConfig
from simile.cafe.lines import Lines
from simile.cafe.menu import load_menu
from simile.world.map import SpotKind, load_maps

from .conftest import make_npc

MENU = load_menu()


def test_the_menu_has_the_five_drinks_each_with_its_own_wait() -> None:
    assert [drink.name for drink in MENU.drinks] == [
        "espresso",
        "flat white",
        "long black",
        "chai",
        "hot chocolate",
    ]
    assert MENU.seconds("espresso") < MENU.seconds("chai")
    assert MENU.seconds(None) == MENU.seconds("anything else") == MENU.improvised_seconds


@pytest.mark.parametrize(
    ("values", "usual"),
    [
        ({"ambition": 1.0, "discipline": 1.0}, "espresso"),
        ({"connection": 1.0, "creativity": 1.0}, "flat_white"),
        ({"independence": 1.0, "knowledge": 1.0}, "long_black"),
        ({"peace_of_mind": 1.0, "tradition": 1.0}, "chai"),
        ({"pleasure": 1.0, "optimism": 1.0}, "hot_chocolate"),
    ],
)
def test_a_residents_usual_follows_their_values(values: dict[str, float], usual: str) -> None:
    assert MENU.usual(make_npc("ana", "house_1", **values)).id == usual


def test_residents_mostly_order_their_usual() -> None:
    npc = make_npc("ana", "house_1", pleasure=1.0, optimism=1.0)
    rng = random.Random(0)

    orders = [MENU.choose(npc, rng, 0.75).id for _ in range(400)]

    assert 0.75 < orders.count("hot_chocolate") / len(orders) < 1
    assert len(set(orders)) > 2


def test_stock_lines_fill_in_names_and_articles() -> None:
    lines = Lines()
    rng = random.Random(0)

    ordered = {lines.pick("order", rng, drink="espresso") for _ in range(30)}
    called = lines.pick("player_gone", rng, drink="oat flat white")

    assert ordered == {
        "An espresso, please.",
        "Just an espresso, thanks.",
        "Could I get an espresso?",
    }
    assert called == "Oat flat white for the Visitor!"


def test_every_stock_line_fills_in() -> None:
    lines, rng = Lines(), random.Random(0)
    names = {"customer": "Ana", "barista": "Bea", "drink": "chai"}

    for kind, options in lines.options.items():
        for _ in options:
            assert "{" not in lines.pick(kind, rng, **names), kind


def test_the_cafe_spots_are_floor_to_stand_on_inside() -> None:
    maps = load_maps()
    config = DEFAULT_CONFIG
    layout = config.layouts["coffee_shop_floor_0"]
    ground = maps["coffee_shop_floor_0"]
    spots = [layout.entrance, layout.machine, layout.hand_over, layout.pickup, layout.upstairs]
    floors = {ground.id, *(floor.map for floor in ground.location(config.home).floors)}

    assert {tile.map for tile in [*spots, *layout.seats]} <= floors
    assert all(maps[tile.map].standing(tile.x, tile.y) for tile in [*spots, *layout.seats])
    for seat in layout.seats:
        spot = maps[seat.map].spot_at(seat.x, seat.y)
        assert spot is not None and spot.kind is SpotKind.SEAT
    staff = ground.location(config.staff).area
    for tile in (layout.machine, layout.hand_over):
        assert (
            staff.x <= tile.x < staff.x + staff.width and staff.y <= tile.y < staff.y + staff.height
        )


def test_the_cafe_opens_before_it_closes() -> None:
    with pytest.raises(ValueError, match="open before it closes"):
        CafeConfig(opens=18, closes=17)
