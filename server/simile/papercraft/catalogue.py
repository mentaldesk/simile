"""Every painting the village needs: its prompt, size, style image and height in metres."""

import zlib
from dataclasses import dataclass, field
from typing import Literal, NamedTuple

from simile.papercraft import skyline
from simile.papercraft.fronts import GREY, Front, backdrop, unit_plans, units
from simile.papercraft.layout import Layout, load_layout
from simile.papercraft.painter import Style, in_style
from simile.papercraft.sketches import SKETCHES
from simile.papercraft.village import (
    GROUNDS,
    LANDMARKS,
    LOOKS,
    PAPER_STYLES,
    PAPERS,
    STREETS,
    Landmark,
    Look,
    front,
    papers,
)

type Kind = Literal["layer", "strip", "ground", "sprite", "front", "glow", "paper", "landmark"]

SPRITE = (
    "Seen straight from the front at eye level, a flat elevation with no perspective. One single "
    "object centred on a plain flat white background with empty space all around it, nothing "
    "else in the picture, and no shadow on the background."
)
SIDE_SPRITE = SPRITE.replace("straight from the front", "exactly from the side")
NOTHING_BUT_PLANTS = " Only plants, fences and garden things: no houses, no buildings, no people."
CARTOON_LEAD = "Make a new picture in exactly the cartoon style of the reference picture: "
CARTOON_REDRAW = (
    "Redraw image 1 as {subject}, hand-drawn in the cartoon style of image 2: thick scratchy dark "
    "ink outlines around every shape, flat colours with simple soft shading, and a little wear. "
    "Keep every shape exactly where it is, with the same outlines and colours, seen exactly from "
    "the side with no perspective, on a plain {back} background, and no shadow on the background."
)
CARTOON_TEXTURE = (
    "A flat hand-drawn texture that fills the whole frame edge to edge: {}. Drawn with scratchy "
    "dark ink lines and flat colours, a few smudges and scuffs, even light, no objects, no edges."
)
CARTOON_PAPER_LEAD = (
    "Make a flat texture in the colours and cartoon style of the reference picture, showing none "
    "of its objects: "
)
GRIMY_LEAD = "Make a new picture in exactly the grimy cartoon style of the reference picture: "
GRIMY_REDRAW = (
    "Redraw image 1 as {subject}, hand-drawn in the grimy cartoon style of image 2: thick "
    "scratchy dark ink outlines around every shape, flat colours with simple soft shading, and "
    "heavy grime, damp stains and slime. Keep every shape exactly where it is, with the same "
    "outlines and colours, seen exactly from the side with no perspective, on a plain {back} "
    "background, and no shadow on the background."
)
TUNNELS = "cartoon/street"
TUNNEL_ROOMS = "cartoon/interior"
"""The tunnels' references, from #329's revised cartoon."""
CLEAN_LEAD = "Make a new picture in exactly the scratchy cartoon style of the reference picture: "
CLEAN_FINISH = (
    "thick scratchy, uneven dark ink outlines around every shape, flat colours with simple soft "
    "shading, everything fresh and new"
)
CLEAN_REDRAW = (
    "Redraw image 1 as {subject}, hand-drawn in the scratchy cartoon style of image 2: "
    + CLEAN_FINISH
    + ". Keep every shape exactly where it is, with the same outlines and colours, seen exactly "
    "from the side with no perspective, on a plain {back} background, and no shadow on the "
    "background."
)
CLEAN_TEXTURE = (
    "A flat hand-drawn texture that fills the whole frame edge to edge: {}. Drawn with scratchy "
    "dark ink lines and flat colours, even light, no objects, no edges."
)
CLEAN_PAPER_LEAD = (
    "Make a flat texture in the colours and scratchy cartoon style of the reference picture, "
    "showing none of its objects: "
)
CLEAN_STREET = "clean/street"
CLEAN_ROOMS = "clean/interior"
"""The village's comic references, line B from #554's study."""
GRIMY_TEXTURE = (
    "A flat hand-drawn texture that fills the whole frame edge to edge: {}. Drawn with scratchy "
    "dark ink lines and flat colours, heavy grime and damp stains, even light, no objects, no "
    "edges."
)
GRIMY_PAPER_LEAD = (
    "Make a flat texture in the colours and grimy cartoon style of the reference picture, "
    "showing none of its objects: "
)


@dataclass(frozen=True)
class Words:
    """What a style's prompts say, and the references its layers and papers are painted from."""

    lead: str
    """Before a new picture's subject."""
    redraw: str
    """A sketch redrawn, with `{subject}` and `{back}`."""
    paper_lead: str
    texture: str
    """A paper's pattern, with `{}`."""
    front: str
    """How a front or a landmark is redrawn from its plan."""
    night: str
    """What a night picture leaves in shadow."""
    variant: str
    """What a colour variant keeps."""
    layers: str
    rooms: str


WORDS: dict[Style, Words] = {
    "clean": Words(
        CLEAN_LEAD,
        CLEAN_REDRAW,
        CLEAN_PAPER_LEAD,
        CLEAN_TEXTURE,
        "hand-drawn in the scratchy cartoon style: " + CLEAN_FINISH,
        "walls",
        "the ink lines",
        CLEAN_STREET,
        CLEAN_ROOMS,
    ),
    "cartoon": Words(
        CARTOON_LEAD,
        CARTOON_REDRAW,
        CARTOON_PAPER_LEAD,
        CARTOON_TEXTURE,
        "hand-drawn in the cartoon style: thick scratchy dark ink outlines around every shape, "
        "flat colours with simple soft shading, and a little wear",
        "walls",
        "the ink lines",
        TUNNELS,
        TUNNEL_ROOMS,
    ),
    "grimy": Words(
        GRIMY_LEAD,
        GRIMY_REDRAW,
        GRIMY_PAPER_LEAD,
        GRIMY_TEXTURE,
        "hand-drawn in the grimy cartoon style: thick scratchy dark ink outlines around every "
        "shape, flat colours with simple soft shading, and heavy grime, damp stains and slime",
        "walls",
        "the ink lines",
        TUNNELS,
        TUNNEL_ROOMS,
    ),
}


@dataclass(frozen=True)
class Painting:
    """One painting, the file it becomes (`key`.webp), and how it's cut and scaled.

    - `layer`: a far street layer, made solid from its top edge down, tileable along x
    - `strip`: a mid, near or foreground layer, cut out like a sprite, tileable along x
    - `ground`: a ground layer, keyed off its backdrop and made solid from its top edge down,
      tileable along x
    - `sprite`: cut out, trimmed and scaled to `height`
    - `front`: a building front redrawn from its plan, cut on the plan's outline
    - `glow`: a building's night picture, kept only where its plan has windows and lamps
    - `paper`: an opaque texture, tileable both ways
    """

    key: str
    kind: Kind
    prompt: str
    size: tuple[int, int]
    refs: tuple[str, ...] = ()
    height: float | None = None
    """How tall it stands in the world, in metres."""
    base: str | None = None
    """The painting this one redraws: a night picture's front, or a colour variant's item."""
    building: str | None = None
    """For a front or a glow map, the building it belongs to."""
    sketch: str | None = None
    """A flat drawing from `sketches.py` that the painting redraws."""
    prompts: tuple[str, ...] = ()
    """For a front or glow map painted a unit at a time, each unit's prompt."""
    reseed: int = 0
    """Added to the seed, to paint a rejected painting again from the same prompt."""
    cut: tuple[str, ...] = ()
    """What else to cut: a sprite's `shadows` and `gaps`, `above` a ground piece's top row, or
    `banded`, a ground piece made solid across its own band."""
    landmark: str | None = None
    """For a landmark or its glow map, its plan in `skyline.PLANS`."""
    reseeds: tuple[int, ...] = ()
    """For a front or glow map, added to each unit's seed, by unit, to paint one unit again."""
    surface: float | None = None
    """For a ground piece, metres down from its top edge to the far edge of its walking surface,
    measured on the art."""
    headroom: float = 0.0
    """For a far layer, the share of its height left clear above its skyline."""

    @property
    def seed(self) -> int:
        return zlib.crc32((self.base or self.key).encode()) % 10_000 + self.reseed

    def unit_reseed(self, unit: int | None) -> int:
        return self.reseeds[unit] if unit is not None and unit < len(self.reseeds) else 0


