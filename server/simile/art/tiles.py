import random
from collections.abc import Callable
from dataclasses import dataclass

from simile.art.canvas import Canvas, draw_text, text_width
from simile.art.palette import shade

TILE_SIZE = 16
COLUMNS = 16
SIDES = ("n", "e", "s", "w")
CORNERS = ("ne", "nw", "se", "sw")


@dataclass(frozen=True)
class Tile:
    name: str
    canvas: Canvas
    collides: bool = False
    above: bool = False


@dataclass(frozen=True)
class Group:
    name: str
    tiles: list[Tile]


def _rng(name: str) -> random.Random:
    return random.Random(f"tile:{name}")


def _split(canvas: Canvas, names: list[list[str]], **flags: bool) -> list[Tile]:
    tiles = []
    for row, row_names in enumerate(names):
        for col, name in enumerate(row_names):
            piece = Canvas()
            for y in range(TILE_SIZE):
                for x in range(TILE_SIZE):
                    piece.px(x, y, canvas.get(col * TILE_SIZE + x, row * TILE_SIZE + y))
            tiles.append(Tile(name, piece, **flags))
    return tiles


# Ground


def grass(name: str = "grass", tufts: int = 5, flowers: tuple[str, ...] = ()) -> Canvas:
    c = Canvas(fill="green")
    r = _rng(name)
    for _ in range(14):
        c.px(r.randrange(16), r.randrange(16), "forest")
    for _ in range(tufts):
        x, y = r.randrange(1, 15), r.randrange(1, 14)
        c.stamp(["l.l", ".f."], {"l": "lime", "f": "forest"}, x - 1, y)
    for colour in flowers:
        x, y = r.randrange(2, 14), r.randrange(2, 14)
        c.stamp([".c.", "cyc", ".c."], {"c": colour, "y": "yellow"}, x - 1, y - 1)
    return c


def pavement() -> Canvas:
    c = Canvas(fill="pavement")
    c.hline(0, 7, 16, "concrete")
    c.hline(0, 15, 16, "concrete")
    c.vline(15, 0, 7, "concrete")
    c.vline(7, 8, 7, "concrete")
    c.px(3, 2, "white")
    c.px(11, 11, "white")
    return c


def tactile(vertical: bool) -> Canvas:
    c = pavement()
    c.rect(0, 5, 16, 6, "amber")
    for y in (6, 8):
        for x in range(1, 16, 4):
            c.hline(x, y, 3, "yellow")
            c.hline(x, y + 1, 3, "orange")
    c.hline(0, 10, 16, "orange")
    return _transpose(c) if vertical else c


def _transpose(c: Canvas) -> Canvas:
    out = Canvas()
    for y in range(16):
        for x in range(16):
            out.px(x, y, c.get(y, x))
    return out


def plaza(inlay: bool = False) -> Canvas:
    c = Canvas(fill="cream")
    for i in (7, 15):
        c.hline(0, i, 16, "sand")
        c.vline(i, 0, 16, "sand")
    for x, y in ((3, 3), (11, 11), (11, 3), (3, 11)):
        c.px(x, y, "white")
    if inlay:
        c.stamp(
            [
                ".......t.......",
                "......tpt......",
                ".....tp.pt.....",
                "....tp...pt....",
                "...tp.....pt...",
                "..tp.......pt..",
                ".tp.........pt.",
                "tp.....n.....pt",
                ".tp.........pt.",
                "..tp.......pt..",
                "...tp.....pt...",
                "....tp...pt....",
                ".....tp.pt.....",
                "......tpt......",
                ".......t.......",
            ],
            {"t": "tan", "p": "peach", "n": "neon"},
            0,
            0,
        )
    return c


def road(name: str = "road") -> Canvas:
    c = Canvas(fill="slate")
    r = _rng(name)
    for _ in range(10):
        c.px(r.randrange(16), r.randrange(16), "night")
    for _ in range(5):
        c.px(r.randrange(16), r.randrange(16), "steel")
    return c


def road_line(vertical: bool) -> Canvas:
    c = road()
    c.rect(4, 7, 8, 2, "pavement")
    return _transpose(c) if vertical else c


def crosswalk(vertical: bool) -> Canvas:
    c = road()
    for y in (1, 5, 9, 13):
        c.rect(1, y, 14, 2, "pavement")
    return _transpose(c) if vertical else c


def water(name: str = "water") -> Canvas:
    c = Canvas(fill="blue")
    r = _rng(name)
    for _ in range(8):
        c.px(r.randrange(16), r.randrange(16), "navy")
    for _ in range(4):
        x, y = r.randrange(0, 13), r.randrange(1, 15)
        c.hline(x, y, 3, "cyan")
        c.px(x + 1, y, "ice")
    return c


# Terrain edges: a terrain patch set into pavement. The suffix names the sides that border
# pavement; "_nook" tiles have pavement only on that diagonal.

EdgeDrawer = Callable[[Canvas, str], None]


def _grass_edge(c: Canvas, side: str) -> None:
    if side == "n":
        c.hline(0, 0, 16, "concrete")
        c.hline(0, 1, 16, "pavement")
        c.hline(0, 2, 16, "forest")
    elif side == "s":
        c.hline(0, 15, 16, "concrete")
        c.hline(0, 14, 16, "pavement")
    elif side == "w":
        c.vline(0, 0, 16, "concrete")
        c.vline(1, 0, 16, "pavement")
    else:
        c.vline(15, 0, 16, "concrete")
        c.vline(14, 0, 16, "pavement")


