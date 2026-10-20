import csv
import math
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, replace
from functools import cache
from pathlib import Path

from simile.schema import Location, MapTile, Tile
from simile.world.map import TownMap

TABLE = Path(__file__).with_name("old_cells.csv")
COLUMNS = ("map", "y", "first_x", "last_x", "new_map", "new_x", "new_y", "by")


@dataclass(frozen=True)
class Moved:
    """Where a run of cells along a row of today's maps is on the side-view maps, and what
    matched it."""

    map: str
    y: int
    first_x: int
    last_x: int
    to: MapTile
    by: str


def moved(map_id: str, x: int, y: int, table: Path = TABLE) -> MapTile | None:
    """Where a position saved on today's maps goes, or None for a map or cell it doesn't have."""
    for row in _read(table).get((map_id, y), ()):
        if row.first_x <= x <= row.last_x:
            return row.to
    return None


@cache
def _read(table: Path) -> dict[tuple[str, int], list[Moved]]:
    rows: dict[tuple[str, int], list[Moved]] = {}
    with table.open(newline="") as file:
        for row in csv.DictReader(file):
            to = MapTile(map=row["new_map"], x=int(row["new_x"]), y=int(row["new_y"]))
            y, first, last = int(row["y"]), int(row["first_x"]), int(row["last_x"])
            rows.setdefault((row["map"], y), []).append(
                Moved(row["map"], y, first, last, to, row["by"])
            )
    return rows


def write(rows: list[Moved], table: Path = TABLE) -> None:
    with table.open("w", newline="") as file:
        out = csv.writer(file, lineterminator="\n")
        out.writerow(COLUMNS)
        for row in rows:
            to = row.to
            out.writerow((row.map, row.y, row.first_x, row.last_x, to.map, to.x, to.y, row.by))
    _read.cache_clear()


def build(old: Mapping[str, TownMap], new: Mapping[str, TownMap]) -> list[Moved]:
    """Each walkable cell of today's maps, in runs along its row, and where it is on the
    side-view maps. A spot, a door's end or an interactable's stand goes to the one with the
    same id. Any other cell goes to the entry of the location it's in, or else outdoors to the
    nearest door's end or place on a street, or the street in front of a house's door. Raises
    KeyError if an id is missing from the new maps."""
    found = _Found(new)
    rows: list[Moved] = []
    for town in old.values():
        anchors = list(_anchors(town, found))
        for y in range(town.height):
            run: Moved | None = None
            for x in range(town.width):
                if not town.walkable(x, y):
                    continue
                to, by = _match(town, x, y, found) or _nearest(x, y, anchors)
                if run is not None and (run.to, run.by) == (to, by):
                    run = replace(run, last_x=x)
                    continue
                if run is not None:
                    rows.append(run)
                run = Moved(town.id, y, x, x, to, by)
            if run is not None:
                rows.append(run)
    return rows


class _Found:
    def __init__(self, maps: Mapping[str, TownMap]) -> None:
        self.maps = maps
        self.locations = {loc.id: loc for town in maps.values() for loc in town.locations}
        self.doors = {door.id: door for town in maps.values() for door in town.doors}
        self.things = {thing.id: thing for town in maps.values() for thing in town.interactables}

    def spot(self, spot_id: str, place: str | None) -> MapTile:
        """On the streets for today's village, or on the place's floors for an interior."""
        location = self.locations.get(place) if place else None
        maps = (
            [location.map, *(floor.map for floor in location.floors)]
            if location
            else [town.id for town in self.maps.values() if town.street]
        )
        for map_id in maps:
            if spot := next((s for s in self.maps[map_id].spots if s.id == spot_id), None):
                return MapTile(map=map_id, x=spot.x, y=spot.y)
        raise KeyError(spot_id)

    def entry(self, location_id: str) -> MapTile:
        location = self.locations[location_id]
        return MapTile(map=location.map, x=location.entry.x, y=location.entry.y)


def _match(town: TownMap, x: int, y: int, found: _Found) -> tuple[MapTile, str] | None:
    if spot := town.spot_at(x, y):
        building = None if town.street else town.id
        return found.spot(spot.id, building), f"spot {spot.id}"
    for door in town.doors:
        for side in ("outside", "inside"):
            end = getattr(door, side)
            if (end.map, end.x, end.y) == (town.id, x, y):
                return getattr(found.doors[door.id], side), f"door {door.id}"
    for thing in town.interactables:
        if Tile(x=x, y=y) in thing.stand:
            stand = found.things[thing.id].stand
            at = stand[min(thing.stand.index(Tile(x=x, y=y)), len(stand) - 1)]
            to = MapTile(map=found.things[thing.id].map, x=at.x, y=at.y)
            return to, f"interactable {thing.id}"
    if location := _smallest(town.locations, x, y):
        return found.entry(location.id), f"location {location.id}"
    return None


def _smallest(locations: tuple[Location, ...], x: int, y: int) -> Location | None:
    inside = [
        loc
        for loc in locations
        if loc.area.x <= x < loc.area.x + loc.area.width
        and loc.area.y <= y < loc.area.y + loc.area.height
    ]
    return min(inside, key=lambda loc: loc.area.width * loc.area.height, default=None)


def _anchors(town: TownMap, found: _Found) -> Iterator[tuple[Tile, MapTile, str]]:
    """Today's doors and places on the map, each with its new place on a street, or the street in
    front of its front door, such as a house's. Inside, a building's places."""
    for door in town.doors:
        end = door.outside if door.outside.map == town.id else door.inside
        new = found.doors[door.id]
        to = new.outside if door.outside.map == town.id else new.inside
        yield Tile(x=end.x, y=end.y), to, f"near door {door.id}"
    for location in town.locations:
        to = found.entry(location.id)
        if town.street and not found.maps[to.map].street and location.id in found.doors:
            to = found.doors[location.id].outside
        if found.maps[to.map].street or not town.street:
            yield location.entry, to, f"near location {location.id}"


def _nearest(x: int, y: int, anchors: list[tuple[Tile, MapTile, str]]) -> tuple[MapTile, str]:
    _, to, by = min(anchors, key=lambda anchor: math.dist((x, y), (anchor[0].x, anchor[0].y)))
    return to, by