def layer(
    key: str,
    kind: Kind,
    subject: str,
    size: tuple[int, int],
    height: float,
    style: Style,
    **kw,
) -> Painting:
    """A street layer. The village's near and foreground ones are kept to plants, since edit
    mode copies the street reference's houses into them otherwise."""
    words = WORDS[style]
    if style == "clean" and key.startswith(("near-", "front-")):
        subject += NOTHING_BUT_PLANTS
    prompt = in_style(words.lead + subject, style)
    return Painting(f"layers/{key}", kind, prompt, size, (words.layers,), height, **kw)


def paper(key: str, pattern: str, style: Style, size: tuple[int, int] = (768, 512)) -> Painting:
    words = WORDS[style]
    prompt = in_style(words.paper_lead + words.texture.format(pattern), style)
    return Painting(f"papers/{key}", "paper", prompt, size, (words.rooms,))


def sewer_layer(
    key: str, kind: Kind, subject: str, size: tuple[int, int], height: float, **kw
) -> Painting:
    """A layer of the sewers, in the grimy cartoon."""
    return layer(key, kind, subject, size, height, "grimy", **kw)


def tunnel_layer(
    key: str, kind: Kind, subject: str, size: tuple[int, int], height: float, **kw
) -> Painting:
    """A layer of the tunnels, in the cartoon."""
    return layer(key, kind, subject, size, height, "cartoon", **kw)


STRIP = (
    "running from the left edge of the frame to the right edge, standing on one straight "
    "baseline on a plain white background."
)


def village_layer(key: str, kind: Kind, subject: str, size: tuple[int, int], height: float, **kw):
    """A village street layer in the comic style, painted on grey if `grey`."""
    if kw.pop("grey", False):
        subject = subject.replace(ON_WHITE, ON_GREY).replace("white space", "empty space")
    return layer(key, kind, subject, size, height, "clean", **kw)


