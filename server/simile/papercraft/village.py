"""How the village looks: each street's layers, each building's front, and each room's paper.
Where things are and how big comes from the maps, through `layout.py`."""

from dataclasses import dataclass

from simile.papercraft.fronts import UNIT, WINDOW, Box, Front, Rgb, Roof
from simile.papercraft.layout import Facade, Layout

TILE = 1.1


@dataclass(frozen=True)
class Street:
    """A street's layers, each a painting key under `layers/`, back to front."""

    far: str
    mid: str
    near: str
    ground: str
    foreground: str
    sky: str = "sky"


STREETS: dict[str, Street] = {
    "high_street": Street(
        "far-hills", "mid-shophouses", "near-walls", "ground-street", "front-plants"
    ),
    "lychee_lane": Street(
        "far-hills", "mid-homes", "near-gardens", "ground-street", "front-plants"
    ),
    "kapok_walk": Street(
        "far-hills", "mid-rooftops", "near-gardens", "ground-street", "front-plants"
    ),
    "banyan_row": Street(
        "far-river", "mid-riverbank", "near-hedges", "ground-street", "front-reeds"
    ),
    "rooftops": Street("far-hills", "mid-rooftops", "near-walls", "ground-street", "front-plants"),
    "metro": Street(
        "far-metro", "mid-metro", "near-metro", "ground-metro", "front-metro", sky="metro-vault"
    ),
}
GROUNDS = {
    "square": "ground-plaza",
    "park": "ground-park",
    "riverside": "ground-promenade",
}
"""Ground strips for stretches of a street that aren't pavement, by the location or place on it."""


@dataclass(frozen=True)
class Look:
    """What a building's front is made of, for its plan and its prompt."""

    look: str
    wall: Rgb
    trim: Rgb
    roof: Rgb
    roof_shape: Roof = "gable"
    shutters: Rgb | None = None
    shop: Rgb | None = None
    """Awnings over shop windows on the ground floor, in this colour striped with cream."""
    lanterns: int = 0
    flower_boxes: Rgb | None = None
    glass_door: bool = False
    window: tuple[float, float] = WINDOW
    one_shop: bool = False
    mural_words: bool = False
    """Ask outright for the mural wall to stay empty, where FLUX fills it otherwise."""
    reseed: int = 0
    """Added to the seed, to paint a rejected front again."""
    cartoon: bool = False
    """Painted in the tunnels' cartoon rather than papercraft."""
    plants: bool = True
    """A potted plant each side of the door."""
    whole: bool = False
    """Painted in one go however wide, for a front that isn't a terrace."""


WOOD: Rgb = (126, 88, 60)
CREAM: Rgb = (240, 232, 214)
TERRACOTTA: Rgb = (184, 96, 70)
SLATE: Rgb = (104, 112, 124)
CLAY: Rgb = (150, 108, 86)
BOXES: Rgb = (150, 100, 70)

