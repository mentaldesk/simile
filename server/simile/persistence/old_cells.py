import csv
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from simile.schema import MapTile

TABLE = Path(__file__).with_name("old_cells.csv")


@dataclass(frozen=True)
class Moved:
    """Where a run of cells along a row of the iso maps is on the side-view maps, and what
    matched it."""

    map: str
    y: int
    first_x: int
    last_x: int
    to: MapTile
    by: str


def moved(map_id: str, x: int, y: int, table: Path = TABLE) -> MapTile | None:
    """Where a position saved on the iso maps goes, or None for a map or cell it doesn't have."""
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
