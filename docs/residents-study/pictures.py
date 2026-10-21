"""The study's pictures and numbers: every approach's residents standing, walking, sitting and
climbing, at full size and at play size, on #329's grimy street and in its dollhouse, side by
side, and measured.

`python pictures.py [step …]`, with steps `stills`, `poses`, `walks`, `play`, `street`,
`dollhouse`, `seams`, `repaints`, `sheets`, `match`, `consistency`, `legibility`, `costs` and
`export`. Full-size pictures go to out/previews/, and the README's to images/.
"""

import json
import math
import sys
from functools import cache

import study  # noqa: F401  # isort: skip
import compose as styled_study
import dolls as port
import numpy as np
import poses
import scaled
from PIL import Image
from study import FULL, OUT, REFS, REGIONS, WHO, flat_labels, gif, measure, save, targets

EVERY = ("dolls", "whole", "cut", "model", "repaint")


def ready(approach: str) -> bool:
    found = {
        "dolls": port.folder("grimy") / "henrietta.json",
        "whole": OUT / "whole" / "sprites" / "feet.json",
        "cut": OUT / "cut" / "dolls" / "henrietta.json",
        "model": OUT / "model" / "henrietta" / "ladder-3.png",
        "repaint": OUT / "repaint" / "henrietta" / "cut" / "ladder-1.png",
        "strip": OUT / "whole" / "strip" / "feet.json",
    }
    return found[approach].exists()


APPROACHES = tuple(a for a in EVERY if ready(a))
WALKING = APPROACHES + (("strip",) if ready("strip") else ())
"""The approaches compared walking: approach 1b paints only the walk."""
TITLES = {
    "dolls": "Today: #310's dolls in #329's grimy cartoon",
    "whole": "1. Whole FLUX characters",
    "cut": "2. Painted whole, then cut",
    "model": "3. 3D, toon-shaded",
    "repaint": "4. 3D, repainted by FLUX",
    "strip": "1b. Whole, its walk painted from the rig",
}
SHORT = {
    "dolls": "#310 dolls",
    "whole": "1. Whole",
    "cut": "2. Cut",
    "model": "3. 3D",
    "repaint": "4. 3D repainted",
    "strip": "1b. Whole from the rig",
}
DOLL_M = styled_study.DOLL_M
BACKDROP = (240, 234, 222)
RENDER = (512, 768)
"""Approach 3's and 4's frames, and where their feet are: the camera puts the ground there."""
RENDER_PPM = 300
GROUND_ROW = RENDER[1] / 2 + (RENDER[1] / RENDER_PPM / 2 - 0.12) * RENDER_PPM


def frame_name(pose: str, facing: str, phase: float) -> str:
    if pose == "walking":
        return f"walk-{round(phase * poses.WALK_FRAMES) % poses.WALK_FRAMES}"
    if pose == "sitting":
        return "sit"
    if pose == "stairs":
        return f"stairs-{round(phase * 4) % 4}"
    if pose == "ladder":
        return f"ladder-{round(phase * 4) % 4}"
    return {"south": "front", "north": "back"}.get(facing, "stand")


@cache
def rendered(approach: str, who: str, name: str) -> Image.Image:
    if approach == "repaint-raw":
        return Image.open(OUT / "repaint" / who / "raw" / f"{name}.png").convert("RGBA")
    if approach == "repaint-strip":
        return Image.open(OUT / "repaint-strip" / who / f"{name}.png").convert("RGBA")
    folder = OUT / approach / who
    if approach == "repaint":
        return Image.open(folder / "cut" / f"{name}.png").convert("RGBA")
    return Image.open(folder / f"{name}.png").convert("RGBA")


@cache
def standing_px(approach: str, who: str) -> float:
    """How tall a figure stands in its own pixels, from the ground to the top of its head."""
    if approach in ("model", "repaint"):
        a = np.asarray(rendered(approach, who, "stand").getchannel("A")) > 100
        return GROUND_ROW - np.flatnonzero(a.any(axis=1))[0]
    if approach == "whole":
        x, bottom, top = whole_feet()[f"{who}/stand"]
        return bottom - top
    if approach == "strip":
        heights = [b - t for k, (x, b, t) in strip_feet().items() if k.startswith(f"{who}/")]
        return float(np.mean(heights))
    raise ValueError(approach)


@cache
def whole_feet() -> dict:
    return json.loads((OUT / "whole" / "sprites" / "feet.json").read_text())


@cache
def strip_feet() -> dict:
    return json.loads((OUT / "whole" / "strip" / "feet.json").read_text())