LOOKS: dict[str, Look] = {
    "house_1": Look(
        "a two-storey family house of dusty pink plaster",
        (214, 156, 158),
        WOOD,
        TERRACOTTA,
        shutters=(120, 140, 110),
        flower_boxes=BOXES,
    ),
    "house_2": Look(
        "a two-storey townhouse of pale blue plaster",
        (160, 190, 210),
        CREAM,
        SLATE,
        "hip",
        flower_boxes=(170, 110, 80),
    ),
    "house_3": Look(
        "a two-storey family house of soft mint plaster",
        (176, 210, 186),
        WOOD,
        TERRACOTTA,
        shutters=(206, 186, 150),
        flower_boxes=BOXES,
    ),
    "house_4": Look(
        "a two-storey house of mustard-yellow plaster",
        (220, 184, 98),
        CREAM,
        SLATE,
        "hip",
        shutters=(90, 110, 130),
    ),
    "house_5": Look(
        "a two-storey house of navy-blue painted wooden boards",
        (70, 86, 124),
        CREAM,
        TERRACOTTA,
        shutters=CREAM,
        flower_boxes=(160, 110, 80),
    ),
    "house_6": Look(
        "a two-storey house of peach plaster",
        (236, 178, 146),
        WOOD,
        TERRACOTTA,
        shutters=(110, 140, 120),
    ),
    "house_7": Look(
        "a two-storey house of lavender plaster",
        (184, 168, 206),
        CREAM,
        SLATE,
        "hip",
        flower_boxes=BOXES,
    ),
    "house_8": Look(
        "a two-storey house of sage-green plaster",
        (164, 184, 150),
        WOOD,
        TERRACOTTA,
        shutters=(206, 186, 150),
        flower_boxes=BOXES,
    ),
    "house_9": Look(
        "a two-storey house of deep teal painted wooden boards",
        (60, 116, 118),
        CREAM,
        SLATE,
        "hip",
        shutters=CREAM,
    ),
    "house_10": Look(
        "a two-storey house of pale butter-yellow plaster",
        (238, 220, 160),
        WOOD,
        TERRACOTTA,
        shutters=(120, 140, 110),
    ),
    "noodle_bar": Look(
        "a two-storey noodle bar of warm ochre plaster",
        (210, 160, 96),
        (124, 72, 52),
        CLAY,
        "hip",
        shop=(196, 72, 60),
        lanterns=6,
    ),
    "corner_shop": Look(
        "a three-storey corner grocery shop of lemon plaster",
        (232, 214, 140),
        (70, 110, 150),
        SLATE,
        "flat",
        shop=(74, 120, 168),
        glass_door=True,
    ),
    "coffee_shop": Look(
        "a three-storey corner cafe of cream plaster",
        (236, 222, 186),
        (110, 78, 56),
        (150, 112, 90),
        shutters=(132, 96, 66),
        shop=(120, 170, 140),
        glass_door=True,
        one_shop=True,
        reseed=2,
    ),
    "maker_space": Look(
        "a three-storey converted brick workshop with big steel-framed windows",
        (168, 92, 74),
        (70, 74, 78),
        (90, 94, 100),
        "flat",
        shop=(60, 120, 120),
        glass_door=True,
    ),
    "tower": Look(
        "an old three-storey tower of pale grey concrete with plain blank walls and no "
        "windows, and a small service door",
        (200, 198, 190),
        (120, 124, 128),
        SLATE,
        "flat",
        glass_door=True,
        mural_words=True,
        reseed=4,
    ),
    "garden_flats": Look(
        "a three-storey block of garden flats of cream plaster",
        (232, 220, 196),
        (110, 120, 100),
        CLAY,
        "flat",
        shutters=(110, 140, 110),
        flower_boxes=BOXES,
        mural_words=True,
    ),
    "gallery": Look(
        "a three-storey art gallery of white plaster with tall windows",
        (238, 236, 230),
        (90, 90, 96),
        (150, 150, 150),
        "flat",
        glass_door=True,
    ),
    "bakery": Look(
        "a one-storey corner bakery of warm apricot plaster with a flat roof",
        (234, 178, 132),
        CREAM,
        TERRACOTTA,
        "flat",
        shop=(176, 96, 70),
        glass_door=True,
    ),
    "print_works": Look(
        "a two-storey old print works of red-brown brick with a flat roof and steel-framed windows",
        (156, 88, 70),
        (70, 74, 78),
        SLATE,
        "flat",
    ),
    "tea_house": Look(
        "a two-storey tea house of pale jade-green painted wooden boards with a flat roof",
        (156, 196, 166),
        (124, 72, 52),
        CLAY,
        "flat",
        shutters=(124, 72, 52),
        lanterns=3,
    ),
    "laundry": Look(
        "a two-storey laundry of pale sky-blue plaster with a flat roof",
        (172, 202, 222),
        CREAM,
        SLATE,
        "flat",
        shop=(80, 120, 168),
        flower_boxes=BOXES,
    ),
    "clinic": Look(
        "a small back-alley clinic built into an old metro station office of cracked pale "
        "green tiles",
        (178, 204, 186),
        (60, 84, 82),
        (88, 92, 96),
        "flat",
        glass_door=True,
        window=(1.3, 1.1),
        cartoon=True,
        plants=False,
        whole=True,
        reseed=1,
    ),
    "clock_house": Look(
        "a three-storey townhouse of pale sandstone with a flat roof",
        (216, 204, 180),
        (110, 100, 90),
        CLAY,
        "flat",
        shutters=(90, 110, 130),
        flower_boxes=BOXES,
    ),
}

