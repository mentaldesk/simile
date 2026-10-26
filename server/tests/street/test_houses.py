import heapq
from collections import Counter
from functools import cache

from simile.clinic.config import DEFAULT_CONFIG as CLINIC_CONFIG
from simile.economy.config import SALVAGE as PRICES
from simile.player.config import DEFAULT_CONFIG as PLAYER
from simile.player.config import SALVAGE
from simile.schema import Bionic, DoorKind, InteractableKind, ItemKind
from simile.street.finds import STASHES
from simile.street.jump import JUMP
from simile.street.moves import moves
from simile.street.sewers import SEWERS
from simile.world.map import PickupKind, load_maps
from simile.world.paths import Spot, door_ends

MAPS = load_maps()
ON_FOOT = {map_id: town for map_id, town in MAPS.items() if map_id != SEWERS}
HOUSES = [f"house_{n}" for n in range(1, 11)]
RECIPES = [CLINIC_CONFIG.recipes[bionic] for bionic in (Bionic.POWER_CELL, Bionic.DATAJACK)]
START = Spot("maker_space_floor_0", 13, 2)
WALK = 2.6
CLIMB = {DoorKind.LADDER: 1.0, DoorKind.STAIRS: 1.3}
"""The player's own pace, in tiles a sim second, as the client moves them."""
DOOR = 2.0
"""Sim seconds through a door."""


@cache
def walk() -> dict[Spot, float]:
    """Sim seconds the player takes on their own legs, jumping, from the maker space to each cell
    of the village and the metro they get to, walking and climbing at their slowest."""
    doors = door_ends(ON_FOOT)
    found: dict[Spot, float] = {}
    frontier = [(0.0, START)]
    while frontier:
        spent, here = heapq.heappop(frontier)
        if here in found:
            continue
        found[here] = spent
        town = ON_FOOT[here.map]
        for step in moves(town, (here.x, here.y), JUMP):
            kind = town.climb(*step.cell) or town.climb(here.x, here.y)
            pace = CLIMB.get(kind, WALK) if kind else WALK
            heapq.heappush(frontier, (spent + step.cost / pace, Spot(here.map, *step.cell)))
        if here in doors:
            heapq.heappush(frontier, (spent + DOOR, doors[here]))
    return found


def reachable() -> set[Spot]:
    return set(walk())


def in_reach(things: list[Spot]) -> bool:
    return any(spot in reachable() for spot in things)


def test_each_house_has_a_place_or_two_to_search_holding_cash() -> None:
    parts = {part for recipe in RECIPES for part in recipe.parts}
    for house in HOUSES:
        floors = [town for town in MAPS.values() if town.building == house]
        things = [thing for town in floors for thing in town.interactables]
        stashes = [STASHES[thing.id] for thing in things]

        assert 1 <= len(things) <= 2, house
        assert all(thing.kind is InteractableKind.SEARCHABLE for thing in things), house
        assert [list(s.items) for s in stashes] == [thing.items for thing in things], house
        assert [s.money for s in stashes] == [thing.money for thing in things], house
        assert all(stash.house == house for stash in stashes), house
        assert sum(stash.money for stash in stashes) > 0, house
        assert all(item.kind is ItemKind.FOOD for s in stashes for item in s.items), house
        assert not {item.id for s in stashes for item in s.items} & parts, house


def test_a_days_exploring_on_foot_pays_for_the_cell_and_the_datajack_without_the_kidney() -> None:
    """Pacing (P27, P28): searching everything, taking every secret and one round of salvage on
    their own legs, the player finds the parts for both and, selling the salvage the recipes don't
    use, affords both without the kidney or a respawn, in a day. Fetching each from home and
    back on its own takes less than half the time from a meal to collapsing."""
    seconds = walk()
    found = [
        thing
        for town in ON_FOOT.values()
        for thing in town.interactables
        if thing.kind is InteractableKind.SEARCHABLE
        and in_reach([Spot(town.id, tile.x, tile.y) for tile in thing.stand])
    ]
    pickups = [
        pickup
        for town in ON_FOOT.values()
        for pickup in town.pickups
        if Spot(town.id, pickup.x, pickup.y) in seconds
    ]
    cash = sum(thing.money for thing in found)
    secrets = sum(pickup.money for pickup in pickups if pickup.kind is PickupKind.SECRET)
    lying = [p.item or SALVAGE[p.id].item for p in pickups if p.kind is PickupKind.SALVAGE]
    salvage = sum(PRICES[item.id] for item in lying)
    parts = Counter(item.id for thing in found for item in thing.items)
    needed = sum((Counter(recipe.parts) for recipe in RECIPES), Counter())
    stripped = sum(PRICES[item] * n for item, n in (parts - needed).items() if item in PRICES)
    cost = sum(recipe.credits for recipe in RECIPES)
    fetched = [
        min(seconds[Spot(t.map, s.x, s.y)] for s in t.stand if Spot(t.map, s.x, s.y) in seconds)
        for t in found
    ]
    fetched += [seconds[Spot(p.map, p.x, p.y)] for p in pickups]

    assert sum(stash.money for stash in STASHES.values()) == cash == 62
    assert (secrets, salvage, stripped, cost) == (95, 44, 42, 200)
    assert all(parts[part] > n for part, n in needed.items()), "a spare of every part"
    assert cash + secrets + salvage + stripped >= 1.2 * cost
    assert 2 * sum(fetched) < 0.5 * 3600 / PLAYER.rise, "in half the time a meal lasts"