def strip_figure(who: str, facing: str, phase: float, height: float):
    """Approach 1b: the four painted walk frames, each held for two of the cycle's eight."""
    i = round(phase * poses.WALK_FRAMES) % poses.WALK_FRAMES
    name = f"w{i // 2}"
    image = Image.open(OUT / "whole" / "strip" / f"{who}-{name}.png").convert("RGBA")
    x, bottom, top = strip_feet()[f"{who}/{name}"]
    scale = height / standing_px("strip", who)
    small = image.resize(
        (max(1, round(image.width * scale)), max(1, round(image.height * scale))), Image.LANCZOS
    )
    origin = (x * scale, bottom * scale)
    if facing == "west":
        small = small.transpose(Image.FLIP_LEFT_RIGHT)
        origin = (small.width - origin[0], origin[1])
    return small, origin


@cache
def whole_sprite(who: str, pose: str) -> Image.Image:
    return Image.open(OUT / "whole" / "sprites" / f"{who}-{pose}.png").convert("RGBA")


WHOLE_WALK = ("stand", "step_a", "step_a", "stand", "stand", "step_b", "step_b", "stand")
"""Approach 1's walk: its two leg paintings and its standing one, eight frames a cycle."""


CUT_VARIANT = "tight"
"""Which of approach 2's paintings the pictures show as approach 2: `loose` or `tight`."""


@cache
def rig_doll(approach: str, who: str):
    poses.use()
    if approach == "dolls":
        return port.doll("grimy", who)
    from cut import doll

    variant = approach.removeprefix("cut-") if approach.startswith("cut-") else CUT_VARIANT
    return doll(who, variant)


def figure(approach: str, who: str, pose: str, facing: str, phase: float, height: float):
    """A resident standing `height` pixels tall, in `pose`, and where its feet are."""
    if approach in ("dolls", "cut", "cut-loose", "cut-tight"):
        return rig_doll(approach, who).draw(pose, facing, phase, height)
    if approach == "strip":
        if pose == "walking":
            return strip_figure(who, facing, phase, height)
        return whole_figure(who, pose, facing, phase, height)
    if approach in ("model", "repaint"):
        image = rendered(approach, who, frame_name(pose, facing, phase))
        scale = height / standing_px(approach, who)
        small = image.resize(
            (max(1, round(image.width * scale)), max(1, round(image.height * scale))), Image.LANCZOS
        )
        origin = (RENDER[0] / 2 * scale, GROUND_ROW * scale)
        if facing == "west":
            small = small.transpose(Image.FLIP_LEFT_RIGHT)
            origin = (small.width - origin[0], origin[1])
        return small, origin
    return whole_figure(who, pose, facing, phase, height)


def whole_figure(who: str, pose: str, facing: str, phase: float, height: float):
    """Approach 1: the sprite for the pose, flipped to face west, bobbing and swaying as it
    walks, and turning left and right on a ladder."""
    name, bob, sway, flip = "stand", 0.0, 0.0, facing == "west"
    i = round(phase * poses.WALK_FRAMES) % poses.WALK_FRAMES
    if pose in ("walking", "stairs"):
        name = WHOLE_WALK[i]
        bob = 0.025 * abs(math.sin(math.tau * phase))
        sway = 2.5 * math.sin(math.tau * phase)
    elif pose == "sitting":
        name = "sit"
    elif pose == "ladder":
        name = "climb"
        flip = (phase % 1.0) >= 0.5
        bob = 0.02 * abs(math.sin(math.tau * phase))
    image = whole_sprite(who, name)
    x, bottom, top = whole_feet()[f"{who}/{name}"]
    scale = height / standing_px("whole", who)
    small = image.resize(
        (max(1, round(image.width * scale)), max(1, round(image.height * scale))), Image.LANCZOS
    )
    origin = (x * scale, bottom * scale + bob * height)
    if sway:
        pad = round(small.height * 0.08)
        grown = Image.new("RGBA", (small.width + 2 * pad, small.height + 2 * pad))
        grown.paste(small, (pad, pad))
        small = grown.rotate(
            -sway, resample=Image.BICUBIC, center=(origin[0] + pad, origin[1] + pad)
        )
        origin = (origin[0] + pad, origin[1] + pad)
    if flip:
        small = small.transpose(Image.FLIP_LEFT_RIGHT)
        origin = (small.width - origin[0], origin[1])
    return small, origin


def label(image: Image.Image, text: str, size: int = 26) -> Image.Image:
    return styled_study.label(image, text, size)


stack = styled_study.stack
over = port.over


def row(approach: str, who_poses, height: float, gap: float = 0.62, top: float = 1.25):
    """Figures side by side on the backdrop, `height` px tall, each `(who, pose, facing, phase)`."""
    step = round(height * gap)
    out = Image.new(
        "RGBA", (step * (len(who_poses) + 1), round(height * top + height * 0.12)), (*BACKDROP, 255)
    )
    for n, (who, pose, facing, phase) in enumerate(who_poses):
        image, (ox, oy) = figure(approach, who, pose, facing, phase, height)
        over(out, image, round(step * (n + 1) - ox), round(height * top - oy))
    return out.convert("RGB")


