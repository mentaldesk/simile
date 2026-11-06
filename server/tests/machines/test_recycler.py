import time
from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from starlette.testclient import TestClient

from simile.app import create_app
from simile.clinic.config import DEFAULT_CONFIG
from simile.machines.materials import plastic
from simile.machines.recycler import offers
from simile.machines.workshop import MACHINES, Broken, Workshop, register_offers
from simile.persistence import player_of
from simile.player.config import SALVAGE
from simile.schema import (
    PLAYER_ID,
    Bionic,
    Item,
    ItemKind,
    MachineKind,
    MachineState,
    Material,
    Player,
    Product,
    lamp,
)
from simile.sim import Clock, FakeWallClock, World
from simile.street.finds import COPPER_WIRE, METAL_SHEET
from simile.street.sewers import APEX_BOARD, GAUGE, SCRAP
from simile.world import Movement, Point, movement_of
from simile.world.map import load_maps

MAPS = load_maps()
RECYCLER = "recycler"
AT_IT = Point(1, 2, "maker_space_floor_0")
STEEL, BOARD = SALVAGE["metro_salvage_2"].item, SALVAGE["metro_salvage_3"].item
RELAY = SALVAGE["metro_salvage_5"].item
BATTERY = SCRAP["old_battery"]


RATION = Item(id="ration_pack", kind=ItemKind.FOOD, name="Ration pack", weight=0.5)
PISTOL = Item(
    id="plastic_pistol",
    kind=ItemKind.WEAPON,
    name="Plastic pistol",
    weight=1.0,
    material=Material.PLASTIC,
    rounds=4,
    capacity=6,
    condition=1.0,
)
ROUNDS = Item(
    id="plastic_rounds",
    kind=ItemKind.ROUNDS,
    name="Plastic rounds",
    weight=0.01,
    amount=6.0,
    material=Material.PLASTIC,
)
DATAJACK = Item(
    id=Bionic.DATAJACK,
    kind=ItemKind.BIONIC,
    name="Salvaged datajack",
    weight=0.5,
    bionic=Bionic.DATAJACK,
)
UNUSED_PART = Item(id="unused_part", kind=ItemKind.PART, name="Unused part", weight=1.0)


def scrap(weight: float) -> Item:
    return Item(id="junk", kind=ItemKind.SALVAGE, name="Junk", weight=weight)


def workshop(player: Player, at: Point = AT_IT) -> Workshop:
    world = World(Clock(datetime(2026, 1, 1, 12, tzinfo=UTC)), FakeWallClock())
    movement = Movement(MAPS, world.bus)
    movement.track(PLAYER_ID, at)
    shop = Workshop(player, movement)
    offers(shop)
    return shop


def working(items: list[Item], carry_limit: float = 15.0) -> tuple[Player, Workshop]:
    player = Player(items=items, carry_limit=carry_limit, repaired=[RECYCLER])
    return player, workshop(player)


def listed(shop: Workshop) -> list[Product]:
    return shop.machine(RECYCLER).makes


def test_scrap_becomes_plastic_by_weight_and_the_rest_is_left_alone() -> None:
    player, shop = working([lamp(), STEEL, METAL_SHEET, BOARD, COPPER_WIRE, RELAY])

    assert listed(shop) == [Product(item=plastic(6.0), uses="scrap", cost=6.0)]
    assert shop.make(RECYCLER, "plastic")

    assert player.items == [lamp(), METAL_SHEET, COPPER_WIRE, plastic(6.0)]
    assert listed(shop) == []


def test_a_press_leaves_everything_that_isnt_salvage() -> None:
    others = [lamp(), RATION, PISTOL, ROUNDS, DATAJACK, UNUSED_PART]
    player, shop = working([*others, STEEL])

    assert listed(shop) == [Product(item=plastic(4.5), uses="scrap", cost=4.5)]
    assert shop.make(RECYCLER, "plastic")

    assert player.items == [*others, plastic(4.5)]


def test_it_keeps_back_what_a_machines_repair_uses_though_no_recipe_does() -> None:
    pipe = SCRAP["lead_pipe"]
    world = World(Clock(datetime(2026, 1, 1, 12, tzinfo=UTC)), FakeWallClock())
    movement = Movement(MAPS, world.bus)
    movement.track(PLAYER_ID, AT_IT)
    player = Player(items=[pipe, STEEL], repaired=[RECYCLER])
    machines = {RECYCLER: Broken(MachineKind.RECYCLER, {pipe.id: 1})}
    shop = Workshop(player, movement, machines=machines)
    offers(shop)

    assert listed(shop) == [Product(item=plastic(4.5), uses="scrap", cost=4.5)]
    assert shop.make(RECYCLER, "plastic")

    assert player.items == [pipe, plastic(4.5)]


def test_what_a_recipe_or_a_repair_uses_is_kept_back_and_the_other_salvage_is_scrap() -> None:
    every = {
        item.id: item
        for item in (
            *(salvage.item for salvage in SALVAGE.values()),
            *SCRAP.values(),
            APEX_BOARD,
            GAUGE,
            COPPER_WIRE,
        )
    }
    used = [
        *(recipe.parts for recipe in DEFAULT_CONFIG.recipes.values()),
        *(machine.parts for machine in MACHINES.values()),
    ]
    needed = {id for parts in used for id in parts}

    scrapped = {id for id, item in every.items() if listed(working([item])[1])}

    assert scrapped == every.keys() - needed
    assert scrapped == {
        "scrap_steel",
        "circuit_board",
        "brass_valve",
        "signal_relay",
        "lead_pipe",
        "filter_mesh",
    }


