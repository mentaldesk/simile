"""High Street and the coffee shop's pieces in one style, painted, cut and scaled by #309's own
`Build`, with this study's references, prompts and front plans.

`python scenery.py <style> [glob …]` builds out/<style>/papercraft/ and its manifest, under the
game's keys, so `simile.papercraft.preview` composes it unchanged.
"""

import dataclasses
import fnmatch
import sys
import time
import zlib

import numpy as np
from common import OUT, REFS, STYLES, Style, log, styled, wait_for_gpu
from PIL import Image, ImageDraw

from simile.papercraft import build as pipeline
from simile.papercraft import cutout
from simile.papercraft import painter as painting
from simile.papercraft.build import Build, digest
from simile.papercraft.catalogue import NOTHING_BUT_PLANTS, SIDE_SPRITE, SPRITE, STRIP, Item
from simile.papercraft.catalogue import Painting as Piece
from simile.papercraft.fronts import GREY, Front, Plan, backdrop, unit_plans, units
from simile.papercraft.layout import load_layout
from simile.papercraft.painter import EditPainter
from simile.papercraft.sketches import SKETCHES
from simile.papercraft.village import Look, front

STREET = "high_street"
HOUSE = "coffee_shop"
PLAN = 1
"""Bump when `modernised` changes, to repaint the fronts."""
FRONT_REFS: tuple[str, ...] = ()
"""Style images for the fronts. #309 paints them from the plan alone."""
RESEEDS = {"cartoon/fronts/coffee_shop": 2}
"""`<style>/<key>` to a reseed, for a front painted again after a look."""

DARK = (52, 56, 62)
GLASS = (120, 150, 170)
BLIND = (226, 222, 212)
LIT = (240, 230, 204)
AC = (214, 216, 218)
LEAF = (78, 140, 84)

LOOKS = {
    "coffee_shop": Look(
        "a three-storey corner coffee shop clad in pale mint glazed tiles",
        (186, 214, 204),
        DARK,
        (96, 100, 108),
        "flat",
        shop=(70, 196, 176),
        flower_boxes=(72, 76, 84),
        glass_door=True,
        window=(1.6, 1.4),
        one_shop=True,
    ),
    "corner_shop": Look(
        "a three-storey corner convenience store of pale grey concrete",
        (190, 194, 198),
        DARK,
        (96, 100, 108),
        "flat",
        shop=(246, 132, 60),
        glass_door=True,
        window=(1.6, 1.4),
        mural_words=True,
    ),
    "maker_space": Look(
        "a three-storey maker space in a converted factory of charcoal-painted brick with big "
        "black steel-framed windows",
        (104, 108, 116),
        (38, 40, 44),
        (80, 84, 90),
        "flat",
        shop=(246, 204, 64),
        flower_boxes=(56, 60, 66),
        glass_door=True,
        window=(1.8, 1.6),
    ),
    "noodle_bar": Look(
        "a two-storey noodle shop clad in warm white tiles",
        (232, 226, 214),
        DARK,
        (96, 100, 108),
        "flat",
        shop=(214, 64, 56),
        lanterns=4,
        glass_door=True,
        window=(1.6, 1.4),
    ),
}
PICTOGRAMS = {
    "coffee_shop": "coffee cup",
    "corner_shop": "shopping basket",
    "maker_space": "gear",
    "noodle_bar": "noodle bowl",
}
COLOURS = {
    "coffee_shop": "teal",
    "corner_shop": "orange",
    "maker_space": "yellow",
    "noodle_bar": "red",
}


def leads(style: Style) -> dict[str, str]:
    return {
        "lead": f"Make a new picture in exactly the {style.name} style of the reference picture: ",
        "redraw": (
            "Redraw image 1 as {subject}, " + style.made + " of image 2: " + style.finish + ". "
            "Keep every shape exactly where it is, with the same outlines and colours, seen "
            "exactly from the side with no perspective, on a plain {back} background, and no "
            "shadow on the background."
        ),
        "paper": (
            f"Make a flat texture in the colours and {style.name} style of the reference "
            "picture, showing none of its objects: "
        ),
    }


TEXTURE = {
    "papercraft": (
        "A flat photo, taken from directly above, of a sheet of patterned craft paper that fills "
        "the whole frame edge to edge: {}. Visible paper fibres, even soft light, no objects, no "
        "edges."
    ),
    "cartoon": (
        "A flat hand-drawn texture that fills the whole frame edge to edge: {}. Drawn with dark "
        "outlines and flat colours, even light, no objects, no edges."
    ),
}