def step_stills() -> None:
    """Each approach's four residents standing, at full size, then at play size 1:1."""
    rows = []
    for approach in APPROACHES:
        rows.append(
            label(
                row(approach, [(w, "standing", "east", 0) for w in WHO], 420, 0.75),
                TITLES[approach],
            )
        )
    save(stack(rows), "compare-stills", 1600)
    small = []
    for approach in APPROACHES:
        one = row(approach, [(w, "standing", "east", 0) for w in WHO], DOLL_M * 40, 0.75)
        two = row(approach, [(w, "standing", "east", 0) for w in WHO], DOLL_M * 80, 0.75)
        small.append(label(stack([one, two], across=True, gap=24), TITLES[approach], 18))
    save(stack(small), "compare-play-stills", None)
    picture = stack(small)
    picture.save(FULL / "compare-play-stills.png")
    picture.convert("RGB").save(OUT.parent / "images" / "compare-play-stills.png", optimize=True)


POSES = [
    ("standing", "east", 0.0, "stand"),
    ("walking", "east", 0.0, "walk"),
    ("walking", "east", 0.25, ""),
    ("walking", "east", 0.5, ""),
    ("walking", "east", 0.75, ""),
    ("sitting", "east", 0.0, "sit"),
    ("stairs", "east", 0.25, "stairs"),
    ("ladder", "north", 0.25, "ladder"),
    ("standing", "south", 0.0, "front"),
    ("standing", "north", 0.0, "back"),
]


def step_poses() -> None:
    """Each approach's residents in every pose, at about twice street size on a retina screen."""
    for approach in APPROACHES:
        rows = [row(approach, [(w, p, f, ph) for p, f, ph, _ in POSES], 230, 0.62) for w in WHO]
        save(
            label(
                stack(rows), TITLES[approach] + ": stand, walk, sit, stairs, ladder, front, back"
            ),
            f"{approach}-poses",
            1600,
        )


def walk_frames(approach: str, height: float) -> list[Image.Image]:
    return [
        row(approach, [(w, "walking", "east", i / poses.WALK_FRAMES) for w in WHO], height, 0.7)
        for i in range(poses.WALK_FRAMES)
    ]


def step_walks() -> None:
    for approach in WALKING:
        gif(walk_frames(approach, 180), f"{approach}-walk", poses.WALK_MS, 96)
    rows = {a: walk_frames(a, 120) for a in WALKING}
    both = [
        stack([label(rows[a][i], TITLES[a], 16) for a in WALKING]) for i in range(poses.WALK_FRAMES)
    ]
    gif(both, "walk-compare", poses.WALK_MS, 160)


CAMERA = 33.0
WALKERS = [
    ("lachlan", 35.0, "east", 0.0),
    ("odalys", 38.6, "west", 0.3),
    ("ingrid", 43.5, "east", 0.55),
    ("henrietta", 47.4, "east", 0.15),
]
"""Who's on the street in the close-ups: id, tile, facing and where they are in their walk."""


def street(approach: str, x0: float, width: int, walkers=WALKERS, scale: int = 1, t: float = 0.0):
    """#329's grimy High Street from tile `x0` at `scale` times play size, with this approach's
    residents walking on it."""
    from simile.papercraft import preview
    from simile.papercraft.village import TILE

    styled_study.use("grimy")
    view = styled_study.views()[styled_study.STREET]
    ppm = preview.SCENE_PPM * scale
    frame = scaled.street_scene(view, "afternoon", x0, width, scale).convert("RGBA")
    tile = TILE * ppm
    feet = scaled.ground_line(view, scale) + 8 * scale
    for who, x, facing, phase in walkers:
        step = (1 if facing == "east" else -1) * 1.2 * t / TILE
        cycle = phase + abs(step) * TILE / styled_study.STRIDE_M
        image, (ox, oy) = figure(approach, who, "walking", facing, cycle, DOLL_M * ppm)
        over(frame, image, round((x + step - x0) * tile - ox), round(feet - oy))
    return frame.convert("RGB")


def step_street() -> None:
    """The street close up as a retina screen draws it, 80 px/m, with each approach's residents."""
    for approach in WALKING:
        save(
            street(approach, CAMERA, 1600, scale=2).crop((0, 700, 1600, 1600)),
            f"{approach}-street",
            1600,
        )
    rows = [
        label(street(a, CAMERA, 1600, scale=2).crop((0, 1160, 1600, 1560)), TITLES[a], 22)
        for a in WALKING
    ]
    save(stack(rows), "compare-street", 1600, quality=88)


