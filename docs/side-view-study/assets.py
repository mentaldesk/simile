"""Paints every asset the study composites. `python assets.py [group ...]`, from `server/` with
`uv run --extra images`. Paintings are cached in out/raw, so a rerun only paints what's missing."""

import sys
import zlib
from dataclasses import dataclass
from pathlib import Path

from common import OUT, RAW, Painter, residents, small_reference, styled

SPRITE = (
    "Seen straight from the front at eye level, a flat elevation with no perspective. One single "
    "object centred on a plain flat white background with empty space all around it, nothing "
    "else in the picture."
)
SIDE_SPRITE = SPRITE.replace("straight from the front", "exactly from the side")
TEXTURE = (
    "A flat photo, taken from directly above, of a sheet of patterned craft paper that fills the "
    "whole frame edge to edge: {}. Visible paper fibres, even soft light, no objects, no edges."
)
LEAD = "Make a new picture in exactly the papercraft style of the reference picture: "


@dataclass
class Asset:
    name: str
    subject: str
    size: tuple[int, int]
    ref: str | None = None
    twin: bool = False
    """Also paint it from the text alone, to compare with the style-referenced one."""
    height: float = 0.0
    """How tall it stands in the world, in metres, for scaling the cut-out."""


STREET = [
    Asset(
        "sky",
        "A plain sky backdrop made of layered paper: a smooth gradient from pale warm cream near "
        "the bottom to soft blue at the top, with five soft cut-paper clouds. Only sky: no ground, "
        "no hills, no buildings, no trees.",
        (1536, 768),
        "street",
        twin=True,
    ),
    Asset(
        "far",
        "A long strip of distant rolling hills cut from pale sage-green and misty blue-grey paper, "
        "with a few tiny far-off houses and trees on the ridges, lying on a plain flat white "
        "background with white space above and below it.",
        (1536, 512),
        "street",
        twin=True,
    ),
    Asset(
        "mid",
        "A long row of distant two-storey village houses with tiled roofs and the round crowns of "
        "trees between them, cut from faded, hazy paper in muted terracotta, cream and green, all "
        "standing on one straight baseline, on a plain flat white background with white space "
        "above them. Empty streets: no people, no animals.",
        (1536, 640),
        "street",
        twin=True,
    ),
    Asset(
        "ground",
        "A long horizontal strip of street seen exactly from the side, cut from layered "
        "cardboard: a sandy paved footpath on top, a kerb edge, and a band of grey road below, "
        "running from the left edge of the frame to the right edge, on a plain white background.",
        (1536, 384),
        "street",
        twin=True,
    ),
    Asset(
        "cafe",
        "The front of a small two-storey corner cafe with a striped awning, shuttered upstairs "
        "windows and a glass shop door, seen straight from the street. " + SPRITE,
        (768, 896),
        "street",
        twin=True,
        height=8.0,
    ),
    Asset(
        "noodle",
        "The front of a small one-storey noodle bar with a tiled roof, an open serving counter "
        "with steaming bowls of noodles and a row of glowing round paper lanterns under the "
        "eaves. " + SPRITE,
        (768, 768),
        "street",
        twin=True,
        height=5.0,
    ),
    Asset(
        "shophouse",
        "The front of a narrow two-storey shophouse painted pale blue, with wooden shutters, a "
        "small balcony with potted plants and a washing line with clothes. " + SPRITE,
        (768, 896),
        "street",
        twin=True,
        height=8.5,
    ),
    Asset(
        "house",
        "The front of a small two-storey family house painted dusty pink, with a front door, two "
        "windows with flower boxes and a tiled roof. " + SPRITE,
        (768, 896),
        "street",
        twin=True,
        height=8.0,
    ),
    Asset(
        "grocer",
        "The front of a small corner grocery shop with crates of fruit and vegetables outside "
        "under a green awning and a flat roof. " + SPRITE,
        (768, 768),
        "street",
        twin=True,
        height=6.5,
    ),
    Asset(
        "banyan",
        "A large banyan tree with a thick trunk, spreading branches, a broad crown of big paper "
        "leaves and hanging aerial roots. " + SPRITE,
        (768, 1024),
        "street",
        twin=True,
        height=11.0,
    ),
    Asset(
        "lamp",
        "An old dark green iron street lamp on a tall post. " + SPRITE,
        (512, 1024),
        "street",
        twin=True,
        height=3.6,
    ),
    Asset(
        "pot",
        "A big leafy plant in a terracotta pot. " + SPRITE,
        (512, 512),
        "street",
        twin=True,
        height=1.1,
    ),
]

