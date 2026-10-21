"""Residents in each style: #310's doll pipeline with this study's references, and the client's
rig (`client/src/dolls/rig.ts`) ported to Python to pose them.

`python dolls.py <style> [who …]` paints the dolls into out/<style>/dolls/, and
`python dolls.py grimy-plain [who …]` the grimy cartoon's with no outline painted on.
"""

import json
import math
import sys
import tempfile
import time
import zlib
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np
from common import CARTOON, GRIMY, OUT, REFS, STYLES, Style, log, styled, wait_for_gpu
from PIL import Image, ImageFilter

from simile.dolls import build as dolls
from simile.dolls import look as looks
from simile.dolls.paint import EditPainter, back_of_head, person
from simile.papercraft import painter as painting

REPO = Path(__file__).resolve().parents[2]
WHO = ("odalys", "lachlan", "ingrid", "henrietta", "kofi", "priya")
"""Six residents across the `Appearance`s' skins, hair styles and accessories: #295's walkers
and dollhouse residents, and Priya."""
CHUNKY = 1.15
"""The cartoons' bodies are this much wider than #310's, through `Look.width`."""
HEAD = 1.22
"""#326's cartoon heads are drawn this much bigger, about the neck."""
INK = (46, 32, 28)
OUTLINE = 0.9
"""#326's cartoon outline, in units: drawn round each piece in the rig, as the scenery's are
painted."""
REROLLS = {
    "cartoon/odalys/front_back": 1,
    "grimy/odalys/front_back": 1,
    "grimy/kofi/front_back": 1,
    "grimy/lachlan/front_back": 1,
}
"""`<style>/<who>/<sheet>` to a reroll, for a painting that came out off-model."""
PLAIN = "grimy-plain"
"""The grimy cartoon's dolls painted with no outline, for the rig to draw one."""

SHEETS = {
    "cartoon": (
        "the separate body parts of a cartoon game character",
        "four separate flat pieces of a cartoon cut-out puppet, laid apart",
        "hand-drawn in the cartoon style of the residents in image 2: a thick dark brown outline "
        "round every piece, flat colours with simple soft shading",
    ),
    "grimy": (
        "the separate body parts of a cartoon game character",
        "four separate flat pieces of a cartoon cut-out puppet, laid apart",
        "hand-drawn in the scratchy, grimy cartoon style of the residents in image 2: a thick "
        "scratchy, uneven dark brown ink outline round every piece, flat colours with simple "
        "soft shading and a few smudges",
    ),
    PLAIN: (
        "the separate body parts of a cartoon game character",
        "four separate flat pieces of a cartoon cut-out puppet, laid apart",
        "hand-drawn in the grimy cartoon style of the residents in image 2, with no outline "
        "round any piece: flat colours with simple soft shading and a few smudges",
    ),
    "pixel": (
        "the separate body parts of a pixel art game character",
        "four separate flat pieces of a pixel art cut-out puppet, laid apart",
        "drawn as crisp pixel art in the style of the residents in image 2: big square pixels, "
        "a limited palette of flat colours, no anti-aliasing",
    ),
    "flat": (
        "the separate body parts of a flat illustrated game character",
        "four separate flat pieces of a cut-out puppet in flat illustration, laid apart",
        "drawn as a flat modern illustration in the style of the residents in image 2: bold flat "
        "colours, simple geometric shapes, clean edges, no outlines and no texture",
    ),
}
"""#310's prompt in each style's words: the side sheet's subject, the front and back sheet's,
and how they're drawn. Papercraft keeps #310's own."""


def sheet_prompt(variant: str, style: Style):
    side, front_back, how = SHEETS[variant]

    def prompt(sheet: str, appearance, who: str | None) -> str:
        if sheet == "side":
            what, layout = side, "a face drawn on the head in profile."
        else:
            what = front_back
            layout = (
                "the head on the left faces the viewer with the face drawn on it, the head on "
                f"the right is the back of the same head, {back_of_head(appearance)}, and "
                "between them are two flat torso pieces, the front and the back, each a plain "
                "shape with no head, arms or legs on it."
            )
        return styled(
            f"Redraw image 1 as {what}, {how}, {layout} {person(appearance, who)} Keep every "
            "piece exactly where it is, with the same outline and the same colours, and add "
            "nothing to it, on a plain light grey background.",
            style,
        )

    return prompt


