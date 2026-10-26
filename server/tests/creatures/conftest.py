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
"""Two floors joined by a ladder at x 6 and a hole at x 12 and 13, with a door at the east end
of the lower floor, (18, 5)."""
UPPER, LOWER = 2, 5


def side_view(
    *rows: str, map_id: str = "tunnel", dark: TileArea | None = None, lit: tuple[TileArea, ...] = ()
) -> TownMap:
    """A side-view map from rows of `#` solid, `.` open, `H` ladder, `/` stairs and `D` the end
    of a door to another map. Open cells and doors are walkable on solid ground, climbable cells
    always. `dark` is a dark stretch, and `lit` lit ones over it."""
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