PAPERS = {
    "living-ochre": "warm ochre wallpaper with a small repeating pattern of cream leaves",
    "living-blue": "soft cornflower-blue wallpaper with a small repeating pattern of white daisies",
    "living-green": "deep green wallpaper with a small repeating pattern of gold palm fronds",
    "bedroom-rose": "dusty rose wallpaper with thin vertical cream stripes",
    "bedroom-sage": "sage-green wallpaper with a small repeating pattern of pale ferns",
    "bedroom-lilac": "pale lilac wallpaper with a small repeating pattern of tiny white stars",
    "cafe-panelling": "warm honey-coloured wooden wall panelling in narrow vertical boards",
    "cafe-tiles": "a printed checkerboard of matt cream and sage-green squares, flat like "
    "wrapping paper",
    "plaster-cream": "plain cream plaster with soft mottled texture",
    "brick": "a printed pattern of red-brown bricks with pale mortar, flat and matt like "
    "wrapping paper",
    "dining-red": "deep red lacquered wall panels with a thin gold border pattern",
    "block-grey": "pale grey painted concrete blocks with thin grey joints",
    "loft-boards": "strips of pale pine-coloured card laid across like boards, with a few "
    "knots drawn in brown pencil",
    "plaster-white": "plain warm white plaster with a faint soft texture",
    "clinic-tiles": "pale green-white wall tiles in a neat grid with dark grout, a few chipped "
    "tiles and faint stains",
}
CARTOON_PAPERS = frozenset({"clinic-tiles"})
"""Papers painted in the tunnels' cartoon."""
ROOMS: dict[str, tuple[str, ...]] = {
    "living_room": ("living-ochre", "living-blue", "living-green"),
    "bedroom": ("bedroom-rose", "bedroom-sage", "bedroom-lilac"),
    "cafe": ("cafe-panelling",),
    "cafe_upstairs": ("cafe-tiles",),
    "flat": ("plaster-cream",),
    "noodle_bar": ("brick",),
    "dining_room": ("dining-red",),
    "workshop": ("block-grey",),
    "loft": ("loft-boards",),
    "gallery": ("plaster-white",),
    "clinic": ("clinic-tiles",),
}
"""Each kind of room's papers. Rooms of one kind take turns, by their building's place in the
village, so neighbours differ."""


def papers(layout: Layout) -> dict[str, list[str]]:
    """Each building's paper for each floor, ground floor first."""
    seen: dict[str, int] = {}
    out = {}
    for building in sorted(layout.rooms, key=_natural):
        rooms = layout.rooms[building]
        out[building] = [ROOMS[r][seen.get(r, 0) % len(ROOMS[r])] for r in rooms]
        for room in set(rooms):
            seen[room] = seen.get(room, 0) + 1
    return out


def _natural(name: str) -> tuple[str, int]:
    stem, _, number = name.rpartition("_")
    return (stem, int(number)) if number.isdigit() else (name, 0)


def front(facade: Facade, look: Look) -> Front:
    """A building's front, as wide and as tall as its facade on the map, with its door where
    the map has it and its mural walls left blank from the ground to the eaves."""
    width, height = facade.width * TILE, facade.height * TILE
    storey = (facade.height + 1) / facade.storeys * TILE
    murals: list[Box] = [
        (
            m.x * TILE,
            max(0.3, m.bottom * storey),
            (m.x + m.width) * TILE,
            min(height - 0.3, m.top * storey),
        )
        for m in facade.murals
    ]
    door = (facade.door + 0.5) * TILE if facade.door is not None else _free_door(width, murals)
    return Front(
        width=width,
        storeys=facade.storeys,
        storey=storey,
        wall_height=height,
        door=door,
        wall=look.wall,
        trim=look.trim,
        roof=look.roof,
        roof_shape=look.roof_shape,
        shutters=look.shutters,
        shop=look.shop,
        lanterns=look.lanterns,
        flower_boxes=look.flower_boxes,
        murals=tuple(murals),
        glass_door=look.glass_door,
        plants=look.plants,
        window=look.window,
        one_shop=look.one_shop,
        unit=width if look.whole else UNIT,
    )


def _free_door(width: float, murals: list[Box]) -> float:
    """Where a door goes on a front the map gives none: in the widest stretch of wall clear of
    murals."""
    edges = sorted([(0.0, 0.0), *[(m[0], m[2]) for m in murals], (width, width)])
    gaps = [(b[0] - a[1], (a[1] + b[0]) / 2) for a, b in zip(edges, edges[1:], strict=False)]
    return max(gaps)[1]