class TimedPainter(EditPainter):
    """#310's sheet painter, loaded only when nothing else is using the model memory."""

    def __enter__(self):
        wait_for_gpu()
        start = time.perf_counter()
        out = super().__enter__()
        log({"event": "load", "mode": "edit", "seconds": round(time.perf_counter() - start, 1)})
        return out


def style_of(variant: str) -> Style:
    return GRIMY if variant == PLAIN else STYLES[variant]


@contextmanager
def styled_pipeline(variant: str):
    """#310's `paint()` reading this style's residents reference, with its prompt, rerolls and
    proportions, and for #329's styles without `rimmed()`'s light card edge. Restores the module
    attributes it swaps."""
    from simile.dolls import doll as atlases

    style = style_of(variant)
    saved = (
        painting.REFERENCES,
        dolls.reference,
        dolls.prompt,
        dolls.REROLLS,
        looks.BUILD,
        atlases.rimmed,
    )
    painting.REFERENCES = REFS / style.name
    dolls.reference = lambda name, width=768: painting.reference("residents", width)
    dolls.REROLLS = {
        k.split("/", 1)[1]: v for k, v in REROLLS.items() if k.startswith(f"{variant}/")
    }
    if variant in SHEETS:
        dolls.prompt = sheet_prompt(variant, style)
    if style.name in (CARTOON.name, GRIMY.name):
        looks.BUILD = {k: v * CHUNKY for k, v in looks.BUILD.items()}
    if style.name not in ("papercraft", CARTOON.name):
        atlases.rimmed = lambda piece: piece
    try:
        yield
    finally:
        (
            painting.REFERENCES,
            dolls.reference,
            dolls.prompt,
            dolls.REROLLS,
            looks.BUILD,
            atlases.rimmed,
        ) = saved


def paint(variant: str, who: list[str]) -> None:
    everyone = dolls.people()
    folder = OUT / variant / "dolls"
    model = dolls.Lazy(TimedPainter)
    with styled_pipeline(variant), model.stack, tempfile.TemporaryDirectory() as scratch:
        for name in who:
            painted = dolls.paint(name, everyone[name], model, Path(scratch), folder / "paintings")
            filled = matched(painted.doll)
            appearance = everyone[name].model_dump(mode="json")
            dolls.write(folder, dolls.files(name, painted.doll, appearance=appearance))
            for sheet, seconds in painted.seconds.items():
                key = f"dolls/{variant}/{name}/{sheet}"
                log({"event": "paint", "key": key, "kind": "doll sheet", "seconds": seconds})
            moved = {k: round(v, 3) for k, v in painted.misplaced.items() if v > 0.02}
            added = {k: round(v, 3) for k, v in painted.patches.items() if v > 0.05}
            print(f"{name}: {painted.seconds} moved {moved} added {added} filled {filled}")
            sheets = folder / "sheets"
            sheets.mkdir(parents=True, exist_ok=True)
            for sheet, image in painted.paintings.items():
                image.save(sheets / f"{name}-{sheet}.png")


OFF = 4.5
"""CIEDE2000 a painted colour region may stay from its flat colour, in the atlas, before it's
filled: under the check's 6, since saving the atlas as lossy WebP moves a small region by
up to 2. #326's dolls were filled at 6."""
LUMA = np.array([0.299, 0.587, 0.114])