HOUSE = [
    Asset(
        "paper-kitchen",
        TEXTURE.format("pale mint-green square tiles with thin white grout"),
        (768, 512),
    ),
    Asset(
        "paper-living",
        TEXTURE.format("warm ochre wallpaper with a small repeating pattern of cream leaves"),
        (768, 512),
    ),
    Asset(
        "paper-bedroom",
        TEXTURE.format("dusty rose wallpaper with thin vertical cream stripes"),
        (768, 512),
    ),
    Asset("paper-bathroom", TEXTURE.format("light blue square tiles with white grout"), (768, 512)),
    Asset(
        "paper-card",
        TEXTURE.format("the cut edge of thick corrugated brown cardboard, a long horizontal band"),
        (1024, 256),
    ),
    Asset(
        "roof",
        "A long, low pitched dollhouse roof covered in rows of terracotta paper tiles, seen "
        "straight from the front, much wider than it is tall. " + SPRITE,
        (1536, 512),
        "house",
        height=2.2,
    ),
    Asset(
        "stairs",
        "A straight wooden staircase seen exactly from the side, rising from the bottom left to "
        "the top right, with a simple wooden handrail, cut from card. " + SIDE_SPRITE,
        (768, 768),
        "house",
        height=2.9,
    ),
    Asset(
        "window",
        "A window with a wooden frame and cream curtains tied to the sides, seen from inside a "
        "room. " + SPRITE,
        (512, 640),
        "house",
        height=1.3,
    ),
    Asset(
        "door",
        "A plain wooden interior door in its frame. " + SPRITE,
        (512, 896),
        "house",
        height=2.1,
    ),
]

FURNITURE = [
    Asset(
        "sofa",
        "a three-seat sofa upholstered in deep teal velvet with round wooden feet",
        (768, 512),
        height=0.85,
    ),
    Asset(
        "armchair",
        "an armchair upholstered in mustard-yellow fabric with dark wooden legs",
        (768, 768),
        height=0.95,
    ),
    Asset(
        "bookshelf",
        "a tall bookshelf painted white, full of books with colourful spines and a small plant",
        (512, 896),
        height=1.9,
    ),
    Asset(
        "floor-lamp",
        "a floor lamp with a thin brass stand and a pleated cream fabric shade",
        (512, 1024),
        height=1.6,
    ),
    Asset("monstera", "a big leafy monstera plant in a terracotta pot", (640, 768), height=1.1),
    Asset(
        "sideboard",
        "a low wooden sideboard with sliding doors and a record player on top",
        (768, 512),
        height=0.95,
    ),
    Asset(
        "stove",
        "an old-fashioned kitchen stove in cream enamel with black iron hotplates and an oven door",
        (640, 768),
        height=0.95,
    ),
    Asset(
        "counter",
        "a kitchen counter with blue-painted wooden cupboard doors and a white ceramic sink with a "
        "chrome tap",
        (768, 640),
        height=1.05,
    ),
    Asset(
        "fridge",
        "a rounded retro fridge in pale mint metal with a chrome handle",
        (512, 896),
        height=1.7,
    ),
    Asset(
        "dining",
        "a small round wooden dining table with a wooden chair on each side",
        (896, 640),
        height=0.95,
    ),
    Asset(
        "bed",
        "a double bed seen from the side, with a carved wooden headboard on the left and a "
        "patchwork quilt in warm reds and oranges",
        (896, 512),
        height=1.05,
    ),
    Asset(
        "wardrobe",
        "a tall wooden wardrobe painted sage green with two doors and brass knobs",
        (640, 896),
        height=2.0,
    ),
    Asset(
        "bedside",
        "a small wooden bedside table with a little lamp with a round pink shade on it",
        (512, 768),
        height=0.95,
    ),
    Asset(
        "bathtub",
        "a white enamel clawfoot bathtub with brass taps, seen from the side",
        (896, 512),
        height=0.75,
    ),
    Asset(
        "basin",
        "a white ceramic pedestal washbasin with a round mirror hanging on the wall above it",
        (512, 896),
        height=1.8,
    ),
]
WHITE_THINGS = {"bathtub", "basin"}
"""White on white defeats the cut-out, so these are painted on grey."""
for asset in FURNITURE:
    backdrop = SPRITE.replace("white", "medium grey") if asset.name in WHITE_THINGS else SPRITE
    asset.subject = f"2D game asset: {asset.subject}. {backdrop}"
    asset.ref = "furniture"
    asset.twin = True

SWATCHES = {"coral": "coral red", "mustard": "mustard yellow", "plum": "dark plum purple"}

