"""The village's pieces in one line and one reference set, painted, cut and scaled by #309's own
`Build`, with #329's modernised plans and subjects. The paintings go to the game's own cache,
`~/.cache/simile/papercraft/raw/`, so a piece the repaint keeps word for word costs nothing.

`python pieces.py <line> <refs> [glob …]` builds out/<line>-<refs>/papercraft/ and its manifest,
under the game's keys. #326's references paint only `COMPARED`.
"""

import dataclasses
import fnmatch
import time

import apex
from PIL import Image, ImageDraw
from study import LINES, OUT, REFERENCE_SETS, Line, args, log, study2, styled, wait_for_gpu

from simile.papercraft import build as pipeline
from simile.papercraft import cutout
from simile.papercraft import painter as painting
from simile.papercraft.build import Build, digest, outline_mask
from simile.papercraft.catalogue import CARTOON_LEAD, NOTHING_BUT_PLANTS, SIDE_SPRITE, SPRITE, Item
from simile.papercraft.catalogue import Painting as Piece
from simile.papercraft.fronts import GREY, Front, Plan, backdrop, draw, plan_ppm, unit_plans, units
from simile.papercraft.painter import EditPainter
from simile.papercraft.sketches import SKETCHES
from simile.papercraft.village import Look, front

S2 = study2("scenery")
DOCS = OUT.parent.parent
PLAN = 1
"""Bump when `lit` or #329's `modernised` changes, to repaint the fronts."""
BUILDINGS = ("house_1", "coffee_shop", "maker_space")
LOOKS = {
    "house_1": Look(
        "a two-storey family townhouse of dusty pink render",
        (214, 156, 158),
        S2.DARK,
        (96, 100, 108),
        "flat",
        flower_boxes=(72, 76, 84),
        glass_door=True,
        window=(1.6, 1.4),
    ),
    "coffee_shop": S2.LOOKS["coffee_shop"],
    "maker_space": S2.LOOKS["maker_space"],
}
RESEEDS = {"a-326/layers/mid-shophouses": 1}
"""`<line>-<refs>/<key>` to a reseed, for a piece painted again after a look."""
ON_GREY = {"furniture/kitchen", "layers/mid-shophouses"}
"""Painted on grey in every build, since their white parts went with a white backdrop."""

INTERIOR, STREET = "interior", "street"
TEXTURE = {
    "a": "A flat hand-drawn texture that fills the whole frame edge to edge: {}. Drawn with "
    "smooth, even dark ink lines and flat colours, clean, even light, no objects, no edges.",
    "b": "A flat hand-drawn texture that fills the whole frame edge to edge: {}. Drawn with "
    "scratchy dark ink lines and flat colours, even light, no objects, no edges.",
}
SLAB = {
    "a": "the cut edge of a pale grey concrete floor slab, a long band with a smooth dark outline",
    "b": "the cut edge of a pale grey concrete floor slab, a long band with a scratchy dark "
    "outline",
}
CITY = (
    "A long strip of a distant modern city skyline seen from far away: a dense row of glass "
    "skyscrapers and office towers of many different heights and widths, in pale misty "
    "blue-grey and soft teal, with flat roofs, a few construction cranes and no single tower far "
    "taller than the rest, all standing on one straight baseline, lying on a plain flat white "
    "background with white space above it. No people, no signs."
)
LAYERS = {
    "sky": S2.LAYERS["sky"],
    "city": ("layer", CITY, (1536, 640), 10.0),
    "mid-shophouses": S2.LAYERS["mid-shophouses"],
    "ground-street": S2.LAYERS["ground-street"],
    "near-walls": S2.LAYERS["near-walls"],
}
"""The near layer isn't one the issue asks for, but without it the composites show sky under
the mid layer, which sits 2.75 m up."""
FURNITURE: dict[str, Item] = {
    **{k: S2.FURNITURE[k] for k in ("sofa", "kitchen", "bed", "wardrobe", "table", "plant")},
    "cafe_table": S2.FURNITURE["cafe_table"],
    "bench": Item(
        "a modern street bench with a backrest, of pale wooden slats on slim dark grey steel "
        "legs, seen straight from the front",
        0.9,
        (896, 512),
        ref=STREET,
    ),
    "stool": Item(
        "a knee-high modern bar stool with a thick round padded seat of teal fabric, a slim "
        "black steel stem and a ring footrest",
        0.7,
        (384, 640),
    ),
    "picture_frame": Item(
        "an empty picture frame of pale oak around a plain cream canvas, hung on a wall, seen "
        "straight from the front",
        0.9,
        (768, 640),
        grey=True,
    ),
    "metro_entrance": Item(
        "a small modern metro station entrance seen straight from the front: a slim curved "
        "canopy of glass on dark grey steel posts over a doorway where a stairway goes down, "
        "with a small round glowing sign showing a simple train pictogram on top of the canopy",
        2.3,
        (512, 896),
        ref=STREET,
    ),
}
PLATFORMS: dict[str, Item] = {
    "stairs": S2.PLATFORMS["stairs"],
    "window": S2.PLATFORMS["window"],
    "door": Item(
        "a plain modern interior door of pale oak in a slim white frame, with a slim black handle",
        2.1,
        (512, 896),
        grey=True,
        ref=INTERIOR,
        folder="platforms",
    ),
}
DIRTY_ENTRANCE = Item(
    FURNITURE["metro_entrance"].subject + ", a little worn",
    2.3,
    (512, 896),
    ref="../content/papercraft/references/cartoon/street",
)
"""The metro entrance in the metro's own style, a little dirty, from the metro's references."""
COMPARED = (
    "layers/sky",
    "layers/city",
    "layers/mid-shophouses",
    "layers/ground-street",
    "furniture/sofa",
    "furniture/bed",
    "furniture/bench",
    "furniture/kitchen",
)
"""What #326's references paint, to compare with the new ones."""