def _road_edge(c: Canvas, side: str) -> None:
    if side == "n":
        c.hline(0, 0, 16, "concrete")
        c.hline(0, 1, 16, "steel")
        c.hline(0, 2, 16, "night")
    elif side == "s":
        c.hline(0, 15, 16, "concrete")
        c.hline(0, 14, 16, "steel")
    elif side == "w":
        c.vline(0, 0, 16, "concrete")
        c.vline(1, 0, 16, "steel")
    else:
        c.vline(15, 0, 16, "concrete")
        c.vline(14, 0, 16, "steel")


def _water_edge(c: Canvas, side: str) -> None:
    if side == "n":
        c.hline(0, 0, 16, "concrete")
        c.hline(0, 1, 16, "steel")
        c.hline(0, 2, 16, "slate")
        c.hline(0, 3, 16, "navy")
    elif side == "s":
        c.hline(0, 15, 16, "concrete")
        c.hline(0, 14, 16, "pavement")
        c.hline(0, 13, 16, "ice")
    elif side == "w":
        c.vline(0, 0, 16, "concrete")
        c.vline(1, 0, 16, "steel")
        c.vline(2, 0, 16, "navy")
    else:
        c.vline(15, 0, 16, "concrete")
        c.vline(14, 0, 16, "steel")
        c.vline(13, 0, 16, "navy")


def _copy(c: Canvas) -> Canvas:
    out = Canvas(c.width, c.height)
    out.paste(c)
    return out


def edge_set(terrain: str, base: Callable[[], Canvas], edge: EdgeDrawer, **flags: bool) -> list[Tile]:
    def with_edges(*sides: str) -> Canvas:
        c = base()
        for side in sides:
            edge(c, side)
        return c

    def changed(c: Canvas) -> set[tuple[int, int]]:
        plain = base()
        return {(x, y) for y in range(16) for x in range(16) if c.get(x, y) != plain.get(x, y)}

    tiles = [Tile(f"{terrain}_{side}", with_edges(side), **flags) for side in SIDES]
    for corner in CORNERS:
        tiles.append(Tile(f"{terrain}_{corner}", with_edges(*corner), **flags))
    for corner in CORNERS:
        outer = with_edges(*corner)
        overlap = changed(with_edges(corner[0])) & changed(with_edges(corner[1]))
        nook = base()
        for x, y in overlap:
            nook.px(x, y, outer.get(x, y))
        tiles.append(Tile(f"{terrain}_{corner}_nook", nook, **flags))
    return tiles


def edge_variant(terrain: str, same: Callable[[int, int], bool]) -> str:
    """Name the tile for a terrain cell, given same(dx, dy) for its neighbours (dy < 0 is north)."""
    sides = {"n": not same(0, -1), "s": not same(0, 1), "e": not same(1, 0), "w": not same(-1, 0)}
    ns = "n" if sides["n"] else "s" if sides["s"] else ""
    ew = "e" if sides["e"] else "w" if sides["w"] else ""
    if ns or ew:
        return f"{terrain}_{ns}{ew}"
    for corner, (dx, dy) in {"ne": (1, -1), "nw": (-1, -1), "se": (1, 1), "sw": (-1, 1)}.items():
        if not same(dx, dy):
            return f"{terrain}_{corner}_nook"
    return terrain


# Roofs