PLATFORMS = [
    Asset(
        "canopy",
        "A background for a side-scrolling level high in the treetops: the leafy crowns of big "
        "banyan trees and a few distant tiled rooftops in soft, hazy colours under a pale sky. "
        "Nothing in the foreground: no platforms, no ladders, no people.",
        (1536, 864),
        "rooftops",
        twin=True,
    ),
    Asset(
        "planks",
        "A long flat wooden walkway of planks with wooden brackets underneath, seen exactly from "
        "the side. " + SIDE_SPRITE,
        (1536, 384),
        "rooftops",
        twin=True,
        height=0.6,
    ),
    Asset(
        "ridge",
        "A small, wide terracotta tiled roof with a flat ridge along the top. " + SPRITE,
        (1024, 512),
        "rooftops",
        twin=True,
        height=1.6,
    ),
    Asset(
        "awning",
        "A striped red and cream fabric shop awning on its own, with no building, wall or "
        "window: a gently sloping canopy on two thin poles, with a scalloped front edge. "
        + SIDE_SPRITE,
        (1024, 384),
        "rooftops",
        twin=True,
        height=0.7,
    ),
    Asset(
        "ladder",
        "A tall wooden ladder standing straight upright. " + SPRITE,
        (512, 1024),
        "rooftops",
        twin=True,
        height=3.0,
    ),
    Asset(
        "plank",
        "One single short wooden plank, a little worn. " + SPRITE,
        (512, 256),
        "rooftops",
        height=0.12,
    ),
]

NIGHT = ["cafe", "noodle", "shophouse", "house", "grocer", "lamp"]

ALL = {a.name: a for a in STREET + HOUSE + FURNITURE + PLATFORMS}


def seed(name: str) -> int:
    return zlib.crc32(name.encode()) % 10_000


def prompt(asset: Asset, referenced: bool) -> str:
    return styled((LEAD if referenced else "") + asset.subject)


def paint(painter: Painter, assets: list[Asset], twins: bool) -> None:
    for asset in assets:
        refs = (
            [small_reference(asset.ref, 512 if asset.ref == "furniture" else 768)]
            if asset.ref
            else None
        )
        painter.paint(asset.name, prompt(asset, bool(refs)), asset.size, seed(asset.name), refs)
    if twins:
        for asset in assets:
            if asset.twin:
                painter.paint(
                    f"{asset.name}-text", prompt(asset, False), asset.size, seed(asset.name)
                )


def swatches(painter: Painter) -> None:
    for name, colour in SWATCHES.items():
        painter.paint(
            f"sofa-{name}",
            styled(
                f"Recolour the sofa's velvet upholstery to {colour}. Keep everything else exactly "
                "the same: the shape, the wooden feet, the paper texture, the white background."
            ),
            ALL["sofa"].size,
            seed("sofa"),
            [RAW / "sofa.png"],
        )


def night(painter: Painter) -> None:
    for name in NIGHT:
        painter.paint(
            f"night-{name}",
            styled(
                "The same picture at night: warm yellow light glows from every window and lamp, "
                "the paper is in deep blue shadow, and the background stays plain white. Keep "
                "every shape exactly where it is."
            ),
            ALL[name].size,
            seed(name),
            [RAW / f"{name}.png"],
        )


def dolls(painter: Painter) -> None:
    import doll
    from common import player_appearance

    people = {**{k: v.appearance for k, v in residents().items()}, "player": player_appearance()}
    for who, appearance in people.items():
        sheet = OUT / "sheets" / f"{who}.png"
        sheet.parent.mkdir(parents=True, exist_ok=True)
        pieces, spots = doll.sheet_pieces(doll.Look.of(appearance, who))
        doll.sheet(pieces, spots, doll.SHEET).save(sheet)
        painter.paint(
            f"doll-{who}",
            styled(
                "Redraw image 1 as paper doll parts cut from coloured paper and card in the style "
                "of the villagers in image 2: paper texture, cut edges, a face drawn on the head "
                "in profile. Keep every piece exactly where it is, with the same outline and "
                "colour, on a plain white background."
            ),
            doll.SHEET,
            seed(who),
            [sheet, small_reference("characters", 768)],
        )


def quantized(bits: int) -> None:
    painter = Painter(bits=bits)
    for name in ("armchair", "cafe"):
        asset = ALL[name]
        painter.paint(f"q{bits}-{name}", prompt(asset, False), asset.size, seed(name))
    painter.unload()


GROUPS = {
    "street": lambda p: paint(p, STREET, True),
    "house": lambda p: paint(p, HOUSE, False),
    "furniture": lambda p: paint(p, FURNITURE, True),
    "swatches": swatches,
    "platforms": lambda p: paint(p, PLATFORMS, True),
    "night": night,
    "dolls": dolls,
}


def main(groups: list[str]) -> None:
    painter = Painter()
    for group in groups or list(GROUPS):
        if group.startswith("q"):
            painter.unload()
            quantized(int(group[1:]))
        else:
            GROUPS[group](painter)
    painter.unload()


if __name__ == "__main__":
    main(sys.argv[1:])
    print(Path(OUT / "timings.jsonl"))
