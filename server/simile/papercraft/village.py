"""How the village looks: each street's layers, each building's front, and each room's paper.
Where things are and how big comes from the maps, through `layout.py`."""

from dataclasses import dataclass

from simile.papercraft.fronts import UNIT, WINDOW, Box, Front, Rgb, Roof
from simile.papercraft.layout import Facade, Layout
from simile.papercraft.painter import Style

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
    city: str | None = None
    """The city's skyline, between the sky and the far layer. Streets underground have none."""


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
    "sewers": Street(
        "far-sewer", "mid-sewer", "near-sewer", "ground-sewer", "front-sewer", sky="sewer-vault"
    ),
}
UNDERGROUND = frozenset({"metro", "sewers"})
"""The streets under the village, painted in the cartoon or the grimy cartoon, with no city."""


@dataclass(frozen=True)
class Landmark:
    """A building drawn once per street behind the city layer, from its plan in `skyline.py`."""

    subject: str
    height: float
    """How tall it's drawn, in the street's metres."""
    at: dict[str, float]
    """By street, where along it it stands, as a fraction of the street's width."""
    style: Style = "clean"
    ref: str = "clean/street"


LANDMARKS: dict[str, Landmark] = {}
"""By plan name in `skyline.PLANS`."""
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
    reseeds: tuple[int, ...] = ()
    """Added to each unit's seed, by unit, to paint one rejected unit again."""
    style: Style = "papercraft"
    plants: bool = True
    """A potted plant each side of the door."""
    whole: bool = False
    """Painted in one go however wide, for a front that isn't a terrace."""
    modern: bool = False
    """Today's details on the plan and in the prompt: see `fronts.modernised`."""
    pictogram: str | None = None
    """What a modern shop window's neon sign shows, such as "coffee cup"."""


TERRACOTTA: Rgb = (184, 96, 70)
SLATE: Rgb = (104, 112, 124)
CLAY: Rgb = (150, 108, 86)

DARK: Rgb = (52, 56, 62)
ROOF: Rgb = (96, 100, 108)
PLANTERS: Rgb = (72, 76, 84)
PANES = (1.6, 1.4)


def modern(look: str, wall: Rgb, **kw) -> Look:
    """A village front in the comic style, with today's details."""
    kw = {"trim": DARK, "roof": ROOF, "glass_door": True, "window": PANES, **kw}
    return Look(look, wall, roof_shape="flat", style="clean", modern=True, **kw)


LOOKS: dict[str, Look] = {
    "house_1": modern(
        "a two-storey family townhouse of dusty pink render", (214, 156, 158), flower_boxes=PLANTERS
    ),
    "house_2": modern(
        "a two-storey townhouse of pale blue render", (160, 190, 210), flower_boxes=PLANTERS
    ),
    "house_3": modern("a two-storey family house of soft mint render", (176, 210, 186)),
    "house_4": modern(
        "a two-storey house of mustard-yellow render", (220, 184, 98), flower_boxes=PLANTERS
    ),
    "house_5": modern(
        "a two-storey house clad in navy-blue painted timber boards",
        (70, 86, 124),
        trim=(38, 40, 44),
        flower_boxes=PLANTERS,
    ),
    "house_6": modern("a two-storey house of peach render", (236, 178, 146)),
    "house_7": modern(
        "a two-storey house of lavender render", (184, 168, 206), flower_boxes=PLANTERS
    ),
    "house_8": modern(
        "a two-storey house of sage-green render", (164, 184, 150), flower_boxes=PLANTERS
    ),
    "house_9": modern(
        "a two-storey house clad in deep teal painted timber boards",
        (60, 116, 118),
        trim=(38, 40, 44),
    ),
    "house_10": modern(
        "a two-storey house of pale butter-yellow render", (238, 220, 160), mural_words=True
    ),
    "noodle_bar": modern(
        "a two-storey noodle shop clad in warm ochre tiles",
        (210, 160, 96),
        shop=(214, 64, 56),
        lanterns=6,
        pictogram="noodle bowl",
    ),
    "corner_shop": modern(
        "a three-storey corner convenience store of pale grey concrete",
        (190, 194, 198),
        shop=(246, 132, 60),
        mural_words=True,
        pictogram="shopping basket",
    ),
    "coffee_shop": modern(
        "a three-storey corner coffee shop clad in pale mint glazed tiles",
        (186, 214, 204),
        shop=(70, 196, 176),
        flower_boxes=PLANTERS,
        one_shop=True,
        mural_words=True,
        pictogram="coffee cup",
        reseeds=(1, 3),
    ),
    "maker_space": modern(
        "a three-storey maker space in a converted factory of charcoal-painted brick with big "
        "black steel-framed windows",
        (104, 108, 116),
        trim=(38, 40, 44),
        roof=(80, 84, 90),
        shop=(246, 204, 64),
        flower_boxes=(56, 60, 66),
        window=(1.8, 1.6),
        pictogram="gear",
    ),
    "tower": modern(
        "an old three-storey tower of pale grey concrete with plain blank walls, and a small "
        "service door",
        (200, 198, 190),
        mural_words=True,
    ),
    "garden_flats": modern(
        "a three-storey block of garden flats of cream render",
        (232, 220, 196),
        flower_boxes=PLANTERS,
        mural_words=True,
    ),
    "gallery": modern(
        "a three-storey art gallery of white render with tall windows",
        (238, 236, 230),
        window=(1.4, 2.0),
    ),
    "bakery": modern(
        "a one-storey corner bakery of warm apricot render",
        (234, 178, 132),
        shop=(214, 120, 70),
        pictogram="bread loaf",
    ),
    "print_works": modern(
        "a two-storey old print works of red-brown brick with big steel-framed windows",
        (156, 88, 70),
        trim=(38, 40, 44),
        window=(1.8, 1.6),
    ),
    "tea_house": modern(
        "a two-storey tea house clad in pale jade-green painted timber boards",
        (156, 196, 166),
        lanterns=3,
    ),
    "laundry": modern(
        "a two-storey laundry of pale sky-blue render",
        (172, 202, 222),
        shop=(80, 120, 168),
        flower_boxes=PLANTERS,
        pictogram="washing machine",
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
        style="cartoon",
        plants=False,
        whole=True,
        reseed=1,
    ),
    "clock_house": modern(
        "a three-storey townhouse of pale sandstone",
        (216, 204, 180),
        flower_boxes=PLANTERS,
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
PAPER_STYLES: dict[str, Style] = {"clinic-tiles": "cartoon"}
"""Papers in a style other than papercraft."""
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
        modern=look.modern,
    )


def _free_door(width: float, murals: list[Box]) -> float:
    """Where a door goes on a front the map gives none: in the widest stretch of wall clear of
    murals."""
    edges = sorted([(0.0, 0.0), *[(m[0], m[2]) for m in murals], (width, width)])
    gaps = [(b[0] - a[1], (a[1] + b[0]) / 2) for a, b in zip(edges, edges[1:], strict=False)]
    return max(gaps)[1]
