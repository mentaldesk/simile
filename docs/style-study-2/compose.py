"""The study's pictures: each style's High Street, panning and with residents walking, the coffee
shop as a dollhouse, the residents and their walk, side-by-side comparisons, and the numbers.

`python compose.py [step …]` with steps `street`, `parallax`, `dollhouse`, `residents`, `walk`,
`play`, `sheets`, `compare`, `drift`, `consistency`, `skin`, `match`, `costs`. Every picture goes to
out/previews/ at full size, and the README's to images/.
"""

import json
import math
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from common import IMAGES, OUT, REFS, STYLES
from dolls import WHO, doll, over
from dolls import folder as dolls_folder
from PIL import Image, ImageDraw, ImageFont

from simile.papercraft import preview
from simile.papercraft.village import TILE

REPO = Path(__file__).resolve().parents[2]
FULL = OUT / "previews"
NOW = "now"
LOOKS = (NOW, "papercraft", "cartoon")
"""The game's committed scenery and dolls, then the two styles."""
TITLES = {
    NOW: "The game now (#309, #310)",
    "papercraft": "Papercraft, modern references",
    "cartoon": "Hand-drawn cartoon",
}
STREET = "high_street"
HOUSE = "coffee_shop"
DOLL_M = 2.04
"""A resident's height on screen, 20% over scale, as the client draws them."""
STRIDE_M = 1.45
"""How far a walk cycle carries a resident, so their feet don't slide."""
CAMERA = 33.0
"""The first tile of the still street frame: the coffee shop, the square and the noodle bar."""
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


def use(look: str) -> None:
    """Points #309's previews at `look`'s scenery."""
    preview.CONTENT = REPO / "content" / "papercraft" if look == NOW else OUT / look / "papercraft"
    preview.manifest.cache_clear()
    preview.piece.cache_clear()


def views() -> dict:
    return preview.read_views()


def street_ground(view) -> float:
    """Where `preview.street_scene` puts the street's feet line."""
    tile = TILE * preview.SCENE_PPM
    row = Counter(view.ground(x) for x in range(view.width)).most_common(1)[0][0]
    lowest = max(view.ground(x) for x in range(view.width))
    return preview.H - 150 - (lowest - row) * tile


def street(look: str, x0: float, width: int, walkers=WALKERS, t: float = 0.0) -> Image.Image:
    """`look`'s High Street from tile `x0`, with its residents `t` seconds into their walk."""
    use(look)
    view = views()[STREET]
    frame = preview.street_scene(view, "afternoon", x0, width).convert("RGBA")
    tile = TILE * preview.SCENE_PPM
    feet = street_ground(view) + 8
    for who, x, facing, phase in walkers:
        walking = facing in ("east", "west")
        step = (1 if facing == "east" else -1) * 1.2 * t / TILE if walking else 0.0
        cycle = phase + abs(step) * TILE / STRIDE_M
        figure, (ox, oy) = doll(look, who).draw(
            "walking" if walking else "standing", facing, cycle, DOLL_M * preview.SCENE_PPM
        )
        over(frame, figure, round((x + step - x0) * tile - ox), round(feet - oy))
    return frame.convert("RGB")


def save(image: Image.Image, name: str, width: int | None = 1600, quality: int = 82) -> None:
    """The full picture to out/previews/, and one `width` wide to images/ (none if None)."""
    FULL.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(FULL / f"{name}.jpg", quality=90)
    if width is None:
        return
    IMAGES.mkdir(parents=True, exist_ok=True)
    small = image.convert("RGB")
    if small.width > width:
        small = small.resize((width, round(small.height * width / small.width)), Image.LANCZOS)
    small.save(IMAGES / f"{name}.jpg", quality=quality, optimize=True, progressive=True)
    print(f"images/{name}.jpg {(IMAGES / f'{name}.jpg').stat().st_size / 1e3:.0f} kB", flush=True)


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
    return [s for s in STYLES if (OUT / s / "papercraft" / "manifest.json").exists()]


def step_street() -> None:
    for look in styles():
        view = views()[STREET]
        save(
            street(look, 0, round(view.width * TILE * preview.SCENE_PPM)),
            f"{look}-street-full",
            None,
        )
        save(street(look, CAMERA, preview.W), f"{look}-street")