def matched(doll) -> list[str]:
    """Fills each painted colour region still more than `OFF` from its flat colour with that
    colour, keeping the painting's light and shade, and names them. #310's restore pins only a
    region's median, with each channel's gain capped at 4x, so an ear painted as a dark ring
    round an orange disc stays orange."""
    from simile.dolls.colour import delta_e, hex_of
    from simile.dolls.sheet import regions

    filled = []
    for name, piece in doll.painted.items():
        f = np.asarray(doll.flat[name].image, dtype=np.float64)
        p = np.asarray(piece.image, dtype=np.float64).copy()
        nearest, main, opaque = regions(doll.flat[name].image)
        lum = p[..., :3] @ LUMA
        for i, colour in enumerate(main):
            region = opaque & (nearest == i)
            core = region & (np.abs(f[..., :3] - colour).max(axis=2) < 1)
            if core.sum() < 6 or delta_e(np.median(p[..., :3][core], axis=0), colour) <= OFF:
                continue
            shade = np.clip(lum[region] / max(float(np.median(lum[core])), 1.0), 0.85, 1.15)
            p[..., :3][region] = f[..., :3][region] * shade[:, None]
            filled.append(f"{name} {hex_of(colour)}")
        piece.image = Image.fromarray(np.clip(p, 0, 255).astype(np.uint8), "RGBA")
    return filled


# The rig, ported from client/src/dolls/rig.ts: angles in degrees, y down, pivots in atlas px.

FAR = 0.8
Px = tuple[float, float]
TAU = math.tau


def _swing(v, degrees: float):
    c, s = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
    return (v[0] * c + v[1] * s, -v[0] * s + v[1] * c)


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1])


def _offset(spec: dict, joint: str, scale_y: float = 1.0):
    at, pivot = spec["joints"][joint], spec["pivot"]
    return (at[0] - pivot[0], (at[1] - pivot[1]) * scale_y)


STAND = {
    "lean": 0,
    "nod": 0,
    "thigh": (3, -3),
    "knee": (0, 0),
    "foot": (0, 0),
    "shoulder": (4, -4),
    "elbow": (8, 8),
}
STRAIGHT = {
    "arm": (4, 4),
    "elbow": (0, 0),
    "forearm": (1, 1),
    "leg": (1.5, 1.5),
    "thigh": (1, 1),
    "knee": (0, 0),
}


def walk(phase: float, stride: float = 24, bend: float = 34) -> dict:
    t = TAU * phase

    def leg(t: float):
        thigh = stride * math.sin(t)
        knee = 8 + bend * max(0.0, math.sin(t + 1.9)) ** 1.5
        foot = -thigh + knee + (18 * max(0.0, -math.cos(t + 0.4)) - 6 * max(0.0, math.cos(t)))
        return thigh, knee, foot

    near, far = leg(t), leg(t + math.pi)
    return {
        "lean": 3,
        "nod": 2,
        "thigh": (near[0], far[0]),
        "knee": (near[1], far[1]),
        "foot": (near[2], far[2]),
        "shoulder": (-22 * math.sin(t), 22 * math.sin(t)),
        "elbow": (14 + 10 * max(0.0, -math.sin(t)), 14 + 10 * max(0.0, math.sin(t))),
    }


@dataclass
class Part:
    piece: str
    x: float
    y: float
    angle: float
    """Degrees clockwise, as Phaser turns."""
    scale_y: float = 1.0
    shade: float = 1.0


def place_side(p: dict, a: dict) -> list[Part]:
    parts: list[Part] = []

    def put(piece, at, turn, shade=1.0):
        parts.append(Part(piece, at[0], at[1], -turn, 1.0, shade))

    hip = (0.0, 0.0)
    torso = -a["lean"]
    torso_at = _add(hip, tuple(-v for v in _swing(_offset(p["torso"], "hip"), torso)))
    neck = _add(torso_at, _swing(_offset(p["torso"], "neck"), torso))
    shoulder = _add(torso_at, _swing(_offset(p["torso"], "shoulder"), torso))

    def leg(i: int, shade: float) -> None:
        thigh = a["thigh"][i]
        shin = thigh - a["knee"][i]
        knee = _add(hip, _swing(_offset(p["upper_leg"], "knee"), thigh))
        ankle = _add(knee, _swing(_offset(p["lower_leg"], "ankle"), shin))
        put("upper_leg", hip, thigh, shade)
        put("lower_leg", knee, shin, shade)
        put("shoe", ankle, shin + a["foot"][i], shade)

    def arm(i: int, shade: float) -> None:
        upper = torso + a["shoulder"][i]
        elbow = _add(shoulder, _swing(_offset(p["upper_arm"], "elbow"), upper))
        put("upper_arm", shoulder, upper, shade)
        put("lower_arm", elbow, upper + a["elbow"][i], shade)

    arm(1, FAR)
    leg(1, FAR)
    leg(0, 1.0)
    put("torso", torso_at, torso)
    put("head", neck, torso - a["nod"])
    arm(0, 1.0)
    return parts


