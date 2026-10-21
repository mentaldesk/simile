"""Residents in each style: #310's doll pipeline with this study's references, and the client's
rig (`client/src/dolls/rig.ts`) ported to Python to pose them.

`python dolls.py <style> [who …]` paints the dolls into out/<style>/dolls/.
"""

import json
import math
import sys
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from common import CARTOON, OUT, REFS, STYLES, Style, log, styled, wait_for_gpu
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
"""The cartoon's bodies are this much wider than #310's, through `Look.width`."""
HEAD = 1.22
"""The cartoon's heads are drawn this much bigger, about the neck."""
INK = (46, 32, 28)
OUTLINE = 0.9
"""The cartoon's outline, in units: drawn round each piece in the rig, as the scenery's are
painted."""
REROLLS = {"cartoon/odalys/front_back": 1}
"""`<style>/<who>/<sheet>` to a reroll, for a painting that came out off-model."""


def cartoon_prompt(sheet: str, appearance, who: str | None) -> str:
    """#310's prompt, in the cartoon style."""
    if sheet == "side":
        what = "the separate body parts of a cartoon game character"
        layout = "a face drawn on the head in profile."
    else:
        what = "four separate flat pieces of a cartoon cut-out puppet, laid apart"
        layout = (
            "the head on the left faces the viewer with the face drawn on it, the head on the "
            f"right is the back of the same head, {back_of_head(appearance)}, and between them "
            "are two flat torso pieces, the front and the back, each a plain shape with no "
            "head, arms or legs on it."
        )
    return styled(
        f"Redraw image 1 as {what}, hand-drawn in "
        "the cartoon style of the residents in image 2: a thick dark brown outline round every "
        f"piece, flat colours with simple soft shading, {layout} {person(appearance, who)} Keep "
        "every piece exactly where it is, with the same outline and the same colours, and add "
        "nothing to it, on a plain light grey background.",
        CARTOON,
    )


class TimedPainter(EditPainter):
    """#310's sheet painter, loaded only when nothing else is using the model memory."""

    def __enter__(self):
        wait_for_gpu()
        start = time.perf_counter()
        out = super().__enter__()
        log({"event": "load", "mode": "edit", "seconds": round(time.perf_counter() - start, 1)})
        return out


@contextmanager
def styled_pipeline(style: Style):
    """#310's `paint()` reading this style's residents reference, with its prompt, rerolls and
    proportions. Restores the module attributes it swaps."""
    saved = (painting.REFERENCES, dolls.reference, dolls.prompt, dolls.REROLLS, looks.BUILD)
    painting.REFERENCES = REFS / style.name
    dolls.reference = lambda name, width=768: painting.reference("residents", width)
    dolls.REROLLS = {
        k.split("/", 1)[1]: v for k, v in REROLLS.items() if k.startswith(f"{style.name}/")
    }
    if style is CARTOON:
        dolls.prompt = cartoon_prompt
        looks.BUILD = {k: v * CHUNKY for k, v in looks.BUILD.items()}
    try:
        yield
    finally:
        painting.REFERENCES, dolls.reference, dolls.prompt, dolls.REROLLS, looks.BUILD = saved


def paint(style: Style, who: list[str]) -> None:
    everyone = dolls.people()
    folder = OUT / style.name / "dolls"
    model = dolls.Lazy(TimedPainter)
    with styled_pipeline(style), model.stack, tempfile.TemporaryDirectory() as scratch:
        for name in who:
            painted = dolls.paint(name, everyone[name], model, Path(scratch), folder / "paintings")
            filled = matched(painted.doll)
            appearance = everyone[name].model_dump(mode="json")
            dolls.write(folder, dolls.files(name, painted.doll, appearance=appearance))
            for sheet, seconds in painted.seconds.items():
                key = f"dolls/{style.name}/{name}/{sheet}"
                log({"event": "paint", "key": key, "kind": "doll sheet", "seconds": seconds})
            moved = {k: round(v, 3) for k, v in painted.misplaced.items() if v > 0.02}
            added = {k: round(v, 3) for k, v in painted.patches.items() if v > 0.05}
            print(f"{name}: {painted.seconds} moved {moved} added {added} filled {filled}")
            sheets = folder / "sheets"
            sheets.mkdir(parents=True, exist_ok=True)
            for sheet, image in painted.paintings.items():
                image.save(sheets / f"{name}-{sheet}.png")