LAYERS = {
    "sky": (
        "paper",
        "A plain sky backdrop: a smooth gradient from pale warm haze near the bottom to clear "
        "soft blue at the top, with five soft clouds. Only sky: no ground, no buildings, no "
        "towers, no trees, no birds, no drones.",
        (1536, 768),
        12.0,
    ),
    "far-hills": (
        "layer",
        "A long strip of a distant city skyline: slim glass skyscrapers and office towers of "
        "different heights in pale misty blue-grey, with soft green hills between them, lying on "
        "a plain flat white background with white space above and below it.",
        (1536, 512),
        5.0,
    ),
    "mid-shophouses": (
        "strip",
        "A long row of distant mid-rise apartment blocks and offices of pale concrete and glass, "
        "with rooftop gardens, solar panels and air-conditioning units, and the round crowns of "
        "banyan trees between them, faded and hazy, all standing on one straight baseline, on a "
        "plain flat white background with white space above them. No people, no signs.",
        (1536, 640),
        9.0,
    ),
    "near-walls": (
        "strip",
        "A long low run of pale concrete planters, seen straight from the front, full of lush "
        "tropical plants, clipped hedges, young palms and magenta bougainvillea, with a slim "
        f"modern railing behind them, {STRIP}",
        (1536, 512),
        2.2,
    ),
    "ground-street": (
        "ground",
        "A long horizontal strip of city street seen exactly from the side: a pale grey paved "
        "footpath with a yellow strip of tactile paving on top, a granite kerb edge, and a band "
        "of dark grey asphalt road with a green painted cycle lane below, running from the left "
        "edge of the frame to the right edge, on a plain flat medium grey background.",
        (1536, 384),
        2.6,
    ),
    "ground-plaza": (
        "ground",
        "A long horizontal strip of a modern plaza's paving seen exactly from the side: large "
        "pale granite slabs on top with a thin inset line of warm LED lights, a low step edge, "
        "and a band of pale grey stone below, running from the left edge of the frame to the "
        "right edge, on a plain flat medium grey background.",
        (1536, 384),
        2.6,
    ),
    "front-plants": (
        "strip",
        "A long low row of big leafy tropical plants, ferns and banana leaves in dark green, "
        f"{STRIP} No flowers, no pots.",
        (1536, 512),
        2.0,
    ),
}
PAPERS = {
    "cafe-panelling": "pale oak wall panelling in narrow vertical slats",
    "cafe-tiles": "white rectangular wall tiles in a neat stacked grid with pale grey grout",
    "plaster-cream": "smooth pale warm grey plaster with a soft mottled texture",
}
SLAB = {
    "papercraft": "the cut edge of thick corrugated brown cardboard, a long band",
    "cartoon": "the cut edge of a pale grey concrete floor slab, a long band with a dark outline",
}

