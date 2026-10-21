"""The study's pictures: each style's High Street, panning and with residents walking, the coffee
shop as a dollhouse, the residents and their walk, side-by-side comparisons, and the numbers.

`python compose.py [step …]` with steps `street`, `parallax`, `dollhouse`, `residents`, `walk`,
`play`, `sheets`, `compare`, `rig`, `outline`, `drift`, `consistency`, `skin`, `match`,
`legibility`, `costs`, `paintings` and `export`. Every picture goes to out/previews/ at full size,
and the README's to images/. `export` gathers what the previews branch holds into out/export/.
"""

import json
import math
import sys
from contextlib import contextmanager
from functools import cache
from pathlib import Path

import numpy as np
import pixel
import scaled
from common import IMAGES, OUT, REFS, STYLES
from dolls import DRAWN, WHO, over
from dolls import doll as load_doll
from dolls import folder as dolls_folder
from PIL import Image, ImageDraw, ImageFont

from simile.papercraft import preview
from simile.papercraft.village import TILE

REPO = Path(__file__).resolve().parents[2]
FULL = OUT / "previews"
NOW = "now"
LOOKS = (NOW, "papercraft", "cartoon", "grimy", "pixel", "flat")
"""The game's committed scenery and dolls, then the five styles."""
NEW = ("grimy", "pixel", "flat")
PEOPLE = (NOW, "papercraft", "cartoon", "grimy", "grimy-1.8", "pixel", "flat")
"""The looks the residents are compared in: the grimy cartoon at both head sizes."""
TITLES = {
    NOW: "The game now (#309, #310)",
    "papercraft": "Papercraft, modern references (#326)",
    "cartoon": "Klei-like cartoon (#326)",
    "grimy": "Grimy cartoon, heads 1.6x",
    "grimy-1.8": "Grimy cartoon, heads 1.8x",
    "grimy-painted": "Grimy cartoon, painted outline",
    "pixel": "Pixel art",
    "flat": "Flat cartoon",
}
STREET = "high_street"
HOUSE = "coffee_shop"
DOLL_M = 2.04
"""A resident's height on screen, 20% over scale, as the client draws them."""
STRIDE_M = 1.45
"""How far a walk cycle carries a resident, so their feet don't slide."""
CAMERA = 33.0
"""The first tile of the still street frame: the coffee shop, the square and the noodle bar."""
RETINA = 2
"""The street as the client draws it on a screen with two device pixels to a CSS pixel."""
CLOSE = (0, 700, 1600, 1600)
"""The part of the retina frame from `CAMERA` the close street picture shows."""
HOUSE_SIZE = (1650, 1100)
"""The dollhouse frame, so it's drawn at 60 px/m, three art pixels to a pixel art pixel."""
HOUSE_CROP = (24, 198, 1626, 1098)
WALKERS = [
    ("odalys", 36.0, "east", 0.0),
    ("lachlan", 39.5, "west", 0.3),
    ("ingrid", 47.0, "east", 0.55),
    ("kofi", 52.0, "east", 0.15),
    ("henrietta", 57.5, "south", 0.0),
    ("priya", 66.0, "west", 0.7),
]
"""Who's on the street: id, tile, facing and where they are in their walk cycle."""
PAN = [
    ("odalys", 8.0, "east", 0.0),
    ("lachlan", 22.0, "west", 0.3),
    ("ingrid", 34.0, "east", 0.55),
    ("kofi", 47.0, "east", 0.15),
    ("henrietta", 56.0, "south", 0.0),
    ("priya", 70.0, "west", 0.7),
]
"""Who's on the street while the camera pans along it."""
INSIDE = [
    ("odalys", 0, 4.5, "east"),
    ("kofi", 0, 11.0, "west"),
    ("priya", 1, 6.0, "south"),
    ("henrietta", 2, 16.0, "west"),
]
"""Who's in the coffee shop: id, floor, cell and facing."""


def scenery(look: str) -> Path:
    if look == NOW:
        return REPO / "content" / "papercraft"
    base = DRAWN[look].folder.split("-")[0] if look in DRAWN else look
    return OUT / base / "papercraft"


def use(look: str) -> None:
    """Points #309's previews at `look`'s scenery."""
    preview.CONTENT = scenery(look)
    preview.manifest.cache_clear()
    preview.piece.cache_clear()


@cache
def views() -> dict:
    return preview.read_views()


@cache
def doll(look: str, who: str):
    return load_doll(look, who)