ON_WHITE = "on a plain flat white background"
ON_GREY = "on a plain flat medium grey background"
CLEAN_STRIP = (
    "running from the left edge of the frame to the right edge, standing on one straight "
    f"baseline {ON_WHITE}."
)
SOLID = " Every building and tree is solid and drawn as clearly as the rest."
GROUND = f"running from the left edge of the frame to the right edge, {ON_GREY}."
HEADROOM = 0.45
"""The share of a far layer left clear above its hills, so the city and the Apex rise over them:
the client draws it 5.75 m tall from 7.5 m up, and the view's top is 15.6 m up."""
SKY = village_layer(
    "sky",
    "paper",
    "A plain sky backdrop: a smooth gradient from pale warm haze near the bottom to clear soft "
    "blue at the top, with five soft clouds. Only sky: no ground, no buildings, no towers, no "
    "trees, no birds, no drones.",
    (1536, 768),
    12.0,
)
CITY = village_layer(
    "city",
    "layer",
    "A long strip of a distant modern city skyline seen from far away: a dense row of glass "
    "office towers and apartment blocks of many different heights and widths, in pale misty "
    "blue-grey and soft teal, every one with a plain flat roof, a few construction cranes, and "
    f"no tower much taller than the rest, all standing on one straight baseline, {ON_WHITE} "
    "with white space above it. No spires, no masts, no antennas, no domes, no people, no signs.",
    (1536, 640),
    5.0,
)
LAYERS = [
    SKY,
    CITY,
    village_layer(
        "far-hills",
        "layer",
        "A long strip of distant low, gently rolling hills in pale sage green and misty blue-grey, "
        f"with a few small round trees on the ridges, lying {ON_WHITE} with white space above and "
        "below it. Only hills and trees: no buildings, no towers.",
        (1536, 512),
        5.0,
        headroom=HEADROOM,
    ),
    village_layer(
        "far-river",
        "layer",
        "A long strip of low misty blue-grey hills on the far bank of a wide river, with a few "
        f"small palm trees and low houses along the shore, lying {ON_WHITE} with white space "
        "above and below it. No towers, no tall buildings.",
        (1536, 512),
        4.0,
        headroom=HEADROOM,
    ),
    village_layer(
        "mid-shophouses",
        "strip",
        "A long row of distant mid-rise apartment blocks and offices of pale concrete and glass, "
        "with rooftop gardens, solar panels and air-conditioning units, and the round crowns of "
        "banyan trees between them, all standing on one straight baseline, "
        f"{ON_WHITE} with white space above them.{SOLID} No people, no signs.",
        (1536, 640),
        9.0,
        grey=True,
    ),
    village_layer(
        "mid-homes",
        "strip",
        "A long row of distant small two-storey modern village homes with flat roofs, solar "
        "panels and little gardens, with kapok trees in red flower and leafy lychee trees between "
        "them, in soft pink, cream, sage and terracotta, all standing on one straight baseline, "
        f"{ON_WHITE} with white space above them.{SOLID} No people, no animals.",
        (1536, 640),
        8.0,
        grey=True,
    ),
    village_layer(
        "mid-rooftops",
        "strip",
        "A long row of distant village rooftops, flat roofs and roofs of terracotta and dark "
        "charcoal slate, over houses with warm-coloured walls and brightly painted doors, with "
        "water tanks, solar panels and air-conditioning units, and the broad crowns of big banyan "
        "trees rising between them, all standing on one straight baseline, "
        f"{ON_WHITE} with white space above them.{SOLID} No people, no towers.",
        (1536, 640),
        9.0,
    ),
    village_layer(
        "mid-riverbank",
        "strip",
        "A long row of distant palm trees, banyan trees and low reed beds on a riverbank, in "
        "greens and sand, all standing on one straight baseline of sandy bank, "
        f"{ON_WHITE} with white space above them.{SOLID} No water, no people, no boats.",
        (1536, 640),
        7.0,
    ),
    village_layer(
        "near-walls",
        "strip",
        "A long low run of pale concrete planters, seen straight from the front, full of lush "
        "tropical plants, clipped hedges, young palms and magenta bougainvillea, with a slim "
        f"modern railing behind them, {CLEAN_STRIP}",
        (1536, 512),
        2.2,
    ),
    village_layer(
        "near-gardens",
        "strip",
        "A long run of small front gardens seen straight from the front: low slatted timber "
        "fences painted cream and sage, clipped hedges, flowering shrubs and small lychee trees, "
        f"{CLEAN_STRIP}",
        (1536, 512),
        2.4,
    ),
    village_layer(
        "near-hedges",
        "strip",
        "A long row of clipped green hedges in low pale concrete planters, with young palm trees "
        f"and flowering hibiscus, seen straight from the front, {CLEAN_STRIP}",
        (1536, 512),
        2.6,
    ),
    village_layer(
        "ground-street",
        "ground",
        "A long horizontal strip of city street seen exactly from the side: a pale grey paved "
        "footpath with a yellow strip of tactile paving on top, a granite kerb edge, and a band "
        f"of dark grey asphalt road with a green painted cycle lane below, {GROUND}",
        (1536, 384),
        2.6,
        cut=("banded",),
        surface=0.06,
    ),
    village_layer(
        "ground-plaza",
        "ground",
        "A long horizontal strip of a modern plaza's paving seen exactly from the side: large "
        "pale granite slabs on top with a thin inset line of warm lights, a low step edge, and a "
        f"band of pale grey stone below, {GROUND}",
        (1536, 384),
        2.6,
        cut=("banded",),
        surface=0.08,
    ),
    village_layer(
        "ground-park",
        "ground",
        "A long horizontal strip of park seen exactly from the side: a band of soft green grass "
        "with tiny daisies on top, a pale paved path edge, and a band of calm blue lake water "
        f"below with round lotus pads and pink lotus flowers, {GROUND}",
        (1536, 384),
        2.6,
        cut=("banded",),
        surface=0.03,
    ),
    village_layer(
        "ground-promenade",
        "ground",
        "A long horizontal strip of a riverside promenade seen exactly from the side: a pale "
        "stone walkway on top, a low stone river wall, and a band of calm blue-green river water "
        f"below with a few round lotus pads, {GROUND}",
        (1536, 384),
        2.6,
        cut=("banded",),
        surface=0.07,
    ),
    village_layer(
        "front-plants",
        "strip",
        "A long low row of big leafy tropical plants, ferns and banana leaves in dark green, "
        f"{CLEAN_STRIP} No flowers, no pots, no fence, no ground.",
        (1536, 512),
        2.0,
        grey=True,
    ),
    village_layer(
        "front-reeds",
        "strip",
        "A long low row of tall reeds, cattails and lotus flowers on long stems in dark green "
        f"and pink, {CLEAN_STRIP} No water, no ground.",
        (1536, 512),
        2.0,
        grey=True,
    ),
]
NO_STREET = " No people, no trains, no trees, no sky, no buildings."
NEAR_WALL = 4.6
"""Metres: tall enough to hide the foot of the mid layer, which the client puts 2.75 m up."""
TUNNEL_LAYERS = [
    tunnel_layer(
        "metro-vault",
        "paper",
        "A plain dark backdrop of the inside of a huge old underground metro hall: a curved "
        "vault of dim cream tiles between heavy dark steel ribs, fading into deep shadow towards "
        "the top, with a few hanging cables. Only the vault: no floor, no platform." + NO_STREET,
        (1536, 768),
        12.0,
    ),
    tunnel_layer(
        "far-metro",
        "layer",
        "A long strip of the upper vault of an old metro hall seen from inside: a row of big "
        "round tiled arches between dark steel ribs, with cable trays and dead lamps hanging "
        "from them, in dim cream, grey and teal, lying on a plain flat white background with "
        "white space above and below it." + NO_STREET,
        (1536, 512),
        5.0,
    ),
    tunnel_layer(
        "mid-metro",
        "strip",
        "A long run of the tiled back wall of an old metro station seen straight from the front: "
        "a wall of dim cream tiles with a dark teal band, a row of tall round arches, empty "
        "frames where posters once hung, old pipes and dead lamps, all standing on one straight "
        "baseline, on a plain flat white background with white space above it. No signs, no "
        "tracks, no rails." + NO_STREET,
        (1536, 640),
        9.0,
    ),
    tunnel_layer(
        "near-metro",
        "ground",
        "A long run of the lower back wall of an old metro platform seen straight from the front: "
        "a solid wall of grimy cream tiles from the ground up to a dark teal band along its "
        "straight top edge, with old pipes and cable trays running along it, and sacks, crates "
        "and tarps piled at its foot, running from the left edge of the frame to the right edge, "
        "on a plain flat white background with white space above it. Only the wall, pipes and "
        "junk." + NO_STREET,
        (1536, 768),
        NEAR_WALL,
        cut=("above",),
    ),
    tunnel_layer(
        "ground-metro",
        "ground",
        "A long horizontal strip of an old metro platform's floor seen exactly from the side: "
        "worn grey concrete paving on top with a faded yellow safety line along it, and a thick "
        "band of dark grimy concrete below, running from the left edge of the frame to the right "
        "edge, on a plain white background.",
        (1536, 384),
        2.6,
    ),
    tunnel_layer(
        "front-metro",
        "strip",
        "A long low row of old metro rails on dark wooden sleepers with gravel, rubble and loose "
        "cables, seen straight from the front, "
        + STRIP
        + " Only rails, rubble and cables."
        + NO_STREET,
        (1536, 512),
        2.0,
    ),
]
SEWER_LAYERS = [
    sewer_layer(
        "sewer-vault",
        "paper",
        "A plain dark backdrop of the inside of a huge old brick sewer: tall curved vaults of "
        "dark red-brown brick, wet, stained and streaked with slime, fading into deep shadow "
        "towards the top, with a few dripping pipes. Only the vault: no floor, no walkway."
        + NO_STREET,
        (1536, 768),
        12.0,
    ),
    sewer_layer(
        "far-sewer",
        "layer",
        "A long strip of the far inside of a huge old brick sewer: a row of big round brick "
        "arches opening onto pitch-dark tunnels, with old pipes and hanging chains, in murky "
        "brown, grey and green, lying on a plain flat white background with white space above "
        "and below it." + NO_STREET,
        (1536, 512),
        5.0,
    ),
    sewer_layer(
        "mid-sewer",
        "strip",
        "A long run of the brick back wall of an old sewer seen straight from the front: filthy "
        "red-brown brick streaked with slime and rust, a row of tall round brick arches with dark "
        "tunnel mouths, and big rusty pipes and valves running along it, all standing on one "
        "straight baseline, on a plain flat white background with white space above it. No "
        "signs." + NO_STREET,
        (1536, 640),
        9.0,
    ),
    sewer_layer(
        "near-sewer",
        "ground",
        "A long run of the lower brick wall of an old sewer seen straight from the front: a solid "
        "wall of filthy damp brick from the ground up to a band of green slime along its straight "
        "top edge, with drain grates, small pipes dribbling dirty water and rusty brackets along "
        "it, and rubbish heaped at its foot, running from the left edge of the frame to the right "
        "edge, on a plain flat white background with white space above it. Only the wall, pipes "
        "and rubbish." + NO_STREET,
        (1536, 768),
        NEAR_WALL,
        cut=("above",),
    ),
    sewer_layer(
        "ground-sewer",
        "ground",
        "A long horizontal strip of an old sewer's walkway seen exactly from the side: wet "
        "cracked concrete on top with a slimy green edge, and a thick band of dark stained brick "
        "below, running from the left edge of the frame to the right edge, on a plain white "
        "background.",
        (1536, 384),
        2.6,
    ),
    sewer_layer(
        "front-sewer",
        "strip",
        "A long low channel of murky green-brown sewage water in a brick gutter, seen straight "
        "from the front, with floating rubbish, scum and a broken iron grate, "
        + STRIP
        + " Only water, brick, rubbish and grates."
        + NO_STREET,
        (1536, 512),
        2.0,
    ),
]
SLAB = Painting(
    "papers/slab",
    "paper",
    in_style(
        CLEAN_LEAD + "A long horizontal band of smooth mid-grey concrete, the cut edge of a floor "
        "slab seen exactly from the side, with a scratchy dark outline along its top and bottom "
        "edges, running from the left edge of the frame to the right edge across the middle of "
        "the frame, on a plain flat white background. Nothing else.",
        "clean",
    ),
    (1024, 256),
    (CLEAN_ROOMS,),
    0.3,
)
"""Painted as a band and cut to it (`band_rows`), since a texture prompt paints it on grey."""


class Moulding(NamedTuple):
    """A frame's moulding on each side, in its piece's own px."""

    left: int
    right: int
    top: int
    bottom: int


@dataclass(frozen=True)
class Item:
    """A piece of furniture, a street prop or a platform piece, by the name the maps use."""

    subject: str
    """What it is, with its materials and colours named."""
    height: float
    size: tuple[int, int] = (640, 640)
    side: bool = False
    grey: bool = False
    """Painted on grey, since white on white defeats the cut-out."""
    stretch: bool = False
    """A run, like a counter, drawn as wide as its cells by repeating its middle."""
    cut: tuple[str, ...] = ()
    """What else to cut away: a kind of painted shadow from `cutout.SHADOWS`, `gaps` of backdrop
    showing through the object, and for a sketched piece `outline`, all that's off its sketch."""
    reseed: int = 0
    ref: str = CLEAN_ROOMS
    sketch: str | None = None
    folder: str = "furniture"
    variants: dict[str, str] = field(default_factory=dict)
    """Colour variants: name, and what's recoloured to what."""
    broken: str | None = None
    """For a machine you repair: what's wrong with it, as an edit of the working picture."""
    style: Style = "clean"
    seat: float | None = None
    """Metres from its foot up to the top of its seat at the front edge."""
    bed: float | None = None
    """Metres from its foot up to the top of its mattress at the front edge."""
    light: float | None = None
    """Metres from its foot up to the middle of its lamp's head."""
    moulding: Moulding | None = None