INTERIOR, SIGNAGE, STREET_REF = "interior", "signage", "street"
FURNITURE: dict[str, Item] = {
    "kitchen": Item(
        "a fitted modern kitchen run, twice as wide as it is tall: handleless matt white base "
        "cupboards under a light oak worktop, with a black induction hob and a steel sink with "
        "a tall tap set into it. No wall cupboards, nothing above the worktop",
        0.95,
        (1024, 512),
        stretch=True,
        ref=INTERIOR,
    ),
    "sofa": Item(
        "a low modern three-seat sofa upholstered in soft sage-green fabric with slim black "
        "metal legs",
        0.85,
        (768, 512),
        ref=INTERIOR,
    ),
    "bed": Item(
        "a low modern bed seen from the side, a pale oak frame with a padded grey headboard on "
        "the left, a white duvet and a mustard-yellow throw",
        1.05,
        (896, 512),
        side=True,
        ref=INTERIOR,
    ),
    "wardrobe": Item(
        "a tall modern wardrobe with two flat handleless doors of pale oak", 2.0, (512, 768)
    ),
    "bookshelf": Item(
        "a tall open shelf unit of black metal and pale wood, with books, a small plant and a "
        "little speaker on it",
        1.9,
        (512, 896),
    ),
    "table": Item(
        "a small round white dining table on a pale wood pedestal, with a moulded coral-red "
        "chair at each side, the chairs facing the table",
        0.95,
        (896, 512),
        side=True,
        cut=("shadows", "gaps"),
    ),
    "plant": Item("a big leafy monstera plant in a white ceramic pot", 1.1, (512, 640)),
    "counter": Item(
        "a modern cafe counter with a front of pale oak slats and a white stone top, with a "
        "small card reader and a glass pastry case with cakes and croissants on top",
        1.25,
        (1008, 448),
        stretch=True,
    ),
    "espresso_machine": Item(
        "a sleek stainless steel espresso machine with two group heads and little cups on top, "
        "standing on a low cupboard of pale oak",
        1.55,
        (512, 768),
    ),
    "grinder": Item(
        "a matt black coffee grinder with a glass hopper full of beans, standing on a low "
        "cupboard of pale oak",
        1.4,
        (512, 768),
    ),
    "menu_board": Item(
        "a wide flat wall-mounted screen glowing with simple pictures of a coffee cup, a "
        "croissant and a leaf, and nothing else",
        1.0,
        (1104, 416),
        grey=True,
    ),
    "bar_counter": Item(
        "a long bar counter seen from the customers' side, three times as wide as it is tall: "
        "a narrow white stone top, a front of pale oak slats and a thin strip of warm light "
        "along the bottom",
        1.1,
        (1024, 384),
        stretch=True,
    ),
    "cafe_table": Item(
        "a small round cafe table with a white top and a slim black metal pedestal, with a "
        "moulded plywood chair at each side facing the table",
        0.95,
        (896, 512),
        side=True,
        grey=True,
        cut=("shadows", "gaps"),
    ),
    "bench": Item(
        "a modern street bench of pale wooden slats on two concrete blocks, seen straight from "
        "the front",
        0.9,
        (896, 512),
        ref=STREET_REF,
    ),
    "news_terminal": Item(
        "a public smart kiosk: a slim upright stand of teal-painted metal with a big blank "
        "glowing screen and a small solar panel on top",
        2.2,
        (512, 1024),
        ref=STREET_REF,
        cut=("tinted shadows",),
    ),
    "fountain": Item(
        "a low round modern fountain of pale granite with three jets of water splashing into "
        "its basin",
        2.2,
        (896, 768),
        ref=STREET_REF,
    ),
    "lamp": Item(
        "a slim modern LED street lamp on a tall dark grey pole with a small solar panel",
        3.6,
        (512, 1024),
        ref=STREET_REF,
    ),
}
PLATFORMS: dict[str, Item] = {
    "stairs": Item(
        "a straight modern staircase of pale oak treads on a black steel frame, rising one "
        "storey to the right, with a thin black metal handrail",
        5.3,
        ref=INTERIOR,
        sketch="stairs",
        folder="platforms",
    ),
    "window": Item(
        "a modern window with a slim black metal frame and a pale roller blind half down, seen "
        "from inside a room",
        1.3,
        (512, 640),
        grey=True,
        ref=INTERIOR,
        folder="platforms",
    ),
}


def layer(key: str, kind, subject: str, size, height: float, style: Style) -> Piece:
    if key.startswith(("near-", "front-")):
        subject += NOTHING_BUT_PLANTS
    prompt = styled(leads(style)["lead"] + subject, style)
    return Piece(f"layers/{key}", kind, prompt, size, (STREET_REF,), height)


def paper(key: str, pattern: str, style: Style, size=(768, 512), **kw) -> Piece:
    prompt = styled(leads(style)["paper"] + TEXTURE[style.name].format(pattern), style)
    return Piece(f"papers/{key}", "paper", prompt, size, (INTERIOR,), **kw)


def item(name: str, spec: Item, style: Style) -> Piece:
    key = f"{spec.folder}/{name}"
    if spec.sketch:
        sketch = SKETCHES[spec.sketch]()
        back = "medium grey" if sketch.getpixel((0, 0)) == GREY else "white"
        prompt = styled(leads(style)["redraw"].format(subject=spec.subject, back=back), style)
        return Piece(
            key, "sprite", prompt, sketch.size, (spec.ref,), spec.height, sketch=spec.sketch
        )
    ref = INTERIOR if spec.ref == "furniture" else spec.ref
    backdrop_text = SIDE_SPRITE if spec.side else SPRITE
    if spec.grey:
        backdrop_text = backdrop_text.replace("plain flat white", "plain flat medium grey")
    prompt = styled(leads(style)["lead"] + f"2D game asset: {spec.subject}. {backdrop_text}", style)
    return Piece(
        key, "sprite", prompt, spec.size, (ref,), spec.height, reseed=spec.reseed, cut=spec.cut
    )