def place_straight(p: dict, view: str, a: dict) -> list[Part]:
    torso = p[f"torso_{view}"]
    legs, uppers, forearms = [], [], []
    for i, side in enumerate((-1, 1)):
        name = "left" if side < 0 else "right"
        hip = _offset(torso, f"hip_{name}")
        thigh = side * a["leg"][i]
        knee = _add(hip, _swing(_offset(p["upper_leg"], "knee", a["thigh"][i]), thigh))
        shin = thigh + side * a["knee"][i]
        ankle = _add(knee, _swing(_offset(p["lower_leg"], "ankle"), shin))
        legs += [
            Part("upper_leg", *hip, -thigh, a["thigh"][i]),
            Part("lower_leg", *knee, -shin),
            Part("shoe_front", *ankle, 0),
        ]
        shoulder = _offset(torso, f"shoulder_{name}")
        upper = side * a["arm"][i]
        elbow = _add(shoulder, _swing(_offset(p["upper_arm"], "elbow"), upper))
        uppers.append(Part("upper_arm", *shoulder, -upper))
        turn = upper - side * a["elbow"][i]
        forearms.append(Part("lower_arm", *elbow, -turn, a["forearm"][i]))
    body = [Part(f"torso_{view}", 0, 0, 0)]
    head = [Part(f"head_{view}", *_offset(torso, "neck"), 0)]
    return [*legs, *body, *uppers, *forearms, *head]


def lowest(p: dict, parts: list[Part]) -> float:
    low = -math.inf
    for part in parts:
        spec = p[part.piece]
        _, _, w, h = spec["frame"]
        for cx, cy in ((0, 0), (w, 0), (0, h), (w, h)):
            corner = (cx - spec["pivot"][0], (cy - spec["pivot"][1]) * part.scale_y)
            low = max(low, part.y + _swing(corner, -part.angle)[1])
    return low


def posed(p: dict, pose: str, facing: str, phase: float = 0.0) -> tuple[list[Part], bool]:
    """Every piece placed, its y from the ground; and whether to draw it mirrored."""
    if facing in ("north", "south"):
        parts = place_straight(p, "back" if facing == "north" else "front", STRAIGHT)
    else:
        parts = place_side(p, walk(phase % 1.0) if pose == "walking" else STAND)
    ground = lowest(p, parts)
    for part in parts:
        part.y -= ground
    return parts, facing == "west"


@dataclass(frozen=True)
class Drawn:
    """How a look's residents are drawn from their atlases."""

    folder: str
    """out/<folder>/dolls/, or `now` for the game's."""
    outline: float = 0.0
    """Ink drawn round each piece, in units."""
    head: float = 1.0
    """Heads drawn this much bigger, about the neck."""
    neck: float = 0.0
    """How far the neck joint rises, as a share of what a bigger head grows below it: 1 keeps
    the chin where it was, and below 0 sinks the head into the shoulders."""
    shoulder: float = 0.0
    """Units the shoulder joints drop, to clear a bigger head."""
    rough: bool = False
    """The drawn ink varies in width, as a scratchy pen's does."""
    pixels: str | None = None
    """Pixel art: `baked`, the smooth rig with each frame pixelated, or the rig drawn at the art's
    own size with `nearest` turns or `rotsprite` turns."""


