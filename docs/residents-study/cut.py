"""Approach 2: paint whole from a mannequin, then cut into #310's rig.

Each resident's flat doll, at #329's grimy proportions, is posed by the rig three times on one
sheet: side-on with its near limbs clear of the body, from the front and from behind. FLUX redraws
the sheet freely as a whole character in the grimy style. The painting is then cut back into
#310's pieces where the mannequin's pieces lie, each piece turned back upright, and whatever
another piece covered is filled in. The client's rig poses the result as it poses #310's dolls.

`python cut.py paint [who …]` paints the sheets into out/cut/, and `python cut.py cut [who …]`
cuts them into dolls in out/cut/dolls/.
"""

import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

import study  # noqa: F401  # isort: skip
import cv2
import dolls as port
import numpy as np
import poses
from PIL import Image
from study import FACE, HEAD, OUT, RESIDENTS_REF, WHO, Painter, described, styled

FOLDER = OUT / "cut"
SHEET = (1344, 768)
BACKGROUND = (214, 210, 202)
FIGURE = 600
"""How tall each mannequin stands on the sheet, in pixels."""
CUT_POSE = {
    "lean": 2,
    "nod": 0,
    "thigh": (26, -20),
    "knee": (10, 6),
    "foot": (0, 0),
    "shoulder": (46, -34),
    "elbow": (30, 12),
}
"""Side-on with the near arm and leg swung forward, clear of the body, so the body under them
is mostly painted."""
VIEWS = (
    ("side", "side", CUT_POSE, 0.27),
    ("front", "front", None, 0.55),
    ("back", "back", None, 0.82),
)
"""Each figure's name, view, side-on angles, and where it stands across the sheet."""
KLEI = port.Drawn(port.PLAIN, head=HEAD, neck=port.KLEI_NECK, shoulder=port.KLEI_SHOULDER)
HIDDEN_PAD = 6
"""Pixels round a covering piece that count as covered, so its painted outline isn't left on
the piece below."""
PROMPT = (
    "Redraw image 1 as three drawings of the same cartoon game character, in the scratchy, grimy "
    "cartoon style of the residents in image 2: on the left seen from the side walking to the "
    "right, in the middle seen from the front, on the right seen from behind with no face. Keep "
    "each figure's pose, size and place, its very big round head and its colours, but draw it "
    "freely as one whole person with natural rounded shapes, real clothes, hands and shoes, "
    "rather than separate flat pieces. {who} {face} Keep the background plain light grey."
)
TIGHT = (
    "Redraw image 1 as three drawings of the same cartoon game character, in the scratchy, grimy "
    "cartoon style of the residents in image 2: on the left seen from the side walking to the "
    "right, in the middle seen from the front, on the right seen from behind with no face. Keep "
    "each figure's exact pose, place, size and outline: on the left the near leg strides forward "
    "and the near arm reaches forward, away from the body, with the elbow bent; in the middle and "
    "on the right the arms hang at the sides. Keep the very big round head and the colours, and "
    "draw real clothes, hands and shoes over the shapes. {who} {face} Keep the background plain "
    "light grey."
)
"""A tighter constraint, for the cut to find each piece where the mannequin put it."""
SEEDS: dict[str, int] = {}
VARIANT = "loose"
"""`loose` or `tight`: which prompt the sheets are painted with, and which are cut."""


@dataclass
class Placed:
    """One posed piece on the sheet."""

    piece: str
    near: bool
    figure: str
    forward: np.ndarray
    """2x3 affine from the piece's padded frame to the sheet."""
    mask: np.ndarray
    """Where the flat piece lies on the sheet."""


@dataclass
class Mannequin:
    who: str
    manifest: dict
    """The flat doll's manifest at #329's proportions, heads grown into their frames."""
    atlas: Image.Image
    image: Image.Image = field(repr=False, default=None)
    placed: list[Placed] = field(default_factory=list)
    scale: float = 1.0