MURAL_WORDS = (
    " The wide plain stretch of wall on the {side} is a blank wall kept for a mural: leave it "
    "smooth and empty, with no windows, no doors, no plants and nothing on it."
)


def front_prompt(building: str, unit: Front, style: Style) -> str:
    look = LOOKS[building]
    extras = ["big glass windows in slim dark frames with pale roller blinds"]
    parts = ["the walls", "the flat roof", "every window"]
    if look.flower_boxes:
        extras.append("planters full of plants under the upper windows")
        parts.append("the planters")
    if any(box[1] > unit.storey for box in unit.window_boxes()):
        extras.append("air-conditioning units on the wall")
        parts.append("the air-conditioning units")
    if unit.shop_boxes():
        extras.append(
            f"a plain glowing {COLOURS[building]} light band over the shopfront, and a glowing "
            f"neon {PICTOGRAMS[building]} pictogram in the shop window"
        )
        parts += ["the light band", "the big shop window", "the neon pictogram"]
    elif unit.awnings:
        parts.append("the slim canopies over the windows")
    if unit.lanterns:
        extras.append("round red paper lanterns")
        parts.append("the lanterns")
    if unit.door is not None:
        extras.append("a glass door")
        parts += ["the glass door", "the small round wall light", "the potted plants"]
    ground = "grey" if backdrop(unit) == GREY else "white"
    rules = ""
    if unit.murals and look.mural_words:
        x0, _, x1, _ = unit.murals[0]
        middle = (x0 + x1) / 2 / unit.width
        side = "left" if middle < 0.4 else "right" if middle > 0.6 else "middle"
        rules = MURAL_WORDS.format(side=side)
    elif unit.murals:
        rules = " Leave the blank stretches of wall plain, with nothing on them."
    if unit.door is None:
        rules += " This part of the building has no door."
    return styled(
        f"Redraw image 1 as the front of {look.look}, a contemporary building with a flat roof, "
        f"{', '.join(extras)}, {style.made}: {style.finish}. Keep every shape exactly where it "
        f"is, with the same outlines and colours: {', '.join(parts)}. Seen straight from the "
        f"front, a flat elevation with no perspective, on a plain {ground} background.{rules} "
        "No people, no words.",
        style,
    )


