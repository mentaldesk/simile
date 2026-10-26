from collections import Counter, deque
from functools import cache

from simile.clinic.config import DEFAULT_CONFIG as CLINIC_CONFIG
from simile.economy.config import SALVAGE as PRICES
from simile.player.config import SALVAGE
from simile.schema import Bionic, InteractableKind, ItemKind
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


@cache
def reachable() -> frozenset[Spot]:
    """Every cell of the village and the metro the player gets to from the maker space on their
    own legs, jumping."""
    doors = door_ends(ON_FOOT)
    start = Spot("maker_space_floor_0", 13, 2)
    seen, queue = {start}, deque([start])
    while queue:
        here = queue.popleft()
        nexts = [Spot(here.map, *c) for c, _ in moves(ON_FOOT[here.map], (here.x, here.y), JUMP)]
        if here in doors:
            nexts.append(doors[here])
        for there in nexts:
            if there not in seen:
                seen.add(there)
                queue.append(there)
    return frozenset(seen)


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
        assert all(stash.house == house for stash in stashes), house
        assert sum(stash.money for stash in stashes) > 0, house
        assert all(item.kind is ItemKind.FOOD for s in stashes for item in s.items), house
        assert not {item.id for s in stashes for item in s.items} & parts, house


def test_the_cell_and_the_datajack_are_paid_for_and_found_on_foot_without_respawns() -> None:
    """Pacing: what an exploring player finds once on foot in the village and today's metro,
    with the kidney, covers both. Without it, P28's metro makes up the rest."""
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
        if Spot(town.id, pickup.x, pickup.y) in reachable()
    ]
    houses = sum(STASHES[thing.id].money for thing in found if thing.id in STASHES)
    secrets = sum(pickup.money for pickup in pickups if pickup.kind is PickupKind.SECRET)
    salvage = sum(PRICES[SALVAGE[p.id].item.id] for p in pickups if p.kind is PickupKind.SALVAGE)
    parts = Counter(item.id for thing in found for item in thing.items)
    needed = sum((Counter(recipe.parts) for recipe in RECIPES), Counter())
    cost = sum(recipe.credits for recipe in RECIPES)

    assert sum(stash.money for stash in STASHES.values()) == houses == 62
    assert (secrets, salvage, cost) == (65, 25, 200)
    assert parts >= needed
    assert CLINIC_CONFIG.kidney + houses + secrets >= cost
    assert houses + secrets + salvage >= 0.75 * cost