def leads(line: Line) -> dict[str, str]:
    return {
        "lead": f"Make a new picture in exactly the {line.called} style of the reference picture: ",
        "redraw": (
            "Redraw image 1 as {subject}, " + line.made + " of image 2: " + line.finish + ". "
            "Keep every shape exactly where it is, with the same outlines and colours, seen "
            "exactly from the side with no perspective, on a plain {back} background, and no "
            "shadow on the background."
        ),
        "paper": (
            f"Make a flat texture in the colours and {line.called} style of the reference "
            "picture, showing none of its objects: "
        ),
    }


class Pieces:
    """Every piece in one line, painted from one reference set."""

    def __init__(self, line: Line, refs: str) -> None:
        self.line, self.refs = line, refs
        self.name = f"{line.name}-{refs}"
        self.folder = REFERENCE_SETS[refs].format(line=line.name)

    def ref(self, scene: str) -> str:
        return scene if scene.startswith("..") else f"{self.folder}/{scene}"

    def reseed(self, key: str, base: int = 0) -> int:
        return RESEEDS.get(f"{self.name}/{key}", base)

    def layer(self, key: str, kind, subject: str, size, height: float) -> Piece:
        if key.startswith(("near-", "front-")):
            subject += NOTHING_BUT_PLANTS
        if f"layers/{key}" in ON_GREY:
            subject = subject.replace("plain flat white", "plain flat medium grey")
        prompt = styled(leads(self.line)["lead"] + subject, self.line)
        refs = (self.ref(STREET),)
        return Piece(
            f"layers/{key}", kind, prompt, size, refs, height, reseed=self.reseed(f"layers/{key}")
        )

    def paper(self, key: str, pattern: str, size=(768, 512), **kw) -> Piece:
        texture = TEXTURE[self.line.name].format(pattern)
        prompt = styled(leads(self.line)["paper"] + texture, self.line)
        return Piece(f"papers/{key}", "paper", prompt, size, (self.ref(INTERIOR),), **kw)

    def item(self, name: str, spec: Item, key: str | None = None) -> Piece:
        key = key or f"{spec.folder}/{name}"
        ref = self.ref(INTERIOR if spec.ref == "furniture" else spec.ref)
        if spec.sketch:
            sketch = SKETCHES[spec.sketch]()
            back = "medium grey" if sketch.getpixel((0, 0)) == GREY else "white"
            prompt = leads(self.line)["redraw"].format(subject=spec.subject, back=back)
            return Piece(
                key,
                "sprite",
                styled(prompt, self.line),
                sketch.size,
                (ref,),
                spec.height,
                sketch=spec.sketch,
                reseed=self.reseed(key),
            )
        backdrop_text = SIDE_SPRITE if spec.side else SPRITE
        if spec.grey or key in ON_GREY:
            backdrop_text = backdrop_text.replace("plain flat white", "plain flat medium grey")
        subject = f"2D game asset: {spec.subject}. {backdrop_text}"
        return Piece(
            key,
            "sprite",
            styled(leads(self.line)["lead"] + subject, self.line),
            spec.size,
            (ref,),
            spec.height,
            reseed=self.reseed(key, spec.reseed),
            cut=spec.cut,
        )

    def apex(self, name: str) -> Piece:
        key = f"apex/{name}"
        prompt = (
            f"Redraw image 1 as the headquarters of a rich biotech company seen from far away "
            f"across a city: {apex.SUBJECTS[name]}, of dark blue-green glass and white steel, "
            f"{self.line.made}: {self.line.finish}. Keep every shape exactly where it is, with the "
            "same outlines and colours, seen straight from the front with no perspective, on a "
            "plain white background, and no shadow on the background. No other buildings, no "
            "clouds."
        )
        sketch = f"apex_{name}"
        size = SKETCHES[sketch]().size
        return Piece(
            key,
            "sprite",
            styled(prompt, self.line),
            size,
            (),
            apex.HEIGHT,
            sketch=sketch,
            cut=("outline",),
            reseed=self.reseed(key),
        )

    def fronts(self, layout) -> list[Piece]:
        out = []
        for building in BUILDINGS:
            f = front(layout.facades[building], LOOKS[building])
            parts = [unit for _, unit in units(f)]
            days = tuple(front_prompt(building, unit, self.line) for unit in parts)
            nights = tuple(night_prompt(building, unit, self.line) for unit in parts)
            size = unit_plans(f)[0][1].image.size
            key, glow = f"fronts/{building}", f"glow/{building}"
            reseed = self.reseed(key)
            out.append(
                Piece(
                    key,
                    "front",
                    days[0],
                    size,
                    (),
                    f.total_height,
                    None,
                    building,
                    None,
                    days,
                    reseed,
                )
            )
            out.append(
                Piece(
                    glow, "glow", nights[0], size, (), f.total_height, key, building, None, nights
                )
            )
        return out

    def all(self, layout) -> list[Piece]:
        layers = [self.layer(key, *spec) for key, spec in LAYERS.items()]
        papers = [
            self.paper("plaster-cream", S2.PAPERS["plaster-cream"]),
            self.paper("slab", SLAB[self.line.name], (1024, 256), height=0.3),
        ]
        items = [self.item(n, s) for n, s in {**FURNITURE, **PLATFORMS}.items()]
        towers = [self.apex(name) for name in apex.SILHOUETTES]
        out = [*layers, *papers, *self.fronts(layout), *items, *towers]
        if self.line.name == "a" and self.refs == "new":
            out.append(dirty_entrance())
        if self.refs == "326":
            out = [p for p in out if p.key in COMPARED]
        return out