def grown(who: str) -> tuple[dict, Image.Image]:
    """#329's grimy flat doll with its neck sunk and shoulders dropped, and its heads drawn 1.6
    times bigger into their own frames, so the rig needs no head scale."""
    folder = port.folder("grimy")
    raw = json.loads((folder / f"{who}.json").read_text())
    manifest = port.adjusted(raw, KLEI)
    flat = Image.open(folder / raw["flat"]).convert("RGBA")
    pieces = {}
    for name, spec in manifest["pieces"].items():
        x, y, w, h = spec["frame"]
        image = flat.crop((x, y, x + w, y + h))
        pivot = spec["pivot"]
        joints = spec["joints"]
        if name.startswith("head"):
            image = image.resize((round(w * HEAD), round(h * HEAD)), Image.LANCZOS)
            pivot = [pivot[0] * HEAD, pivot[1] * HEAD]
            joints = {k: [v[0] * HEAD, v[1] * HEAD] for k, v in joints.items()}
        pieces[name] = (image, pivot, joints)
    return packed(manifest, pieces)


def packed(manifest: dict, pieces: dict, pad: int = 2) -> tuple[dict, Image.Image]:
    """Pieces on one atlas, in shelves, and their manifest."""
    order = sorted(pieces, key=lambda n: -pieces[n][0].height)
    width = max(512, max(p[0].width for p in pieces.values()) + pad)
    x = y = shelf = 0
    frames = {}
    for name in order:
        w, h = pieces[name][0].size
        if x + w + pad > width:
            x, y, shelf = 0, y + shelf + pad, 0
        frames[name] = (x, y, w, h)
        x += w + pad
        shelf = max(shelf, h)
    atlas = Image.new("RGBA", (width, y + shelf), (0, 0, 0, 0))
    out = json.loads(json.dumps({k: v for k, v in manifest.items() if k != "pieces"}))
    out["pieces"] = {}
    for name, (image, pivot, joints) in pieces.items():
        fx, fy, w, h = frames[name]
        atlas.paste(image, (fx, fy))
        out["pieces"][name] = {
            "frame": [fx, fy, w, h],
            "pivot": [round(pivot[0], 2), round(pivot[1], 2)],
            "joints": {k: [round(v[0], 2), round(v[1], 2)] for k, v in joints.items()},
        }
    return out, atlas


def crop(atlas: Image.Image, spec: dict) -> Image.Image:
    x, y, w, h = spec["frame"]
    return atlas.crop((x, y, x + w, y + h))


def affine(pivot, at, angle: float, scale: float) -> np.ndarray:
    """Piece pixels to sheet pixels: about `pivot`, turned `angle` degrees clockwise, scaled,
    and put at `at`."""
    c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    rot = np.array([[c, -s], [s, c]]) * scale
    offset = np.array(at) - rot @ np.array(pivot)
    return np.hstack([rot, offset[:, None]])


def mannequin(who: str, fits: dict | None = None, figures=VIEWS) -> Mannequin:
    """The flat doll posed on the sheet once for each of `figures`, with each piece's place.
    `fits` moves and scales a figure, by name, from one feet point to another, to lie over what
    FLUX painted."""
    manifest, atlas = grown(who)
    p = manifest["pieces"]
    stand = port.place_straight(p, "front", port.STRAIGHT)
    height = -min(
        part.y - p[part.piece]["pivot"][1] for part in stand if part.piece == "head_front"
    )
    height += port.lowest(p, stand)
    scale = FIGURE / height
    sheet = np.zeros((SHEET[1], SHEET[0], 4), np.float32)
    out = Mannequin(who, manifest, atlas, scale=scale)
    for figure, view, angles, across in figures:
        if view == "side":
            parts = port.place_side(p, angles)
        else:
            parts = port.place_straight(p, view, port.STRAIGHT)
        ground = port.lowest(p, parts)
        origin = (SHEET[0] * across, SHEET[1] - 50)
        for part in parts:
            image = crop(atlas, p[part.piece])
            if part.scale_y != 1.0:
                image = image.resize((image.width, max(1, round(image.height * part.scale_y))))
            pivot = (p[part.piece]["pivot"][0], p[part.piece]["pivot"][1] * part.scale_y)
            at = np.array((origin[0] + part.x * scale, origin[1] + (part.y - ground) * scale))
            size = scale
            if fits and figure in fits:
                was, now, k = fits[figure]
                at, size = np.array(now) + k * (at - np.array(was)), scale * k
            matrix = affine(pivot, at, part.angle, size)
            rgba = np.asarray(image, np.float32)
            warped = cv2.warpAffine(rgba, matrix, SHEET, flags=cv2.INTER_LINEAR)
            if part.shade != 1.0:
                warped[..., :3] *= part.shade
            alpha = warped[..., 3:] / 255
            sheet[..., :3] = sheet[..., :3] * (1 - alpha) + warped[..., :3] * alpha
            sheet[..., 3:] = np.maximum(sheet[..., 3:], warped[..., 3:])
            if part.scale_y == 1.0:
                out.placed.append(
                    Placed(part.piece, part.shade == 1.0, figure, matrix, warped[..., 3] > 127)
                )
    flat = np.full((SHEET[1], SHEET[0], 3), BACKGROUND, np.float32)
    a = sheet[..., 3:] / 255
    flat = flat * (1 - a) + sheet[..., :3] * a
    out.image = Image.fromarray(np.clip(flat, 0, 255).astype(np.uint8))
    return out