def step_parallax(frames: int = 36) -> None:
    for look in styles():
        view = views()[STREET]
        span = view.width - preview.W / (TILE * preview.SCENE_PPM)
        images = []
        for i in range(frames):
            x0 = span * (0.5 - 0.5 * math.cos(math.pi * i / (frames - 1)))
            images.append(street(look, x0, preview.W, PAN, t=i * 0.11))
        small = [f.resize((480, 270), Image.LANCZOS) for f in images]
        gif(small, f"{look}-street-parallax", 110, 96)
        FULL.mkdir(parents=True, exist_ok=True)
        images[0].save(
            FULL / f"{look}-street-parallax.webp",
            save_all=True,
            append_images=images[1:],
            duration=110,
            loop=0,
            quality=80,
        )


def dollhouse(look: str) -> Image.Image:
    """The coffee shop with its front off, as #309's preview draws it, and its residents in."""
    use(look)
    all_views = views()
    picture = preview.dollhouse(all_views, HOUSE).convert("RGBA")
    street_view = all_views[preview.manifest()["buildings"][HOUSE]["street"]]
    facade = next(b for b in street_view.buildings if b.name == HOUSE)
    floors = sorted(
        (v for v in all_views.values() if v.props.get("building") == HOUSE),
        key=lambda v: v.props["floor"],
    )
    rows = facade.h + 3
    ppm = min(preview.W * 0.8 / (facade.w * TILE), preview.H * 0.84 / (rows * TILE))
    tile = TILE * ppm
    left = (preview.W - facade.w * tile) / 2
    ground = preview.H - 60
    for who, floor, cell, facing in INSIDE:
        view = floors[floor]
        feet = ground - (facade.y + facade.h - (view.props["street_y"] + 3)) * tile + 3
        figure, (ox, oy) = doll(look, who).draw("standing", facing, 0, DOLL_M * ppm)
        over(picture, figure, round(left + (cell + 0.5) * tile - ox), round(feet - oy))
    return picture.convert("RGB")


def step_dollhouse() -> None:
    for look in styles():
        save(dollhouse(look), f"{look}-dollhouse")


def lineup(look: str, height: float = 245) -> Image.Image:
    """Every resident from the front, the side and the back, at twice street size."""
    gap = round(height * 0.42)
    out = Image.new("RGBA", (gap * (3 * len(WHO) + 1), round(height * 1.5)), (240, 234, 222, 255))
    x = gap
    for who in WHO:
        d = doll(look, who)
        for facing in ("south", "east", "north"):
            figure, (ox, oy) = d.draw("standing", facing, 0, height)
            over(out, figure, round(x - ox), round(height * 1.32 - oy))
            x += gap
    return out.convert("RGB")


def step_residents() -> None:
    for look in styles():
        save(lineup(look), f"{look}-residents")


def walk_frames(look: str, height: float = 180, frames: int = 12) -> list[Image.Image]:
    gap = round(height * 0.62)
    out = []
    for i in range(frames):
        frame = Image.new(
            "RGBA", (gap * (len(WHO) + 1), round(height * 1.32)), (240, 234, 222, 255)
        )
        for n, who in enumerate(WHO):
            figure, (ox, oy) = doll(look, who).draw("walking", "east", i / frames, height)
            over(frame, figure, round(gap * (n + 1) - ox), round(height * 1.2 - oy))
        out.append(frame.convert("RGB"))
    return out