def grid_of(look: str, ppm: float) -> int | None:
    """For pixel art, how many pixels an art pixel is at `ppm`."""
    if look not in DRAWN or not DRAWN[look].pixels:
        return None
    k = round(ppm / pixel.NATIVE)
    assert abs(k * pixel.NATIVE - ppm) < 1e-6, f"{ppm} px/m isn't a whole number of art pixels"
    return k


def figure(look: str, who: str, pose: str, facing: str, phase: float, ppm: float, k=None):
    """A resident `DOLL_M` tall at `ppm`, or in art pixels if `k`."""
    if k:
        return doll(look, who).native(pose, facing, phase, DOLL_M * pixel.NATIVE)
    return doll(look, who).draw(pose, facing, phase, DOLL_M * ppm)


def street(
    look: str, x0: float, width: int, walkers=WALKERS, t: float = 0.0, scale: int = 1
) -> Image.Image:
    """`look`'s High Street from tile `x0` at `scale` times play size, with its residents `t`
    seconds into their walk. Pixel art is drawn on its grid and its residents in art pixels."""
    use(look)
    view = views()[STREET]
    ppm = preview.SCENE_PPM * scale
    frame = scaled.street_scene(view, "afternoon", x0, width, scale)
    k = grid_of(look, ppm)
    if k:
        frame = pixel.snap_frame(frame, k)
    frame = frame.convert("RGBA")
    tile = TILE * ppm / (k or 1)
    feet = (scaled.ground_line(view, scale) + 8 * scale) / (k or 1)
    for who, x, facing, phase in walkers:
        walking = facing in ("east", "west")
        step = (1 if facing == "east" else -1) * 1.2 * t / TILE if walking else 0.0
        cycle = phase + abs(step) * TILE / STRIDE_M
        pose = "walking" if walking else "standing"
        image, (ox, oy) = figure(look, who, pose, facing, cycle, ppm, k)
        over(frame, image, round((x + step - x0) * tile - ox), round(feet - oy))
    return (pixel.up(frame, k) if k else frame).convert("RGB")


def close_street(look: str) -> Image.Image:
    """The street as the client draws it on a retina screen, 80 px/m: the coffee shop and the
    square."""
    return street(look, CAMERA, 1600, scale=RETINA).crop(CLOSE)


def save(image: Image.Image, name: str, width: int | None = 1600, quality: int = 86) -> None:
    """The full picture to out/previews/, and one `width` wide to images/ (none if None), with
    full colour resolution so thin lines and pixel edges stay crisp."""
    FULL.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(FULL / f"{name}.jpg", quality=92, subsampling=0)
    if width is None:
        return
    IMAGES.mkdir(parents=True, exist_ok=True)
    small = image.convert("RGB")
    if small.width > width:
        small = small.resize((width, round(small.height * width / small.width)), Image.LANCZOS)
    path = IMAGES / f"{name}.jpg"
    small.save(path, quality=quality, optimize=True, progressive=True, subsampling=0)
    print(f"images/{name}.jpg {path.stat().st_size / 1e3:.0f} kB", flush=True)