def prompt(who: str) -> str:
    words = TIGHT if VARIANT == "tight" else PROMPT
    return styled(words.format(who=described(who), face=FACE))


def painting_path(who: str) -> Path:
    suffix = "-tight" if VARIANT == "tight" else ""
    return FOLDER / "paintings" / f"{who}-{SEEDS.get(who, 1)}{suffix}.png"


def paint(who: list[str]) -> None:
    todo = [w for w in who if not painting_path(w).exists()]
    if not todo:
        return
    reference = Image.open(RESIDENTS_REF).convert("RGB")
    reference = reference.resize((768, round(reference.height * 768 / reference.width / 16) * 16))
    with Painter("cut") as painter:
        for name in todo:
            guide = mannequin(name).image
            (FOLDER / "mannequins").mkdir(parents=True, exist_ok=True)
            guide.save(FOLDER / "mannequins" / f"{name}.png")
            image = painter.paint(name, prompt(name), SHEET, SEEDS.get(name, 1), [guide, reference])
            painting_path(name).parent.mkdir(parents=True, exist_ok=True)
            image.save(painting_path(name))


def silhouette(painting: Image.Image) -> np.ndarray:
    from study import cut_out

    return np.asarray(cut_out(painting).getchannel("A"), np.float32) / 255


def fitted(who: str, alpha: np.ndarray, figures=VIEWS) -> tuple[Mannequin, dict]:
    """The mannequin with each figure moved and scaled so its outline's box sits on the painted
    figure's: FLUX keeps the figures in order but moves them about and draws them a little
    bigger or smaller. Each painted blob goes to the figure whose middle is nearest."""
    m = mannequin(who, figures=figures)
    boxes = {}
    for view, *_ in figures:
        drawn = np.zeros_like(alpha, dtype=bool)
        for placed in m.placed:
            if placed.figure == view:
                drawn |= placed.mask
        boxes[view] = np.argwhere(drawn).min(0), np.argwhere(drawn).max(0)
    count, labels, stats, centres = cv2.connectedComponentsWithStats(
        (alpha > 0.5).astype(np.uint8), 8
    )
    middles = {view: (lo[1] + hi[1]) / 2 for view, (lo, hi) in boxes.items()}
    painted = {view: np.zeros_like(alpha, dtype=bool) for view in boxes}
    for i in range(1, count):
        if stats[i, cv2.CC_STAT_AREA] < 400:
            continue
        view = min(middles, key=lambda v: abs(middles[v] - centres[i][0]))
        painted[view] |= labels == i
    fits = {}
    for view, ((y0, x0), (y1, x1)) in boxes.items():
        if not painted[view].any():
            continue
        (py0, px0), (py1, px1) = (
            np.argwhere(painted[view]).min(0),
            np.argwhere(painted[view]).max(0),
        )
        k = (py1 - py0) / max(1, y1 - y0)
        fits[view] = (((x0 + x1) / 2, y1), ((px0 + px1) / 2, py1), k)
    return mannequin(who, fits, figures), fits


