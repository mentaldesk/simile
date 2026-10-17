import json
from collections import deque
from pathlib import Path

import pytest

from simile.schema import VILLAGE_MAP, Door, InteractableKind, LocationKind, MapTile, Tile
from simile.world.map import TownMap, load_map, load_maps

MAPS = load_maps()
INTERIORS = ["coffee_shop", "gallery", "maker_space", "noodle_bar"]


def reachable(town: TownMap, start: Tile) -> set[tuple[int, int]]:
    found, queue = {(start.x, start.y)}, deque([(start.x, start.y)])
    while queue:
        x, y = queue.popleft()
        for step in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if town.walkable(*step) and step not in found:
                found.add(step)
                queue.append(step)
    return found


def walkable(town: TownMap) -> set[tuple[int, int]]:
    return {(x, y) for y in range(town.height) for x in range(town.width) if town.walkable(x, y)}


def test_load_maps_has_the_village_and_every_interior_by_id() -> None:
    assert list(MAPS) == [VILLAGE_MAP, *INTERIORS]
    assert MAPS[VILLAGE_MAP] == load_map()
    for map_id, town in MAPS.items():
        assert town.id == map_id


def test_interiors_are_bigger_on_the_inside() -> None:
    for map_id in ("coffee_shop", "maker_space", "noodle_bar"):
        assert (MAPS[map_id].width, MAPS[map_id].height) == (20, 14), map_id
    gallery = MAPS["gallery"]
    assert gallery.width > 20 and gallery.height > 14


@pytest.mark.parametrize("map_id", INTERIORS)
def test_every_interior_is_fully_connected(map_id: str) -> None:
    town = MAPS[map_id]
    entry = town.location(map_id).entry

    assert reachable(town, entry) == walkable(town)


def test_every_door_links_walkable_tiles_in_both_directions() -> None:
    ends: dict[str, list[tuple[str, Door]]] = {}
    for town in MAPS.values():
        for door in town.doors:
            ends.setdefault(door.id, []).append((town.id, door))

    assert set(ends) == set(INTERIORS)
    for door_id, found in ends.items():
        [(first, door), (second, same)] = found
        assert door == same, door_id
        assert {first, second} == {door.outside.map, door.inside.map}, door_id
        for end in (door.outside, door.inside):
            assert MAPS[end.map].walkable(end.x, end.y), (door_id, end)


def test_each_door_runs_from_a_doorstep_to_the_mat_in_its_interiors_front_wall() -> None:
    village = MAPS[VILLAGE_MAP]
    for door in village.doors:
        outside, inside = door.outside, door.inside
        assert outside.map == VILLAGE_MAP and inside.map == door.id
        assert not village.walkable(outside.x, outside.y - 1), door.id
        room = MAPS[inside.map]
        assert inside.y == room.height - 1, door.id
        assert not room.walkable(inside.x - 1, inside.y), door.id
        assert not room.walkable(inside.x + 1, inside.y), door.id
        assert room.walkable(inside.x, inside.y - 1), door.id


def test_every_location_entry_is_walkable_on_its_own_map() -> None:
    for town in MAPS.values():
        for location in town.locations:
            entry, area = location.entry, location.area
            assert location.map == town.id, location.id
            assert town.walkable(entry.x, entry.y), location.id
            assert area.x <= entry.x < area.x + area.width, location.id
            assert area.y <= entry.y < area.y + area.height, location.id


def test_each_building_with_a_door_has_its_location_inside_and_ids_are_unique() -> None:
    ids = [location.id for town in MAPS.values() for location in town.locations]

    assert len(ids) == len(set(ids))
    for location_id in INTERIORS:
        assert MAPS[location_id].location(location_id).map == location_id
    terrace = MAPS[VILLAGE_MAP].location("cafe_terrace")
    assert terrace.kind is LocationKind.AMENITY


@pytest.mark.parametrize("map_id", INTERIORS)
def test_each_interiors_own_location_covers_its_floor(map_id: str) -> None:
    town = MAPS[map_id]
    area = town.location(map_id).area

    assert (area.x, area.y, area.width, area.height) == (1, 2, town.width - 2, town.height - 3)
    inside = {(area.x + dx, area.y + dy) for dx in range(area.width) for dy in range(area.height)}
    [mat] = walkable(town) - inside
    assert mat[1] == town.height - 1
    assert all((door.inside.x, door.inside.y) == mat for door in town.doors)