def clean(
    subject: str,
    height: float,
    size: tuple[int, int] = (640, 640),
    ref: str = CLEAN_ROOMS,
    **kw,
) -> Item:
    """A village piece in the comic style."""
    return Item(subject, height, size, ref=ref, style="clean", **kw)


FURNITURE: dict[str, Item] = {
    "kitchen": clean(
        "a fitted modern kitchen run of handleless matt white base cupboards under a light oak "
        "worktop, with a small steel sink and a tap at its very left end, a black hob with a "
        "small red pan over an oven at its very right end, and plain cupboard doors between "
        "them. No wall cupboards, nothing above the worktop",
        0.95,
        sketch="kitchen",
        stretch=True,
    ),
    "sofa": clean(
        "a low modern three-seat sofa upholstered in soft sage-green fabric with slim black metal "
        "legs",
        0.85,
        (768, 512),
        variants={
            "coral": "Recolour the sofa's fabric upholstery to coral red.",
            "mustard": "Recolour the sofa's fabric upholstery to mustard yellow.",
            "plum": "Recolour the sofa's fabric upholstery to dark plum purple.",
        },
    ),
    "bed": clean(
        "a low modern double bed seen from the side, a pale oak frame with a tall padded grey "
        "headboard on the left, a white pillow, a white duvet and a mustard-yellow throw over "
        "its foot",
        1.05,
        sketch="bed",
        variants={"blue": "Recolour the mustard-yellow throw to soft blue."},
        bed=0.492,
    ),
    "wardrobe": clean(
        "a tall modern wardrobe with two flat handleless doors of pale oak",
        2.0,
        (512, 768),
        grey=True,
    ),
    "bookshelf": clean(
        "a tall open shelf unit of black metal and pale wood, with books with colourful spines, a "
        "small plant and a little speaker on it",
        1.9,
        (512, 896),
    ),
    "table": clean(
        "a small square dining table of pale oak on two legs, with a moulded coral-red chair at "
        "each end, the chairs facing the table",
        0.95,
        sketch="table",
        cut=("shadows", "gaps"),
        seat=0.492,
    ),
    "plant": clean("a big leafy monstera plant in a white ceramic pot", 1.1, (512, 640), grey=True),
    "counter": clean(
        "a modern cafe counter with a front of pale oak slats and a white stone top, with a "
        "small card reader and a glass pastry case with cakes and croissants on top",
        1.25,
        (1008, 448),
        grey=True,
        stretch=True,
    ),
    "espresso_machine": clean(
        "a sleek stainless steel espresso machine with two group heads and little cups on top, "
        "standing on a low cupboard of pale oak",
        1.55,
        (512, 768),
        grey=True,
    ),
    "grinder": clean(
        "a matt black coffee grinder with a glass hopper full of beans, standing on a low "
        "cupboard of pale oak with sacks of coffee beans beside it",
        1.4,
        (512, 768),
    ),
    "menu_board": clean(
        "a wide flat black chalkboard in a slim pale oak frame, hung on a wall, with simple "
        "chalk drawings of a coffee cup, a croissant and leaves and no words at all",
        1.0,
        (1104, 416),
    ),
    "bar_counter": clean(
        "a long bar counter seen from the customers' side, three times as wide as it is tall: "
        "one long, thin, flat slab of white stone along the top, a front of vertical pale oak "
        "slats and a slim black foot rail along the bottom",
        1.1,
        (1024, 384),
        grey=True,
        stretch=True,
    ),
    "cafe_table": clean(
        "a small round cafe table with a white top and a slim black metal pedestal, with a "
        "moulded plywood chair at each side facing the table",
        0.95,
        sketch="cafe_table",
        cut=("shadows", "gaps"),
        seat=0.5,
    ),
    "stove": clean(
        "a big noodle stove of brushed steel with two gas burners, two tall stock pots and a "
        "wok, under a steel extractor hood",
        2.0,
        (768, 768),
        grey=True,
    ),
    "kitchen_counter": clean(
        "a small steel prep counter with a chopping board, a cleaver and bowls of spring onions "
        "and chillies",
        1.0,
        (512, 512),
        grey=True,
    ),
    "noodle_counter": clean(
        "a long noodle bar counter of red-lacquered wood with a pale wood ledge, bowls, "
        "chopsticks in a pot and a bottle of chilli oil on top",
        1.05,
        (1376, 336),
        stretch=True,
    ),
    "stool": clean(
        "a knee-high modern bar stool with a thick round padded seat of red fabric, a slim "
        "black steel stem and a ring footrest",
        0.7,
        sketch="stool",
        variants={"teal": "Recolour the stool's seat to teal."},
        seat=0.567,
    ),
    "noodle_table": clean(
        "a small square wooden table with a red paper lantern on a cord above it and a "
        "red-topped wooden stool at each side",
        1.9,
        sketch="noodle_table",
        cut=("deep shadows", "gaps"),
        seat=0.542,
    ),
    "laser_cutter": clean(
        "a big modern laser cutter, a wide boxy cabinet of pale grey metal with a tinted orange "
        "lid and a small blank control panel",
        1.1,
        (768, 640),
        grey=True,
    ),
    "printer_3d": clean(
        "a 3D printer: an open frame of black metal on a desk-high stand, with a spool of bright "
        "orange filament, one tiny round green LED lamp on its frame and a small half-printed "
        "orange boat on its bed",
        1.5,
        (512, 768),
        cut=("gaps",),
        broken=(
            "Make the 3D printer broken and dead: no spool and no boat, an empty bed, the print "
            "head of dark steel hanging down loose on its wires, a snapped drive belt dangling "
            "from it and the green lamp dark grey. The frame, the bed and the stand stay solid "
            "black metal."
        ),
    ),
    "recycler": clean(
        "a plastic recycling machine: a tall boxy cabinet of teal-painted metal with a wide steel "
        "funnel on top for scrap, a small round window in its front showing shredder blades, one "
        "tiny round green LED lamp, and a short chute at the bottom spilling bright orange "
        "plastic pellets into a little steel tray",
        1.7,
        (512, 768),
        broken=(
            "Make the recycling machine broken and dead: the round window smashed open with "
            "loose coloured wires spilling out, no pellets and an empty tray. The machine has "
            "no power: nothing on it is lit, and the bright green lamp at the top right of the "
            "cabinet is now plain black, the same as the lamp beside it. Only one funnel, as it "
            "is."
        ),
    ),
    "clean_lockers": clean(
        "one steel locker cabinet painted deep sage green, a single tall unit with two narrow "
        "doors side by side and no gap between them, each door with a small row of air vents "
        "near its top, a small silver handle and a blank white label slot, clean and new",
        1.9,
        (512, 768),
        grey=True,
        cut=("shadows",),
    ),
    "loom": clean(
        "a wooden floor loom of pale wood with colourful warp threads in rainbow stripes and a "
        "half-woven cloth",
        1.6,
        (768, 768),
    ),
    "sewing_machine": clean(
        "a white and mint-green sewing machine on a small pale oak table with slim legs",
        1.1,
        (512, 768),
        grey=True,
    ),
    "workbench": clean(
        "a long sturdy workbench with a thick pale oak top on black steel legs, with a vice, a "
        "few hand tools and a small toolbox on top, and a shelf underneath",
        0.95,
        (1280, 352),
        stretch=True,
    ),
    "rope_bridge": clean(
        "a rope bridge: a deck of wooden planks hung from two rope handrails, with a sturdy "
        "wooden post at each end",
        1.25,
        ref=CLEAN_STREET,
        sketch="rope_bridge",
        folder="platforms",
        stretch=True,
        cut=("outline", "shadows", "gaps"),
    ),
    "pegboard": clean(
        "a wide pale wooden pegboard panel hung on a wall, with hammers, saws, pliers and "
        "screwdrivers hanging on it",
        1.0,
        (1264, 352),
        stretch=True,
    ),
    "shelf": clean(
        "a long wall shelf unit, three times as wide as it is tall: three long open shelves of "
        "pale wood on slim black uprights, holding cardboard boxes, glass jars of screws, spools "
        "of thread and rolls of fabric. No furniture, no people, no rooms",
        1.6,
        (1152, 384),
    ),
    "plinth": clean(
        "a tall white plinth with a small bronze sculpture of a smooth round pebble on top",
        1.4,
        (512, 896),
        grey=True,
    ),
    "bench": clean(
        "a modern street bench with a backrest, of pale wooden slats on slim dark grey steel "
        "legs, seen straight from the front",
        0.9,
        ref=CLEAN_STREET,
        sketch="bench",
        seat=0.408,
    ),
    "news_terminal": clean(
        "a public smart kiosk: a slim upright stand of teal-painted metal with a big blank "
        "glowing screen and a small solar panel on top",
        2.2,
        (512, 1024),
        ref=CLEAN_STREET,
        grey=True,
        cut=("tinted shadows",),
    ),
    "fountain": clean(
        "a round modern town fountain of pale granite, a little narrower than it is tall, with "
        "two tiers and water splashing into its basin",
        2.2,
        (640, 768),
        ref=CLEAN_STREET,
        grey=True,
    ),
    "lamp": clean(
        "a slim modern street lamp: a tall dark grey steel pole topped by one round frosted "
        "white glass lamp head, centred on the pole",
        3.6,
        (512, 1024),
        ref=CLEAN_STREET,
        grey=True,
        light=3.31,
    ),
    "tree": clean(
        "a leafy shade tree with a sturdy trunk and a broad round crown of big leaves",
        6.0,
        (768, 1024),
        ref=CLEAN_STREET,
    ),
    "bush": clean(
        "a low mound of hibiscus leaves and pink flowers growing straight from the ground, "
        "twice as wide as it is tall, like a little hedge",
        1.0,
        (640, 512),
        ref=CLEAN_STREET,
    ),
    "lift": clean(
        "a small modern lift car: a cage of slim black steel bars with a brushed steel trim, a "
        "pale oak floor and a little lamp on top",
        2.9,
        sketch="lift",
        folder="platforms",
    ),
    "metro_entrance": Item(
        "a small narrow modern metro station entrance, twice as tall as it is wide, seen straight "
        "from the front: a slim curved canopy of glass on dark grey steel posts over a doorway "
        "where a stairway goes down, with a small round glowing sign showing a simple train "
        "pictogram on top of the canopy",
        2.3,
        (512, 896),
        ref=CLEAN_STREET,
        style="clean",
    ),
    "train_carriage": Item(
        "an abandoned old metro train carriage seen exactly from the side: a long boxy body of "
        "faded cream painted steel with a teal stripe, a row of dark windows, two pairs of "
        "closed sliding doors, a flat grey roof with low vents, and its bogies and wheels",
        3.36,
        ref=TUNNELS,
        sketch="train_carriage",
        cut=("outline",),
        style="cartoon",
    ),
    "catwalk": Item(
        "a steel maintenance catwalk seen exactly from the side: a deck of steel grating on a "
        "riveted plate girder, a thin steel handrail on posts above it, and an angled steel "
        "strut under each end",
        2.16,
        ref=TUNNELS,
        sketch="catwalk",
        folder="platforms",
        stretch=True,
        cut=("outline",),
        style="cartoon",
    ),
    "metro_steps": Item(
        "a flight of old metro station steps seen exactly from the side, rising to the left: "
        "worn concrete treads with dark steel nosings, over a solid side wall of grimy cream "
        "tiles",
        3.36,
        ref=TUNNELS,
        sketch="metro_steps",
        cut=("outline",),
        style="cartoon",
    ),
    "freight_lift": Item(
        "an old dead freight lift seen from the front: its car behind a folding steel grille "
        "gate, in a riveted steel frame, under a winding wheel in a steel housing",
        4.4,
        ref=TUNNELS,
        sketch="freight_lift",
        cut=("outline",),
        style="cartoon",
    ),
    "scrap_stall": Item(
        "a scrap trader's stall: a battered trestle table piled with salvaged electronics, coils "
        "of copper wire, gears and old circuit boards, under a patched canvas awning on two "
        "poles, with a crate of parts beside it",
        2.2,
        (896, 768),
        ref=TUNNEL_ROOMS,
        style="cartoon",
    ),
    "turnstile": Item(
        "a pair of old metro turnstiles side by side: two waist-high posts of scuffed stainless "
        "steel, each with three rotating metal bars sticking out to one side and a little round "
        "card reader on top, dead and dusty",
        1.1,
        (768, 512),
        ref=TUNNEL_ROOMS,
        style="cartoon",
    ),
    "ticket_machine": Item(
        "an old metro ticket machine: a tall cabinet of scuffed steel and faded teal panels with "
        "a dark dead screen, a coin slot and a little ticket tray",
        1.9,
        (512, 896),
        ref=TUNNEL_ROOMS,
        style="cartoon",
    ),
    "metro_bench": Item(
        "an old metro platform bench seen straight from the front: a row of three moulded orange "
        "plastic seats on a steel frame, scuffed and dusty",
        0.9,
        (896, 512),
        ref=TUNNEL_ROOMS,
        style="cartoon",
    ),
    "dead_terminal": Item(
        "an old metro control console: a waist-high cabinet of grimy grey steel with a dark "
        "cracked screen on top, a row of unlit buttons and a small round data port, dead",
        1.5,
        (512, 768),
        ref=TUNNEL_ROOMS,
        style="cartoon",
    ),
    "breaker_box": Item(
        "a maintenance power point: a grey steel breaker box on a short steel post, with a "
        "yellow and black hazard stripe, a big power socket, a coiled cable and a small "
        "glowing green light",
        1.4,
        (512, 768),
        ref=TUNNEL_ROOMS,
        style="cartoon",
    ),
    "crates": Item(
        "a stack of two battered wooden crates", 1.0, (640, 640), ref=TUNNELS, style="cartoon"
    ),
    "rubble": Item(
        "a low heap of broken concrete chunks, bricks and twisted rusty rebar, twice as wide as "
        "it is tall",
        0.7,
        (768, 448),
        ref=TUNNELS,
        style="cartoon",
    ),
    "bedroll": Item(
        "an abandoned sleeping spot on the floor seen from the side: a rolled-out stained "
        "sleeping bag on flattened cardboard, with a tin mug and a candle stub",
        0.45,
        (768, 384),
        side=True,
        ref=TUNNEL_ROOMS,
        style="cartoon",
    ),
    "pipes": Item(
        "a long run of three old pipes one above the other along a wall, of rusty iron and "
        "faded green-painted steel, held by plain brackets, with no valves",
        0.8,
        (1280, 352),
        stretch=True,
        ref=TUNNELS,
        style="cartoon",
    ),
    "sewer_walkway": Item(
        "a narrow old sewer walkway seen exactly from the side: a slab of stained concrete on "
        "rusty iron brackets with slime dripping from its edge, and a bent rusty iron handrail on "
        "posts above it",
        2.16,
        ref=TUNNELS,
        sketch="sewer_walkway",
        folder="platforms",
        stretch=True,
        cut=("outline",),
        style="grimy",
    ),
    "sewer_pipe": Item(
        "a huge old cast-iron sewer pipe lying along, seen exactly from the side, rusty and "
        "banded at its joints, with green slime along its underside",
        1.16,
        ref=TUNNELS,
        sketch="sewer_pipe",
        folder="platforms",
        stretch=True,
        cut=("outline",),
        style="grimy",
    ),
    "sewer_pier": Item(
        "a tall narrow pier of old dark red brick between two sewer rooms, filthy and streaked "
        "with slime and rust, with a worn stone cap at its top and its foot",
        4.46,
        ref=TUNNELS,
        sketch="sewer_pier",
        folder="platforms",
        cut=("outline",),
        style="grimy",
    ),
    "sewer_vault": Item(
        "a long band of the low brick vault of an old sewer seen exactly from the side, wet and "
        "stained, with a dark slimy underside along its bottom edge",
        2.3,
        ref=TUNNELS,
        sketch="sewer_vault",
        folder="platforms",
        stretch=True,
        cut=("outline",),
        style="grimy",
    ),
    "sewer_weir": Item(
        "a squat old brick weir across a sewer, seen exactly from the side, with a rusty iron "
        "sluice gate and its wheel set in its face and slime along its foot, standing on the "
        "concrete edge of a walkway over a brick channel wall",
        5.56,
        ref=TUNNELS,
        sketch="sewer_weir",
        folder="platforms",
        cut=("outline",),
        style="grimy",
    ),
    "maintenance_hatch": Item(
        "a heavy round steel maintenance hatch set in a patch of filthy brick wall, with big "
        "bolts around its rim and a locking wheel in its middle, and beside it a small steel "
        "panel with a dim green light and a round data port",
        2.0,
        (768, 768),
        ref=TUNNELS,
        style="grimy",
    ),
    "sewer_outfall": Item(
        "the mouth of a big round old outflow pipe sticking out of a patch of filthy brick wall, "
        "with a trickle of murky green water and slime pouring from it",
        1.6,
        (768, 768),
        ref=TUNNELS,
        style="grimy",
    ),
    "sewer_lamp": Item(
        "a caged bulkhead work lamp on a short rusty iron wall bracket, its bulb glowing a weak "
        "warm yellow",
        0.6,
        (512, 512),
        ref=TUNNELS,
        style="grimy",
    ),
    "tunnel_arch": Item(
        "a tall archway at the mouth of an old metro tunnel, seen straight from the front: two "
        "square pillars of grimy cream tiles joined by a round concrete arch, with cables and a "
        "dead lamp on it, and nothing in the opening",
        8.8,
        (512, 1280),
        ref=TUNNELS,
        cut=("gaps",),
        style="cartoon",
    ),
    "shipping_container": Item(
        "an old steel shipping container seen exactly from the side: corrugated walls of faded "
        "blue paint with rust patches and streaks, a flat roof, and its double doors at one end "
        "with long vertical locking bars",
        3.36,
        ref=TUNNELS,
        sketch="shipping_container",
        cut=("outline",),
        reseed=1,
        variants={
            "rust": "Recolour the container's blue paint to faded rust red.",
            "mustard": "Recolour the container's blue paint to faded mustard yellow.",
        },
        style="cartoon",
    ),
    "switchboard": Item(
        "an old railway signal switchboard seen straight from the front: a tall cabinet of "
        "grimy green-grey steel, its front a panel of rows of dead toggle switches, little round "
        "dials and dark indicator lamps, with bundles of cut copper wire hanging out of an open "
        "access hatch at the bottom",
        2.0,
        (640, 640),
        ref=TUNNEL_ROOMS,
        style="cartoon",
    ),
    "lockers": Item(
        "a row of three tall battered steel workers' lockers, dented and scuffed grey-green "
        "paint, one door hanging open, with a hard hat on top",
        1.9,
        (640, 640),
        ref=TUNNEL_ROOMS,
        style="cartoon",
    ),
    "bulkhead": Item(
        "a tall wall of grimy cream tiles seen straight from the front, with a heavy riveted "
        "steel door at its foot, jammed shut and rusted, with yellow and black hazard stripes "
        "and a big locking wheel, and a dark vent grille high up, standing on a strip of grey "
        "concrete floor edge",
        10.0,
        ref=TUNNELS,
        sketch="bulkhead",
        cut=("outline",),
        style="cartoon",
    ),
}
EXTRAS: dict[str, Item] = {
    "muzzle_flash": clean(
        "a comic-book gunshot flash seen from the side: one jagged spiky star burst of bright "
        "yellow and orange flame with a pale yellow-white middle and sharp points, nothing else, "
        "floating in mid-air",
        0.42,
        grey=True,
    ),
    "armchair": clean(
        "a modern armchair upholstered in mustard-yellow fabric with slim black metal legs",
        0.95,
        variants={
            "sage": "Recolour the armchair's upholstery to sage green.",
            "teal": "Recolour the armchair's upholstery to deep teal.",
        },
    ),
    "floor_lamp": clean(
        "a modern floor lamp, switched off, with a thin black stand and a round white fabric shade",
        1.6,
        (512, 1024),
        grey=True,
    ),
    "bedside_table": clean(
        "a small pale oak bedside table with a little lamp with a round pink shade on it",
        0.95,
        (512, 768),
        grey=True,
    ),
    "fridge": clean("a rounded retro fridge in pale mint", 1.7, sketch="fridge"),
    "bathtub": clean(
        "a white freestanding bathtub with brass feet and taps", 0.75, sketch="bathtub"
    ),
    "washbasin": clean(
        "a white pedestal washbasin with a round mirror in a pale wooden frame above it",
        1.8,
        sketch="washbasin",
    ),
    "picture_frame": clean(
        "an empty picture frame of pale oak around a plain cream canvas, hung on a wall, seen "
        "straight from the front",
        0.9,
        sketch="picture_frame",
        moulding=Moulding(14, 15, 13, 14),
    ),
    "banyan_tree": clean(
        "a large banyan tree with a thick trunk, spreading branches, a broad crown of big leaves "
        "and hanging aerial roots",
        11.0,
        (768, 1024),
        ref=CLEAN_STREET,
    ),
    "kapok_tree": clean(
        "a tall kapok tree with a straight pale trunk, layered branches and clusters of red "
        "flowers",
        10.0,
        (768, 1024),
        ref=CLEAN_STREET,
    ),
    "palm_tree": clean(
        "a slender coconut palm tree with a gently curving trunk",
        7.0,
        (512, 1024),
        ref=CLEAN_STREET,
    ),
    "bicycle": clean(
        "a modern city bicycle painted pale blue with a basket on the front, its wheels thin "
        "rims with fine wire spokes and open gaps between them",
        1.0,
        (896, 576),
        side=True,
        grey=True,
        ref=CLEAN_STREET,
        cut=("gaps",),
    ),
    "bin": clean(
        "a round litter bin of dark green metal with a domed lid",
        0.95,
        (384, 640),
        ref=CLEAN_STREET,
    ),
}
PLATFORMS: dict[str, Item] = {
    "stairs": clean(
        "a straight modern staircase of pale oak treads on a black steel frame, rising one "
        "storey to the right, with a thin black metal handrail",
        5.3,
        sketch="stairs",
        folder="platforms",
    ),
    "ladder": clean(
        "a tall wooden ladder", 3.6, ref=CLEAN_STREET, sketch="ladder", folder="platforms"
    ),
    "steps": clean(
        "a short flight of warm grey stone steps rising to the right, each tread with a darker "
        "edge",
        2.2,
        ref=CLEAN_STREET,
        sketch="steps",
        folder="platforms",
        cut=("outline",),
    ),
    "ledge": clean(
        "a long flat wooden walkway of planks on two wooden brackets",
        0.6,
        ref=CLEAN_STREET,
        sketch="ledge",
        folder="platforms",
        cut=("outline", "shadows", "gaps"),
    ),
    "lift_shaft": clean(
        "one storey of an open lift shaft frame of slim black steel posts and diagonal braces "
        "with a cable down the middle, nothing between the bars but the background",
        4.4,
        sketch="lift_shaft",
        folder="platforms",
        cut=("outline",),
    ),
    "window": clean(
        "a modern window with a slim black metal frame, two panes and a pale roller blind half "
        "down, seen from inside a room",
        1.3,
        sketch="window",
        folder="platforms",
    ),
    "door": clean(
        "a plain modern interior door of pale oak in a slim white frame, with a slim black handle",
        2.1,
        (512, 896),
        grey=True,
        folder="platforms",
    ),
}
PLATFORMS_BELOW: dict[str, dict[str, Item]] = {
    "metro": {
        "ladder": Item(
            "a tall old maintenance ladder of dark gunmetal-grey painted steel: two flat rails and "
            "round rungs",
            3.6,
            ref=TUNNELS,
            sketch="metro_ladder",
            folder="platforms",
            style="cartoon",
        ),
        "steps": Item(
            "a short flight of old metro station steps rising to the right: worn concrete treads "
            "with dark steel nosings, over a solid side wall of grimy cream tiles",
            2.2,
            ref=TUNNELS,
            sketch="metro_flight",
            folder="platforms",
            cut=("outline",),
            style="cartoon",
        ),
        "ledge": Item(
            "a long flat steel walkway: a deck of steel grating on two angled steel brackets",
            0.6,
            ref=TUNNELS,
            sketch="metro_ledge",
            folder="platforms",
            cut=("outline",),
            style="cartoon",
        ),
    },
    "sewers": {
        "ladder": Item(
            "a tall old ladder of two rusty iron rails and round rusty iron rungs",
            3.6,
            ref=TUNNELS,
            sketch="sewer_ladder",
            folder="platforms",
            style="grimy",
        ),
        "ledge": Item(
            "a long narrow ledge of stained concrete on two rusty iron brackets, with slime "
            "dripping from its edge",
            0.6,
            ref=TUNNELS,
            sketch="sewer_ledge",
            folder="platforms",
            cut=("outline",),
            style="grimy",
        ),
    },
}
"""The tunnels' own ladders, steps and ledges, by street, in place of the village's
`PLATFORMS`. The sewers have no steps."""