REACH = 80
"""Sheet pixels round a mannequin piece that a painted pixel may still belong to it."""
FAR_COST = 0.25
"""What each pixel outside a piece's place adds to its colour distance, in CIE76."""
INK_RGB = (46, 32, 28)


def palette_of(m: Mannequin, piece: str) -> np.ndarray:
    """The flat colours a piece is drawn in, in CIELAB."""
    from simile.dolls.colour import cielab
    from simile.dolls.sheet import regions

    _, main, _ = regions(crop(m.atlas, m.manifest["pieces"][piece]))
    return cielab(main)


def assign(m: Mannequin, alpha: np.ndarray, rgb: np.ndarray) -> np.ndarray:
    """Each painted pixel's piece. Among the pieces whose place, grown by `REACH`, covers it,
    the one drawn in the colour nearest its own, so a shirt the painter drew under where the
    mannequin's bigger head was still goes to the torso. Ink goes to the topmost piece, and
    what lies past every piece to the nearest. -1 for the background."""
    from simile.dolls.colour import cielab

    painted = alpha > 0.5
    lab = cielab(rgb)
    ink = np.linalg.norm(lab - cielab(np.array(INK_RGB, np.float64)), axis=-1) < 22
    best = np.full(alpha.shape, np.inf, np.float32)
    owner = np.full(alpha.shape, -1, np.int32)
    top = np.full(alpha.shape, -1, np.int32)
    for i, placed in enumerate(m.placed):
        top[placed.mask] = i
        away = cv2.distanceTransform((~placed.mask).astype(np.uint8), cv2.DIST_L2, 5)
        ys, xs = np.nonzero((away < REACH) & painted)
        colours = palette_of(m, placed.piece)
        d = np.linalg.norm(lab[ys, xs][:, None] - colours[None], axis=-1).min(axis=1)
        d += FAR_COST * away[ys, xs] - 0.01 * i
        better = d < best[ys, xs]
        best[ys[better], xs[better]] = d[better]
        owner[ys[better], xs[better]] = i
    owner[ink & (top >= 0)] = top[ink & (top >= 0)]
    spill = painted & (owner < 0)
    if spill.any():
        far = np.full(alpha.shape, np.inf, np.float32)
        for i, placed in enumerate(m.placed):
            distance = cv2.distanceTransform((~placed.mask).astype(np.uint8), cv2.DIST_L2, 5)
            closer = spill & (distance < far)
            far[closer] = distance[closer]
            owner[closer] = i
    owner[~painted] = -1
    return owner


def unwarp(m: Mannequin, placed: Placed, image: np.ndarray, size, pad: int, flags=cv2.INTER_LINEAR):
    """A sheet-sized array back in the piece's own frame at atlas scale, padded `pad` pixels."""
    shift = np.array([[1, 0, -pad], [0, 1, -pad], [0, 0, 1]], np.float64)
    forward = np.vstack([placed.forward, [0, 0, 1]]) @ shift
    w, h = size
    return cv2.warpAffine(
        image, forward[:2], (w + 2 * pad, h + 2 * pad), flags=flags | cv2.WARP_INVERSE_MAP
    )