KLEI_NECK, KLEI_SHOULDER = -1.0, 2.0
KLEI = {"neck": KLEI_NECK, "shoulder": KLEI_SHOULDER}
INKED = {"outline": OUTLINE, "rough": True}
DRAWN = {
    "now": Drawn("now"),
    "papercraft": Drawn("papercraft"),
    "cartoon": Drawn("cartoon", outline=OUTLINE, head=HEAD),
    "grimy": Drawn(PLAIN, head=1.6, **KLEI, **INKED),
    "grimy-1.8": Drawn(PLAIN, head=1.8, **KLEI, **INKED),
    "grimy-painted": Drawn("grimy", head=1.6, **KLEI),
    "pixel": Drawn("pixel", pixels="nearest"),
    "flat": Drawn("flat"),
}
"""Each look's residents. The revised cartoon's are painted with no outline and drawn with one,
about as wide as its furniture's painted lines, at two head sizes; `grimy-painted` keeps the
painted outline alone instead."""


@dataclass
class Doll:
    manifest: dict
    atlas: Image.Image
    flat: Image.Image
    drawn: Drawn = field(default_factory=lambda: Drawn("now"))
    sprites: dict = field(default_factory=dict, repr=False)

    @classmethod
    def load(cls, folder: Path, who: str, drawn: Drawn, painted: bool = True) -> "Doll":
        manifest = json.loads((folder / f"{who}.json").read_text())
        atlas = Image.open(folder / manifest["painted" if painted else "flat"]).convert("RGBA")
        flat = Image.open(folder / manifest["flat"]).convert("RGBA")
        return cls(adjusted(manifest, drawn), atlas, flat, drawn)

    @property
    def pieces(self) -> dict:
        return self.manifest["pieces"]

    @property
    def outline(self) -> float:
        return self.drawn.outline

    def standing_height(self) -> float:
        """Atlas px from the ground to the top of the head, hats included, as the client's."""
        parts, _ = posed(self.pieces, "standing", "south")
        head = next(p for p in parts if p.piece == "head_front")
        return -(head.y - self.pieces["head_front"]["pivot"][1] * self.drawn.head)

    def sprite(self, name: str) -> tuple[Image.Image, tuple[float, float]]:
        """A piece and its pivot, its head scaled and its outline drawn."""
        if name not in self.sprites:
            self.sprites[name] = self._sprite(name)
        return self.sprites[name]

    def _sprite(self, name: str) -> tuple[Image.Image, tuple[float, float]]:
        x, y, w, h = self.pieces[name]["frame"]
        image = self.atlas.crop((x, y, x + w, y + h))
        pivot = tuple(self.pieces[name]["pivot"])
        head = self.drawn.head
        if head != 1.0 and name.startswith("head"):
            image = image.resize((round(w * head), round(h * head)), Image.LANCZOS)
            pivot = (pivot[0] * head, pivot[1] * head)
        if self.outline:
            image, pivot = inked(image, pivot, self.outline * self.manifest["unit"], self.drawn)
        return image, pivot

    def canvas(self, pose: str, facing: str, phase: float, shadows: bool = True):
        """The posed doll at atlas size, mirrored if it faces west, and its ground origin."""
        parts, flip = posed(self.pieces, pose, facing, phase)
        unit = self.manifest["unit"]
        size = round(self.standing_height() * 1.6)
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        origin = (size / 2, size * 0.92)
        nudge = unit * 0.5
        for i, part in enumerate(parts):
            image, pivot = self.sprite(part.piece)
            if part.scale_y != 1.0:
                image = image.resize((image.width, max(1, round(image.height * part.scale_y))))
                pivot = (pivot[0], pivot[1] * part.scale_y)
            at = (origin[0] + part.x, origin[1] + part.y)
            if i > 0 and shadows:
                shadow = Image.new("RGBA", image.size, (20, 14, 10, 0))
                shadow.putalpha(image.getchannel("A").point(lambda v: round(v * 0.3)))
                _paste(canvas, shadow, pivot, (at[0] + nudge, at[1] + nudge * 1.4), part.angle)
            if part.shade != 1.0:
                image = shaded(image, part.shade)
            _paste(canvas, image, pivot, at, part.angle)
        if flip:
            canvas = canvas.transpose(Image.FLIP_LEFT_RIGHT)
        return canvas, origin

    def draw(self, pose: str, facing: str, phase: float, height: float) -> tuple[Image.Image, Px]:
        """The posed doll `height` px tall, with the point under its hips at the ground."""
        canvas, origin = self.canvas(pose, facing, phase)
        scale = height / self.standing_height()
        size = canvas.width
        small = canvas.resize((round(size * scale), round(size * scale)), Image.LANCZOS)
        return small, (small.width / 2, origin[1] * scale)

    def native(self, pose: str, facing: str, phase: float, height: float, mode=None):
        """The posed doll as pixel art `height` art pixels tall, and its ground origin there."""
        import pixel

        mode = mode or self.drawn.pixels
        colours = self._palette()
        scale = self.standing_height() / height
        if mode == "baked":
            canvas, origin = self.canvas(pose, facing, phase, shadows=False)
            plain = replace(self, atlas=self.flat, sprites={})
            flat, _ = plain.canvas(pose, facing, phase, shadows=False)
            size = (round(canvas.width / scale), round(canvas.height / scale))
            image = pixel.region_pixels(canvas, flat, size)
            return image, (image.width / 2, origin[1] * size[1] / canvas.height)
        parts, flip = posed(self.pieces, pose, facing, phase)
        size = round(self.standing_height() * 1.6 / scale)
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        origin = (size / 2, round(size * 0.92))
        for part in parts:
            image, pivot = self._native_piece(part.piece, scale, colours)
            if part.scale_y != 1.0:
                image = image.resize(
                    (image.width, max(1, round(image.height * part.scale_y))), Image.NEAREST
                )
                pivot = (pivot[0], pivot[1] * part.scale_y)
            if part.shade != 1.0:
                image = pixel_shaded(image, part.shade, colours)
            turned, centre = pixel.rotate_nearest(image, part.angle, pivot, mode == "rotsprite")
            at = (origin[0] + part.x / scale, origin[1] + part.y / scale)
            over(canvas, turned, round(at[0] - centre[0]), round(at[1] - centre[1]))
        if flip:
            canvas = canvas.transpose(Image.FLIP_LEFT_RIGHT)
        return canvas, (canvas.width / 2, origin[1])

    def _native_piece(self, name: str, scale: float, colours):
        key = ("native", name, round(scale, 3))
        if key not in self.sprites:
            import pixel

            image, pivot = self.sprite(name)
            x, y, w, h = self.pieces[name]["frame"]
            flat = self.flat.crop((x, y, x + w, y + h)).resize(image.size, Image.NEAREST)
            size = (max(1, round(image.width / scale)), max(1, round(image.height / scale)))
            small = pixel.region_pixels(image, flat, size)
            fx, fy = size[0] / image.width, size[1] / image.height
            self.sprites[key] = (small, (pivot[0] * fx, pivot[1] * fy))
        return self.sprites[key]

    def _palette(self):
        if "palette" not in self.sprites:
            import pixel

            self.sprites["palette"] = pixel.doll_palette(self)
        return self.sprites["palette"]