def step_play() -> None:
    """At play size 1:1: on a 1x screen at 40 px/m, and a retina screen at 80 px/m."""
    rows = []
    for approach in WALKING:
        wide = street(approach, CAMERA, 1600).crop((40, 372, 840, 792))
        close = street(approach, CAMERA, 1600, scale=2).crop((80, 1116, 880, 1536))
        rows.append(label(stack([wide, close], across=True, gap=16), TITLES[approach], 22))
    save(stack(rows), "compare-play-size", 1616, quality=88)


INSIDE = [
    ("odalys", 0, 4.5, "east", "standing"),
    ("lachlan", 0, 11.0, "west", "standing"),
    ("ingrid", 1, 6.0, "south", "standing"),
    ("henrietta", 2, 16.0, "west", "standing"),
]


def dollhouse(approach: str) -> Image.Image:
    """#329's coffee shop with its front off at 60 px/m, and this approach's residents in it."""
    from simile.papercraft import preview
    from simile.papercraft.village import TILE

    styled_study.use("grimy")
    all_views = styled_study.views()
    with styled_study.frame_size(styled_study.HOUSE_SIZE):
        picture = preview.dollhouse(all_views, styled_study.HOUSE)
        street_view = all_views[preview.manifest()["buildings"][styled_study.HOUSE]["street"]]
        facade = next(b for b in street_view.buildings if b.name == styled_study.HOUSE)
        rows = facade.h + 3
        ppm = min(preview.W * 0.8 / (facade.w * TILE), preview.H * 0.84 / (rows * TILE))
        left = (preview.W - facade.w * TILE * ppm) / 2
        ground = preview.H - 60
    floors = sorted(
        (v for v in all_views.values() if v.props.get("building") == styled_study.HOUSE),
        key=lambda v: v.props["floor"],
    )
    picture = picture.convert("RGBA")
    tile = TILE * ppm
    for who, floor, cell, facing, pose in INSIDE:
        view = floors[floor]
        feet = ground - (facade.y + facade.h - (view.props["street_y"] + 3)) * TILE * ppm + 3
        image, (ox, oy) = figure(approach, who, pose, facing, 0, DOLL_M * ppm)
        over(picture, image, round(left + (cell + 0.5) * tile - ox), round(feet - oy))
    return picture.convert("RGB").crop(styled_study.HOUSE_CROP)


def step_dollhouse() -> None:
    houses = [label(dollhouse(a).crop((126, 66, 1476, 876)), TITLES[a]) for a in APPROACHES]
    save(stack(houses), "compare-dollhouse", 1600, quality=84)


def step_seams() -> None:
    """Approach 2's cuts at the shoulder and hip through a walk, at full size, beside the same
    frames of #310's dolls."""
    rows = []
    variants = ["cut-loose"] + (
        ["cut-tight"] if (OUT / "cut" / "dolls-tight" / "henrietta.json").exists() else []
    )
    for approach in ("dolls", *variants):
        cells = []
        for who in WHO:
            for phase in (0.0, 0.25, 0.5, 0.75):
                image, (ox, oy) = figure(approach, who, "walking", "east", phase, 520)
                cell = Image.new("RGBA", (260, 300), (*BACKDROP, 255))
                over(cell, image, round(130 - ox), round(300 + 520 * 0.27 - oy))
                cells.append(cell.convert("RGB"))
        rows.append(
            label(
                stack(cells, across=True, gap=4),
                TITLES.get(approach, TITLES["cut"] + f", {approach[4:]} prompt")
                + ": shoulders and hips, walking",
                22,
            )
        )
    save(stack(rows), "cut-seams", 1800)


def step_sheets() -> None:
    """Approach 2's mannequins and what FLUX painted from them, with the loose prompt and the
    tight one."""
    import cut

    rows = []
    for who in WHO:
        cells = [Image.open(cut.FOLDER / "mannequins" / f"{who}.png").convert("RGB")]
        for variant in ("loose", "tight"):
            cut.VARIANT = variant
            if cut.painting_path(who).exists():
                cells.append(Image.open(cut.painting_path(who)).convert("RGB"))
        rows.append(stack(cells, across=True, gap=8))
    cut.VARIANT = "loose"
    title = "2. The mannequin sheet, then FLUX's painting of it with the loose and tight prompts"
    save(label(stack(rows, gap=8), title, 40), "cut-sheets", 1800)


def step_repaints() -> None:
    """Approach 4: each walk frame as Blender rendered it and as FLUX repainted it, frame by frame
    and four frames to a painting."""
    from repaint import STRIP_FOLDER

    rows = []
    for who in WHO:
        cells = {"model": [], "repaint": [], "strip": []}
        for i in range(poses.WALK_FRAMES):
            name = f"walk-{i}"
            for kind in cells:
                if kind == "strip":
                    path = STRIP_FOLDER / who / f"{name}.png"
                    image = Image.open(path).convert("RGBA") if path.exists() else None
                else:
                    image = rendered(kind, who, name)
                cell = Image.new("RGBA", RENDER, (*BACKDROP, 255))
                if image is not None:
                    cell.alpha_composite(image)
                cells[kind].append(
                    cell.convert("RGB").crop((56, 120, 456, 760)).resize((200, 320), Image.LANCZOS)
                )
        rows.append(stack([stack(cells[k], across=True, gap=0) for k in cells], gap=4))
    titled = label(
        stack(rows, gap=16),
        "4. The walk: Blender's render, FLUX frame by frame, and four frames to a painting",
    )
    save(titled, "repaint-frames", 1600)