def cut(who: str) -> dict:
    """The painting cut into the near pieces, each upright at atlas scale, with what other
    pieces covered filled in. Writes the doll and returns what it measured."""
    painting = Image.open(painting_path(who)).convert("RGB")
    alpha = silhouette(painting)
    m, fits = fitted(who, alpha)
    rgb = np.asarray(painting, np.float32)
    owner = assign(m, alpha, rgb.astype(np.float64))
    pad = 90
    p = m.manifest["pieces"]
    pieces, flats, covered_share = {}, {}, {}
    kernel = np.ones((2 * HIDDEN_PAD + 1,) * 2, np.uint8)
    for i, placed in enumerate(m.placed):
        if not placed.near or placed.piece in pieces:
            continue
        spec = p[placed.piece]
        size = (spec["frame"][2], spec["frame"][3])
        above = owner > i
        hidden = placed.mask & (above | (cv2.dilate(above.astype(np.uint8), kernel) > 0))
        mine = (owner == i) & ~hidden
        colour = unwarp(m, placed, rgb, size, pad)
        kept = unwarp(m, placed, mine.astype(np.float32) * alpha, size, pad)
        fill = unwarp(m, placed, hidden.astype(np.float32), size, pad) > 0.5
        if fill.any():
            colour = cv2.inpaint(
                np.clip(colour, 0, 255).astype(np.uint8),
                (fill | (kept < 0.5)).astype(np.uint8) * 255,
                5,
                cv2.INPAINT_TELEA,
            ).astype(np.float32)
        a = np.clip(np.maximum(kept, fill.astype(np.float32)), 0, 1)
        covered_share[placed.piece] = round(float(fill.sum() / max(1, (a > 0.5).sum())), 3)
        rgba = np.dstack([np.clip(colour, 0, 255), a * 255]).astype(np.uint8)
        pieces[placed.piece] = Image.fromarray(rgba, "RGBA")
        flats[placed.piece] = crop(m.atlas, spec)
    covered_share["fits"] = {k: round(v[2], 3) for k, v in fits.items()}
    return finish(m, pieces, flats, pad, covered_share)


def finish(m: Mannequin, pieces: dict, flats: dict, pad: int, covered: dict) -> dict:
    p = m.manifest["pieces"]
    painted, flat = {}, {}
    for name, image in pieces.items():
        spec = p[name]
        bare = Image.new("RGBA", image.size, (0, 0, 0, 0))
        bare.paste(flats[name], (pad, pad))
        box = image.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox()
        box = box or (0, 0, image.width, image.height)
        x0, y0 = box[0], box[1]
        pivot = [spec["pivot"][0] + pad - x0, spec["pivot"][1] + pad - y0]
        joints = {k: [v[0] + pad - x0, v[1] + pad - y0] for k, v in spec["joints"].items()}
        painted[name] = (image.crop(box), pivot, joints)
        flat[name] = (bare.crop(box), pivot, joints)
    manifest, atlas = packed(m.manifest, painted)
    _, flat_atlas = packed(m.manifest, flat)
    folder = dolls_folder()
    folder.mkdir(parents=True, exist_ok=True)
    manifest["painted"], manifest["flat"] = f"{m.who}-painted.png", f"{m.who}-flat.png"
    atlas.save(folder / manifest["painted"])
    flat_atlas.save(folder / manifest["flat"])
    (folder / f"{m.who}.json").write_text(json.dumps(manifest, indent=1))
    print(m.who, "covered", covered, flush=True)
    return covered


def dolls_folder(variant: str | None = None) -> Path:
    return FOLDER / ("dolls-tight" if (variant or VARIANT) == "tight" else "dolls")


def doll(who: str, variant: str | None = None):
    """The cut doll, for #329's rig port to pose."""
    folder = dolls_folder(variant)
    manifest = json.loads((folder / f"{who}.json").read_text())
    atlas = Image.open(folder / manifest["painted"]).convert("RGBA")
    flat = Image.open(folder / manifest["flat"]).convert("RGBA")
    return port.Doll(manifest, atlas, flat, port.Drawn("cut"))


if __name__ == "__main__":
    poses.use()
    if "--tight" in sys.argv:
        VARIANT = "tight"
        sys.argv.remove("--tight")
    step = sys.argv[1]
    names = [a for a in sys.argv[2:] if a in WHO] or list(WHO)
    if step == "guide":
        for name in names:
            (FOLDER / "mannequins").mkdir(parents=True, exist_ok=True)
            mannequin(name).image.save(FOLDER / "mannequins" / f"{name}.png")
    elif step == "paint":
        paint(names)
    else:
        found = {name: cut(name) for name in names}
        (dolls_folder() / "covered.json").write_text(json.dumps(found, indent=1, default=float))
