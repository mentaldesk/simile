from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from simile.app import create_app
from simile.machines.materials import plastic
from simile.machines.printer import PISTOL, ROUNDS
from simile.machines.workshop import Workshop, register_offers
from simile.persistence import player_of
from simile.schema import PLAYER_ID, Item, ItemKind, Material, Player, lamp
from simile.sim import Clock, FakeWallClock, World
from simile.street.village import ARIS_SPOOL
from simile.world import Movement, Point, movement_of
from simile.world.map import load_maps

MAPS = load_maps()
PRINTER = "printer_3d"
FLOOR = "maker_space_floor_0"
AT_THE_PRINTER = Point(9, 2, FLOOR)
MakePackage = Callable[[dict[str, str]], str]


def scrap(weight: float) -> Item:
    return Item(id="ballast", kind=ItemKind.SALVAGE, name="Ballast", weight=weight)


def the_spool() -> Item:
    [spool] = [thing for thing in MAPS[FLOOR].interactables if thing.id == ARIS_SPOOL]
    [plastic_on_it] = spool.items
    return plastic_on_it


def printer(player: Player, at: Point = AT_THE_PRINTER) -> Workshop:
    world = World(Clock(datetime(2026, 1, 1, 12, tzinfo=UTC)), FakeWallClock())
    movement = Movement(MAPS, world.bus)
    movement.track(PLAYER_ID, at)
    shop = Workshop(player, movement)
    register_offers(shop)
    return shop


def ids(player: Player) -> dict[str, float]:
    return {item.id: item.amount for item in player.items}


def test_a_broken_printer_offers_nothing_and_makes_nothing() -> None:
    player = Player(items=[the_spool()])
    shop = printer(player)

    assert shop.machine(PRINTER).makes == []
    assert not shop.make(PRINTER, PISTOL.id)
    assert player.items == [the_spool()]


def test_a_working_printer_offers_a_pistol_and_a_magazine_for_their_plastic() -> None:
    makes = printer(Player(repaired=[PRINTER])).machine(PRINTER).makes

    assert [(p.item.id, p.item.amount, p.uses, p.cost) for p in makes] == [
        ("plastic_pistol", 1, Material.PLASTIC, 6),
        ("plastic_rounds", 6, Material.PLASTIC, 2),
    ]


def test_the_pistol_holds_six_and_comes_empty_and_new() -> None:
    assert (PISTOL.kind, PISTOL.material) == (ItemKind.WEAPON, Material.PLASTIC)
    assert (PISTOL.rounds, PISTOL.capacity, PISTOL.condition) == (0, 6, 1.0)
    assert (ROUNDS.kind, ROUNDS.material) == (ItemKind.ROUNDS, Material.PLASTIC)


def test_what_it_prints_survives_a_save() -> None:
    player = Player(items=[PISTOL, ROUNDS, the_spool()])

    assert Player.model_validate_json(player.model_dump_json()).items == player.items


def test_the_spool_is_on_arises_bench_and_weighs_four_kilos() -> None:
    assert the_spool() == plastic(8.0)
    assert the_spool().load == 4.0


@pytest.mark.parametrize("first", [PISTOL.id, ROUNDS.id])
def test_the_spool_alone_prints_one_of_each_and_no_more(first: str) -> None:
    second = ROUNDS.id if first == PISTOL.id else PISTOL.id
    player = Player(items=[lamp(), the_spool()], repaired=[PRINTER])
    shop = printer(player)

    assert shop.make(PRINTER, first)
    assert shop.make(PRINTER, second)
    made = list(player.items)

    assert not shop.make(PRINTER, PISTOL.id)
    assert not shop.make(PRINTER, ROUNDS.id)
    assert player.items == made
    assert sorted(item.id for item in made) == ["lamp", PISTOL.id, ROUNDS.id]


def test_the_spool_is_not_enough_for_two_pistols() -> None:
    player = Player(items=[the_spool()], repaired=[PRINTER])
    shop = printer(player)

    assert shop.make(PRINTER, PISTOL.id)
    assert not shop.make(PRINTER, PISTOL.id)
    assert ids(player) == {"plastic": 2.0, PISTOL.id: 1}


def test_rounds_join_what_they_carry_but_each_pistol_is_its_own() -> None:
    player = Player(items=[plastic(16.0)], repaired=[PRINTER])
    shop = printer(player)

    assert shop.make(PRINTER, ROUNDS.id) and shop.make(PRINTER, ROUNDS.id)
    assert shop.make(PRINTER, PISTOL.id) and shop.make(PRINTER, PISTOL.id)

    assert [(item.id, item.amount) for item in player.items] == [
        (ROUNDS.id, 12.0),
        (PISTOL.id, 1),
        (PISTOL.id, 1),
    ]