def roof_interior(kind: str, name: str) -> Canvas:
    r = _rng(name)
    if kind == "green":
        return grass(name, tufts=4)
    c = Canvas(fill="steel")
    for y in range(1, 16, 4):
        for x in range((y // 4 % 2) * 2, 16, 4):
            c.px(x, y, "concrete")
    for _ in range(4):
        c.px(r.randrange(16), r.randrange(16), "slate")
    return c


def roof_piece(kind: str, name: str, sides: str) -> Canvas:
    c = roof_interior(kind, name)
    face_top = 12
    if "n" in sides:
        c.hline(0, 0, 16, "slate")
        c.hline(0, 1, 16, "pavement")
        c.hline(0, 2, 16, "concrete")
        c.hline(0, 3, 16, shade(c.get(8, 8) or "steel"))
    if "s" in sides:
        c.hline(0, face_top - 1, 16, "concrete")
        c.hline(0, face_top, 16, "pavement")
        c.rect(0, face_top + 1, 16, 2, "concrete")
        c.hline(0, 15, 16, "steel")
    rim_rows = range(face_top + 1) if "s" in sides else range(16)
    if "w" in sides:
        for y in rim_rows:
            c.px(1, y, "pavement")
            if y > 1 and c.get(2, y) not in ("concrete", "pavement"):
                c.px(2, y, shade(c.get(2, y) or "steel"))
        c.vline(0, 0, 16, "slate")
    if "e" in sides:
        for y in rim_rows:
            c.px(14, y, "concrete")
        c.vline(15, 0, 16, "slate")
    if "n" in sides:
        if "w" in sides:
            c.px(1, 1, "white")
        c.hline(0, 0, 16, "slate")
    return c


def roof_set(kind: str) -> list[Tile]:
    prefix = "roof" if kind == "grey" else f"roof_{kind}"
    layout = {
        "nw": "nw",
        "n": "n",
        "ne": "ne",
        "w": "w",
        "": "",
        "e": "e",
        "sw": "sw",
        "s": "s",
        "se": "se",
    }
    tiles = []
    for suffix, sides in layout.items():
        name = f"{prefix}_{suffix}" if suffix else prefix
        tiles.append(Tile(name, roof_piece(kind, name, sides), collides=True))
    return tiles


def roof_extra(kind: str) -> Canvas:
    c = roof_interior("grey", f"roof_{kind}")
    if kind == "solar":
        c.rect(1, 2, 14, 12, "night")
        for y in range(3, 13, 1):
            for x in range(2, 14):
                c.px(x, y, "navy" if (x % 4 == 1 or y % 5 == 2) else "blue")
        c.hline(2, 3, 12, "ice")
        c.hline(1, 14, 14, "slate")
    elif kind == "ac":
        c.stamp(
            [
                "..ssssssssss..",
                ".spppppppppps.",
                ".pcccccccccpp.",
                ".pcsssssssccp.",
                ".pcs.sss.scp..",
                ".pcsss.sssc...",
                ".pcs.sss.sc...",
                ".pcsssssssc...",
                ".pccccccccc...",
                ".ssssssssss...",
            ],
            {"s": "slate", "p": "pavement", "c": "concrete", ".": None},
            1,
            3,
        )
        c.hline(2, 13, 11, "night")
    elif kind == "skylight":
        c.rect(2, 3, 12, 10, "concrete")
        c.rect(3, 4, 10, 8, "ice")
        c.rect(3, 4, 10, 2, "cyan")
        c.vline(7, 4, 8, "concrete")
        c.hline(3, 8, 10, "concrete")
        c.hline(2, 13, 12, "slate")
    return c


# Facades


@dataclass(frozen=True)
class Material:
    base: str
    light: str
    dark: str
    outline: str
    glass: tuple[str, str, str]
    door: tuple[str, str, str]


MATERIALS = {
    "cream": Material(
        "cream", "white", "sand", "umber", ("navy", "blue", "ice"), ("espresso", "brown", "tan")
    ),
    "slate": Material(
        "slate", "steel", "night", "ink", ("umber", "amber", "yellow"), ("ink", "navy", "blue")
    ),
}


def wall(m: Material, end: str = "") -> Canvas:
    c = Canvas(fill=m.base)
    if m.base == "slate":
        c.vline(7, 0, 16, "night")
        c.vline(8, 0, 16, "steel")
    else:
        c.hline(0, 7, 16, "peach")
    c.hline(0, 0, 16, m.dark)
    if end == "l":
        c.vline(0, 0, 16, m.outline)
        c.vline(1, 0, 16, m.light)
    if end == "r":
        c.vline(15, 0, 16, m.outline)
        c.vline(14, 0, 16, m.dark)
    return c


def base_wall(m: Material, end: str = "") -> Canvas:
    c = wall(m, end)
    c.hline(0, 0, 16, m.base if end == "" else m.base)
    if end == "l":
        c.px(1, 0, m.light)
    if end == "r":
        c.px(14, 0, m.dark)
    c.hline(0, 13, 16, m.dark)
    c.hline(0, 14, 16, "steel")
    c.hline(0, 15, 16, "slate")
    if end == "l":
        c.vline(0, 0, 16, m.outline)
    if end == "r":
        c.vline(15, 0, 16, m.outline)
    return c


def _window(c: Canvas, m: Material, top: int, bottom: int) -> None:
    frame = m.outline
    c.rect(2, top, 12, bottom - top + 1, frame)
    deep, mid, glint = m.glass
    for y in range(top + 1, bottom):
        for x in (*range(3, 7), *range(9, 13)):
            c.px(x, y, deep if y == top + 1 else mid)
    for x, y in ((4, top + 4), (5, top + 3), (6, top + 2), (10, top + 5), (11, top + 4)):
        c.px(x, y, glint)
    for x, y in ((3, top + 5), (4, top + 5), (9, top + 6)):
        c.px(x, y, glint)
    c.hline(1, bottom + 1, 14, m.light)
    c.hline(2, bottom + 2, 12, m.dark)


def window(m: Material) -> Canvas:
    c = wall(m)
    _window(c, m, 3, 11)
    return c


def base_window(m: Material) -> Canvas:
    c = base_wall(m)
    _window(c, m, 1, 9)
    return c


def door(m: Material, top: bool) -> Canvas:
    frame, leaf, light = m.door
    if top:
        c = wall(m)
        c.hline(1, 3, 14, m.light)
        c.hline(1, 4, 14, "concrete")
        c.hline(2, 5, 12, m.dark)
        c.rect(3, 6, 10, 10, frame)
        c.rect(4, 7, 8, 9, leaf)
        c.rect(6, 9, 4, 4, m.glass[1] if m.base == "cream" else light)
        c.px(6, 9, m.glass[2] if m.base == "cream" else "ice")
        c.vline(4, 7, 9, light)
    else:
        c = base_wall(m)
        c.rect(3, 0, 10, 14, frame)
        c.rect(4, 0, 8, 14, leaf)
        c.vline(4, 0, 14, light)
        c.rect(10, 5, 1, 3, "amber" if m.base == "cream" else "pavement")
        c.hline(2, 14, 12, "pavement")
        c.hline(2, 15, 12, "concrete")
    return c


def facade_set(material: str) -> list[Tile]:
    m = MATERIALS[material]
    tiles = [
        Tile(f"wall_{material}_l", wall(m, "l")),
        Tile(f"wall_{material}", wall(m)),
        Tile(f"wall_{material}_r", wall(m, "r")),
        Tile(f"window_{material}", window(m)),
        Tile(f"door_{material}_top", door(m, top=True)),
        Tile(f"base_{material}_l", base_wall(m, "l")),
        Tile(f"base_{material}", base_wall(m)),
        Tile(f"base_{material}_r", base_wall(m, "r")),
        Tile(f"base_window_{material}", base_window(m)),
        Tile(f"door_{material}", door(m, top=False)),
    ]
    return [Tile(t.name, t.canvas, collides=True) for t in tiles]


# Shops


def shopfront(end: str = "", name: str = "shopfront") -> Canvas:
    c = Canvas(fill="night")
    r = _rng(name)
    c.hline(0, 0, 16, "ink")
    for shelf in (5, 10):
        c.hline(0, shelf, 16, "slate")
        for x in range(0, 16, 2):
            if r.random() < 0.7:
                colour = r.choice(["red", "amber", "lime", "cyan", "neon", "white", "violet"])
                c.px(x, shelf - 1, colour)
                if r.random() < 0.5:
                    c.px(x, shelf - 2, colour)
    for x, y in ((2, 11), (3, 10), (4, 9), (5, 8), (6, 7), (7, 6), (8, 5), (9, 4), (10, 3)):
        c.px(x, y, "ice")
        c.px(x + 2, y, "blue")
    c.hline(0, 12, 16, "ink")
    c.hline(0, 13, 16, "concrete")
    c.hline(0, 14, 16, "steel")
    c.hline(0, 15, 16, "slate")
    c.vline(0, 0, 13, "ink")
    if end == "l":
        c.vline(1, 0, 13, "steel")
    if end == "r":
        c.vline(15, 0, 13, "ink")
        c.vline(14, 0, 13, "steel")
    return c


def shop_door() -> Canvas:
    c = Canvas(fill="ink")
    c.rect(2, 1, 12, 15, "steel")
    c.rect(3, 2, 10, 14, "blue")
    c.rect(3, 2, 10, 1, "navy")
    for x, y in ((4, 7), (5, 6), (6, 5), (7, 4), (4, 10), (5, 9), (6, 8), (7, 7), (8, 6)):
        c.px(x, y, "ice")
    c.vline(8, 2, 14, "steel")
    c.rect(6, 8, 1, 3, "white")
    c.rect(10, 8, 1, 3, "white")
    c.vline(0, 0, 16, "ink")
    return c


def awning(colour: str, stripe: str, end: str = "") -> Canvas:
    c = Canvas()
    for x in range(16):
        main = colour if (x // 2) % 2 == 0 else stripe
        c.px(x, 0, shade(colour, 2))
        c.px(x, 1, shade(main))
        c.vline(x, 2, 3, main)
        if x % 4 in (1, 2):
            c.px(x, 5, main)
            c.px(x, 6, shade(main))
        else:
            c.px(x, 5, shade(main))
    if end == "l":
        c.vline(0, 0, 6, shade(colour, 2))
    if end == "r":
        c.vline(15, 0, 6, shade(colour, 2))
    return c


def awning_set(name: str, colour: str, stripe: str) -> list[Tile]:
    return [
        Tile(f"{name}_l", awning(colour, stripe, "l")),
        Tile(name, awning(colour, stripe)),
        Tile(f"{name}_r", awning(colour, stripe, "r")),
    ]


# Coffee shop


def cafe_wall(end: str = "") -> Canvas:
    c = Canvas(fill="umber")
    for x in range(1, 16, 3):
        c.vline(x, 0, 16, "espresso")
        c.vline(x + 1, 0, 16, "brown")
    c.hline(0, 0, 16, "espresso")
    if end == "l":
        c.vline(0, 0, 16, "ink")
        c.vline(1, 0, 16, "tan")
    if end == "r":
        c.vline(15, 0, 16, "ink")
        c.vline(14, 0, 16, "espresso")
    return c


def cafe_sign() -> Canvas:
    c = Canvas(32, 16)
    for x in range(32):
        for y in range(16):
            c.px(x, y, cafe_wall().get(x % 16, y))
    c.rect(1, 2, 30, 12, "amber")
    c.rect(2, 3, 28, 10, "espresso")
    text = "COFFEE"
    draw_text(c, text, (32 - text_width(text)) // 2, 6, "cream")
    c.hline(2, 12, 28, "ink")
    return c


def cafe_window(end: str = "") -> Canvas:
    c = Canvas(fill="sand")
    c.rect(0, 0, 16, 3, "amber")
    c.hline(0, 0, 16, "espresso")
    for x in (3, 11):
        c.vline(x, 1, 2, "espresso")
        c.rect(x - 1, 3, 3, 1, "yellow")
    c.rect(0, 8, 16, 4, "umber")
    c.hline(0, 8, 16, "tan")
    c.px(5, 7, "white")
    c.px(6, 7, "white")
    c.px(12, 7, "red")
    for x, y in ((9, 2), (10, 3), (11, 4), (2, 6), (3, 5)):
        c.px(x, y, "cream")
    c.hline(0, 12, 16, "espresso")
    c.hline(0, 13, 16, "umber")
    c.hline(0, 14, 16, "espresso")
    c.hline(0, 15, 16, "ink")
    c.vline(0, 0, 13, "espresso")
    if end == "l":
        c.vline(0, 0, 16, "ink")
        c.vline(1, 0, 13, "tan")
    if end == "r":
        c.vline(15, 0, 16, "ink")
        c.vline(14, 0, 13, "espresso")
    return c


def cafe_door() -> Canvas:
    c = Canvas(fill="espresso")
    c.rect(2, 0, 12, 16, "umber")
    c.rect(4, 1, 8, 9, "amber")
    c.rect(4, 1, 8, 1, "orange")
    c.px(5, 3, "cream")
    c.px(6, 2, "cream")
    c.rect(4, 11, 8, 4, "brown")
    c.vline(3, 0, 16, "tan")
    c.rect(10, 7, 1, 3, "cream")
    c.hline(2, 15, 12, "espresso")
    return c


def cafe_table() -> Canvas:
    c = Canvas()
    c.stamp(
        [
            "................",
            "................",
            "................",
            "................",
            "......wwww......",
            "..b..wppppw..b..",
            ".bbb.wpcwpw.bbb.",
            ".bob.wppppw.bob.",
            ".ttt..wwww..ttt.",
            ".tot...ss...tot.",
            ".t.t...ss...t.t.",
            ".t.t...ss...t.t.",
            ".......ss.......",
            "......ssss......",
        ],
        {
            "w": "steel",
            "p": "white",
            "c": "brown",
            "s": "slate",
            "b": "umber",
            "t": "tan",
            "o": "brown",
        },
    )
    return c


def cafe_menu() -> Canvas:
    c = Canvas()
    c.stamp(
        [
            "....bbbbbbbb....",
            "....beeeeeeb....",
            "....bewweeeb....",
            "....beeeeeeb....",
            "....bewwwweb....",
            "....beeeeeeb....",
            "....beweweeb....",
            "....beeeeeeb....",
            "....bewwwweb....",
            "....beeeeeeb....",
            "....bbbbbbbb....",
            "....b......b....",
            "...b........b...",
            "...b........b...",
        ],
        {"b": "tan", "e": "espresso", "w": "cream"},
        0,
        2,
    )
    return c


# Signs


def _panel(c: Canvas, top: int, bottom: int, glow: str) -> None:
    c.rect(0, top, 16, bottom - top + 1, glow)
    c.rect(1, top + 1, 14, bottom - top - 1, "night")


def neon_text(text: str, colour: str, glow: str) -> Canvas:
    c = Canvas()
    _panel(c, 4, 12, glow)
    draw_text(c, text, (16 - text_width(text)) // 2, 6, colour)
    return c


def neon_icon(rows: list[str], colour: str, glow: str) -> Canvas:
    c = Canvas()
    _panel(c, 2, 13, glow)
    c.stamp(rows, {"#": colour, "+": glow}, 3, 4)
    return c


CUP = [
    "..+.+.....",
    ".+.+......",
    "..........",
    "#######...",
    "#.....###.",
    "#.....#.#.",
    "#.....###.",
    ".#...#....",
]
BOWL = [
    ".....+...+",
    "....+...+.",
    "...+...+..",
    "##########",
    "#........#",
    ".#......#.",
    "..######..",
    "...####...",
]
BOLT = [
    "....####..",
    "...####...",
    "..####....",
    ".#######..",
    "....###...",
    "...###....",
    "..##......",
    ".#........",
]
ZHONG = [
    "...#...",
    "#######",
    "#..#..#",
    "#..#..#",
    "#######",
    "...#...",
    "...#...",
]
SHAN = [
    "...#...",
    "...#...",
    "#..#..#",
    "#..#..#",
    "#..#..#",
    "#..#..#",
    "#######",
]


def neon_vertical() -> Canvas:
    c = Canvas(16, 32)
    c.rect(3, 2, 10, 28, "magenta")
    c.rect(4, 3, 8, 26, "night")
    c.stamp(ZHONG, {"#": "neon"}, 4, 6)
    c.stamp(SHAN, {"#": "neon"}, 4, 18)
    c.rect(6, 0, 1, 2, "steel")
    c.rect(9, 0, 1, 2, "steel")
    return c


def street_screen() -> Canvas:
    c = Canvas(32, 16)
    c.rect(0, 1, 32, 14, "ink")
    c.rect(1, 2, 30, 12, "violet")
    c.rect(1, 2, 30, 4, "plum")
    c.rect(1, 9, 30, 5, "neon")
    c.rect(1, 12, 30, 2, "magenta")
    for x, h in ((3, 6), (6, 9), (9, 5), (21, 8), (24, 10), (27, 6)):
        c.rect(x, 14 - h, 2, h, "night")
        c.px(x, 14 - h + 2, "amber")
    text = "2026"
    draw_text(c, text, (32 - text_width(text)) // 2, 4, "white")
    c.hline(0, 15, 32, "steel")
    return c


def ac_unit() -> Canvas:
    c = Canvas()
    c.stamp(
        [
            "sssssssssssss",
            "spppppppppppc",
            "spcccppccccpc",
            "spc.cppc..cpc",
            "spcccppc..cpc",
            "sppppppccccpc",
            "spppppppppppc",
            "scccccccccccc",
            ".s.........s.",
        ],
        {"s": "steel", "p": "pavement", "c": "concrete", ".": None},
        1,
        4,
    )
    c.stamp(["cc", "c.", "c."], {"c": "steel"}, 13, 6)
    return c


# Street furniture


def terminal() -> Canvas:
    c = Canvas(16, 32)
    c.rect(3, 4, 10, 16, "ink")
    c.rect(4, 5, 8, 13, "navy")
    c.rect(4, 5, 8, 2, "neon")
    for y, w in ((8, 7), (10, 5), (12, 6), (14, 4), (16, 6)):
        c.hline(5, y, w, "ice" if y == 8 else "cyan")
    c.hline(3, 19, 10, "steel")
    c.rect(5, 20, 6, 9, "slate")
    c.vline(5, 20, 9, "steel")
    c.vline(8, 21, 7, "cyan")
    c.rect(3, 29, 10, 2, "night")
    c.hline(3, 29, 10, "steel")
    return c


def lamp() -> Canvas:
    c = Canvas(16, 32)
    c.stamp(
        [
            "......sssssss...",
            ".....sppppppps..",
            "......siiiiis...",
            ".......wwwww....",
        ],
        {"s": "slate", "p": "concrete", "i": "ice", "w": "white"},
        0,
        4,
    )
    c.rect(6, 5, 2, 24, "steel")
    c.vline(6, 5, 24, "concrete")
    c.rect(4, 28, 6, 2, "slate")
    c.hline(4, 28, 6, "steel")
    c.rect(6, 18, 2, 2, "cyan")
    return c


def bench() -> Canvas:
    c = Canvas(32, 16)
    c.rect(2, 3, 28, 2, "tan")
    c.hline(2, 3, 28, "sand")
    c.rect(2, 6, 28, 2, "tan")
    c.hline(2, 6, 28, "sand")
    c.rect(4, 5, 2, 1, "slate")
    c.rect(26, 5, 2, 1, "slate")
    c.rect(1, 9, 30, 3, "sand")
    c.hline(1, 9, 30, "cream")
    c.hline(1, 11, 30, "brown")
    for x in (3, 27):
        c.rect(x, 12, 2, 3, "slate")
        c.px(x, 12, "steel")
    return c


BIKE = [
    "............hh..",
    ".....ss.....h...",
    "......f....bbb..",
    "......ff..fbbb..",
    "..wwwfwwfffww...",
    ".w...f.wf..w.w..",
    "w...xxx.f.w...w.",
    "w..x.x..w.w.x.w.",
    "w...x..xx.w...w.",
    ".w...w......w.w.",
    "..www........w..",
]


def bike(colour: str) -> Canvas:
    c = Canvas()
    c.stamp(
        BIKE,
        {"w": "ink", "f": colour, "s": "ink", "h": "slate", "b": shade(colour), "x": "steel"},
        0,
        4,
    )
    return c


def bins() -> Canvas:
    c = Canvas()
    for x, colour in ((1, "green"), (8, "blue")):
        c.rect(x, 4, 7, 2, shade(colour))
        c.hline(x, 4, 7, colour)
        c.rect(x, 6, 7, 9, colour)
        c.vline(x + 6, 6, 9, shade(colour))
        c.rect(x + 2, 8, 3, 3, "white")
        c.hline(x, 15, 7, shade(colour, 2))
    return c


def bollard() -> Canvas:
    c = Canvas()
    c.rect(6, 6, 4, 9, "steel")
    c.vline(6, 6, 9, "concrete")
    c.hline(6, 5, 4, "pavement")
    c.rect(6, 8, 4, 2, "amber")
    c.vline(6, 8, 2, "yellow")
    c.hline(5, 15, 6, "slate")
    return c


def vending() -> Canvas:
    c = Canvas(16, 32)
    c.rect(2, 4, 12, 27, "red")
    c.vline(13, 4, 27, "maroon")
    c.hline(2, 4, 12, "pink")
    c.rect(3, 6, 9, 3, "ink")
    c.hline(4, 7, 7, "cyan")
    c.rect(3, 10, 9, 13, "ice")
    for y, colours in ((11, ("blue", "lime", "amber")), (15, ("neon", "cyan", "orange")), (19, ("white", "red", "lime"))):
        for i, colour in enumerate(colours):
            c.rect(4 + i * 3, y, 2, 3, colour)
        c.hline(3, y + 3, 9, "pavement")
    c.rect(4, 25, 7, 3, "ink")
    c.px(12, 12, "yellow")
    c.px(12, 14, "lime")
    c.rect(2, 30, 12, 1, "maroon")
    return c


# Greenery


def tree() -> Canvas:
    c = Canvas(32, 32)
    r = random.Random("tile:tree")
    blobs = [(16, 10, 10), (9, 13, 7), (23, 13, 7), (12, 17, 7), (20, 17, 7), (16, 6, 6)]
    for y in range(32):
        for x in range(32):
            for bx, by, rad in blobs:
                if (x - bx) ** 2 + (y - by) ** 2 <= rad * rad:
                    light = (x - 12) + (y - 6)
                    colour = "lime" if light < 0 else "green" if light < 14 else "forest"
                    c.px(x, y, colour)
                    break
    for _ in range(40):
        x, y = r.randrange(32), r.randrange(32)
        if c.get(x, y) == "green":
            c.px(x, y, r.choice(["lime", "forest"]))
        elif c.get(x, y) == "lime":
            c.px(x, y, "yellow" if r.random() < 0.2 else "green")
    c.rect(14, 22, 4, 8, "umber")
    c.vline(14, 22, 8, "brown")
    c.hline(13, 29, 6, "umber")
    c.hline(14, 22, 4, "espresso")
    return c.outlined("deep")


def palm() -> Canvas:
    c = Canvas(16, 32)
    c.stamp(
        [
            "....l......l....",
            "..lll.l..l.lll..",
            ".llggglllggglll.",
            "lgg..gggggg..ggl",
            "gf..ggfllfgg..fg",
            "f..gf.gbbg.fg..f",
            "..gf.gf.bfg.fg..",
            ".gf..f..b..f..f.",
            ".f..f...bb..f...",
            "....f....b......",
            ".........bt.....",
            ".........bt.....",
            "........bt......",
            "........bt......",
            "........bt......",
            "........bt......",
            ".......bt.......",
            ".......bt.......",
            ".......bt.......",
            ".......bt.......",
            ".......bt.......",
            ".......bt.......",
            ".......bt.......",
            "......bbtt......",
        ],
        {"l": "lime", "g": "green", "f": "forest", "b": "brown", "t": "umber"},
        0,
        5,
    )
    for y in range(17, 28, 3):
        for x in range(16):
            if c.get(x, y) in ("brown", "umber"):
                c.px(x, y, "tan")
    return c


def bush() -> Canvas:
    c = Canvas()
    for y in range(16):
        for x in range(16):
            if ((x - 7.5) / 6.5) ** 2 + ((y - 10) / 5.5) ** 2 <= 1:
                light = (x - 5) + (y - 7)
                c.px(x, y, "lime" if light < 0 else "green" if light < 7 else "forest")
    c.px(5, 7, "lime")
    c.px(9, 10, "forest")
    return c.outlined("deep")


def planter(flowers: bool) -> Canvas:
    c = Canvas()
    plant = bush()
    c.paste(plant, 0, -3)
    if flowers:
        for x, y, colour in ((4, 6, "neon"), (8, 5, "yellow"), (11, 8, "neon"), (6, 9, "white")):
            c.px(x, y, colour)
            c.px(x + 1, y, shade(colour))
    c.rect(1, 10, 14, 6, "concrete")
    c.hline(1, 10, 14, "white")
    c.hline(1, 11, 14, "pavement")
    c.hline(1, 15, 14, "steel")
    c.vline(1, 11, 4, "pavement")
    c.vline(14, 11, 4, "steel")
    return c


def fountain() -> Canvas:
    c = Canvas(32, 32)
    for y in range(32):
        for x in range(32):
            d = ((x - 15.5) / 14.5) ** 2 + ((y - 17) / 12) ** 2
            if d <= 1:
                c.px(x, y, "concrete" if d > 0.78 else "pavement" if d > 0.62 else "blue")
    for y in range(32):
        for x in range(32):
            d = ((x - 15.5) / 14.5) ** 2 + ((y - 17) / 12) ** 2
            if 0.62 < d <= 0.78 and y < 17:
                c.px(x, y, "white")
            if d <= 0.62 and ((x + y) % 7 == 0 or (x * 3 + y) % 11 == 0):
                c.px(x, y, "cyan")
    c.rect(13, 12, 6, 7, "pavement")
    c.hline(13, 12, 6, "white")
    c.vline(18, 12, 7, "concrete")
    c.stamp(
        [
            "...i....i...",
            "....i..i....",
            ".i...ii...i.",
            "..i..ww..i..",
            "...iwwwwi...",
            "....wwww....",
            "......w.....",
        ],
        {"i": "ice", "w": "white"},
        10,
        5,
    )
    return c.outlined("slate")


def _vertical(canvas: Canvas, name: str) -> list[Tile]:
    return [
        *_split(canvas, [[f"{name}_top"]], above=True),
        *_split(canvas, [[], [name]], collides=True),
    ]


def groups() -> list[Group]:
    return [
        Group(
            "ground",
            [
                Tile("grass", grass()),
                Tile("grass_tufts", grass("grass_tufts", tufts=10)),
                Tile("grass_flowers", grass("grass_flowers", 3, ("neon", "white", "violet"))),
                Tile("pavement", pavement()),
                Tile("tactile_h", tactile(vertical=False)),
                Tile("tactile_v", tactile(vertical=True)),
                Tile("plaza", plaza()),
                Tile("plaza_inlay", plaza(inlay=True)),
                Tile("road", road()),
                Tile("road_line_h", road_line(vertical=False)),
                Tile("road_line_v", road_line(vertical=True)),
                Tile("crosswalk_h", crosswalk(vertical=False)),
                Tile("crosswalk_v", crosswalk(vertical=True)),
                Tile("water", water(), collides=True),
            ],
        ),
        Group("grass edges", edge_set("grass", grass, _grass_edge)),
        Group("road edges", edge_set("road", road, _road_edge)),
        Group("water edges", edge_set("water", water, _water_edge, collides=True)),
        Group(
            "roofs",
            [
                *roof_set("grey"),
                Tile("roof_solar", roof_extra("solar"), collides=True),
                Tile("roof_ac", roof_extra("ac"), collides=True),
                Tile("roof_skylight", roof_extra("skylight"), collides=True),
            ],
        ),
        Group("green roofs", roof_set("green")),
        Group("cream facades", facade_set("cream")),
        Group("slate facades", facade_set("slate")),
        Group(
            "shops",
            [
                Tile("shopfront_l", shopfront("l"), collides=True),
                Tile("shopfront", shopfront(), collides=True),
                Tile("shopfront_r", shopfront("r"), collides=True),
                Tile("shop_door", shop_door(), collides=True),
                *awning_set("awning_red", "red", "white"),
                *awning_set("awning_blue", "blue", "white"),
            ],
        ),
        Group(
            "coffee shop",
            [
                Tile("cafe_wall_l", cafe_wall("l"), collides=True),
                Tile("cafe_wall", cafe_wall(), collides=True),
                Tile("cafe_wall_r", cafe_wall("r"), collides=True),
                *_split(cafe_sign(), [["cafe_sign_l", "cafe_sign_r"]], collides=True),
                Tile("cafe_window_l", cafe_window("l"), collides=True),
                Tile("cafe_window", cafe_window(), collides=True),
                Tile("cafe_window_r", cafe_window("r"), collides=True),
                Tile("cafe_door", cafe_door(), collides=True),
                *awning_set("cafe_awning", "forest", "cream"),
                Tile("cafe_table", cafe_table(), collides=True),
                Tile("cafe_menu", cafe_menu(), collides=True),
            ],
        ),
        Group(
            "signs",
            [
                Tile("neon_tea", neon_text("TEA", "cyan", "blue")),
                Tile("neon_24h", neon_text("24H", "amber", "orange")),
                Tile("neon_cup", neon_icon(CUP, "neon", "magenta")),
                Tile("neon_bowl", neon_icon(BOWL, "amber", "orange")),
                Tile("neon_bolt", neon_icon(BOLT, "cyan", "blue")),
                *_split(neon_vertical(), [["neon_vertical_top"], ["neon_vertical_bottom"]]),
                *_split(street_screen(), [["screen_l", "screen_r"]]),
                Tile("ac_unit", ac_unit()),
            ],
        ),
        Group(
            "street",
            [
                *_vertical(terminal(), "terminal"),
                *_vertical(lamp(), "lamp"),
                *_split(bench(), [["bench_l", "bench_r"]], collides=True),
                Tile("bike_yellow", bike("amber"), collides=True),
                Tile("bike_blue", bike("blue"), collides=True),
                Tile("bins", bins(), collides=True),
                Tile("bollard", bollard(), collides=True),
                *_vertical(vending(), "vending"),
            ],
        ),
        Group(
            "greenery",
            [
                *_split(tree(), [["tree_tl", "tree_tr"]], above=True),
                *_split(tree(), [[], ["tree_bl", "tree_br"]], collides=True),
                *_vertical(palm(), "palm"),
                Tile("bush", bush(), collides=True),
                Tile("planter", planter(flowers=False), collides=True),
                Tile("planter_flowers", planter(flowers=True), collides=True),
                *_split(fountain(), [["fountain_tl", "fountain_tr"]], collides=True),
                *_split(fountain(), [[], ["fountain_bl", "fountain_br"]], collides=True),
            ],
        ),
    ]


def layout() -> list[Tile | None]:
    """Every tile in tileset order: each group starts a new row; None pads the rows."""
    cells: list[Tile | None] = []
    for group in groups():
        cells.extend(group.tiles)
        cells.extend([None] * (-len(cells) % COLUMNS))
    return cells


def tile_ids(cells: list[Tile | None]) -> dict[str, int]:
    return {tile.name: i for i, tile in enumerate(cells) if tile is not None}


def tileset_canvas(cells: list[Tile | None]) -> Canvas:
    sheet = Canvas(COLUMNS * TILE_SIZE, len(cells) // COLUMNS * TILE_SIZE)
    for i, tile in enumerate(cells):
        if tile is not None:
            sheet.paste(tile.canvas, i % COLUMNS * TILE_SIZE, i // COLUMNS * TILE_SIZE)
    return sheet


TERRAINS = {"grass": "#3e8948", "road": "#3a4466", "water": "#0099db"}
_PAVED_CORNERS = {
    "": (),
    "_n": ("ne", "nw"),
    "_s": ("se", "sw"),
    "_e": ("ne", "se"),
    "_w": ("nw", "sw"),
    "_ne": ("ne", "nw", "se"),
    "_nw": ("nw", "ne", "sw"),
    "_se": ("se", "sw", "ne"),
    "_sw": ("sw", "se", "nw"),
    "_ne_nook": ("ne",),
    "_nw_nook": ("nw",),
    "_se_nook": ("se",),
    "_sw_nook": ("sw",),
}


def _wangset(terrain: str, colour: str, ids: dict[str, int]) -> dict[str, object]:
    def wangid(paved: tuple[str, ...]) -> list[int]:
        ne, se, sw, nw = (1 if corner in paved else 2 for corner in ("ne", "se", "sw", "nw"))
        return [0, ne, 0, se, 0, sw, 0, nw]

    wangtiles = [{"tileid": ids["pavement"], "wangid": wangid(("ne", "se", "sw", "nw"))}]
    wangtiles += [
        {"tileid": ids[f"{terrain}{suffix}"], "wangid": wangid(paved)}
        for suffix, paved in _PAVED_CORNERS.items()
    ]
    return {
        "name": terrain,
        "type": "corner",
        "tile": ids[terrain],
        "colors": [
            {"name": "pavement", "color": "#c0cbdc", "tile": ids["pavement"], "probability": 1},
            {"name": terrain, "color": colour, "tile": ids[terrain], "probability": 1},
        ],
        "wangtiles": sorted(wangtiles, key=lambda t: t["tileid"]),
    }


def tileset_json(cells: list[Tile | None], image: str = "tiles.png") -> dict[str, object]:
    ids = tile_ids(cells)
    tiles = [
        {
            "id": i,
            "properties": [
                {"name": "above", "type": "bool", "value": tile.above},
                {"name": "collides", "type": "bool", "value": tile.collides},
                {"name": "name", "type": "string", "value": tile.name},
            ],
        }
        for i, tile in enumerate(cells)
        if tile is not None
    ]
    return {
        "type": "tileset",
        "version": "1.10",
        "tiledversion": "1.11.2",
        "name": "simile",
        "image": image,
        "imagewidth": COLUMNS * TILE_SIZE,
        "imageheight": len(cells) // COLUMNS * TILE_SIZE,
        "tilewidth": TILE_SIZE,
        "tileheight": TILE_SIZE,
        "tilecount": len(cells),
        "columns": COLUMNS,
        "margin": 0,
        "spacing": 0,
        "tiles": tiles,
        "wangsets": [_wangset(t, colour, ids) for t, colour in TERRAINS.items()],
    }