def labels_for(approach: str, who: str, name: str, image: Image.Image) -> np.ndarray:
    """Each pixel's region, from a picture in the `Look`'s exact colours where the approach has
    one, or else by its nearest `Look` colour."""
    if approach == "model":
        flat = Image.open(OUT / "model" / who / f"{name}-flat.png")
        return flat_labels(flat, who, erode=2)
    if approach.startswith("repaint"):
        flat = Image.open(OUT / "model" / who / f"{name}-flat.png")
        return flat_labels(flat, who, erode=5)
    return nearest_labels(image, who)


def nearest_labels(image: Image.Image, who: str, far: float = 18.0) -> np.ndarray:
    """Each opaque pixel's nearest `Look` colour, CIEDE2000, if it's within `far` of it and
    nearer it than to ink or white: for pictures with nothing drawn in exact colours."""
    from simile.dolls.colour import delta_e

    rgba = np.asarray(image.convert("RGBA"), np.float64)
    wanted = targets(who)
    names = list(wanted)
    colours = [wanted[n] for n in names] + [np.array((46, 32, 28.0)), np.array((250, 250, 250.0))]
    distance = np.stack([delta_e(rgba[..., :3], c) for c in colours], axis=-1)
    best = distance.argmin(axis=-1)
    labels = np.full(best.shape, -1, np.int32)
    for i, name in enumerate(names):
        hit = (best == i) & (distance[..., i] < far) & (rgba[..., 3] > 200)
        labels[hit] = REGIONS.index(name)
    return labels


def match_doll(approach: str, who: str, pose: str, facing: str) -> dict:
    """A rig doll drawn painted and flat in the same pose, the flat one naming the regions."""
    d = rig_doll(approach, who)
    painted, _ = d.canvas(pose, facing, 0.0, shadows=False)
    plain = port.Doll(d.manifest, d.flat, d.flat, d.drawn)
    flat, _ = plain.canvas(pose, facing, 0.0, shadows=False)
    return measure(painted, flat_labels(flat, who, erode=2), who)


def cluster_match(image: Image.Image, who: str, k: int = 12, least: float = 0.006) -> dict:
    """The same check for a picture with nothing to name its regions: its opaque pixels in `k`
    colour clusters, and each `Look` colour against the nearest cluster that covers at least
    `least` of the figure. It finds whether a colour is there, not where."""
    import cv2

    from simile.dolls.colour import cielab, delta_e, hex_of

    rgba = np.asarray(image.convert("RGBA"), np.float64)
    pixels = rgba[..., :3][rgba[..., 3] > 200]
    lab = cielab(pixels).astype(np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.5)
    cv2.setRNGSeed(1)
    _, which, _ = cv2.kmeans(lab, k, None, criteria, 3, cv2.KMEANS_PP_CENTERS)
    which = which.ravel()
    clusters = []
    for i in range(k):
        mine = pixels[which == i]
        if len(mine) >= least * len(pixels):
            clusters.append((np.median(mine, axis=0), len(mine) / len(pixels)))
    out = {}
    for name, colour in targets(who).items():
        error, got, share = min(
            ((float(delta_e(c, colour)), c, share) for c, share in clusters), key=lambda f: f[0]
        )
        out[name] = {
            "want": hex_of(colour),
            "got": hex_of(got),
            "share": round(share, 3),
            "delta_e": round(error, 1),
        }
    return out


SPATIAL = {"dolls", "model", "repaint", "repaint-raw"}
"""Approaches with a picture in the `Look`'s exact colours lined up with what's painted: #310's
flat doll, and Blender's flat pass under each render and repaint."""


def standing(approach: str, who: str, facing: str) -> Image.Image:
    if approach == "whole":
        return whole_sprite(who, "stand")
    if approach == "strip":
        return Image.open(OUT / "whole" / "strip" / f"{who}-w0.png").convert("RGBA")
    if approach == "strip-raw":
        return Image.open(OUT / "whole" / "strip" / "raw" / f"{who}-w0.png").convert("RGBA")
    if approach in ("model", "repaint", "repaint-raw"):
        return rendered(approach, who, "stand" if facing == "east" else "front")
    image, _ = rig_doll(approach, who).canvas("standing", facing, 0.0, shadows=False)
    return image