def gif(frames: list[Image.Image], name: str, ms: int, colours: int = 128) -> None:
    IMAGES.mkdir(parents=True, exist_ok=True)
    first = frames[0].quantize(colours, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    rest = [f.quantize(palette=first, dither=Image.Dither.NONE) for f in frames[1:]]
    path = IMAGES / f"{name}.gif"
    first.save(path, save_all=True, append_images=rest, duration=ms, loop=0, optimize=True)
    print(f"images/{name}.gif {path.stat().st_size / 1e3:.0f} kB", flush=True)


def label(image: Image.Image, text: str, size: int = 28) -> Image.Image:
    out = Image.new("RGB", (image.width, image.height + size + 16), (246, 242, 234))
    out.paste(image.convert("RGB"), (0, size + 16))
    font = ImageFont.load_default(size=size)
    ImageDraw.Draw(out).text((12, 6), text, (40, 34, 30), font)
    return out


def stack(images: list[Image.Image], across: bool = False, gap: int = 12) -> Image.Image:
    if across:
        h = max(i.height for i in images)
        out = Image.new("RGB", (sum(i.width for i in images) + gap * (len(images) - 1), h), "white")
        x = 0
        for i in images:
            out.paste(i, (x, 0))
            x += i.width + gap
        return out
    w = max(i.width for i in images)
    out = Image.new("RGB", (w, sum(i.height for i in images) + gap * (len(images) - 1)), "white")
    y = 0
    for i in images:
        out.paste(i, (0, y))
        y += i.height + gap
    return out


def styles() -> list[str]:
    return [look for look in LOOKS[1:] if (scenery(look) / "manifest.json").exists()]


def step_street(looks=None) -> None:
    for look in looks or styles():
        view = views()[STREET]
        width = round(view.width * TILE * preview.SCENE_PPM)
        save(street(look, 0, width - width % 2), f"{look}-street-full", None)
        save(close_street(look), f"{look}-street")


def step_parallax(looks=None, frames: int = 24) -> None:
    """Panning along the street, 24 frames at 400 x 225, or for pixel art a 400 x 225 window of
    its art pixels."""
    for look in looks or styles():
        view = views()[STREET]
        k = grid_of(look, preview.SCENE_PPM) or 1
        span = view.width - preview.W / (TILE * preview.SCENE_PPM)
        images = []
        for i in range(frames):
            x0 = span * (0.5 - 0.5 * math.cos(math.pi * i / (frames - 1)))
            x0 = round(x0 * TILE * pixel.NATIVE) / (TILE * pixel.NATIVE) if k > 1 else x0
            images.append(street(look, x0, preview.W, PAN, t=i * 0.165))
        if k > 1:
            small = [f.resize((f.width // k, f.height // k), Image.NEAREST) for f in images]
            small = [f.crop((200, 180, 600, 405)) for f in small]
        else:
            small = [f.resize((400, 225), Image.LANCZOS) for f in images]
        gif(small, f"{look}-street-parallax", 165, 64)
        FULL.mkdir(parents=True, exist_ok=True)
        images[0].save(
            FULL / f"{look}-street-parallax.webp",
            save_all=True,
            append_images=images[1:],
            duration=165,
            loop=0,
            quality=80,
        )


@contextmanager
def frame_size(size: tuple[int, int]):
    saved = preview.W, preview.H
    preview.W, preview.H = size
    try:
        yield
    finally:
        preview.W, preview.H = saved


def dollhouse(look: str) -> Image.Image:
    """The coffee shop with its front off, as #309's preview draws it at 60 px/m, and its
    residents in."""
    use(look)
    all_views = views()
    with frame_size(HOUSE_SIZE):
        picture = preview.dollhouse(all_views, HOUSE)
        street_view = all_views[preview.manifest()["buildings"][HOUSE]["street"]]
        facade = next(b for b in street_view.buildings if b.name == HOUSE)
        rows = facade.h + 3
        ppm = min(preview.W * 0.8 / (facade.w * TILE), preview.H * 0.84 / (rows * TILE))
        left = (preview.W - facade.w * TILE * ppm) / 2
        ground = preview.H - 60
    floors = sorted(
        (v for v in all_views.values() if v.props.get("building") == HOUSE),
        key=lambda v: v.props["floor"],
    )
    k = grid_of(look, round(ppm, 6))
    if k:
        picture = pixel.snap_frame(picture, k)
    picture = picture.convert("RGBA")
    tile = TILE * ppm / (k or 1)
    for who, floor, cell, facing in INSIDE:
        view = floors[floor]
        feet = ground - (facade.y + facade.h - (view.props["street_y"] + 3)) * TILE * ppm + 3
        image, (ox, oy) = figure(look, who, "standing", facing, 0, ppm, k)
        over(
            picture,
            image,
            round(left / (k or 1) + (cell + 0.5) * tile - ox),
            round(feet / (k or 1) - oy),
        )
    picture = pixel.up(picture, k) if k else picture
    return picture.convert("RGB").crop(HOUSE_CROP)


def step_dollhouse(looks=None) -> None:
    for look in looks or styles():
        save(dollhouse(look), f"{look}-dollhouse")


def lineup(look: str, height: float = 245) -> Image.Image:
    """Every resident from the front, the side and the back, at twice street size or so. Pixel
    art at the whole number of pixels to an art pixel nearest `height`."""
    k = grid_of(look, pixel.NATIVE) and max(1, round(height / (DOLL_M * pixel.NATIVE)))
    gap = round(height * 0.42)
    out = Image.new("RGBA", (gap * (3 * len(WHO) + 1), round(height * 1.5)), (240, 234, 222, 255))
    x = gap
    for who in WHO:
        for facing in ("south", "east", "north"):
            image, (ox, oy) = posed(look, who, "standing", facing, 0, height, k)
            over(out, image, round(x - ox), round(height * 1.32 - oy))
            x += gap
    return out.convert("RGB")


def posed(look, who, pose, facing, phase, height, k):
    """A resident `height` px tall, or for pixel art in art pixels scaled `k` times."""
    if k:
        image, (ox, oy) = doll(look, who).native(pose, facing, phase, DOLL_M * pixel.NATIVE)
        return pixel.up(image, k), (ox * k, oy * k)
    return doll(look, who).draw(pose, facing, phase, height)


def step_residents(looks=None) -> None:
    for look in looks or [*styles(), "grimy-1.8"]:
        if look == "grimy-1.8" and "grimy" not in styles():
            continue
        save(lineup(look), f"{look}-residents")


def walk_frames(look: str, height: float = 164, frames: int = 12) -> list[Image.Image]:
    k = grid_of(look, pixel.NATIVE) and max(1, round(height / (DOLL_M * pixel.NATIVE)))
    gap = round(height * 0.62)
    out = []
    for i in range(frames):
        frame = Image.new(
            "RGBA", (gap * (len(WHO) + 1), round(height * 1.32)), (240, 234, 222, 255)
        )
        for n, who in enumerate(WHO):
            image, (ox, oy) = posed(look, who, "walking", "east", i / frames, height, k)
            over(frame, image, round(gap * (n + 1) - ox), round(height * 1.2 - oy))
        out.append(frame.convert("RGB"))
    return out


def step_walk(looks=None) -> None:
    for look in looks or styles():
        frames = walk_frames(look)
        gif(frames, f"{look}-walk", 90, 96)
        save(stack(frames[::3], across=True, gap=0), f"{look}-walk-frames", 1600)
    rows = {look: walk_frames(look, 122) for look in PEOPLE if look_exists(look)}
    both = [stack([label(rows[look][i], TITLES[look], 18) for look in rows]) for i in range(12)]
    gif(both, "walk-compare", 90, 160)


def look_exists(look: str) -> bool:
    return look == NOW or (dolls_folder(look) / "odalys.json").exists()


def step_play() -> None:
    """A stretch of street 1:1 at play size, 40 px/m, and as the client draws it on a retina
    screen, 80 px/m, about the same middle."""
    rows = []
    for look in LOOKS:
        wide = street(look, CAMERA, 1600).crop((180, 372, 980, 792))
        close = street(look, CAMERA, 1600, scale=RETINA).crop((760, 1116, 1560, 1536))
        rows.append(label(stack([wide, close], across=True, gap=16), TITLES[look], 22))
    save(stack(rows), "compare-play-size", 1616, quality=88)


def contact(look: str) -> Image.Image:
    use(look)
    keys = [
        k for k in preview.manifest()["pieces"] if k.split("/")[0] in ("furniture", "platforms")
    ]
    return preview.grid([(k.split("/", 1)[1], preview.piece(k)) for k in keys], (240, 240), 7)


def step_sheets(looks=None) -> None:
    for look in looks or styles():
        save(contact(look), f"{look}-furniture")
        use(look)
        fronts = [
            (k.split("/")[1], preview.piece(k))
            for k in preview.manifest()["pieces"]
            if k.startswith("fronts/")
        ]
        save(preview.grid(fronts, (520, 420), 4), f"{look}-fronts")
        layers = [
            (k.split("/")[1], preview.piece(k))
            for k in preview.manifest()["pieces"]
            if k.startswith(("layers/", "papers/"))
        ]
        save(preview.grid(layers, (380, 260), 4), f"{look}-layers")


def step_compare() -> None:
    streets = [
        label(street(look, CAMERA, 1600).crop((0, 160, 1600, 900)), TITLES[look]) for look in LOOKS
    ]
    save(stack(streets), "compare-street", 1600, quality=84)
    houses = [label(dollhouse(look).crop((126, 66, 1476, 876)), TITLES[look]) for look in LOOKS]
    save(stack(houses), "compare-dollhouse", 1600, quality=84)
    people = [label(lineup(look, 204), TITLES[look]) for look in PEOPLE if look_exists(look)]
    save(stack(people), "compare-residents", 1800)
    refs = []
    for look in STYLES:
        row = [
            Image.open(REFS / look / f"{n}.jpg").resize((448, 256), Image.LANCZOS)
            for n in ("street", "interior", "residents", "signage")
            if (REFS / look / f"{n}.jpg").exists()
        ]
        if row:
            refs.append(label(stack(row, across=True, gap=6), TITLES[look], 22))
    save(stack(refs), "references", 1800)


def step_rig() -> None:
    """Pixel art residents three ways: the rig drawn at the art's own size with nearest-neighbour
    turns, the same with turns at eight times the size, and the smooth rig with each frame
    pixelated. Each at four times its art pixels, and how many stray pixels and loose bits each
    frame has."""
    import cv2

    modes = {
        "nearest": "Rig at 41 px, nearest-neighbour turns",
        "rotsprite": "Rig at 41 px, turns at 8x then back down",
        "baked": "Smooth rig, each frame pixelated",
    }
    frames, zoom, box = 12, 4, (44, 54)
    numbers = {}
    rows = {mode: [] for mode in modes}
    for mode in modes:
        strays, pieces = [], []
        for i in range(frames):
            cells = []
            for name in WHO:
                image, (ox, oy) = doll("pixel", name).native(
                    "walking", "east", i / frames, DOLL_M * pixel.NATIVE, mode
                )
                a = np.asarray(image)
                solid = a[..., 3] > 0
                same = np.zeros(solid.shape, dtype=int)
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        if dy or dx:
                            moved = np.roll(np.roll(a, dy, 0), dx, 1)
                            same += solid & (moved == a).all(axis=2)
                strays.append(int((solid & (same == 0)).sum()))
                count, _ = cv2.connectedComponents(solid.astype(np.uint8), connectivity=8)
                pieces.append(count - 1)
                cell = Image.new("RGBA", box, (240, 234, 222, 255))
                over(cell, image, round(box[0] / 2 - ox), round(box[1] - 3 - oy))
                cells.append(cell.convert("RGB"))
            rows[mode].append(pixel.up(stack(cells, across=True, gap=0), zoom))
        numbers[mode] = {
            "stray pixels a frame": round(float(np.mean(strays)), 1),
            "frames in more than one bit": round(float(np.mean(np.array(pieces) > 1)), 2),
        }
    print(numbers)
    (OUT / "rig.json").write_text(json.dumps(numbers, indent=1))
    shown = [stack([label(rows[m][i], t, 18) for m, t in modes.items()]) for i in range(frames)]
    gif(shown, "pixel-rig", 110, 128)
    still = [stack([rows[m][i] for i in (0, 3, 6, 9)], gap=6) for m in modes]
    titled = [label(s, t, 20) for s, t in zip(still, modes.values(), strict=True)]
    save(stack(titled, across=True, gap=16), "pixel-rig", 1600)


def step_outline() -> None:
    """The grimy cartoon's one outline: the painted line alone, the drawn one alone, and #326's
    two together, on the residents painted both ways, at three times street size."""
    who = [w for w in WHO if (dolls_folder("grimy") / f"{w}.json").exists()]
    rows = []
    for look, title in (
        ("grimy-painted", "Painted outline alone"),
        ("grimy", "Drawn outline alone, on sheets painted without one"),
        ("cartoon", "#326: painted and drawn"),
    ):
        height = 250
        gap = round(height * 0.5)
        out = Image.new(
            "RGBA", (gap * (3 * len(who) + 1), round(height * 1.4)), (240, 234, 222, 255)
        )
        x = gap
        for name in who:
            for facing in ("south", "east", "north"):
                image, (ox, oy) = posed(look, name, "standing", facing, 0, height, None)
                over(out, image, round(x - ox), round(height * 1.3 - oy))
                x += gap
        rows.append(label(out.convert("RGB"), title, 22))
    save(stack(rows), "grimy-outline", 1600)


def step_paintings(looks=None) -> None:
    """Every painting a style's pieces are cut from, named by piece, to out/paintings/ for the
    previews branch: a front is one painting a unit, numbered from the left."""
    from scenery import builder

    for look in looks or NEW:
        build = builder(STYLES[look])
        folder = OUT / "paintings" / look / "used"
        folder.mkdir(parents=True, exist_ok=True)
        for key, piece in build.pieces.items():
            for unit in build.jobs(piece):
                path = build.raw_path(piece, unit)
                if path.exists():
                    name = key.replace("/", "-") + ("" if unit is None else f"-{unit}")
                    Image.open(path).convert("RGB").save(folder / f"{name}.jpg", quality=88)


def step_legibility() -> None:
    """How clearly each resident stands out from the street at play size: the mean CIEDE2000
    between the doll's own edge pixels and the street just outside them, over the six on the
    still street frame. Higher stands out more."""
    from PIL import ImageFilter

    from simile.dolls.colour import delta_e

    rows = {}
    for look in LOOKS:
        empty = np.asarray(street(look, CAMERA, 1600, walkers=[]), dtype=np.float64)
        scores = {}
        for who, x, facing, phase in WALKERS:
            shown = np.asarray(street(look, CAMERA, 1600, [(who, x, facing, phase)]), float)
            moved = np.abs(shown - empty).max(axis=2) > 12
            mask = Image.fromarray((moved * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(3))
            body = np.asarray(mask.filter(ImageFilter.MinFilter(3))) > 0
            outer = np.asarray(mask.filter(ImageFilter.MaxFilter(5))) > 0
            inner = body & ~(np.asarray(mask.filter(ImageFilter.MinFilter(5))) > 0)
            ring = outer & ~body
            if not inner.any() or not ring.any():
                continue
            a = np.median(shown[inner], axis=0)
            b = np.median(empty[ring], axis=0)
            scores[who] = round(float(np.mean(delta_e(a, b))), 1)
        rows[look] = {"mean": round(float(np.mean(list(scores.values()))), 1), **scores}
        print(look, rows[look])
    (OUT / "legibility.json").write_text(json.dumps(rows, indent=1))


def step_export() -> None:
    """Everything for the previews branch, to out/export/: the full-size pictures, every painting,
    piece, doll and reference, rejected ones included, and the numbers."""
    import shutil

    from references import SEEDS

    target = OUT / "export"
    if target.exists():
        shutil.rmtree(target)

    def copy(source: Path, to: str) -> None:
        if source.exists():
            (target / to).parent.mkdir(parents=True, exist_ok=True)
            if source.is_dir():
                shutil.copytree(source, target / to)
            else:
                shutil.copy(source, target / to)

    copy(FULL, "previews")
    for look in NEW:
        copy(OUT / "paintings" / look, f"paintings/{look}")
        copy(scenery(look), f"pieces/{look}")
    copy(OUT / "pixel" / "smooth", "pieces/pixel-smooth")
    for variant in (*NEW, "grimy-plain"):
        folder = OUT / variant / "dolls"
        for path in sorted(folder.glob("*")):
            copy(path, f"dolls/{variant}/{path.name}")
    for path in sorted((OUT / "references").glob("*.png")):
        style, scene, seed = path.stem.split("-")[:3]
        if style not in NEW:
            continue
        kept = SEEDS.get(f"{style}/{scene}", 42) == int(seed) and path.stem.count("-") == 2
        image = Image.open(path).convert("RGB")
        folder = target / ("references/used" if kept else "references/rejected")
        folder.mkdir(parents=True, exist_ok=True)
        image.save(folder / f"{path.stem}.jpg", quality=90)
    for style in NEW:
        copy(REFS / style / "signage.jpg", f"references/used/{style}-signage-as-kept.jpg")
    for variant in ("8-bit", "bf16", "large", "text"):
        for folder in sorted((OUT / "sharpness" / variant).glob("*")):
            for kind in ("papercraft", "dolls"):
                copy(folder / kind, f"sharpness/{variant}/{folder.name}/{kind}")
    copy(OUT / "timings.jsonl", "timings.jsonl")
    for look in NEW:
        copy(OUT / look / "cache" / "timings.jsonl", f"timings-{look}-scenery.jsonl")
    for name in ("consistency", "skin", "match", "sharpness", "legibility", "rig"):
        copy(OUT / f"{name}.json", f"{name}.json")


def step_drift() -> None:
    """#309's pieces, the same prompts against the modern references, and this study's prompts."""
    from scenery import DRIFT

    OURS = {"layers/near-gardens": "layers/near-walls"}
    columns = [
        ("#309: its prompt and references", NOW, lambda k: k),
        ("#309's prompt, modern references", "papercraft", lambda k: f"drift/{k.split('/')[1]}"),
        ("Modern prompt and references", "papercraft", lambda k: OURS.get(k, k)),
    ]
    rows = []
    for key in DRIFT:
        cells = []
        for title, look, name in columns:
            use(look)
            image = preview.piece(name(key))
            box = Image.new("RGBA", (520, 300), (232, 226, 214, 255))
            image.thumbnail((500, 280), Image.LANCZOS)
            box.alpha_composite(image, ((520 - image.width) // 2, (300 - image.height) // 2))
            cells.append(label(box.convert("RGB"), title, 18) if not rows else box.convert("RGB"))
        rows.append(stack(cells, across=True, gap=8))
    save(stack(rows, gap=8), "drift", 1600)


def palette(image: Image.Image, n: int = 8) -> tuple[np.ndarray, np.ndarray]:
    """`image`'s `n` main opaque colours in CIELAB, and how much of it each covers."""
    from simile.dolls.colour import cielab

    rgba = np.asarray(
        image.convert("RGBA").resize((128, round(128 * image.height / image.width) or 1))
    )
    rgb = rgba[..., :3][rgba[..., 3] > 128].astype(np.float64)
    if len(rgb) < n:
        return np.zeros((0, 3)), np.zeros(0)
    q = Image.fromarray(rgb[None].astype(np.uint8)).quantize(n, method=Image.Quantize.MEDIANCUT)
    colours = np.asarray(q.getpalette()[: 3 * n]).reshape(-1, 3)
    counts = np.bincount(np.asarray(q).ravel(), minlength=n)[:n]
    return cielab(colours), counts / counts.sum()


def step_consistency() -> None:
    """How far each piece's colours sit from its style's references: the weighted mean CIE76
    distance from each of its 8 main colours to the nearest of the references', as #295
    measured it. Lower is closer."""
    rows = {}
    for look in LOOKS:
        folder = REPO / "content" / "papercraft" / "references" if look == NOW else REFS / look
        refs = np.concatenate([palette(Image.open(p))[0] for p in sorted(folder.glob("*.jpg"))])
        use(look)
        manifest = preview.manifest()
        distances = {}
        for key in manifest["pieces"]:
            if key.startswith("glow/"):
                continue
            colours, weights = palette(preview.piece(key))
            if not len(colours):
                continue
            d = np.sqrt(((colours[:, None] - refs[None]) ** 2).sum(axis=2)).min(axis=1)
            distances[key] = round(float((d * weights).sum()), 1)
        rows[look] = {"pieces": distances}
    shared = set.intersection(*(set(row["pieces"]) for row in rows.values()))
    for look, row in rows.items():
        values = [row["pieces"][k] for k in sorted(shared)]
        row["mean"], row["max"] = round(float(np.mean(values)), 1), max(values)
        print(look, row["mean"], row["max"], f"over the {len(shared)} pieces they all have")
    (OUT / "consistency.json").write_text(json.dumps(rows, indent=1))


def step_skin() -> None:
    """How far the painter moved each resident's skin on their side sheet, before #310's
    restore pulls it back: CIEDE2000 from the `Appearance`, and the lightness change."""
    from dolls import styled_pipeline

    from simile.dolls.build import people
    from simile.dolls.colour import cielab, delta_e
    from simile.dolls.look import Look
    from simile.dolls.sheet import sheet

    everyone, rows = people(), {}
    for look in LOOKS:
        with styled_pipeline(look if look in STYLES else "papercraft"):
            for who in WHO:
                sheets = OUT / NOW / "sheets" if look == NOW else dolls_folder(look) / "sheets"
                path = sheets / f"{who}-side"
                painted = Image.open(next(path.parent.glob(f"{path.name}.*"))).convert("RGB")
                skin_look = Look.of(everyone[who], who)
                laid = sheet("side", skin_look)
                drawn = np.asarray(laid.pieces["head"].drawn.convert("RGB"))
                x, y = laid.spots["head"]
                h, w = drawn.shape[:2]
                crop = np.asarray(painted)[y : y + h, x : x + w].astype(np.float64)
                skin = (drawn == np.array(skin_look.skin)).all(axis=2)
                got = np.median(crop[skin], axis=0)
                lightness = cielab(got)[0] - cielab(np.array(skin_look.skin))[0]
                rows.setdefault(look, {})[who] = {
                    "skin": everyone[who].skin,
                    "painted": "#" + "".join(f"{round(v):02x}" for v in got),
                    "delta_e": round(float(delta_e(got, np.array(skin_look.skin))), 1),
                    "lighter": round(float(lightness), 1),
                }
    for look, row in rows.items():
        mean = np.mean([r["delta_e"] for r in row.values()])
        lighter = np.mean([r["lighter"] for r in row.values()])
        print(
            f"{look}: ΔE {mean:.1f}, L* {lighter:+.1f}", {k: v["delta_e"] for k, v in row.items()}
        )
    (OUT / "skin.json").write_text(json.dumps(rows, indent=1))


MATCHED = (NOW, "papercraft", "cartoon", "grimy", "grimy-painted", "pixel", "flat")


def step_match() -> None:
    """How far each colour region of each painted piece sits from its flat colour, in the
    atlases as committed: the median of its painted pixels, CIEDE2000. Every region of every
    doll, so ears and noses count as much as faces. For pixel art, also each region's art
    pixels in the frames the street shows."""
    from simile.dolls.colour import delta_e
    from simile.dolls.sheet import regions

    rows = {}
    for look in MATCHED:
        if not look_exists(look):
            continue
        worst = []
        for who in WHO:
            d = doll(look, who)
            flat = Image.open(dolls_folder(look) / d.manifest["flat"]).convert("RGBA")
            for piece, spec in d.pieces.items():
                x, y, w, h = spec["frame"]
                f = flat.crop((x, y, x + w, y + h))
                p = np.asarray(d.atlas.crop((x, y, x + w, y + h)).convert("RGB"), dtype=float)
                a = np.asarray(f, dtype=float)
                nearest, main, opaque = regions(f)
                for i, colour in enumerate(main):
                    core = opaque & (nearest == i) & (np.abs(a[..., :3] - colour).max(axis=2) < 1)
                    if core.sum() < 6:
                        continue
                    got = np.median(p[core], axis=0)
                    error = round(float(delta_e(got, colour)), 1)
                    hexes = ["#" + "".join(f"{round(v):02x}" for v in c) for c in (colour, got)]
                    worst.append((error, who, piece, *hexes))
        worst.sort(reverse=True)
        rows[look] = {
            "regions": len(worst),
            "over 6": sum(e > 6 for e, *_ in worst),
            "worst": worst[:8],
        }
        print(look, rows[look]["regions"], rows[look]["over 6"], worst[:5])
    if look_exists("pixel"):
        rows["pixel frames"] = pixel_match()
        print("pixel frames", rows["pixel frames"]["regions"], rows["pixel frames"]["over 6"])
    (OUT / "match.json").write_text(json.dumps(rows, indent=1))


def pixel_match() -> dict:
    """Each colour region of each piece as the pixel art rig draws it, at the art's own size:
    every art pixel is given the flat region that covers most of it, and each region's median
    art pixel is measured against its flat colour. Ears and noses an art pixel or two across
    count as much as faces."""
    from simile.dolls.colour import delta_e

    worst = []
    for who in WHO:
        painted = doll("pixel", who)
        plain = load_doll("pixel", who)
        plain.atlas = plain.flat
        scale = painted.standing_height() / (DOLL_M * pixel.NATIVE)
        palette = painted._palette()
        for name in painted.pieces:
            shown, _ = painted._native_piece(name, scale, palette)
            flat, _ = plain.sprite(name)
            ids, main, _ = pixel.region_ids(flat, shown.size)
            s = np.asarray(shown)
            for region in np.unique(ids[ids >= 0]):
                found = s[..., :3][(ids == region) & (s[..., 3] > 0)]
                got = np.median(found, axis=0)
                error = round(float(delta_e(got, main[region])), 1)
                hexes = ["#" + "".join(f"{round(v):02x}" for v in c) for c in (main[region], got)]
                worst.append((error, who, name, len(found), *hexes))
    worst.sort(reverse=True)
    return {"regions": len(worst), "over 6": sum(e > 6 for e, *_ in worst), "worst": worst[:8]}


START = 1792560000
"""When #329's painting began: earlier timings are #326's."""


def step_costs() -> None:
    """#329's FLUX time from the timing logs: the references, sharpness tests and doll sheets
    since `START`, and every scenery painting of the three new styles."""
    ours = [json.loads(line) for line in (OUT / "timings.jsonl").read_text().splitlines()]
    ours = [e for e in ours if e.get("at", 0) >= START]
    for style in NEW:
        path = OUT / style / "cache" / "timings.jsonl"
        if path.exists():
            for line in path.read_text().splitlines():
                ours.append({**json.loads(line), "event": "paint", "style": style})
    groups: dict[str, list[float]] = {}
    for e in ours:
        if e["event"] == "sharpness":
            group = "sharpness " + ("text" if e.get("text") else e["bits"] and "8-bit" or "bf16")
        elif e["event"] != "paint":
            continue
        elif "style" in e:
            group = f"{e['style']} {e['kind']}"
        else:
            group = f"{e['key'].split('/')[1]} {e['kind']}"
        groups.setdefault(group, []).append(e["seconds"])
    for key, seconds in sorted(groups.items()):
        print(
            f"{key}: {len(seconds)} at {np.mean(seconds):.1f} s "
            f"({min(seconds):.0f} to {max(seconds):.0f})"
        )
    paints = sum(len(v) for v in groups.values())
    loads = [e["seconds"] for e in ours if e["event"] == "load"]
    total = sum(sum(v) for v in groups.values()) + sum(loads)
    print(f"{paints} paintings, {len(loads)} loads, {total / 60:.0f} min of FLUX in all")


STEPS = {
    "street": step_street,
    "parallax": step_parallax,
    "dollhouse": step_dollhouse,
    "residents": step_residents,
    "walk": step_walk,
    "play": step_play,
    "sheets": step_sheets,
    "compare": step_compare,
    "rig": step_rig,
    "outline": step_outline,
    "drift": step_drift,
    "consistency": step_consistency,
    "skin": step_skin,
    "match": step_match,
    "legibility": step_legibility,
    "costs": step_costs,
    "paintings": step_paintings,
    "export": step_export,
}


if __name__ == "__main__":
    for step in sys.argv[1:] or STEPS:
        STEPS[step]()
