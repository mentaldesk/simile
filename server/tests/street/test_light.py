"""Light is scarce: on the metro and every committed level of the sewers, each run between plugs on
the way the player's meant to go fits in a full charge with a little to spare, and none of the
plugs could be done without (content/street/README.md's *Light*)."""

from functools import cache

import pytest

from simile.schema import InteractableKind
from simile.street.charge import LIGHT, REACH, SPARE, Ways, needless, runs, seconds
from simile.street.metro import (
    ARRIVAL,
    BOTS,
    CONTAINER,
    FREIGHT_CRATES,
    FRIDGE,
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
OVER_THE_BOTS = Ways(
    METRO_MAP, avoid={(x, GROUND) for _, west, east in BOTS for x in range(west - 1, east + 2)}
)
"""The metro on the player's own legs, never on the bots' floor: P34's way is overhead."""
WEST = [TICKET_MACHINE, "metro_salvage_1", "metro_salvage_2", "metro_salvage_3", FRIDGE]
EAST = [
    "metro_salvage_5",
    FREIGHT_CRATES,
    CONTAINER,
    "metro_salvage_7",
    SWITCHBOARD,
    RELAY_RACK,
    SIGNAL_DESK,
    "metro_salvage_8",
    TOOL_CRATE,
    "metro_salvage_9",
    LOCKERS,
]
"""What the player's own legs reach on the metro, either side of the maintenance plug."""


def place(town: TownMap, thing: str) -> Cell:
    for item in town.interactables:
        if item.id == thing:
            return item.stand[0].x, item.stand[0].y
    [cell] = [(p.x, p.y) for p in town.pickups if p.id == thing]
    return cell


def plugs(town: TownMap) -> set[Cell]:
    return {place(town, i.id) for i in town.interactables if i.kind is InteractableKind.PLUG}


def metro_way() -> list[Cell]:
    """From the stairway down past the bots to everything on the way to the plug, then on along
    the tracks to the shed and back, and up to the village."""
    arrival, plug = (ARRIVAL.x, ARRIVAL.y), place(METRO_MAP, PLUG)
    west = [place(METRO_MAP, thing) for thing in WEST]
    east = [place(METRO_MAP, thing) for thing in EAST]
    there = OVER_THE_BOTS.tour(arrival, west, plug)
    along = OVER_THE_BOTS.tour(plug, east, plug)
    return [*there, *along[1:], *OVER_THE_BOTS.cells(plug, arrival)[1:]]


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


def sewers_runs(level: int, without: Cell | None = None) -> list[float]:
    """Each run's seconds of light, from the metro's plug down the lift and back to it."""
    town, cells = sewers(level)
    found = runs(town, cells, plugs(town) - {without})
    going, coming = lift()
    return [found[0] + going, *found[1:-1], found[-1] + coming]


def test_a_full_charge_lasts_under_two_minutes_and_a_run_leaves_some_of_it() -> None:
    assert LIGHT == 112.5
    assert REACH == LIGHT * (1 - SPARE) and SPARE == 0.15


def test_the_metro_has_one_plug_and_every_run_from_it_fits_in_a_charge() -> None:
    cells = metro_way()
    found = runs(METRO_MAP, cells, plugs(METRO_MAP))

    assert plugs(METRO_MAP) == {place(METRO_MAP, PLUG)}
    assert max(found) <= REACH, found
    assert max(found) > LIGHT / 2, "the long way east is a decision"
    assert needless(METRO_MAP, cells, plugs(METRO_MAP)) == []


@pytest.mark.parametrize("level", range(LEVELS))
def test_every_run_through_a_sewers_level_fits_in_a_charge(level: int) -> None:
    found = sewers_runs(level)

    assert max(found) <= REACH, found
    assert max(found) > LIGHT / 2, found


@pytest.mark.parametrize("level", range(LEVELS))
def test_no_junction_box_could_be_done_without(level: int) -> None:
    town, _ = sewers(level)

    for box in plugs(town):
        assert max(sewers_runs(level, without=box)) > REACH, box


@pytest.mark.parametrize("level", range(LEVELS))
def test_the_gate_has_a_junction_box_and_any_more_are_past_it(level: int) -> None:
    town, _ = sewers(level)
    gate = next(light.area for light in town.light if light.id == "sewers_gate")
    first = place(town, GATE_BOX)

    assert first[0] < gate.x
    assert all(x >= gate.x + gate.width for x, _ in plugs(town) - {first})
    assert len(plugs(town)) <= 2