def adjusted(manifest: dict, drawn: Drawn) -> dict:
    """The manifest with its neck joints raised and its shoulders dropped for a bigger head."""
    if not (drawn.neck or drawn.shoulder):
        return manifest
    out = json.loads(json.dumps(manifest))
    pieces, unit = out["pieces"], out["unit"]
    for torso, head in (
        ("torso", "head"),
        ("torso_front", "head_front"),
        ("torso_back", "head_back"),
    ):
        _, _, _, h = pieces[head]["frame"]
        below = h - pieces[head]["pivot"][1]
        joints = pieces[torso]["joints"]
        joints["neck"][1] -= (drawn.head - 1) * below * drawn.neck
        for name in joints:
            if name.startswith("shoulder"):
                joints[name][1] += drawn.shoulder * unit
    return out


def shaded(image: Image.Image, shade: float) -> Image.Image:
    a = np.asarray(image, dtype=np.float32).copy()
    a[..., :3] *= shade
    return Image.fromarray(a.astype(np.uint8), "RGBA")


def pixel_shaded(image: Image.Image, shade: float, colours) -> Image.Image:
    import pixel

    a = np.asarray(shaded(image, shade))
    rgb = pixel.quantise(a[..., :3].astype(np.float32), colours)
    return Image.fromarray(np.dstack([rgb, a[..., 3]]), "RGBA")