OFF = 6.0
"""CIEDE2000 a painted colour region may stay from its flat colour, in the atlas, before it's
filled."""
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


@dataclass
class Doll:
    manifest: dict
    atlas: Image.Image
    outline: float = 0.0
    """Ink round each piece, in units."""
    head: float = 1.0
    sprites: dict = field(default_factory=dict, repr=False)

    @classmethod
    def load(cls, folder: Path, who: str, painted: bool = True, cartoon: bool = False) -> "Doll":
        manifest = json.loads((folder / f"{who}.json").read_text())
        atlas = Image.open(folder / manifest["painted" if painted else "flat"]).convert("RGBA")
        return cls(manifest, atlas, OUTLINE if cartoon else 0.0, HEAD if cartoon else 1.0)

    @property
    def pieces(self) -> dict:
        return self.manifest["pieces"]

    def standing_height(self) -> float:
        """Atlas px from the ground to the top of the head, hats included, as the client's."""
        parts, _ = posed(self.pieces, "standing", "south")
        head = next(p for p in parts if p.piece == "head_front")
        return -(head.y - self.pieces["head_front"]["pivot"][1] * self.head)

    def sprite(self, name: str) -> tuple[Image.Image, tuple[float, float]]:
        """A piece and its pivot, the cartoon's with its head scaled and its outline drawn."""
        if name not in self.sprites:
            self.sprites[name] = self._sprite(name)
        return self.sprites[name]

    def _sprite(self, name: str) -> tuple[Image.Image, tuple[float, float]]:
        x, y, w, h = self.pieces[name]["frame"]
        image = self.atlas.crop((x, y, x + w, y + h))
        pivot = tuple(self.pieces[name]["pivot"])
        if self.head != 1.0 and name.startswith("head"):
            image = image.resize((round(w * self.head), round(h * self.head)), Image.LANCZOS)
            pivot = (pivot[0] * self.head, pivot[1] * self.head)
        if self.outline:
            pad = math.ceil(self.outline * self.manifest["unit"]) + 2
            grown = Image.new("RGBA", (image.width + 2 * pad, image.height + 2 * pad))
            grown.paste(image, (pad, pad))
            alpha = grown.getchannel("A").filter(ImageFilter.MaxFilter(2 * (pad - 2) + 1))
            alpha = alpha.filter(ImageFilter.GaussianBlur(0.8))
            ink = Image.new("RGBA", grown.size, (*INK, 255))
            ink.putalpha(alpha)
            ink.alpha_composite(grown)
            image, pivot = ink, (pivot[0] + pad, pivot[1] + pad)
        return image, pivot

    def draw(self, pose: str, facing: str, phase: float, height: float) -> tuple[Image.Image, Px]:
        """The posed doll `height` px tall, with the point under its hips at the ground."""
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
            if i > 0:
                shadow = Image.new("RGBA", image.size, (20, 14, 10, 0))
                shadow.putalpha(image.getchannel("A").point(lambda v: round(v * 0.3)))
                _paste(canvas, shadow, pivot, (at[0] + nudge, at[1] + nudge * 1.4), part.angle)
            if part.shade != 1.0:
                a = np.asarray(image, dtype=np.float32).copy()
                a[..., :3] *= part.shade
                image = Image.fromarray(a.astype(np.uint8), "RGBA")
            _paste(canvas, image, pivot, at, part.angle)
        if flip:
            canvas = canvas.transpose(Image.FLIP_LEFT_RIGHT)
        scale = height / self.standing_height()
        small = canvas.resize((round(size * scale), round(size * scale)), Image.LANCZOS)
        return small, (small.width / 2, origin[1] * scale)


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


def folder(style: str) -> Path:
    """Where a style's dolls are: `now` for the game's committed ones."""
    return REPO / "content" / "dolls" if style == "now" else OUT / style / "dolls"


def doll(style: str, who: str) -> Doll:
    return Doll.load(folder(style), who, cartoon=style == CARTOON.name)


def main(args: list[str]) -> None:
    style = STYLES[args[0]]
    paint(style, args[1:] or list(WHO))


if __name__ == "__main__":
    main(sys.argv[1:])
