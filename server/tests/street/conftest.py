from simile.schema import DoorKind
from simile.world.map import MapKind, TownMap

CLIMBABLE = {"H": DoorKind.LADDER, "/": DoorKind.STAIRS}


def side_view(*rows: str, map_id: str = "street") -> TownMap:
    """A side-view street from rows of `#` solid, `.` open, `H` ladder and `/` stairs. Open cells
    are walkable on solid ground, and climbable cells always."""
    width, height = len(rows[0]), len(rows)

    def solid(x: int, y: int) -> bool:
        return 0 <= y < height and rows[y][x] == "#"

    def walkable(x: int, y: int) -> bool:
        return rows[y][x] in CLIMBABLE or (rows[y][x] == "." and solid(x, y + 1))

    blocked = tuple(tuple(not walkable(x, y) for x in range(width)) for y in range(height))
    climbable = tuple(tuple(CLIMBABLE.get(cell) for cell in row) for row in rows)
    return TownMap(
        map_id,
        width,
        height,
        blocked,
        (),
        side_view=True,
        kind=MapKind.STREET,
        climbable=climbable,
    )