def test_a_press_with_only_kept_back_salvage_changes_nothing() -> None:
    items = [lamp(), COPPER_WIRE, BATTERY, APEX_BOARD]
    player, shop = working(items)

    assert listed(shop) == []
    assert shop.machine(RECYCLER).state is MachineState.WORKING
    assert not shop.make(RECYCLER, "plastic")
    assert player.items == items


def test_a_broken_recycler_offers_nothing_however_much_scrap_they_carry() -> None:
    player = Player(items=[STEEL, BOARD])
    shop = workshop(player)

    machine = shop.machine(RECYCLER)
    assert machine.state is MachineState.BROKEN and machine.makes == []
    assert not shop.make(RECYCLER, "plastic")
    assert player.items == [STEEL, BOARD]


def test_it_needs_them_at_the_machine() -> None:
    player = Player(items=[STEEL], repaired=[RECYCLER])
    shop = workshop(player, Point(9, 2, "maker_space_floor_0"))

    assert not shop.make(RECYCLER, "plastic")
    assert player.items == [STEEL]


def test_what_it_makes_joins_the_plastic_they_carry_where_it_is() -> None:
    player, shop = working([plastic(2.0), BOARD, lamp()])

    assert shop.make(RECYCLER, "plastic")

    assert player.items == [plastic(2.5), lamp()]


def test_what_it_makes_joins_only_the_first_of_two_stacks_even_of_one_object() -> None:
    stack = plastic(2.0)
    player, shop = working([stack, stack, BOARD])

    assert shop.make(RECYCLER, "plastic")

    assert player.items == [plastic(2.5), plastic(2.0)]


def test_a_fractional_press_is_sent_with_its_amount() -> None:
    _, shop = working([BOARD])

    [press] = shop.machine(RECYCLER).model_dump(mode="json")["makes"]

    assert press["item"]["amount"] == 0.5 and press["cost"] == 0.5


@pytest.mark.parametrize(
    ("limit", "made"),
    [(15.0, True), (3.25, True), (3.25 - 1e-10, True), (3.25 - 1e-6, False), (1.0, False)],
)
def test_make_refuses_what_wont_fit_where_the_panels_load_after_does(
    limit: float, made: bool
) -> None:
    # loadAfter of a lamp and 4.5 kg of scrap: 1 + 4.5 - 4.5 + 4.5 * 0.5 = 3.25.
    items = [lamp(), STEEL]
    player, shop = working(items, carry_limit=limit)

    assert listed(shop)
    assert shop.make(RECYCLER, "plastic") is made
    assert player.items == ([lamp(), plastic(4.5)] if made else items)


def test_a_press_that_brings_them_back_under_their_limit_is_made() -> None:
    player, shop = working([scrap(10.0), scrap(10.0)], carry_limit=15.0)

    assert shop.make(RECYCLER, "plastic")
    assert player.items == [plastic(20.0)]


@pytest.mark.parametrize(
    ("items", "lists"),
    [
        ([], False),
        ([scrap(0.0)], False),
        ([scrap(0.0), scrap(0.0)], False),
        ([scrap(1e308), scrap(1e308)], False),
        ([scrap(5e-324)], True),
        ([scrap(1.0), METAL_SHEET.model_copy(update={"weight": 1e308})] * 2, True),
    ],
)
def test_no_carried_items_make_the_offer_raise(items: list[Item], lists: bool) -> None:
    _, shop = working(items)

    assert bool(listed(shop)) is lists
    shop.make(RECYCLER, "plastic")
    shop.machines()


def test_it_makes_nothing_of_scrap_with_no_weight() -> None:
    items = [scrap(0.0)]
    player, shop = working(items)

    assert not shop.make(RECYCLER, "plastic")
    assert player.items == items


def test_register_offers_finds_it() -> None:
    world = World(Clock(datetime(2026, 1, 1, 12, tzinfo=UTC)), FakeWallClock())
    player = Player(items=[STEEL], repaired=[RECYCLER])
    shop = Workshop(player, Movement(MAPS, world.bus))

    register_offers(shop)

    assert [product.item.id for product in shop.machine(RECYCLER).makes] == ["plastic"]


def test_a_press_over_the_socket_turns_scrap_into_plastic(
    make_package: Callable[[dict[str, str]], str],
) -> None:
    modules = ("behaviour", "economy", "memory", "protocol", "world")
    files = {f"{m}/lifespan.py": f"from simile.{m}.lifespan import lifespan\n" for m in modules}
    files["protocol/routes.py"] = "from simile.protocol.routes import routes\n"
    files["machines/lifespan.py"] = "from simile.machines.lifespan import running\n"
    app = create_app(make_package(files))
    app.state.world = World(Clock(datetime(2026, 1, 1, 10, tzinfo=UTC)))
    position = {"x": AT_IT.x, "y": AT_IT.y, "map": AT_IT.map}

    def until(client: TestClient, done: Callable[[], bool]) -> None:
        deadline = time.monotonic() + 2
        while not client.portal.call(done):
            assert time.monotonic() < deadline, "the server never got there"
            time.sleep(0.001)

    with TestClient(app) as client:
        player = player_of(app)
        player.repaired = [RECYCLER]
        player.items = [lamp(), BOARD, BATTERY]
        with client.websocket_connect("/ws") as ws:
            snapshot = ws.receive_json()
            assert snapshot["type"] == "snapshot"
            [press] = next(m for m in snapshot["machines"] if m["id"] == RECYCLER)["makes"]
            assert press["item"]["amount"] == 0.5
            ws.send_json({"type": "player_move", "position": position})
            until(client, lambda: movement_of(app).entities().get(PLAYER_ID) == AT_IT)
            ws.send_json({"type": "make", "machine": RECYCLER, "item": "plastic"})
            until(client, lambda: BOARD not in player.items)

    assert player.items == [lamp(), BATTERY, plastic(0.5)]