def dirty_entrance() -> Piece:
    """The metro entrance as the game paints the tunnels' furniture."""
    spec = DIRTY_ENTRANCE
    prompt = painting.cartoon(CARTOON_LEAD + f"2D game asset: {spec.subject}. {SPRITE}")
    key = "furniture/metro_entrance-dirty"
    return Piece(key, "sprite", prompt, spec.size, (spec.ref,), spec.height)


def front_prompt(building: str, unit: Front, line: Line) -> str:
    """#329's `front_prompt` in `line`."""
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
            f"a plain glowing {S2.COLOURS[building]} light band over the shopfront, and a glowing "
            f"neon {S2.PICTOGRAMS[building]} pictogram in the shop window"
        )
        parts += ["the light band", "the big shop window", "the neon pictogram"]
    elif unit.awnings:
        parts.append("the slim canopies over the windows")
    if unit.door is not None:
        extras.append("a glass door")
        parts += ["the glass door", "the small round wall light", "the potted plants"]
    ground = "grey" if backdrop(unit) == GREY else "white"
    rules = " Leave the blank stretches of wall plain, with nothing on them." if unit.murals else ""
    if unit.door is None:
        rules += " This part of the building has no door."
    return styled(
        f"Redraw image 1 as the front of {look.look}, a contemporary building with a flat roof, "
        f"{', '.join(extras)}, {line.made}: {line.finish}. Keep every shape exactly where it "
        f"is, with the same outlines and colours: {', '.join(parts)}. Seen straight from the "
        f"front, a flat elevation with no perspective, on a plain {ground} background.{rules} "
        "No people, no words.",
        line,
    )


def night_prompt(building: str, unit: Front, line: Line) -> str:
    lit = ["every window"]
    if unit.shop_boxes():
        lit += ["the shop window", "the light band", "the neon pictogram"]
    if unit.door is not None:
        lit += ["the glass door", "the wall light"]
    ground = "grey" if backdrop(unit) == GREY else "white"
    return styled(
        f"The same picture at night: warm yellow light glows from {', '.join(lit)}, the walls "
        f"are in deep blue shadow, and the background stays plain {ground}. Keep every shape "
        "exactly where it is, and add nothing.",
        line,
    )


def lit(plan: Plan, f: Front) -> Plan:
    """#329's modernised plan, with its light bands added to what glows at night."""
    plan = S2.modernised(plan, f)
    glow = plan.glow.copy()
    pen = ImageDraw.Draw(glow)
    for x0, _, x1, y1 in f.shop_boxes():
        box = (x0 - 0.15, y1 + 0.12, x1 + 0.15, y1 + 0.52)
        pen.rectangle(
            (
                plan.left + box[0] * plan.ppm,
                plan.ground - box[3] * plan.ppm,
                plan.left + box[2] * plan.ppm,
                plan.ground - box[1] * plan.ppm,
            ),
            fill=255,
        )
    return dataclasses.replace(plan, glow=glow)