def step_match() -> None:
    """Every approach's colours against each resident's `Look`, region by region: skin, hair,
    top, bottom, shoes, the accent and the apron. Where a flat picture names the regions, each
    region's median is measured there, as `dolls.matched` checks; and for every approach, the
    nearest colour cluster to each region."""
    rows = {}
    extra = ("strip", "strip-raw") if ready("strip") else ()
    raw = ("repaint-raw",) if ready("repaint") else ()
    for approach in APPROACHES + extra + raw:
        spatial, clustered = {}, {}
        for who in WHO:
            spatial[who], clustered[who] = {}, {}
            for facing, name in (("east", "stand"), ("south", "front")):
                if approach in ("whole", *extra) and facing == "south":
                    continue
                image = standing(approach, who, facing)
                clustered[who][name] = cluster_match(image, who)
                if approach == "dolls":
                    spatial[who][name] = match_doll(approach, who, "standing", facing)
                elif approach in SPATIAL:
                    spatial[who][name] = measure(image, labels_for(approach, who, name, image), who)
        rows[approach] = {"cluster": summary(clustered)}
        if approach in SPATIAL:
            rows[approach]["spatial"] = summary(spatial)
        print(
            approach,
            {k: (v["mean"], v["worst"][:2], v["missing"]) for k, v in rows[approach].items()},
        )
    (OUT / "match.json").write_text(json.dumps(rows, indent=1))


def summary(found: dict) -> dict:
    values, missing = [], []
    for who, views in found.items():
        for view, regions in views.items():
            for region, got in regions.items():
                if got["delta_e"] is None:
                    missing.append(f"{who} {view} {region}")
                else:
                    values.append(
                        (got["delta_e"], who, view, region, got.get("want"), got.get("got"))
                    )
    values.sort(reverse=True)
    return {
        "regions": len(values),
        "mean": round(float(np.mean([v[0] for v in values])), 1),
        "over 6": sum(v[0] > 6 for v in values),
        "worst": values[:6],
        "missing": missing,
        "by resident": found,
    }


def walk_cells(approach: str, who: str, height: float = 520) -> list[Image.Image]:
    out = []
    for i in range(poses.WALK_FRAMES):
        image, (ox, oy) = figure(approach, who, "walking", "east", i / poses.WALK_FRAMES, height)
        cell = Image.new("RGBA", (round(height * 1.1), round(height * 1.25)), (0, 0, 0, 0))
        over(cell, image, round(cell.width / 2 - ox), round(height * 1.15 - oy))
        out.append(cell)
    return out


def flicker(approach: str, who: str) -> dict:
    """How much each region's colour changes between walk frames: the mean CIEDE2000 from each
    frame's median to the cycle's, over the regions found in every frame."""
    from simile.dolls.colour import delta_e

    medians: dict[str, list] = {}
    rigless = ("dolls", "whole", "cut", "strip")
    cells = walk_cells(approach, who) if approach in rigless else range(8)
    for i, cell in enumerate(cells):
        if approach not in rigless:
            name = f"walk-{i}"
            labels = labels_for("repaint", who, name, None)
            p = np.asarray(rendered(approach, who, name), np.float64)
        else:
            labels = nearest_labels(cell, who)
            p = np.asarray(cell, np.float64)
        for region in targets(who):
            hit = (labels == REGIONS.index(region)) & (p[..., 3] > 200)
            if hit.sum() >= 30:
                medians.setdefault(region, []).append(np.median(p[..., :3][hit], axis=0))
    out = {}
    for region, found in medians.items():
        if len(found) == poses.WALK_FRAMES:
            centre = np.median(np.array(found), axis=0)
            out[region] = round(float(np.mean([delta_e(f, centre) for f in found])), 2)
    return out


def head_share(approach: str, who: str) -> float:
    """The head's share of the standing height: from the top of the head down to the neck, the
    narrowest row between a fifth and two thirds of the way down. From the front, or for
    approach 1 in three-quarter view and 1b from the side."""
    if approach == "strip":
        image, (ox, oy) = figure(approach, who, "walking", "east", 0, 600)
    else:
        facing = "east" if approach == "whole" else "south"
        image, (ox, oy) = figure(approach, who, "standing", facing, 0, 600)
    a = np.asarray(image.getchannel("A")) > 128
    rows = np.flatnonzero(a.any(axis=1))
    top = rows[0]
    widths = np.array([np.ptp(np.flatnonzero(r)) if r.any() else 0 for r in a])
    lo, hi = round(top + 0.2 * (oy - top)), round(top + 0.67 * (oy - top))
    neck = lo + int(np.argmin(widths[lo:hi]))
    return round(float((neck - top) / (oy - top)), 3)


