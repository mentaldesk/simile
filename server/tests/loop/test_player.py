import asyncio
import math
from collections.abc import Callable
from types import SimpleNamespace

import pytest

from simile.loop.player import LoopPlayer, Refused
from simile.protocol import PlayerStateMessage
from simile.schema import Bionic, Body, DoorKind, Item, ItemKind, Material, Player
from simile.street.charge import CLIMB
from simile.street.jump import LEGS
from simile.street.village import ARIS_SPOOL
from simile.world.map import Pickup, PickupKind, load_maps
from simile.world.paths import Spot, crossings

MAPS = load_maps()
CROSSINGS = crossings(MAPS)


def player_on(legs: Bionic | None) -> LoopPlayer:
    player = object.__new__(LoopPlayer)
    player.movement = SimpleNamespace(maps=MAPS, crossings=CROSSINGS)  # type: ignore[assignment]
    body = Body() if legs is None else Body(legs=legs)
    player.state = PlayerStateMessage(player=Player(body=body))
    return player


def climb_up(kind: DoorKind) -> tuple[Spot, Spot]:
    """A step up from one cell of a ladder or a flight to the next."""
    return next(
        (Spot(town.id, x, y), Spot(town.id, x + dx, y - 1))
        for town in MAPS.values()
        for y in range(1, town.height)
        for x in range(town.width)
        for dx in (-1, 0, 1)
        if town.climb(x, y) is kind and town.climb(x + dx, y - 1) is kind
    )


def crossing_by(kind: DoorKind) -> Spot:
    return next(spot for spot, (found, _) in CROSSINGS.items() if found is kind)


@pytest.mark.parametrize("kind", [DoorKind.LADDER, DoorKind.STAIRS])
def test_their_own_legs_climb_at_the_clients_pace(kind: DoorKind) -> None:
    a, b = climb_up(kind)

    assert player_on(None).step(a, b) == pytest.approx(math.dist(a[1:], b[1:]) / CLIMB[kind])


@pytest.mark.parametrize("legs", list(LEGS))
@pytest.mark.parametrize("kind", [DoorKind.LADDER, DoorKind.STAIRS])
def test_bionic_legs_climb_and_cross_floors_faster_by_their_climb(
    legs: Bionic, kind: DoorKind
) -> None:
    a, b = climb_up(kind)
    end = crossing_by(kind)
    own, fitted = player_on(None), player_on(legs)

    assert fitted.step(a, b) == pytest.approx(own.step(a, b) / LEGS[legs].climb)
    assert fitted.crossing(end) == pytest.approx(own.crossing(end) / LEGS[legs].climb)


def test_what_they_gained_includes_a_stack_that_grew_and_fits_weighs_a_whole_stack() -> None:
    player = player_on(None)
    plastic = Item(
        id="plastic",
        kind=ItemKind.MATERIAL,
        name="Plastic",
        weight=0.5,
        amount=2.0,
        material=Material.PLASTIC,
    )
    bun = Item(id="bun", kind=ItemKind.FOOD, name="Bun", weight=0.2)
    before = [plastic]
    player.player.items = [plastic.model_copy(update={"amount": 10.0}), bun]

    assert player.gained(before) == ["Plastic", "Bun"]
    player.player.items = []
    assert player.fits([plastic.model_copy(update={"amount": 30.0})])
    assert not player.fits([plastic.model_copy(update={"amount": 30.5})])


def test_a_door_takes_as_long_on_any_legs() -> None:
    end = crossing_by(DoorKind.DOOR)

    assert player_on(Bionic.BIONIC_LEGS_3).crossing(end) == player_on(None).crossing(end)


def playing(gives: Callable[[Player], None]) -> tuple[LoopPlayer, list[str]]:
    """A player whose every message has the server do `gives`, already where it's going."""
    player = player_on(None)
    notes: list[str] = []

    async def to(goal: Spot) -> None:
        pass

    player.to = to  # type: ignore[method-assign]
    player.send = lambda message: gives(player.player)  # type: ignore[method-assign]
    player.note = notes.append  # type: ignore[method-assign]
    return player, notes


def stack_of(amount: float) -> Item:
    return Item(
        id="plastic",
        kind=ItemKind.MATERIAL,
        name="Plastic",
        weight=0.5,
        amount=amount,
        material=Material.PLASTIC,
    )


PILE = Pickup("pile", PickupKind.SECRET, "kapok_walk", 1, 15)


def test_taking_counts_a_stack_that_grew_as_picked_up() -> None:
    def gives(carrying: Player) -> None:
        carrying.items = [stack_of(10.0)]

    player, notes = playing(gives)
    player.player.items = [stack_of(2.0)]

    asyncio.run(player.take(PILE))

    assert notes == ["Picked up Plastic at pile"]


def test_taking_nothing_is_refused() -> None:
    player, _ = playing(lambda carrying: None)
    player.player.items = [stack_of(2.0)]

    with pytest.raises(Refused):
        asyncio.run(player.take(PILE))


def test_searching_notes_a_stack_that_grew() -> None:
    def gives(carrying: Player) -> None:
        carrying.items = [stack_of(10.0)]
        carrying.searched = [ARIS_SPOOL]

    player, notes = playing(gives)
    player.player.items = [stack_of(2.0)]
    player.reach = lambda jump=None: {Spot("maker_space_floor_0", 4, 2)}  # type: ignore[method-assign]

    asyncio.run(player.search(ARIS_SPOOL))

    assert notes == [f"Searched {ARIS_SPOOL}: Plastic"]