def modernised(plan: Plan, f: Front) -> Plan:
    """`plan` with today's details drawn over #309's: slim dark window frames with blinds
    instead of curtains and sills, a light band instead of each striped awning, a lit shop
    window with a neon ring for the pictogram, and air-conditioning units."""
    image = plan.image.copy()
    pen = ImageDraw.Draw(image)
    ppm = plan.ppm

    def px(box):
        x0, y0, x1, y1 = box
        return (
            plan.left + x0 * ppm,
            plan.ground - y1 * ppm,
            plan.left + x1 * ppm,
            plan.ground - y0 * ppm,
        )

    def rect(box, fill):
        pen.rectangle(px(box), fill=fill)

    windows = f.window_boxes()
    canopies = [w for w in windows if f.awnings and w[1] < f.storey]
    for x0, _, x1, y1 in canopies:
        rect((x0 - 0.35, y1 - 0.2, x1 + 0.35, y1 + 0.7), f.wall)
    for x0, _, x1, y1 in f.shop_boxes():
        rect((x0 - 0.3, y1 - 0.2, x1 + 0.3, y1 + 0.7), f.wall)
    for x0, y0, x1, y1 in windows:
        rect((x0 - 0.17, y0 - 0.32, x1 + 0.17, y1 + 0.22), f.wall)
        rect((x0 - 0.06, y0 - 0.06, x1 + 0.06, y1 + 0.06), DARK)
        rect((x0, y0, x1, y1), GLASS)
        rect((x0, y1 - 0.3 * (y1 - y0), x1, y1), BLIND)
        middle = (x0 + x1) / 2
        rect((middle - 0.03, y0, middle + 0.03, y1), DARK)
        if f.flower_boxes and y0 > f.storey:
            rect((x0 - 0.12, y0 - 0.3, x1 + 0.12, y0 - 0.06), f.flower_boxes)
            for i, lx in enumerate(np.arange(x0, x1 + 0.01, 0.28)):
                r = 0.16 if i % 2 else 0.12
                pen.ellipse(px((lx - r, y0 - 0.1 - r, lx + r, y0 - 0.1 + r)), fill=LEAF)
    for x0, _, x1, y1 in canopies:
        rect((x0 - 0.3, y1 + 0.12, x1 + 0.3, y1 + 0.26), DARK)
    for x0, y0, x1, y1 in f.shop_boxes():
        rect((x0, y0, x1, y1), DARK)
        rect((x0 + 0.1, y0 + 0.1, x1 - 0.1, y1 - 0.08), LIT)
        panes = max(2, round((x1 - x0) / 1.6))
        for i in range(1, panes):
            x = x0 + (x1 - x0) * i / panes
            rect((x - 0.04, y0, x + 0.04, y1), DARK)
        middle = x0 + (x1 - x0) * (panes // 2 + 0.5) / panes
        if panes % 2:
            middle = (x0 + x1) / 2
        ring = (middle - 0.36, (y0 + y1) / 2 - 0.36, middle + 0.36, (y0 + y1) / 2 + 0.36)
        pen.ellipse(px(ring), outline=f.shop, width=max(2, round(0.07 * ppm)))
        rect((x0 - 0.25, y1 + 0.02, x1 + 0.25, y1 + 0.62), DARK)
        rect((x0 - 0.15, y1 + 0.12, x1 + 0.15, y1 + 0.52), f.shop)
    clear = [(w[0] - 0.2, w[1], w[2] + 0.2, w[3]) for w in windows] + list(f.murals)
    for i, (_, y0, x1, _) in enumerate(w for w in windows if w[1] > f.storey):
        box = (x1 + 0.3, y0 + 0.15, x1 + 1.05, y0 + 0.7)
        inside = box[2] < f.width - 0.25
        if i % 2 or not inside or any(_overlaps(box, c) for c in clear):
            continue
        rect(box, AC)
        r = 0.2
        cx, cy = box[0] + 0.28, (box[1] + box[3]) / 2
        pen.ellipse(px((cx - r, cy - r, cx + r, cy + r)), fill=(150, 154, 160))
    a = np.asarray(image, dtype=np.int16)
    drawn = (np.abs(a - np.array(backdrop(f))).max(axis=2) > 6).astype(np.uint8) * 255
    shape = Image.fromarray(np.maximum(drawn, np.asarray(plan.shape)))
    return dataclasses.replace(plan, image=image, shape=shape)


def _overlaps(a, b) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


class StudyBuild(Build):
    """#309's build, with this study's looks and modernised plans for the fronts."""

    def front(self, piece: Piece) -> Front:
        building = piece.building or ""
        return front(self.layout.facades[building], LOOKS[building])

    def units(self, piece: Piece) -> tuple[tuple[float, Plan], ...]:
        f = self.front(piece)
        parts = [unit for _, unit in units(f)]
        return tuple(
            (x, modernised(plan, unit))
            for (x, plan), unit in zip(unit_plans(f), parts, strict=True)
        )

    def paint_hash(self, piece: Piece, unit: int | None = None) -> str:
        base = super().paint_hash(piece, unit)
        return digest(base, PLAN) if piece.kind == "front" else base

    def out_hash(self, piece: Piece) -> str:
        base = super().out_hash(piece)
        return digest(base, BAND) if piece.kind == "ground" else base

    def finish(self, piece: Piece) -> dict:
        """#309's finish, with each ground strip cut to its own band."""
        if piece.kind != "ground":
            return super().finish(piece)
        raw = self.raw(piece)
        mask, (x0, x1) = banded(cutout.skyline(self.key(raw)))
        image = cutout.unmix(raw, mask).crop((x0, 0, x1, raw.height))
        image = pipeline.tileable(pipeline.trim_rows(image))
        file = f"{piece.key}.webp"
        pipeline.save_webp(image, self.content / file, pipeline.QUALITY["ground"])
        height = piece.height or image.height / pipeline.PPM
        return {
            "file": file,
            "size": list(image.size),
            "height": round(height, 3),
            "kind": piece.kind,
            "hash": self.out_hash(piece),
        }


BAND = 1
"""Bump when `banded` changes, to cut the ground strips again."""


def banded(mask: Image.Image, slack: float = 0.04) -> tuple[Image.Image, tuple[int, int]]:
    """A ground strip's mask made solid across its own band, from the band's usual top row to its
    usual bottom one, and the columns where the painting fills that band. A slab keyed away with
    the backdrop comes back, and the sloped ends of a slab painted in perspective are cut off."""
    m = np.asarray(mask, dtype=np.uint8)
    solid = m > 128
    h = solid.shape[0]
    any_ = solid.any(axis=0)
    top = np.where(any_, solid.argmax(axis=0), h)
    bottom = np.where(any_, h - 1 - solid[::-1].argmax(axis=0), -1)
    band_top, band_bottom = int(np.median(top[any_])), int(np.median(bottom[any_]))
    reach = round(slack * h)
    full = np.flatnonzero((top <= band_top + reach) & (bottom >= band_bottom - reach))
    x0, x1 = int(full[0]), int(full[-1]) + 1
    out = m.copy()
    out[band_top : band_bottom + 1, x0:x1] = 255
    return Image.fromarray(out), (x0, x1)


class TimedPainter(EditPainter):
    """#309's painter, loaded only when nothing else is using the model memory."""

    def __enter__(self):
        wait_for_gpu()
        start = time.perf_counter()
        out = super().__enter__()
        log({"event": "load", "mode": "edit", "seconds": round(time.perf_counter() - start, 1)})
        return out


def fronts(style: Style, layout) -> list[Piece]:
    out = []
    for building, facade in layout.facades.items():
        if facade.street != STREET:
            continue
        f = front(facade, LOOKS[building])
        prompts = tuple(front_prompt(building, unit, style) for _, unit in units(f))
        size = unit_plans(f)[0][1].image.size
        key = f"fronts/{building}"
        out.append(
            Piece(
                key,
                "front",
                prompts[0],
                size,
                FRONT_REFS,
                f.total_height,
                None,
                building,
                None,
                prompts,
                RESEEDS.get(f"{style.name}/{key}", 0),
            )
        )
    return out


def pieces(style: Style) -> list[Piece]:
    layout = load_layout()
    layers = [layer(key, *spec, style) for key, spec in LAYERS.items()]
    papers = [paper(key, pattern, style) for key, pattern in PAPERS.items()]
    papers.append(paper("slab", SLAB[style.name], style, (1024, 256), height=0.3))
    items = [item(name, spec, style) for name, spec in {**FURNITURE, **PLATFORMS}.items()]
    extra = drift(layout) if style.name == "papercraft" else []
    return [*layers, *papers, *fronts(style, layout), *items, *extra]


DRIFT = ("layers/mid-shophouses", "layers/near-gardens", "furniture/sofa", "furniture/bed")
"""#309's pieces painted from #309's own prompts against this study's references, to see what
the references change on their own."""


def drift(layout) -> list[Piece]:
    from simile.papercraft import catalogue as game

    theirs = {p.key: p for p in game.paintings(layout)}
    renamed = {"furniture": INTERIOR, "house": INTERIOR}
    return [
        dataclasses.replace(
            theirs[key],
            key=f"drift/{key.split('/')[1]}",
            refs=tuple(renamed.get(r, r) for r in theirs[key].refs),
            reseed=theirs[key].seed - zlib.crc32(f"drift/{key.split('/')[1]}".encode()) % 10_000,
        )
        for key in DRIFT
    ]


def builder(style: Style) -> StudyBuild:
    """#309's `Build` reading this style's references and writing under out/<style>/."""
    pipeline.REFERENCES = painting.REFERENCES = REFS / style.name
    return StudyBuild(
        pieces(style),
        content=OUT / style.name / "papercraft",
        cache_dir=OUT / style.name / "cache",
        painter=TimedPainter,
    )


def main(args: list[str]) -> None:
    style, globs = STYLES[args[0]], args[1:]
    build = builder(style)
    started = time.perf_counter()
    report = build.run(lambda key: not globs or any(fnmatch.fnmatch(key, g) for g in globs))
    seconds = sum(report.painted.values())
    print(
        f"{style.name}: painted {len(report.painted)} in {seconds:.0f} s, wrote "
        f"{len(report.written)}, {time.perf_counter() - started:.0f} s in all"
    )


if __name__ == "__main__":
    main(sys.argv[1:])