def below() -> dict[str, Item]:
    """`PLATFORMS_BELOW` by name: `<street>-<platform>`."""
    return {f"{s}-{n}": spec for s, pieces in PLATFORMS_BELOW.items() for n, spec in pieces.items()}


def item(name: str, spec: Item, layout: Layout) -> Painting:
    key = f"{spec.folder}/{name}"
    words = WORDS[spec.style]
    if spec.sketch:
        sketch = SKETCHES[spec.sketch]()
        back = "medium grey" if sketch.getpixel((0, 0)) == GREY else "white"
        prompt = in_style(words.redraw.format(subject=spec.subject, back=back), spec.style)
        refs = (spec.ref,)
        size, height = sketch.size, spec.height
        return Painting(
            key,
            "sprite",
            prompt,
            size,
            refs,
            height,
            reseed=spec.reseed,
            sketch=spec.sketch,
            cut=spec.cut,
        )
    size = spec.size
    backdrop_text = SIDE_SPRITE if spec.side else SPRITE
    if spec.grey:
        backdrop_text = backdrop_text.replace("plain flat white", "plain flat medium grey")
    prompt = in_style(words.lead + f"2D game asset: {spec.subject}. {backdrop_text}", spec.style)
    return Painting(
        key, "sprite", prompt, size, (spec.ref,), spec.height, reseed=spec.reseed, cut=spec.cut
    )