def test_it_uses_plastic_across_stacks_and_leaves_what_is_over() -> None:
    player = Player(items=[plastic(1.5), lamp(), plastic(4.75)], repaired=[PRINTER])

    assert printer(player).make(PRINTER, PISTOL.id)

    assert [(item.id, item.amount) for item in player.items] == [
        ("lamp", 1),
        ("plastic", 0.25),
        (PISTOL.id, 1),
    ]


def test_plastic_used_up_to_a_rounding_error_leaves_no_stack() -> None:
    player = Player(items=[plastic(0.1 + 0.2), plastic(1.7)], repaired=[PRINTER])

    assert printer(player).make(PRINTER, ROUNDS.id)

    assert [item.id for item in player.items] == [ROUNDS.id]
    assert Player.model_validate_json(player.model_dump_json()).items == player.items


def test_too_little_plastic_changes_nothing() -> None:
    items = [plastic(5.5)]
    player = Player(items=items, repaired=[PRINTER])

    assert not printer(player).make(PRINTER, PISTOL.id)
    assert player.items == items


def test_it_prints_only_while_they_stand_at_it() -> None:
    items = [the_spool()]
    player = Player(items=items, repaired=[PRINTER])

    assert not printer(player, Point(4, 2, FLOOR)).make(PRINTER, PISTOL.id)
    assert player.items == items


@pytest.mark.parametrize(
    ("ballast", "fits"),
    [(10.88, True), (10.89, False)],
)
def test_it_refuses_what_wouldnt_fit_as_the_panels_load_after_does(
    ballast: float, fits: bool
) -> None:
    items = [plastic(10.0), scrap(ballast)]
    player = Player(items=items, repaired=[PRINTER])

    # loadAfter: 5 kg of plastic + ballast - 2 * 0.5 kg + 6 * 0.02 kg against the limit of 15.
    assert printer(player).make(PRINTER, ROUNDS.id) is fits
    assert (player.items == items) is not fits


def make_app(make_package: MakePackage) -> Starlette:
    modules = ("behaviour", "economy", "memory", "protocol", "world")
    files = {f"{m}/lifespan.py": f"from simile.{m}.lifespan import lifespan\n" for m in modules}
    files["protocol/routes.py"] = "from simile.protocol.routes import routes\n"
    for module in ("machines", "player", "sim"):
        files[f"{module}/lifespan.py"] = f"from simile.{module}.lifespan import running\n"
    app = create_app(make_package(files))
    app.state.world = World(Clock(datetime(2026, 1, 1, 10, tzinfo=UTC)))
    return app


def moved(client: TestClient, app: Starlette, ws: Any, at: Point) -> None:
    ws.send_json({"type": "player_move", "position": {"x": at.x, "y": at.y, "map": at.map}})
    movement = movement_of(app)
    for _ in range(2000):
        if client.portal.call(movement.entities).get(PLAYER_ID) == at:
            return
    raise AssertionError(f"the server never had the player at {at}")


def carrying(ws: Any, item: str, seconds: float = 5) -> dict[str, Any]:
    """The next `player_state` showing `item` among what they carry, failing rather than hanging:
    `receive_json` has no timeout."""

    def read() -> dict[str, Any]:
        for _ in range(500):
            message = ws.receive_json()
            if message["type"] == "player_state":
                items = {found["id"]: found for found in message["player"]["items"]}
                if item in items:
                    return items
        raise AssertionError(f"they never carried {item}")

    pool = ThreadPoolExecutor(1)
    try:
        return pool.submit(read).result(timeout=seconds)
    finally:
        pool.shutdown(wait=False)


def test_pressing_make_against_a_server_prints_from_the_spool(make_package: MakePackage) -> None:
    app = make_app(make_package)

    with TestClient(app) as client:
        player_of(app).repaired = [PRINTER]
        with client.websocket_connect("/ws") as ws:
            moved(client, app, ws, Point(4, 2, FLOOR))
            ws.send_json({"type": "pick_up"})
            spooled = carrying(ws, "plastic")

            moved(client, app, ws, AT_THE_PRINTER)
            ws.send_json({"type": "make", "machine": PRINTER, "item": PISTOL.id})
            armed = carrying(ws, PISTOL.id)
            ws.send_json({"type": "make", "machine": PRINTER, "item": ROUNDS.id})
            loaded = carrying(ws, ROUNDS.id)

            ws.send_json({"type": "make", "machine": PRINTER, "item": ROUNDS.id})
            moved(client, app, ws, Point(4, 2, FLOOR))
            player = player_of(app)

    assert spooled["plastic"]["amount"] == 8
    assert armed["plastic"]["amount"] == 2
    assert armed[PISTOL.id]["capacity"] == 6
    assert "plastic" not in loaded
    assert loaded[ROUNDS.id]["amount"] == 6
    assert ARIS_SPOOL in player.searched
    assert sorted(item.id for item in player.items) == ["lamp", PISTOL.id, ROUNDS.id]
    assert ids(player)[ROUNDS.id] == 6
