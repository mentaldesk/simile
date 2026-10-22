"""Every painting the village needs: its prompt, size, style image and height in metres."""

import zlib
from dataclasses import dataclass, field
from typing import Literal

from simile.papercraft.fronts import GREY, Front, backdrop, unit_plans, units
from simile.papercraft.layout import Layout, load_layout
from simile.papercraft.painter import cartoon, styled
from simile.papercraft.sketches import SKETCHES
from simile.papercraft.village import (
    CARTOON_PAPERS,
    CLAY,
    GROUNDS,
    LOOKS,
    PAPERS,
    SLATE,
    STREETS,
    TERRACOTTA,
    Look,
    front,
    papers,
)

type Kind = Literal["layer", "strip", "ground", "sprite", "front", "glow", "paper"]

SPRITE = (
    "Seen straight from the front at eye level, a flat elevation with no perspective. One single "
    "object centred on a plain flat white background with empty space all around it, nothing "
    "else in the picture, and no shadow on the background."
)
SIDE_SPRITE = SPRITE.replace("straight from the front", "exactly from the side")
LEAD = "Make a new picture in exactly the papercraft style of the reference picture: "
REDRAW = (
    "Redraw image 1 as {subject}, made of cut paper and card in the papercraft style of image 2: "
    "matt paper with visible fibres and cut edges. Keep every shape exactly where it is, with the "
    "same outlines and colours, seen exactly from the side with no perspective, on a plain {back} "
    "background, and no shadow on the background."
)
TEXTURE = (
    "A flat photo, taken from directly above, of a sheet of patterned craft paper that fills the "
    "whole frame edge to edge: {}. Visible paper fibres, even soft light, no objects, no edges."
)
PAPER_LEAD = (
    "Make a flat texture in the colours and paper style of the reference picture, showing none "
    "of its objects: "
)
PAPER_CARD = "all matt paper and card, with visible paper fibres and cut edges, not glossy"
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
TUNNELS = "cartoon/street"
TUNNEL_ROOMS = "cartoon/interior"
"""The tunnels' references, from #329's revised cartoon."""


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
    """For a sprite, what else to cut away: `shadows` and `gaps` (see `cutout.tidy`)."""

    @property
    def seed(self) -> int:
        return zlib.crc32((self.base or self.key).encode()) % 10_000 + self.reseed


def layer(key: str, kind: Kind, subject: str, size: tuple[int, int], height: float) -> Painting:
    """A street layer. The near and foreground ones are kept to plants, since edit mode copies
    the street reference's houses into them otherwise."""
    if key.startswith(("near-", "front-")):
        subject += NOTHING_BUT_PLANTS
    return Painting(f"layers/{key}", kind, styled(LEAD + subject), size, ("street",), height)


def paper(key: str, pattern: str, size: tuple[int, int] = (768, 512), **kw) -> Painting:
    prompt = styled(PAPER_LEAD + TEXTURE.format(pattern))
    return Painting(f"papers/{key}", "paper", prompt, size, ("house",), **kw)


def cartoon_paper(key: str, pattern: str, size: tuple[int, int] = (768, 512)) -> Painting:
    prompt = cartoon(CARTOON_PAPER_LEAD + CARTOON_TEXTURE.format(pattern))
    return Painting(f"papers/{key}", "paper", prompt, size, (TUNNEL_ROOMS,))


def tunnel_layer(
    key: str, kind: Kind, subject: str, size: tuple[int, int], height: float
) -> Painting:
    """A layer of the tunnels, kept to what it names, since edit mode copies the reference's
    buildings, trees and people otherwise."""
    prompt = cartoon(CARTOON_LEAD + subject)
    return Painting(f"layers/{key}", kind, prompt, size, (TUNNELS,), height)


SKY = Painting(
    "layers/sky",
    "paper",
    styled(
        LEAD + "A plain sky backdrop made of layered paper: a smooth gradient from pale warm "
        "cream near the bottom to soft blue at the top, with five soft cut-paper clouds. Only "
        "sky: no ground, no hills, no buildings, no trees, no birds."
    ),
    (1536, 768),
    ("street",),
    12.0,
)