BROKEN = "broken"


def variants(spec: Item, base: Painting) -> list[Painting]:
    texture = WORDS[spec.style].variant
    changes = spec.variants | ({BROKEN: spec.broken} if spec.broken else {})
    return [
        Painting(
            f"{base.key}-{variant}",
            "sprite",
            in_style(
                f"{change} Keep everything else exactly the same: the shape, {texture}, "
                "the background.",
                spec.style,
            ),
            base.size,
            height=base.height,
            base=base.key,
            cut=spec.cut if variant == BROKEN else (),
        )
        for variant, change in changes.items()
    ]


def used(layout: Layout) -> dict[str, Item]:
    """The furniture the maps use."""
    return {name: spec for name, spec in FURNITURE.items() if name in layout.furniture}


def items(layout: Layout) -> list[Painting]:
    """Every item's painting: the maps' furniture, the extras and the platform pieces, then
    their colour variants."""
    unknown = sorted(set(layout.furniture) - set(FURNITURE) - set(EXTRAS))
    if unknown:
        raise KeyError(f"no painting for the maps' furniture: {', '.join(unknown)}")
    specs = {**used(layout), **EXTRAS, **PLATFORMS, **below()}
    bases = {name: item(name, spec, layout) for name, spec in specs.items()}
    return [*bases.values(), *(v for n, s in specs.items() for v in variants(s, bases[n]))]


