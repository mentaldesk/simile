from simile.schema import Door, DoorKind, MapTile, TileArea
from simile.world.map import Light, MapKind, TownMap

CLIMBABLE = {"H": DoorKind.LADDER, "/": DoorKind.STAIRS}

TWO_FLOORS = (
    "####################",
    "#..................#",
    "#.....H............#",
    "######H#####..######",
    "#.....H............#",
    "#.................D#",
    "####################",
)
"""A ladder at x 6, a hole at 12 and 13, and a door at (18, 5)."""
UPPER, LOWER = 2, 5


def side_view(
    *rows: str, map_id: str = "tunnel", dark: TileArea | None = None, lit: tuple[TileArea, ...] = ()
) -> TownMap:
    """From rows of `#` solid, `.` open, `H` ladder, `/` stairs and `D` a door's end."""
    width, height = len(rows[0]), len(rows)

    def solid(x: int, y: int) -> bool:
        return 0 <= y < height and rows[y][x] == "#"

    def walkable(x: int, y: int) -> bool:
        return rows[y][x] in CLIMBABLE or (rows[y][x] in ".D" and solid(x, y + 1))

    doors = tuple(
        Door(
            id=f"door_{x}",
            outside=MapTile(map="elsewhere", x=0, y=0),
            inside=MapTile(map=map_id, x=x, y=y),
        )
        for y, row in enumerate(rows)
        for x, cell in enumerate(row)
        if cell == "D"
    )
    light = tuple(Light(f"lit_{i}", area, True) for i, area in enumerate(lit))
    if dark is not None:
        light = (Light("dark", dark, False), *light)
    return TownMap(
        map_id,
        width,
        height,
        tuple(tuple(not walkable(x, y) for x in range(width)) for y in range(height)),
        (),
        doors=doors,
        kind=MapKind.STREET,
        climbable=tuple(tuple(CLIMBABLE.get(cell) for cell in row) for row in rows),
        solids=tuple(tuple(cell == "#" for cell in row) for row in rows),
        light=light,
    )