STRIP = (
    "running from the left edge of the frame to the right edge, standing on one straight "
    "baseline on a plain white background."
)
LAYERS = [
    SKY,
    layer(
        "far-hills",
        "layer",
        "A long strip of distant rolling hills cut from pale sage-green and misty blue-grey "
        "paper, with a few tiny far-off houses and trees on the ridges, lying on a plain flat "
        "white background with white space above and below it.",
        (1536, 512),
        5.0,
    ),
    layer(
        "far-river",
        "layer",
        "A long strip of low misty blue-grey hills on the far bank of a wide river, with a few "
        "tiny palm trees and stilt houses along the shore, cut from pale paper, lying on a plain "
        "flat white background with white space above and below it.",
        (1536, 512),
        4.0,
    ),
    layer(
        "mid-shophouses",
        "strip",
        "A long row of distant two- and three-storey shophouses with tiled roofs, shutters and "
        "faded awnings, with the round crowns of trees between them, cut from faded, hazy paper "
        "in muted terracotta, cream and green, all standing on one straight baseline, on a plain "
        "flat white background with white space above them. Empty streets: no people, no "
        "animals, no signs.",
        (1536, 640),
        9.0,
    ),
    layer(
        "mid-homes",
        "strip",
        "A long row of distant small two-storey village homes with tiled roofs and little "
        "gardens, with kapok trees in red flower and leafy lychee trees between them, cut from "
        "faded, hazy paper in muted pink, cream, sage and terracotta, all standing on one "
        "straight baseline, on a plain flat white background with white space above them. Empty "
        "streets: no people, no animals.",
        (1536, 640),
        8.0,
    ),
    layer(
        "mid-rooftops",
        "strip",
        "A long row of distant village rooftops of terracotta and grey slate, a few chimneys and "
        "water tanks, and the broad crowns of big banyan trees rising between them, cut from "
        "faded, hazy paper, all standing on one straight baseline, on a plain flat white "
        "background with white space above them. No people, no towers.",
        (1536, 640),
        9.0,
    ),
    layer(
        "mid-riverbank",
        "strip",
        "A long row of distant palm trees, banyan trees and low reed beds along a riverbank, "
        "with a small wooden jetty, cut from faded, hazy paper in muted greens and sand, all "
        "standing on one straight baseline, on a plain flat white background with white space "
        "above them. No people, no boats.",
        (1536, 640),
        7.0,
    ),
    layer(
        "near-walls",
        "strip",
        "A long low garden wall of pale stone, seen straight from the front, with bougainvillea "
        "in magenta flower spilling over it and small potted trees, cut from layered card, "
        + STRIP,
        (1536, 512),
        2.2,
    ),
    layer(
        "near-gardens",
        "strip",
        "A long run of front gardens seen straight from the front: low wooden picket fences "
        "painted cream and sage, clipped hedges, flowering shrubs and small lychee trees, cut "
        f"from layered card, {STRIP}",
        (1536, 512),
        2.4,
    ),
    layer(
        "near-hedges",
        "strip",
        "A long row of clipped green hedges in low stone planters, with young palm trees and "
        f"flowering hibiscus, seen straight from the front, cut from layered card, {STRIP}",
        (1536, 512),
        2.6,
    ),
    layer(
        "ground-street",
        "ground",
        "A long horizontal strip of street seen exactly from the side, cut from layered "
        "cardboard: a sandy paved footpath on top, a kerb edge, and a band of grey road below, "
        "running from the left edge of the frame to the right edge, on a plain white background.",
        (1536, 384),
        2.6,
    ),
    layer(
        "ground-plaza",
        "ground",
        "A long horizontal strip of a town square's paving seen exactly from the side, cut from "
        "layered cardboard: warm terracotta and sand paving tiles on top, a low step edge, and a "
        "band of pale stone below, running from the left edge of the frame to the right edge, "
        "on a plain white background.",
        (1536, 384),
        2.6,
    ),
    layer(
        "ground-park",
        "ground",
        "A long horizontal strip of park seen exactly from the side, cut from layered card and "
        "paper: a band of soft green grass with tiny daisies on top, a sandy path edge, and a "
        "band of calm blue lake water below with round lotus pads and pink lotus flowers, "
        "running from the left edge of the frame to the right edge, on a plain white background.",
        (1536, 384),
        2.6,
    ),
    layer(
        "ground-promenade",
        "ground",
        "A long horizontal strip of a riverside promenade seen exactly from the side, cut from "
        "layered cardboard: a pale stone walkway on top, a low stone river wall, and a band of "
        "calm blue-green river water below with a few round lotus pads, running from the left "
        "edge of the frame to the right edge, on a plain white background.",
        (1536, 384),
        2.6,
    ),
    layer(
        "front-plants",
        "strip",
        "A long low row of big leafy tropical plants, ferns and banana leaves in dark green, cut "
        f"from layered paper, {STRIP} No flowers, no pots.",
        (1536, 512),
        2.0,
    ),
    layer(
        "front-reeds",
        "strip",
        "A long low row of tall reeds, cattails and lotus flowers on long stems in dark green "
        f"and pink, cut from layered paper, {STRIP}",
        (1536, 512),
        2.0,
    ),
]
NO_STREET = " No people, no trains, no trees, no sky, no buildings."
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
        "A long run of the tiled back wall of an old metro station seen straight from the front, "
        "across the tracks: a wall of dim cream tiles with a dark teal band, a row of tall round "
        "arches, empty frames where posters once hung, old pipes and dead lamps, all standing on "
        "one straight baseline, on a plain flat white background with white space above it. "
        "No signs." + NO_STREET,
        (1536, 640),
        9.0,
    ),
    tunnel_layer(
        "near-metro",
        "strip",
        "A long low run of clutter along the foot of an old metro station's tiled wall, seen "
        "straight from the front: old pipes, cable trays, a few sacks, crates and tarps, "
        + STRIP
        + " Only pipes, cables and junk."
        + NO_STREET,
        (1536, 512),
        2.2,
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
SLAB = paper(
    "slab", "the cut edge of thick corrugated brown cardboard, a long band", (1024, 256), height=0.3
)


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
    ref: str = "furniture"
    sketch: str | None = None
    folder: str = "furniture"
    variants: dict[str, str] = field(default_factory=dict)
    """Colour variants: name, and what's recoloured to what."""
    cartoon: bool = False
    """Painted in the tunnels' cartoon rather than papercraft."""


STREET = "street"
FURNITURE: dict[str, Item] = {
    "kitchen": Item(
        "a fitted kitchen run, twice as wide as it is tall: blue-painted wooden base cupboards "
        "under a wooden worktop, with a sink and tap and a little two-ring hob set into the "
        "worktop. No wall cupboards, nothing above the worktop",
        0.95,
        (1024, 512),
        stretch=True,
    ),
    "sofa": Item(
        "a three-seat sofa upholstered in deep teal velvet with round wooden feet",
        0.85,
        (768, 512),
        variants={
            "coral": "Recolour the sofa's velvet upholstery to coral red.",
            "mustard": "Recolour the sofa's velvet upholstery to mustard yellow.",
            "plum": "Recolour the sofa's velvet upholstery to dark plum purple.",
        },
    ),
    "bed": Item(
        "a double bed seen from the side, with a carved wooden headboard on the left and a "
        "patchwork quilt in warm reds and oranges",
        1.05,
        (896, 512),
        side=True,
        variants={"blue": "Recolour the patchwork quilt to soft blues and greens."},
    ),
    "wardrobe": Item(
        "a tall wooden wardrobe painted sage green with two doors and brass knobs", 2.0, (512, 768)
    ),
    "bookshelf": Item(
        "a tall bookshelf painted pale sage green, full of books with colourful spines and a "
        "small plant",
        1.9,
        (512, 896),
    ),
    "table": Item(
        "a small square wooden kitchen table with a wooden chair at each end, the chairs facing "
        "the table",
        0.95,
        (896, 512),
        side=True,
        cut=("shadows", "gaps"),
    ),
    "plant": Item("a big leafy monstera plant in a terracotta pot", 1.1, (512, 640)),
    "counter": Item(
        "a cafe counter with a front of honey-coloured wooden panels, a little brass cash till "
        "and a glass pastry case with cakes and croissants on top",
        1.25,
        (1008, 448),
        stretch=True,
    ),
    "espresso_machine": Item(
        "a big copper and cream espresso machine with two group heads and little cups on top, "
        "standing on a low cupboard of dark wood",
        1.55,
        (512, 768),
    ),
    "grinder": Item(
        "a coffee grinder with a glass hopper full of beans, standing on a low cupboard of dark "
        "wood with sacks of coffee beside it",
        1.4,
        (512, 768),
    ),
    "menu_board": Item(
        "a wide chalkboard in a wooden frame, hung on a wall, with chalk drawings of coffee "
        "cups, cakes and leaves and no words at all",
        1.0,
        (1104, 416),
    ),
    "bar_counter": Item(
        "a long wooden bar counter seen from the customers' side, three times as wide as it is "
        "tall: a narrow top of honey-coloured wood, a front of vertical wooden boards and a "
        "brass foot rail running along the bottom",
        1.1,
        (1024, 384),
        stretch=True,
    ),
    "cafe_table": Item(
        "a small round cafe table with a marble top and a black iron pedestal, with a bentwood "
        "chair at each side facing the table",
        0.95,
        (896, 512),
        side=True,
        grey=True,
        cut=("shadows", "gaps"),
    ),
    "stove": Item(
        f"a big noodle stove of grey card with two burners, two tall stock pots and a wok, "
        f"and a hood above, {PAPER_CARD}",
        2.0,
        (768, 768),
    ),
    "kitchen_counter": Item(
        "a small steel prep counter with a chopping board, a cleaver and bowls of spring "
        "onions and chillies",
        1.0,
        (512, 512),
    ),
    "noodle_counter": Item(
        "a long noodle bar counter of red-lacquered wood with a ledge, bowls, chopsticks in a "
        "pot and a bottle of chilli oil on top",
        1.05,
        (1376, 336),
        stretch=True,
    ),
    "stool": Item(
        f"a knee-high bar stool with a thick round padded seat of red card, a thin stem and a "
        f"ring footrest, {PAPER_CARD}",
        0.7,
        (384, 640),
        variants={"teal": "Recolour the stool's seat to teal."},
    ),
    "noodle_table": Item(
        "a small square wooden table with a red paper lantern on a cord above it and a red "
        "stool at each side",
        1.9,
        (768, 768),
        side=True,
        grey=True,
        cut=("deep shadows", "gaps"),
    ),
    "laser_cutter": Item(
        "a big laser cutter, a wide boxy cabinet of pale grey card with a tinted orange lid "
        "and a small control panel",
        1.1,
        (768, 640),
    ),
    "printer_3d": Item(
        "a 3D printer: an open frame of black card on a desk-high stand, with a spool of blue "
        "filament and a small half-printed boat on its bed",
        1.5,
        (512, 768),
    ),
    "loom": Item(
        "a wooden floor loom with colourful warp threads in rainbow stripes and a half-woven cloth",
        1.6,
        (768, 768),
    ),
    "sewing_machine": Item(
        "a vintage sewing machine of mint-green card on a small wooden table with an iron treadle",
        1.1,
        (512, 768),
    ),
    "workbench": Item(
        "a long sturdy wooden workbench with a vice, a few hand tools and a small toolbox on "
        "top, and a shelf underneath",
        0.95,
        (1280, 352),
        stretch=True,
    ),
    "rope_bridge": Item(
        "a rope bridge: a deck of wooden planks hung from two rope handrails, with a sturdy "
        "wooden post at each end",
        1.25,
        ref="rooftops",
        sketch="rope_bridge",
        folder="platforms",
        stretch=True,
        cut=("outline", "shadows", "gaps"),
    ),
    "pegboard": Item(
        "a wide pegboard panel hung on a wall, with hammers, saws, pliers and screwdrivers "
        "hanging on it",
        1.0,
        (1264, 352),
        stretch=True,
    ),
    "shelf": Item(
        "a long run of open wooden shelves full of boxes, jars of screws, spools of thread and "
        "rolls of fabric",
        1.6,
        (944, 480),
    ),
    "plinth": Item(
        "a tall white plinth with a small bronze sculpture of a smooth round pebble on top",
        1.4,
        (512, 896),
        grey=True,
    ),
    "bench": Item(
        "a wooden bench with a backrest and dark green iron legs, seen straight from the front",
        0.9,
        (896, 512),
        ref=STREET,
    ),
    "news_terminal": Item(
        "a public news kiosk: a slim upright stand of teal-painted metal card with a small "
        "glowing blank screen and a little roof",
        2.2,
        (512, 1024),
        ref=STREET,
        cut=("tinted shadows",),
    ),
    "fountain": Item(
        "a round stone town fountain with two tiers and water splashing into its basin",
        2.2,
        (896, 768),
        ref=STREET,
    ),
    "lamp": Item("an old dark green iron street lamp on a tall post", 3.6, (512, 1024), ref=STREET),
    "tree": Item(
        "a leafy shade tree with a sturdy trunk and a broad round crown of big paper leaves",
        6.0,
        (768, 1024),
        ref=STREET,
    ),
    "bush": Item(
        "a low mound of hibiscus leaves and pink flowers growing straight from the ground, "
        "twice as wide as it is tall, like a little hedge",
        1.0,
        (640, 512),
        ref=STREET,
    ),
    "lift": Item(
        "a small old-fashioned lift car: a cage of black iron bars with a brass trim, a wooden "
        "floor and a little lamp on top",
        2.9,
        ref="house",
        sketch="lift",
        folder="platforms",
    ),
    "metro_entrance": Item(
        "a small old metro station entrance seen straight from the front: an arched canopy of "
        "dark green painted iron and glass on two slim iron posts, over a dark doorway where a "
        "stairway goes down, with a small round glowing sign showing a simple train pictogram "
        "on top of the canopy",
        2.8,
        (640, 832),
        ref=STREET,
    ),
    "train_carriage": Item(
        "an abandoned old metro train carriage seen exactly from the side: a long boxy body of "
        "faded cream painted steel with a teal stripe, a row of dark windows, two pairs of "
        "closed sliding doors, a flat grey roof with low vents, and its bogies and wheels",
        3.36,
        ref=TUNNELS,
        sketch="train_carriage",
        cut=("outline",),
        cartoon=True,
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
        cartoon=True,
    ),
    "metro_steps": Item(
        "a flight of old metro station steps seen exactly from the side, rising to the left: "
        "worn concrete treads with dark steel nosings, over a solid side wall of grimy cream "
        "tiles",
        3.36,
        ref=TUNNELS,
        sketch="metro_steps",
        cut=("outline",),
        cartoon=True,
    ),
    "freight_lift": Item(
        "an old dead freight lift seen from the front: its car behind a folding steel grille "
        "gate, in a riveted steel frame, under a winding wheel in a steel housing",
        4.4,
        ref=TUNNELS,
        sketch="freight_lift",
        cut=("outline",),
        cartoon=True,
    ),
    "scrap_stall": Item(
        "a scrap trader's stall: a battered trestle table piled with salvaged electronics, coils "
        "of copper wire, gears and old circuit boards, under a patched canvas awning on two "
        "poles, with a crate of parts beside it",
        2.2,
        (896, 768),
        ref=TUNNEL_ROOMS,
        cartoon=True,
    ),
    "turnstile": Item(
        "a pair of old metro turnstiles side by side: two waist-high posts of scuffed stainless "
        "steel, each with three rotating metal bars sticking out to one side and a little round "
        "card reader on top, dead and dusty",
        1.1,
        (768, 512),
        ref=TUNNEL_ROOMS,
        cartoon=True,
    ),
    "ticket_machine": Item(
        "an old metro ticket machine: a tall cabinet of scuffed steel and faded teal panels with "
        "a dark dead screen, a coin slot and a little ticket tray",
        1.9,
        (512, 896),
        ref=TUNNEL_ROOMS,
        cartoon=True,
    ),
    "metro_bench": Item(
        "an old metro platform bench seen straight from the front: a row of three moulded orange "
        "plastic seats on a steel frame, scuffed and dusty",
        0.9,
        (896, 512),
        ref=TUNNEL_ROOMS,
        cartoon=True,
    ),
    "dead_terminal": Item(
        "an old metro control console: a waist-high cabinet of grimy grey steel with a dark "
        "cracked screen on top, a row of unlit buttons and a small round data port, dead",
        1.5,
        (512, 768),
        ref=TUNNEL_ROOMS,
        cartoon=True,
    ),
    "breaker_box": Item(
        "a maintenance power point: a grey steel breaker box on a short steel post, with a "
        "yellow and black hazard stripe, a big power socket, a coiled cable and a small "
        "glowing green light",
        1.4,
        (512, 768),
        ref=TUNNEL_ROOMS,
        cartoon=True,
    ),
    "crates": Item(
        "a stack of two battered wooden crates", 1.0, (640, 640), ref=TUNNELS, cartoon=True
    ),
    "rubble": Item(
        "a low heap of broken concrete chunks, bricks and twisted rusty rebar, twice as wide as "
        "it is tall",
        0.7,
        (768, 448),
        ref=TUNNELS,
        cartoon=True,
    ),
    "bedroll": Item(
        "an abandoned sleeping spot on the floor seen from the side: a rolled-out stained "
        "sleeping bag on flattened cardboard, with a tin mug and a candle stub",
        0.45,
        (768, 384),
        side=True,
        ref=TUNNEL_ROOMS,
        cartoon=True,
    ),
    "pipes": Item(
        "a long run of three old pipes one above the other along a wall, of rusty iron and "
        "faded green-painted steel, held by plain brackets, with no valves",
        0.8,
        (1280, 352),
        stretch=True,
        ref=TUNNELS,
        cartoon=True,
    ),
    "tunnel_arch": Item(
        "a tall archway at the mouth of an old metro tunnel, seen straight from the front: two "
        "square pillars of grimy cream tiles joined by a round concrete arch, with cables and a "
        "dead lamp on it, and nothing in the opening",
        8.8,
        (512, 1280),
        ref=TUNNELS,
        cut=("gaps",),
        cartoon=True,
    ),
}
EXTRAS: dict[str, Item] = {
    "armchair": Item(
        "an armchair upholstered in mustard-yellow fabric with dark wooden legs",
        0.95,
        variants={
            "sage": "Recolour the armchair's upholstery to sage green.",
            "teal": "Recolour the armchair's upholstery to deep teal.",
        },
    ),
    "floor_lamp": Item(
        "a floor lamp, switched off, with a thin brass stand and a pleated cream fabric shade",
        1.6,
        (512, 1024),
    ),
    "bedside_table": Item(
        "a small wooden bedside table with a little lamp with a round pink shade on it",
        0.95,
        (512, 768),
    ),
    "fridge": Item("a rounded retro fridge of pale mint card", 1.7, sketch="fridge"),
    "bathtub": Item(
        "a clawfoot bathtub of white card with gold paper feet and taps", 0.75, sketch="bathtub"
    ),
    "washbasin": Item(
        "a pedestal washbasin of white card with a round mirror in a wooden frame above it",
        1.8,
        sketch="washbasin",
    ),
    "picture_frame": Item(
        "an empty picture frame of gilded wood around a plain cream canvas, hung on a wall, "
        "seen straight from the front",
        0.9,
        (768, 640),
        grey=True,
    ),
    "banyan_tree": Item(
        "a large banyan tree with a thick trunk, spreading branches, a broad crown of big paper "
        "leaves and hanging aerial roots",
        11.0,
        (768, 1024),
        ref=STREET,
    ),
    "kapok_tree": Item(
        "a tall kapok tree with a straight pale trunk, layered branches and clusters of red "
        "flowers",
        10.0,
        (768, 1024),
        ref=STREET,
    ),
    "palm_tree": Item(
        "a slender coconut palm tree with a gently curving trunk", 7.0, (512, 1024), ref=STREET
    ),
    "bicycle": Item(
        "an old bicycle with a basket on the front, painted pale blue, its wheels thin rims "
        "with fine wire spokes and open gaps between them",
        1.0,
        (896, 576),
        side=True,
        grey=True,
        ref=STREET,
        cut=("gaps",),
    ),
    "bin": Item(
        f"a round litter bin of muted dark green card with a domed lid and a paper texture, "
        f"{PAPER_CARD}",
        0.95,
        (384, 640),
        ref=STREET,
    ),
}
PLATFORMS: dict[str, Item] = {
    "stairs": Item(
        "a straight wooden staircase rising one storey to the right, with a handrail on posts",
        5.3,
        ref="house",
        sketch="stairs",
        folder="platforms",
    ),
    "ladder": Item(
        "a tall wooden ladder", 3.6, ref="rooftops", sketch="ladder", folder="platforms"
    ),
    "steps": Item(
        "a short flight of pale stone steps rising to the right",
        2.2,
        ref="street",
        sketch="steps",
        folder="platforms",
    ),
    "ledge": Item(
        "a long flat wooden walkway of planks on two wooden brackets",
        0.6,
        ref="rooftops",
        sketch="ledge",
        folder="platforms",
        cut=("outline", "shadows", "gaps"),
    ),
    "lift_shaft": Item(
        "one storey of a lift shaft's black iron frame with a cable down the middle",
        4.4,
        ref="house",
        sketch="lift_shaft",
        folder="platforms",
    ),
    "window": Item(
        "a window with a wooden frame and cream curtains tied to the sides, seen from inside a "
        "room",
        1.3,
        (512, 640),
        ref="house",
        folder="platforms",
    ),
    "door": Item(
        "a plain wooden interior door in its frame",
        2.1,
        (512, 896),
        ref="house",
        folder="platforms",
    ),
}


def item(name: str, spec: Item, layout: Layout) -> Painting:
    key = f"{spec.folder}/{name}"
    style, lead, redraw = (
        (cartoon, CARTOON_LEAD, CARTOON_REDRAW) if spec.cartoon else (styled, LEAD, REDRAW)
    )
    if spec.sketch:
        sketch = SKETCHES[spec.sketch]()
        back = "medium grey" if sketch.getpixel((0, 0)) == GREY else "white"
        prompt = style(redraw.format(subject=spec.subject, back=back))
        refs = (spec.ref,)
        size, height = sketch.size, spec.height
        return Painting(key, "sprite", prompt, size, refs, height, sketch=spec.sketch, cut=spec.cut)
    size = spec.size
    backdrop_text = SIDE_SPRITE if spec.side else SPRITE
    if spec.grey:
        backdrop_text = backdrop_text.replace("plain flat white", "plain flat medium grey")
    prompt = style(lead + f"2D game asset: {spec.subject}. {backdrop_text}")
    return Painting(
        key, "sprite", prompt, size, (spec.ref,), spec.height, reseed=spec.reseed, cut=spec.cut
    )


def variants(spec: Item, base: Painting) -> list[Painting]:
    return [
        Painting(
            f"{base.key}-{variant}",
            "sprite",
            styled(
                f"{change} Keep everything else exactly the same: the shape, the paper texture, "
                "the background."
            ),
            base.size,
            height=base.height,
            base=base.key,
        )
        for variant, change in spec.variants.items()
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
    specs = {**used(layout), **EXTRAS, **PLATFORMS}
    bases = {name: item(name, spec, layout) for name, spec in specs.items()}
    return [*bases.values(), *(v for n, s in specs.items() for v in variants(s, bases[n]))]


ROOF_TILES = {
    TERRACOTTA: "terracotta clay tiles",
    SLATE: "grey slate tiles",
    CLAY: "brown clay tiles",
}


MURAL_WORDS = (
    " The wide plain stretch of wall on the {side} is a blank wall kept for a mural: leave it "
    "smooth and empty, with no windows, no doors, no flower boxes and no plants on it."
)


def _side(unit: Front) -> str:
    x0, _, x1, _ = unit.murals[0]
    middle = (x0 + x1) / 2 / unit.width
    return "left" if middle < 0.4 else "right" if middle > 0.6 else "middle"


def cartoon_front_prompt(look: Look, unit: Front) -> str:
    """A front in the tunnels' cartoon, naming only what its plan has."""
    extras = ["a flat roof", "small windows lit from inside"]
    parts = ["the walls", "the roof", "every window"]
    if unit.door is not None:
        extras += ["a glass door", "a glowing neon medical cross pictogram over the door"]
        parts += ["the glass door", "the small round wall light"]
    ground = "grey" if backdrop(unit) == GREY else "white"
    return cartoon(
        f"Redraw image 1 as the front of {look.look}, with {', '.join(extras)}, hand-drawn in "
        "the cartoon style: thick scratchy dark ink outlines around every shape, flat colours "
        "with simple soft shading, and a little wear. Keep every shape exactly where it is, with "
        f"the same outlines and colours: {', '.join(parts)}. Seen straight from the front, a "
        f"flat elevation with no perspective, on a plain {ground} background. No people."
    )


def front_prompt(look: Look, unit: Front) -> str:
    """The prompt for one unit of a front, naming only what its plan has."""
    if look.cartoon:
        return cartoon_front_prompt(look, unit)
    roof = (
        "a flat roof with a low parapet"
        if look.roof_shape == "flat"
        else f"a {'hipped' if look.roof_shape == 'hip' else 'pitched'} roof of "
        f"{ROOF_TILES.get(look.roof, 'clay tiles')}"
    )
    parts = ["the walls", "the roof", "every window"]
    extras = []
    if look.shutters:
        extras.append("wooden shutters")
    if look.flower_boxes:
        extras.append("flower boxes under the windows")
    if unit.shop_boxes():
        parts.append("the striped awnings over the shop windows")
    elif unit.awnings:
        parts.append("the striped awnings over the windows")
    if unit.lanterns:
        parts.append("the round paper lanterns")
        extras.append("round red paper lanterns")
    if unit.door is not None:
        parts += ["the door", "the wall lamp", "the potted plants"]
        if look.glass_door:
            extras.append("a glass door")
    ground = "grey" if backdrop(unit) == GREY else "white"
    rules = " Leave the blank stretches of wall plain, with nothing on them." if unit.murals else ""
    if unit.murals and look.mural_words:
        rules = MURAL_WORDS.format(side=_side(unit))
    if unit.door is None and unit.awnings:
        rules += " This part of the building has no door: only the windows shown."
    elif unit.door is None:
        rules += " It has no door."
    return styled(
        f"Redraw image 1 as the front of {look.look}, with {roof}"
        + (f", {', '.join(extras)}" if extras else "")
        + ", made of cut paper and card as a papercraft diorama: matt paper with visible fibres, "
        "cut edges and soft shadows between layers. Keep every shape exactly where it is, with "
        f"the same outlines and colours: {', '.join(parts)}. Seen straight from the front, a "
        f"flat elevation with no perspective, on a plain {ground} background.{rules} No people, "
        "no signs."
    )


def night_prompt(look: Look, unit: Front) -> str:
    lit = ["every window"]
    if unit.shop_boxes():
        lit.append("the shop windows")
    if unit.door is not None:
        lit += ["the glass door", "the wall lamp"] if look.glass_door else ["the wall lamp"]
    if unit.lanterns:
        lit.append("the paper lanterns")
    ground = "grey" if backdrop(unit) == GREY else "white"
    style, walls = (cartoon, "walls") if look.cartoon else (styled, "paper walls")
    return style(
        f"The same picture at night: warm yellow light glows from {', '.join(lit)}, the {walls} "
        f"are in deep blue shadow, and the background stays plain {ground}. Keep every shape "
        "exactly where it is, and add nothing."
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
                key, "front", days[0], size, (), height, None, building, None, days, look.reseed
            )
        )
        glow = f"glow/{building}"
        out.append(Painting(glow, "glow", nights[0], size, (), height, key, building, None, nights))
    return out


def room_papers(layout: Layout) -> list[Painting]:
    used = sorted({p for floors in papers(layout).values() for p in floors})
    made = [
        cartoon_paper(key, PAPERS[key]) if key in CARTOON_PAPERS else paper(key, PAPERS[key])
        for key in used
    ]
    return [*made, SLAB]


def paintings(layout: Layout | None = None) -> list[Painting]:
    """Every painting, in the order they're painted: a redrawn painting after its base."""
    layout = layout or load_layout()
    return [*LAYERS, *TUNNEL_LAYERS, *room_papers(layout), *fronts(layout), *items(layout)]


PARALLAX = {"sky": 0.04, "far": 0.2, "mid": 0.45, "near": 0.85, "ground": 1.0, "foreground": 1.3}
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


def index(layout: Layout | None = None) -> dict:
    """The manifest's lookups by the ids the maps use, each naming pieces by key."""
    layout = layout or load_layout()
    furniture = {}
    for name, spec in {**used(layout), **EXTRAS}.items():
        key = f"{spec.folder}/{name}"
        found = {v: f"{key}-{v}" for v in spec.variants}
        furniture[name] = {"piece": key, **({"variants": found} if found else {})}
        if spec.stretch:
            furniture[name]["stretch"] = True
    floors = papers(layout)
    return {
        "parallax": PARALLAX,
        "times": TIMES,
        "streets": {
            street: {
                name: f"layers/{getattr(STREETS[street], name)}"
                for name in ("sky", "far", "mid", "near", "ground", "foreground")
            }
            for street in sorted(layout.streets)
        },
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
        "slab": SLAB.key,
    }