def inked(image: Image.Image, pivot, width: float, drawn: Drawn):
    """`image` with an ink outline `width` px wide round it, varying in width if `rough`."""
    pad = math.ceil(width * (1.4 if drawn.rough else 1.0)) + 2
    grown = Image.new("RGBA", (image.width + 2 * pad, image.height + 2 * pad))
    grown.paste(image, (pad, pad))
    alpha = grown.getchannel("A")
    if drawn.rough:
        thin = np.asarray(alpha.filter(ImageFilter.MaxFilter(2 * round(width * 0.5) + 1)), float)
        thick = np.asarray(alpha.filter(ImageFilter.MaxFilter(2 * round(width * 1.4) + 1)), float)
        rng = np.random.default_rng(zlib.crc32(image.tobytes()))
        noise = rng.random((max(2, grown.height // 9), max(2, grown.width // 9)))
        mix = (
            np.asarray(
                Image.fromarray((noise * 255).astype(np.uint8)).resize(grown.size, Image.BICUBIC),
                float,
            )
            / 255
        )
        alpha = Image.fromarray(np.clip(thin + (thick - thin) * mix, 0, 255).astype(np.uint8))
    else:
        alpha = alpha.filter(ImageFilter.MaxFilter(2 * (pad - 2) + 1))
    alpha = alpha.filter(ImageFilter.GaussianBlur(0.8))
    ink = Image.new("RGBA", grown.size, (*INK, 255))
    ink.putalpha(alpha)
    ink.alpha_composite(grown)
    return ink, (pivot[0] + pad, pivot[1] + pad)


def _paste(canvas: Image.Image, image: Image.Image, pivot, at, angle: float) -> None:
    corners = [(0, 0), (image.width, 0), (0, image.height), (image.width, image.height)]
    r = math.ceil(max(math.hypot(x - pivot[0], y - pivot[1]) for x, y in corners)) + 2
    square = Image.new("RGBA", (2 * r, 2 * r), (0, 0, 0, 0))
    square.paste(image, (round(r - pivot[0]), round(r - pivot[1])))
    square = square.rotate(-angle, resample=Image.BICUBIC, center=(r, r))
    over(canvas, square, round(at[0] - r), round(at[1] - r))


def over(canvas: Image.Image, image: Image.Image, x: int, y: int) -> None:
    """`image` composited onto `canvas` at (x, y), clipped to it."""
    left, top = max(0, -x), max(0, -y)
    right = min(image.width, canvas.width - x)
    bottom = min(image.height, canvas.height - y)
    if right > left and bottom > top:
        canvas.alpha_composite(image.crop((left, top, right, bottom)), (x + left, y + top))


def folder(look: str) -> Path:
    """Where a look's dolls are: `now` for the game's committed ones."""
    name = DRAWN[look].folder if look in DRAWN else look
    return REPO / "content" / "dolls" if name == "now" else OUT / name / "dolls"


def doll(look: str, who: str, **changes) -> Doll:
    drawn = replace(DRAWN[look], **changes) if changes else DRAWN[look]
    return Doll.load(folder(look), who, drawn)


def main(args: list[str]) -> None:
    paint(args[0], args[1:] or list(WHO))


if __name__ == "__main__":
    main(sys.argv[1:])