def palette_distance(image: Image.Image) -> float:
    """#329's measure of how close a picture sits to the grimy references: the weighted mean CIE76
    from its 8 main colours to the nearest of theirs."""
    refs = np.concatenate(
        [styled_study.palette(Image.open(p))[0] for p in sorted((REFS / "grimy").glob("*.jpg"))]
    )
    colours, weights = styled_study.palette(image)
    d = np.sqrt(((colours[:, None] - refs[None]) ** 2).sum(axis=2)).min(axis=1)
    return round(float((d * weights).sum()), 1)


def edge_darkness(image: Image.Image) -> float:
    """The median lightness (L*) of a figure's outermost 3 px, where an ink line would be."""
    import cv2

    from simile.dolls.colour import cielab

    rgba = np.asarray(image, np.float64)
    a = (rgba[..., 3] > 128).astype(np.uint8)
    ring = a.astype(bool) & ~(cv2.erode(a, np.ones((7, 7), np.uint8)) > 0)
    return round(float(np.median(cielab(rgba[..., :3][ring])[..., 0])), 1)


def silhouette_iou(who: str) -> list[float]:
    """Approach 4: how much of each walk frame's outline FLUX kept, as the overlap of the repaint's
    silhouette with the render's."""
    out = []
    for i in range(poses.WALK_FRAMES):
        name = f"walk-{i}"
        a = np.asarray(rendered("model", who, name).getchannel("A")) > 128
        b = np.asarray(rendered("repaint", who, name).getchannel("A")) > 128
        out.append(round(float((a & b).sum() / max(1, (a | b).sum())), 3))
    return out


def step_consistency() -> None:
    rows = {}
    for approach in WALKING:
        row = {"flicker": {}, "head share": {}, "palette": {}, "edge L*": {}}
        for who in WHO:
            row["flicker"][who] = flicker(approach, who)
            row["head share"][who] = head_share(approach, who)
            image, _ = figure(
                approach, who, "walking" if approach == "strip" else "standing", "east", 0, 520
            )
            row["palette"][who] = palette_distance(image)
            row["edge L*"][who] = edge_darkness(image)
        if approach == "repaint":
            row["silhouette kept"] = {who: silhouette_iou(who) for who in WHO}
            for kind in ("repaint-raw", "repaint-strip"):
                found = {who: flicker(kind, who) for who in WHO}
                values = [v for f in found.values() for v in f.values()]
                row[f"flicker {kind}"] = found
                row[f"mean flicker {kind}"] = round(float(np.mean(values)), 2) if values else None
                row[f"worst flicker {kind}"] = round(float(np.max(values)), 2) if values else None
        flick = [v for f in row["flicker"].values() for v in f.values()]
        row["mean flicker"] = round(float(np.mean(flick)), 2) if flick else None
        row["worst flicker"] = round(float(np.max(flick)), 2) if flick else None
        shares = list(row["head share"].values())
        row["head share range"] = [min(shares), max(shares)]
        row["mean palette"] = round(float(np.mean(list(row["palette"].values()))), 1)
        darks = list(row["edge L*"].values())
        row["edge L* range"] = [min(darks), max(darks)]
        rows[approach] = row
        print(
            approach,
            row["mean flicker"],
            row["worst flicker"],
            row["head share range"],
            row["mean palette"],
            row["edge L* range"],
        )
    (OUT / "consistency.json").write_text(json.dumps(rows, indent=1))