MURAL_WORDS = (
    " The wide plain stretch of wall on the {side} is a blank wall kept for a mural: leave it "
    "smooth and empty, with no windows, no doors, no flower boxes and no plants on it."
)


def _side(unit: Front) -> str:
    x0, _, x1, _ = unit.murals[0]
    middle = (x0 + x1) / 2 / unit.width
    return "left" if middle < 0.4 else "right" if middle > 0.6 else "middle"


def cartoon_front_prompt(look: Look, unit: Front) -> str:
    """A front underground, naming only what its plan has."""
    extras = ["a flat roof", "small windows lit from inside"]
    parts = ["the walls", "the roof", "every window"]
    if unit.door is not None:
        extras += ["a glass door", "a glowing neon medical cross pictogram over the door"]
        parts += ["the glass door", "the small round wall light"]
    ground = "grey" if backdrop(unit) == GREY else "white"
    return in_style(
        f"Redraw image 1 as the front of {look.look}, with {', '.join(extras)}, "
        f"{WORDS[look.style].front}. Keep every shape exactly where it is, with the same "
        f"outlines and colours: {', '.join(parts)}. Seen straight from the front, a flat "
        f"elevation with no perspective, on a plain {ground} background. No people.",
        look.style,
    )


def modern_front_prompt(look: Look, unit: Front) -> str:
    """A front with today's details, as `fronts.modernised` draws them."""
    windows = unit.window_boxes()
    upper = any(box[1] > unit.storey for box in windows)
    extras = ["big glass windows in slim dark frames with pale roller blinds"] if windows else []
    parts = ["the walls", "the flat roof"] + (["every window"] if windows else [])
    if look.flower_boxes and upper:
        extras.append("planters full of plants under the upper windows")
        parts.append("the planters")
    if upper:
        extras.append("air-conditioning units on the wall")
        parts.append("the air-conditioning units")
    if unit.shop_boxes():
        sign = f"{look.pictogram} pictogram" if look.pictogram else "pictogram"
        extras.append(
            f"a plain glowing light band over the shopfront, and a glowing neon {sign} in the "
            "shop window"
        )
        parts += ["the light band", "the big shop window", "the neon pictogram"]
    elif unit.awnings:
        parts.append("the slim canopies over the windows")
    if unit.lanterns:
        extras.append("round red paper lanterns")
        parts.append("the lanterns")
    if unit.door is not None:
        extras.append("a glass door")
        parts += ["the glass door", "the small round wall light"]
        if unit.plant_spots():
            parts.append("the potted plants")
    ground = "grey" if backdrop(unit) == GREY else "white"
    rules = ""
    if unit.murals and look.mural_words:
        rules = MURAL_WORDS.format(side=_side(unit))
    elif unit.murals:
        rules = " Leave the blank stretches of wall plain, with nothing on them."
    if unit.door is None:
        rules += " This part of the building has no door at all: only the windows shown."
    if unit.door is None and unit.awnings:
        rules += (
            " The ground floor's windows are small ordinary windows with plain wall under them "
            "down to the pavement, not doors."
        )
    if not windows:
        rules += " It has no windows."
    made = ", ".join(["a contemporary building with a flat roof", *extras, WORDS[look.style].front])
    return in_style(
        f"Redraw image 1 as the front of {look.look}, {made}. Keep every shape exactly where it "
        f"is, with the same outlines and colours: {', '.join(parts)}. Seen straight from the "
        f"front, a flat elevation with no perspective, on a plain {ground} background.{rules} No "
        "people, no words.",
        look.style,
    )