def test_every_interactables_stand_tiles_are_walkable() -> None:
    for town in MAPS.values():
        for item in town.interactables:
            area = item.area
            covered = {
                (area.x + dx, area.y + dy) for dx in range(area.width) for dy in range(area.height)
            }
            assert item.map == town.id, item.id
            for tile in item.stand:
                assert town.walkable(tile.x, tile.y), (item.id, tile)
                assert (tile.x, tile.y) not in covered, (item.id, tile)


def test_interactable_ids_are_unique_across_maps() -> None:
    ids = [item.id for town in MAPS.values() for item in town.interactables]

    assert len(ids) == len(set(ids))


def test_the_daily_grind_has_a_counter_a_queue_and_a_spot_for_the_barista() -> None:
    cafe = MAPS["coffee_shop"]
    [counter] = cafe.interactables
    queue = cafe.location("coffee_shop_queue")
    staff = cafe.location("coffee_shop_staff")
    front = queue.entry

    assert counter.kind is InteractableKind.COUNTER
    assert counter.stand == [front] == [cafe.location("coffee_shop").entry]
    assert front.y == counter.area.y + 1
    assert (queue.area.x, queue.area.width) == (front.x, 1) and queue.area.y == front.y
    assert all(cafe.walkable(front.x, y) for y in range(front.y, front.y + queue.area.height))
    assert (staff.entry.x, staff.entry.y) == (front.x, counter.area.y - 1)
    assert staff.area.y + staff.area.height == counter.area.y
    for location in (queue, staff):
        assert location.kind is LocationKind.AMENITY


def test_the_gallery_hangs_paintings_on_its_walls() -> None:
    gallery = MAPS["gallery"]
    paintings = gallery.interactables

    assert 10 <= len(paintings) <= 16
    for painting in paintings:
        assert painting.kind is InteractableKind.PAINTING
        area = painting.area
        assert not any(gallery.walkable(area.x + dx, area.y) for dx in range(area.width))
    assert gallery.location("gallery").kind is LocationKind.GALLERY


def test_the_maker_space_has_its_machines() -> None:
    machines = MAPS["maker_space"].interactables

    assert {item.label for item in machines} == {
        "3D printer",
        "Laser cutter",
        "Loom",
        "Sewing machine",
    }
    assert {item.kind for item in machines} == {InteractableKind.MACHINE}


def test_the_noodle_bar_has_nothing_to_use_yet() -> None:
    assert MAPS["noodle_bar"].interactables == ()


def test_load_map_reads_doors_and_interactables(tmp_path: Path) -> None:
    def obj(name: str, kind: str, x: int, y: int, width: int, **props: object) -> dict:
        properties = [
            {"name": k, "type": "int" if isinstance(v, int) else "string", "value": v}
            for k, v in props.items()
        ]
        return {
            "name": name,
            "type": kind,
            "x": x * 16,
            "y": y * 16,
            "width": width * 16,
            "height": 16,
            "properties": properties,
        }

    door = obj("shop", "door", 1, 2, 1, side="inside", to_map="village", to_x=7, to_y=8)
    loom = obj("loom", "machine", 0, 0, 2, label="Loom", stand="0,1 1,1")
    layers = [
        {"name": "collision", "type": "tilelayer", "data": [0] * 12},
        {"name": "locations", "type": "objectgroup", "objects": []},
        {"name": "doors", "type": "objectgroup", "objects": [door]},
        {"name": "interactables", "type": "objectgroup", "objects": [loom]},
    ]
    path = tmp_path / "shop.tmj"
    path.write_text(json.dumps({"width": 4, "height": 3, "tilewidth": 16, "layers": layers}))

    shop = load_map(path)

    assert shop.doors == (
        Door(
            id="shop",
            outside=MapTile(map="village", x=7, y=8),
            inside=MapTile(map="shop", x=1, y=2),
        ),
    )
    [item] = shop.interactables
    assert (item.id, item.label, item.kind, item.map) == (
        "loom",
        "Loom",
        InteractableKind.MACHINE,
        "shop",
    )
    assert item.area.model_dump() == {"x": 0, "y": 0, "width": 2, "height": 1}
    assert item.stand == [Tile(x=0, y=1), Tile(x=1, y=1)]