def step_legibility() -> None:
    """#329's measure: how far each resident's edge stands out from the street just behind it at
    play size, CIEDE2000, averaged over the four."""
    from PIL import ImageFilter

    from simile.dolls.colour import delta_e

    rows = {}
    for approach in WALKING:
        empty = np.asarray(street(approach, CAMERA, 1600, walkers=[]), np.float64)
        scores = {}
        for walker in WALKERS:
            shown = np.asarray(street(approach, CAMERA, 1600, [walker]), np.float64)
            moved = np.abs(shown - empty).max(axis=2) > 12
            mask = Image.fromarray((moved * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(3))
            body = np.asarray(mask.filter(ImageFilter.MinFilter(3))) > 0
            outer = np.asarray(mask.filter(ImageFilter.MaxFilter(5))) > 0
            inner = body & ~(np.asarray(mask.filter(ImageFilter.MinFilter(5))) > 0)
            ring = outer & ~body
            if inner.any() and ring.any():
                a = np.median(shown[inner], axis=0)
                b = np.median(empty[ring], axis=0)
                scores[walker[0]] = round(float(delta_e(a, b)), 1)
        rows[approach] = {"mean": round(float(np.mean(list(scores.values()))), 1), **scores}
        print(approach, rows[approach])
    (OUT / "legibility.json").write_text(json.dumps(rows, indent=1))


def cost_group(e: dict) -> str:
    """What a painting was for, from its approach, key and prompt."""
    approach, key = e["approach"], e["key"]
    if approach == "whole":
        if key.startswith("strip/"):
            return "1b walk sheet"
        return "1 standing, from text" if key.endswith("/stand") else "1 pose edit"
    if approach == "cut":
        return "2 sheet, tight" if "exact pose" in e["prompt"] else "2 sheet, loose"
    if approach == "model":
        return "3 grime texture"
    return "4 strip of four" if key.startswith("strip/") else "4 frame"


def step_costs() -> None:
    """FLUX and Blender seconds, from the timing log."""
    entries = [json.loads(line) for line in (OUT / "timings.jsonl").read_text().splitlines()]
    groups: dict[str, list[float]] = {}
    loads: dict[str, list[float]] = {}
    for e in entries:
        if e["event"] == "paint":
            groups.setdefault(cost_group(e), []).append(e["seconds"])
        elif e["event"] == "load":
            loads.setdefault(e["approach"], []).append(e["seconds"])
    out = {}
    for key, seconds in sorted(groups.items()):
        out[key] = {
            "count": len(seconds),
            "mean": round(float(np.mean(seconds)), 1),
            "sum": round(sum(seconds)),
        }
        print(f"{key}: {len(seconds)} at {np.mean(seconds):.1f} s, {sum(seconds) / 60:.1f} min")
    for key, seconds in loads.items():
        out[f"{key} loads"] = {"count": len(seconds), "sum": round(sum(seconds))}
        print(f"{key} loads: {len(seconds)}, {sum(seconds) / 60:.1f} min")
    total = sum(v["sum"] for v in out.values())
    out["all FLUX minutes"] = round(total / 60, 1)
    print(f"FLUX in all: {total / 60:.0f} min")
    blender = {}
    for who in WHO:
        path = OUT / "model" / who / "timings.json"
        if path.exists():
            t = json.loads(path.read_text())
            frames = t["frames"]
            blender[who] = {
                "build": t["build"],
                "frames": len(frames),
                "toon per frame": round(float(np.mean([f["toon"] for f in frames.values()])), 2),
                "flat per frame": round(float(np.mean([f["flat"] for f in frames.values()])), 2),
            }
    out["blender"] = blender
    print(blender)
    (OUT / "costs.json").write_text(json.dumps(out, indent=1))


def step_export() -> None:
    """Everything for the previews branch, to out/export/: every painting, rejected ones
    included, every cut-out, doll and render at full size, the full-size pictures, the numbers
    and the timings."""
    import shutil

    target = OUT / "export"
    if target.exists():
        shutil.rmtree(target)

    def copy(source, to: str, pattern: str = "*") -> None:
        if source.is_dir():
            for path in sorted(source.rglob(pattern)):
                if path.is_file():
                    (target / to / path.relative_to(source)).parent.mkdir(
                        parents=True, exist_ok=True
                    )
                    shutil.copy(path, target / to / path.relative_to(source))
        elif source.exists():
            (target / to).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(source, target / to)

    copy(FULL, "pictures")
    copy(OUT / "whole" / "paintings", "1-whole/paintings")
    copy(OUT / "whole" / "rejected", "1-whole/rejected")
    copy(OUT / "whole" / "sprites", "1-whole/sprites")
    copy(OUT / "whole" / "strip", "1-whole/strip")
    copy(OUT / "cut" / "mannequins", "2-cut/mannequins")
    copy(OUT / "cut" / "paintings", "2-cut/paintings")
    copy(OUT / "cut" / "dolls", "2-cut/dolls")
    copy(OUT / "cut" / "dolls-tight", "2-cut/dolls-tight")
    for who in WHO:
        copy(OUT / "model" / who, f"3-model/{who}", "*.png")
        copy(OUT / "model" / who / "spec.json", f"3-model/{who}/spec.json")
        copy(OUT / "model" / who / "timings.json", f"3-model/{who}/timings.json")
        copy(OUT / "repaint" / who, f"4-repaint/{who}", "*.png")
        copy(OUT / "repaint-strip" / who, f"4-repaint-strip/{who}", "*.png")
    copy(OUT / "model" / "grime.png", "3-model/grime.png")
    copy(OUT / "model" / "grime-raw.png", "3-model/grime-raw.png")
    for name in (
        "timings.jsonl",
        "match.json",
        "consistency.json",
        "legibility.json",
        "costs.json",
    ):
        copy(OUT / name, name)


STEPS = {
    "stills": step_stills,
    "poses": step_poses,
    "walks": step_walks,
    "street": step_street,
    "play": step_play,
    "dollhouse": step_dollhouse,
    "seams": step_seams,
    "sheets": step_sheets,
    "repaints": step_repaints,
    "match": step_match,
    "consistency": step_consistency,
    "legibility": step_legibility,
    "costs": step_costs,
    "export": step_export,
}


if __name__ == "__main__":
    for step in sys.argv[1:] or [s for s in STEPS if s != "export"]:
        STEPS[step]()