class StudyBuild(Build):
    """#309's build, with this study's looks, lit modernised plans, banded ground and the
    Apex's lights."""

    def front(self, piece: Piece) -> Front:
        return front(self.layout.facades[piece.building or ""], LOOKS[piece.building or ""])

    def units(self, piece: Piece) -> tuple[tuple[float, Plan], ...]:
        parts = units(self.front(piece))
        ppm = min(plan_ppm(unit) for _, unit in parts)
        return tuple((x, lit(draw(unit, ppm), unit)) for x, unit in parts)

    def plan(self, piece: Piece) -> Plan:
        return draw(self.front(piece), self.units(piece)[0][1].ppm)

    def paint_hash(self, piece: Piece, unit: int | None = None) -> str:
        base = super().paint_hash(piece, unit)
        return digest(base, PLAN) if piece.kind == "front" else base

    def out_hash(self, piece: Piece) -> str:
        base = super().out_hash(piece)
        if piece.kind in ("front", "glow"):
            return digest(base, PLAN)
        return digest(base, S2.BAND) if piece.kind == "ground" else base

    def finish(self, piece: Piece) -> dict:
        if piece.kind == "ground":
            return self.finish_ground(piece)
        entry = super().finish(piece)
        if piece.key.startswith("apex/"):
            entry["glow"] = self.finish_lights(piece, entry)
        return entry

    def finish_ground(self, piece: Piece) -> dict:
        """#329's ground strip, cut to its own band."""
        raw = self.raw(piece)
        mask, (x0, x1) = S2.banded(cutout.skyline(self.key(raw)))
        image = cutout.unmix(raw, mask).crop((x0, 0, x1, raw.height))
        image = pipeline.tileable(pipeline.trim_rows(image))
        file = f"{piece.key}.webp"
        pipeline.save_webp(image, self.content / file, pipeline.QUALITY["ground"])
        return {
            "file": file,
            "size": list(image.size),
            "height": round(piece.height or image.height / pipeline.PPM, 3),
            "kind": piece.kind,
            "hash": self.out_hash(piece),
        }

    def finish_lights(self, piece: Piece, entry: dict) -> str:
        """The Apex's night lights, cut and scaled as its painting was."""
        raw = self.raw(piece)
        shape = pipeline._sketch_shape(piece.sketch)
        mask = outline_mask(raw, shape, round(0.012 * raw.width) | 1, 5)
        alpha = cutout.unmix(raw, mask).getchannel("A")
        box = alpha.getbbox() or (0, 0, *raw.size)
        light = apex.glow(piece.key.split("/")[1], raw).crop(box)
        light = light.resize(tuple(entry["size"]), Image.Resampling.LANCZOS)
        file = f"{piece.key}-glow.webp"
        pipeline.save_webp(light, self.content / file, pipeline.QUALITY["glow"])
        return file


class TimedPainter(EditPainter):
    """#309's painter, loaded only when nothing else is using the model memory."""

    def __enter__(self):
        wait_for_gpu()
        start = time.perf_counter()
        out = super().__enter__()
        log({"event": "load", "mode": "edit", "seconds": round(time.perf_counter() - start, 1)})
        return out


def builder(line: str, refs: str) -> StudyBuild:
    """#309's `Build` reading references from docs/ and writing under out/<line>-<refs>/, with
    the raw paintings in the game's cache."""
    pipeline.REFERENCES = painting.REFERENCES = DOCS
    made = Pieces(LINES[line], refs)
    build = StudyBuild([], content=OUT / made.name / "papercraft", painter=TimedPainter)
    build.pieces = {p.key: p for p in made.all(build.layout)}
    return build


def main(argv: list[str]) -> None:
    line, refs, globs = argv[0], argv[1], argv[2:]
    build = builder(line, refs)
    started = time.perf_counter()

    def note(text: str) -> None:
        print(text, flush=True)
        if text.startswith("  ") and text.endswith("s") and "wrote" not in text:
            name, seconds = text.split()
            log(
                {
                    "event": "paint",
                    "build": f"{line}-{refs}",
                    "key": name,
                    "seconds": float(seconds[:-1]),
                }
            )

    report = build.run(lambda key: not globs or any(fnmatch.fnmatch(key, g) for g in globs), note)
    seconds = sum(report.painted.values())
    print(
        f"{line}-{refs}: painted {len(report.painted)} in {seconds:.0f} s, wrote "
        f"{len(report.written)}, {time.perf_counter() - started:.0f} s in all"
    )


if __name__ == "__main__":
    main(args())
