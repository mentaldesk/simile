from collections.abc import Collection, Sequence
from dataclasses import replace
from functools import cache

import pytest

from simile.schema import Bionic, InteractableKind
from simile.street.charge import LIGHT, REACH, Ways, runs, seconds
from simile.street.jump import FEET, JUMP, Jump
from simile.street.metro import (
    ARRIVAL,
    BOTS,
    CONTAINER,
    CRANE_SECRET,
    FREIGHT_CRATES,
    FRIDGE,
    LEDGE_SECRET,
    LIFT_FOOT,
    LOCKERS,
    METRO,
    PLUG,
    RELAY_RACK,
    SIGNAL_DESK,
    SWITCHBOARD,
    TICKET_MACHINE,
    TOOL_CRATE,
)
from simile.street.sewers import GATE_BOX, LANDING, LEVELS, SEWERS, way_in, way_on
from simile.street.village import GROUND
from simile.world.map import TownMap, load_maps

type Cell = tuple[int, int]

METRO_MAP = load_maps()[METRO]
BOT_FLOORS = {(x, GROUND) for _, west, east in BOTS for x in range(west - 1, east + 2)}
"""Never walked: P34's way past the bots is overhead."""
OVER_THE_BOTS = Ways(METRO_MAP, avoid=BOT_FLOORS)
WEST = [
    "metro_secret_stairwell",
    TICKET_MACHINE,
    "metro_salvage_1",
    "metro_secret_catwalk",
    "metro_salvage_2",
    "metro_salvage_3",
    FRIDGE,
]
EAST = [
    "metro_salvage_5",
    FREIGHT_CRATES,
    CONTAINER,
    "metro_secret_container",
    "metro_salvage_7",
    SWITCHBOARD,
    RELAY_RACK,
    SIGNAL_DESK,
    "metro_salvage_8",
    TOOL_CRATE,
    "metro_salvage_9",
    "metro_secret_tunnel",
    LOCKERS,
]
"""What the player's own legs reach on the metro, either side of the maintenance plug."""
ON_THE_FEET = [LEDGE_SECRET, "metro_salvage_6", CRANE_SECRET, "metro_salvage_10"]
"""What the spring feet reach besides, east of the plug: they're bought before the datajack."""


def place(town: TownMap, thing: str) -> Cell:
    for item in town.interactables:
        if item.id == thing:
            return item.stand[0].x, item.stand[0].y
    [cell] = [(p.x, p.y) for p in town.pickups if p.id == thing]
    return cell


def plugs(town: TownMap) -> set[Cell]:
    return {place(town, i.id) for i in town.interactables if i.kind is InteractableKind.PLUG}


def needless(town: TownMap, cells: Sequence[Cell], plugs: Collection[Cell]) -> list[Cell]:
    """The plugs on the way that it's in the lamp's reach without."""
    return [
        plug
        for plug in plugs
        if plug in cells and max(runs(town, cells, set(plugs) - {plug})) <= REACH
    ]


def metro_way(jump: Jump, more: list[str]) -> list[Cell]:
    """From the stairway down past the bots to everything on the way to the plug, then on along
    the tracks to the shed and back, and up to the village."""
    ways = Ways(METRO_MAP, jump, BOT_FLOORS)
    arrival, plug = (ARRIVAL.x, ARRIVAL.y), place(METRO_MAP, PLUG)
    west = [place(METRO_MAP, thing) for thing in WEST]
    east = [place(METRO_MAP, thing) for thing in [*EAST, *more]]
    there = ways.tour(arrival, west, plug)
    along = ways.tour(plug, east, plug)
    return [*there, *along[1:], *ways.cells(plug, arrival)[1:]]


def dark(town: TownMap, cells: list[Cell]) -> float:
    return sum(
        seconds(town, a, b)
        for a, b in zip(cells, cells[1:], strict=False)
        if not (town.lit(*a) and town.lit(*b))
    )


@cache
def lift() -> tuple[float, float]:
    """Seconds of light from the maintenance plug to the lift down, and back."""
    plug, foot = place(METRO_MAP, PLUG), (LIFT_FOOT.x, LIFT_FOOT.y)
    return dark(METRO_MAP, OVER_THE_BOTS.cells(plug, foot)), dark(
        METRO_MAP, OVER_THE_BOTS.cells(foot, plug)
    )


@cache
def sewers(level: int) -> tuple[TownMap, list[Cell]]:
    """A level and the way through it: in from the lift on the player's own legs to everything
    before the gate and its junction box, on the legs past the gate to everything there and the
    den's stash, back to the box, and out to the lift."""
    town = load_maps(level=level)[SEWERS]
    on = way_on(town)
    out = Ways(town).cells(on[-1], (LANDING.x, LANDING.y))
    return town, [*way_in(town), *on[1:], *out[1:]]


def sewers_runs(level: int, without: str | None = None) -> list[float]:
    """Each run's seconds of light, from the metro's plug down the lift and back to it, and
    `without` a junction box and the light it gives, if one's named."""
    town, cells = sewers(level)
    if without is not None:
        town = replace(
            town,
            light=tuple(light for light in town.light if light.id != without),
            interactables=tuple(item for item in town.interactables if item.id != without),
        )
    found = runs(town, cells, plugs(town))
    going, coming = lift()
    return [found[0] + going, *found[1:-1], found[-1] + coming]


@pytest.mark.parametrize(
    ("jump", "more"), [(JUMP, []), (FEET[Bionic.SPRING_FEET], ON_THE_FEET)], ids=["own", "feet"]
)
def test_the_metro_has_one_plug_and_every_run_from_it_fits_in_a_charge(
    jump: Jump, more: list[str]
) -> None:
    cells = metro_way(jump, more)
    found = runs(METRO_MAP, cells, plugs(METRO_MAP))

    assert plugs(METRO_MAP) == {place(METRO_MAP, PLUG)}
    assert max(found) <= REACH, found
    assert max(found) > LIGHT / 2, "the long way east is a decision"
    assert needless(METRO_MAP, cells, plugs(METRO_MAP)) == []


@pytest.mark.parametrize("level", range(LEVELS))
def test_every_run_through_a_sewers_level_fits_in_a_charge(level: int) -> None:
    found = sewers_runs(level)

    assert max(found) <= REACH, found


@pytest.mark.parametrize("level", range(LEVELS))
def test_no_junction_box_past_the_gate_could_be_done_without(level: int) -> None:
    town, _ = sewers(level)
    plugs = [item.id for item in town.interactables if item.kind is InteractableKind.PLUG]
    boxes = [box for box in plugs if box != GATE_BOX]

    for box in boxes:
        assert max(sewers_runs(level, without=box)) > REACH, box


@pytest.mark.parametrize("level", range(LEVELS))
def test_the_gate_has_a_junction_box_and_any_more_are_past_it(level: int) -> None:
    town, _ = sewers(level)
    gate = next(light.area for light in town.light if light.id == "sewers_gate")
    first = place(town, GATE_BOX)

    assert first[0] < gate.x
    assert all(x >= gate.x + gate.width for x, _ in plugs(town) - {first})
    assert len(plugs(town)) <= 2