def front_prompt(look: Look, unit: Front) -> str:
    """The prompt for one unit of a front, naming only what its plan has."""
    return modern_front_prompt(look, unit) if look.modern else cartoon_front_prompt(look, unit)


def night_prompt(look: Look, unit: Front) -> str:
    lit = ["every window"] if unit.window_boxes() else []
    if unit.shop_boxes():
        lit.append("the shop windows")
    if unit.door is not None:
        lit += ["the glass door", "the wall lamp"] if look.glass_door else ["the wall lamp"]
    if unit.lanterns:
        lit.append("the paper lanterns")
    if look.modern and unit.shop_boxes():
        lit += ["the light band", "the neon pictogram"]
    ground = "grey" if backdrop(unit) == GREY else "white"
    return in_style(
        f"The same picture at night: warm yellow light glows from {', '.join(lit)}, the "
        f"{WORDS[look.style].night} are in deep blue shadow, and the background stays plain "
        f"{ground}. Keep every shape exactly where it is, and add nothing.",
        look.style,
    )


def fronts(layout: Layout) -> list[Painting]:
    """Each building's front and its glow map, each painted a unit at a time."""
    out = []
    for building, facade in layout.facades.items():
        look = LOOKS[building]
        f = front(facade, look)
        parts = [unit for _, unit in units(f)]
        key, height = f"fronts/{building}", f.total_height
        size = unit_plans(f)[0][1].image.size
        days = tuple(front_prompt(look, unit) for unit in parts)
        nights = tuple(night_prompt(look, unit) for unit in parts)
        out.append(
            Painting(
                key,
                "front",
                days[0],
                size,
                (),
                height,
                None,
                building,
                None,
                days,
                look.reseed,
                reseeds=look.reseeds,
            )
        )
        glow = f"glow/{building}"
        out.append(Painting(glow, "glow", nights[0], size, (), height, key, building, None, nights))
    return out


def room_papers(layout: Layout) -> list[Painting]:
    used = sorted({p for floors in papers(layout).values() for p in floors})
    made = [paper(key, PAPERS[key], PAPER_STYLES[key]) for key in used]
    return [*made, SLAB]


def landmark_prompt(spec: Landmark) -> str:
    return in_style(
        f"Redraw image 1 as {spec.subject}, {WORDS[spec.style].front}. Keep every shape exactly "
        "where it is, with the same outlines and colours: every tower, every spire and every "
        "window. Seen straight from the front, a flat elevation with no perspective, on a plain "
        "white background. No people.",
        spec.style,
    )


def landmarks(chosen: dict[str, Landmark] | None = None) -> list[Painting]:
    """Each landmark, redrawn from its plan in `skyline.py`, and its glow map, drawn from the
    plan's lit windows on that painting."""
    out = []
    for name, spec in (LANDMARKS if chosen is None else chosen).items():
        size = skyline.plan(name).image.size
        key, refs = f"landmarks/{name}", (spec.ref,)
        day = landmark_prompt(spec)
        out.append(Painting(key, "landmark", day, size, refs, spec.height, landmark=name))
        out.append(Painting(f"glow/{name}", "glow", "", size, (), spec.height, key, landmark=name))
    return out


def paintings(layout: Layout | None = None) -> list[Painting]:
    """Every painting, in the order they're painted: a redrawn painting after its base."""
    layout = layout or load_layout()
    return [
        *LAYERS,
        *TUNNEL_LAYERS,
        *SEWER_LAYERS,
        *room_papers(layout),
        *fronts(layout),
        *landmarks(),
        *items(layout),
    ]


PARALLAX = {
    "sky": 0.04,
    "city": 0.1,
    "far": 0.2,
    "mid": 0.45,
    "near": 0.85,
    "ground": 1.0,
    "foreground": 1.3,
}
"""How fast each street layer moves with the camera, as the study drew them."""

TIMES = {
    "morning": {
        "tint": [0.97, 0.95, 0.97],
        "sky": [1.08, 0.9, 0.96],
        "haze": [0.55, 242, 222, 230],
        "glow": 0.0,
    },
    "afternoon": {
        "tint": [1.0, 0.99, 0.96],
        "sky": [1.0, 1.0, 1.0],
        "haze": [0.2, 232, 238, 240],
        "glow": 0.0,
    },
    "evening": {
        "tint": [1.0, 0.86, 0.76],
        "sky": [1.02, 0.8, 0.7],
        "haze": [0.3, 214, 172, 160],
        "glow": 0.55,
    },
    "night": {
        "tint": [0.36, 0.42, 0.66],
        "sky": [0.2, 0.24, 0.46],
        "haze": [0.35, 40, 50, 90],
        "glow": 1.0,
    },
}
"""Suggested tints, as the previews draw them: `tint` multiplies near layers and sprites, `sky`
the sky, `haze` mixes the far layer that much towards a colour (the mid layer half as much), and
`glow` scales the glow maps added on top."""


def measurements(spec: Item) -> dict:
    """What the client measures an item's art by, where it has any."""
    out: dict = {
        name: value
        for name, value in (("seat", spec.seat), ("bed", spec.bed), ("light", spec.light))
        if value is not None
    }
    if spec.moulding:
        out["moulding"] = spec.moulding._asdict()
    return out


def street_layers(street: str) -> dict[str, str]:
    layers = STREETS[street]
    names = ("sky", "city", "far", "mid", "near", "ground", "foreground")
    return {name: f"layers/{key}" for name in names if (key := getattr(layers, name))}


def index(layout: Layout | None = None) -> dict:
    """The manifest's lookups by the ids the maps use, each naming pieces by key."""
    layout = layout or load_layout()
    furniture = {}
    for name, spec in {**used(layout), **EXTRAS}.items():
        key = f"{spec.folder}/{name}"
        found = {v: f"{key}-{v}" for v in spec.variants}
        furniture[name] = {"piece": key, **({"variants": found} if found else {})}
        if spec.broken:
            furniture[name][BROKEN] = f"{key}-{BROKEN}"
        if spec.stretch:
            furniture[name]["stretch"] = True
        furniture[name].update(measurements(spec))
    floors = papers(layout)
    marks = {
        name: {"piece": f"landmarks/{name}", "glow": f"glow/{name}", "at": spec.at}
        for name, spec in sorted(LANDMARKS.items())
    }
    return {
        "parallax": PARALLAX,
        "times": TIMES,
        "streets": {street: street_layers(street) for street in sorted(layout.streets)},
        **({"landmarks": marks} if marks else {}),
        "grounds": {place: f"layers/{key}" for place, key in GROUNDS.items()},
        "buildings": {
            building: {
                "street": facade.street,
                "front": f"fronts/{building}",
                "glow": f"glow/{building}",
                "floors": [f"papers/{p}" for p in floors.get(building, [])],
            }
            for building, facade in sorted(layout.facades.items())
        },
        "furniture": furniture,
        "platforms": {
            name: f"platforms/{name}"
            for name, spec in {**used(layout), **PLATFORMS}.items()
            if spec.folder == "platforms"
        },
        "platforms_below": {
            street: {name: f"platforms/{street}-{name}" for name in pieces}
            for street, pieces in sorted(PLATFORMS_BELOW.items())
        },
        "slab": SLAB.key,
    }