def step_walk() -> None:
    rows = {look: walk_frames(look) for look in [NOW, *styles()]}
    for look, frames in rows.items():
        if look != NOW:
            gif(frames, f"{look}-walk", 90, 96)
            save(stack(frames[::3], across=True, gap=0), f"{look}-walk-frames", 1600)
    both = [stack([label(rows[look][i], TITLES[look], 22) for look in rows]) for i in range(12)]
    gif(
        [f.resize((f.width * 2 // 3, f.height * 2 // 3), Image.LANCZOS) for f in both],
        "walk-compare",
        90,
        128,
    )


def step_play() -> None:
    """A stretch of street at play size, 1:1: a 900 px tall window shows 22.5 m."""
    crops = []
    for look in LOOKS:
        frame = street(look, CAMERA, preview.W)
        crops.append(label(frame.crop((80, 380, 1080, 880)), TITLES[look], 22))
    save(stack(crops), "compare-play-size", 1000, quality=90)


def contact(look: str) -> Image.Image:
    use(look)
    keys = [
        k for k in preview.manifest()["pieces"] if k.split("/")[0] in ("furniture", "platforms")
    ]
    return preview.grid([(k.split("/", 1)[1], preview.piece(k)) for k in keys], (240, 240), 7)


def step_sheets() -> None:
    for look in styles():
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
    def shrink(image: Image.Image, width: int) -> Image.Image:
        return image.resize((width, round(image.height * width / image.width)), Image.LANCZOS)

    streets = [label(shrink(street(look, CAMERA, preview.W), 1200), TITLES[look]) for look in LOOKS]
    save(stack(streets), "compare-street", 1200)
    houses = [label(shrink(dollhouse(look), 1200), TITLES[look]) for look in LOOKS]
    save(stack(houses), "compare-dollhouse", 1200)
    people = [label(shrink(lineup(look, 200), 1200), TITLES[look]) for look in LOOKS]
    save(stack(people), "compare-residents", 1200)
    refs = []
    for look in STYLES:
        row = [
            Image.open(REFS / look / f"{n}.jpg").resize((448, 256), Image.LANCZOS)
            for n in ("street", "interior", "residents", "signage")
        ]
        refs.append(label(stack(row, across=True, gap=6), TITLES[look], 22))
    save(stack(refs), "references", 1800)


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
        print(look, row["mean"], row["max"], f"over the {len(shared)} pieces all three have")
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
        with styled_pipeline(STYLES.get(look, STYLES["papercraft"])):
            for who in WHO:
                path = OUT / look / ("sheets" if look == NOW else "dolls/sheets") / f"{who}-side"
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


def step_match() -> None:
    """How far each colour region of each painted piece sits from its flat colour, in the
    atlases as committed: the median of its painted pixels, CIEDE2000. Every region of every
    doll, so ears and noses count as much as faces."""
    from simile.dolls.colour import delta_e
    from simile.dolls.sheet import regions

    rows = {}
    for look in LOOKS:
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
    (OUT / "match.json").write_text(json.dumps(rows, indent=1))


def step_costs() -> None:
    entries = []
    for path in [OUT / "timings.jsonl", *sorted(OUT.glob("*/cache/timings.jsonl"))]:
        style = path.parts[-3] if path.parent.name == "cache" else None
        for line in path.read_text().splitlines():
            entry = json.loads(line)
            if style:
                entry |= {"event": "paint", "key": f"{style}/{entry['key']}"}
            entries.append(entry)
    paints = [e for e in entries if e.get("event") == "paint"]
    groups: dict[str, list[float]] = {}
    for e in paints:
        style = (
            e["key"].split("/")[1]
            if e["key"].startswith(("references", "dolls"))
            else e["key"].split("/")[0]
        )
        groups.setdefault(f"{style} {e['kind']}", []).append(e["seconds"])
    for key, seconds in sorted(groups.items()):
        print(
            f"{key}: {len(seconds)} at {np.mean(seconds):.1f} s "
            f"({min(seconds):.0f} to {max(seconds):.0f})"
        )
    loads = [e["seconds"] for e in entries if e.get("event") == "load"]
    total = sum(e["seconds"] for e in paints) + sum(loads)
    print(f"{len(paints)} paintings, {len(loads)} loads, {total / 60:.0f} min of FLUX in all")


STEPS = {
    "street": step_street,
    "parallax": step_parallax,
    "dollhouse": step_dollhouse,
    "residents": step_residents,
    "walk": step_walk,
    "play": step_play,
    "sheets": step_sheets,
    "compare": step_compare,
    "drift": step_drift,
    "consistency": step_consistency,
    "skin": step_skin,
    "match": step_match,
    "costs": step_costs,
}


if __name__ == "__main__":
    for step in sys.argv[1:] or STEPS:
        STEPS[step]()
