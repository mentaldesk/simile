"""Turns the Blender renders in out/ into the committed mock-ups in images/ and lighting/.

uv run --no-project --with pillow --with numpy python compose.py xcom fallout | lighting costs
"""

import json
import math
import sys

import numpy as np
import scene as S
from PIL import Image, ImageDraw, ImageFilter

POST = {
    "xcom": {"glow": (10, 0.85), "painterly": 0, "colours": None, "show": 1},
    "fallout": {"glow": (4, 0.7), "painterly": 2, "colours": 256, "show": 2},
}
PREFIX = {"xcom": "1-xcom", "fallout": "1b-fallout"}


def glow(im: Image.Image, radius: int, strength: float) -> Image.Image:
    a = np.asarray(im.convert("RGB")).astype(np.float32) / 255
    hi, lo = a.max(axis=2), a.min(axis=2)
    sat = (hi - lo) / np.maximum(hi, 1e-3)
    mask = np.clip((hi - 0.72) / 0.25, 0, 1) * np.clip((sat - 0.35) / 0.35, 0, 1)
    bright = Image.fromarray((a * mask[..., None] * 255).astype(np.uint8))
    halo = np.asarray(bright.filter(ImageFilter.GaussianBlur(radius))).astype(np.float32) / 255
    out = 1 - (1 - a) * (1 - np.clip(halo * strength * 1.6, 0, 1))
    result = Image.fromarray((out * 255).astype(np.uint8))
    if im.mode == "RGBA":
        result.putalpha(im.getchannel("A"))
    return result


def kuwahara(im: Image.Image, r: int) -> Image.Image:
    rgba = im.convert("RGBA")
    img = np.asarray(rgba).astype(np.float64)
    rgb = img[..., :3]
    lum = rgb @ np.array([0.299, 0.587, 0.114])
    h, w = lum.shape
    n = r + 1

    def integral(a):
        s = a.cumsum(0).cumsum(1)
        return np.pad(s, ((1, 0), (1, 0)) + ((0, 0),) * (a.ndim - 2))

    pr = np.pad(rgb, ((r, r), (r, r), (0, 0)), mode="edge")
    pl = np.pad(lum, r, mode="edge")
    ir, il, il2 = integral(pr), integral(pl), integral(pl * pl)
    ys = np.arange(h)[:, None] + r
    xs = np.arange(w)[None, :] + r

    def window(s, dy, dx):
        y, x = ys + dy, xs + dx
        return s[y + n, x + n] - s[y, x + n] - s[y + n, x] + s[y, x]

    best, out = None, None
    for dy, dx in ((-r, -r), (-r, 0), (0, -r), (0, 0)):
        mean_l = window(il, dy, dx) / (n * n)
        var = window(il2, dy, dx) / (n * n) - mean_l**2
        mean = window(ir, dy, dx) / (n * n)
        if best is None:
            best, out = var, mean
        else:
            pick = var < best
            best = np.where(pick, var, best)
            out = np.where(pick[..., None], mean, out)
    result = np.concatenate([out, img[..., 3:]], axis=2)
    return Image.fromarray(np.clip(result, 0, 255).astype(np.uint8), "RGBA")


def reduce(im: Image.Image, colours: int, palette: Image.Image | None = None) -> Image.Image:
    rgb = im.convert("RGB")
    q = (
        rgb.quantize(palette=palette, dither=Image.Dither.NONE)
        if palette
        else rgb.quantize(colours, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    )
    out = q.convert("RGB")
    if im.mode == "RGBA":
        out = out.convert("RGBA")
        alpha = im.getchannel("A")
        out.putalpha(alpha)
    return out


def painterly(im: Image.Image, level: str, sprite: bool = False) -> Image.Image:
    r = POST[level]["painterly"]
    r = min(r, 1) if sprite else r
    return kuwahara(im, r) if r else im


def _colours(images: list[Image.Image], n: int) -> list[int]:
    width = max(im.width for im in images)
    montage = Image.new("RGB", (width, sum(im.height for im in images)))
    y = 0
    for im in images:
        rgba = im.convert("RGBA")
        flat = Image.new("RGB", rgba.size, (0, 0, 0))
        flat.paste(rgba, mask=rgba.getchannel("A").point(lambda v: 255 if v > 200 else 0))
        montage.paste(flat, (0, y))
        y += im.height
    q = montage.quantize(n, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    return q.getpalette()[: n * 3]


def shared_palette(groups: list[tuple[list[Image.Image], int]]) -> Image.Image:
    """One 256-colour palette for a set of images, as Fallout 2 had one for the whole game."""
    entries = [c for name in S.a1_palette().PALETTE.values() for c in bytes.fromhex(name[1:])]
    for images, n in groups:
        entries += _colours(images, n)
    entries = entries[: 256 * 3]
    entries += entries[-3:] * (256 - len(entries) // 3)
    palette = Image.new("P", (1, 1))
    palette.putpalette(entries)
    return palette


def tile_px(meta, tx, ty):
    o, ex, ey = meta["origin"], meta["ex"], meta["ey"]
    return o[0] + tx * ex[0] + ty * ey[0], o[1] + tx * ex[1] + ty * ey[1]


def composite(level: str) -> Image.Image:
    out = S.OUT / level
    meta = json.loads((out / "scene.json").read_text())
    sprites = json.loads((out / "sprites.json").read_text())
    radius, strength = POST[level]["glow"]
    bg = painterly(glow(Image.open(out / "scene.png").convert("RGB"), radius, strength), level)
    people = {
        npc_id: painterly(Image.open(out / f"sprite_{npc_id}.png").convert("RGBA"), level, True)
        for npc_id, *_ in S.RESIDENTS
    }
    if POST[level]["colours"]:
        palette = shared_palette([([bg], 160), (list(people.values()), 64)])
        bg = reduce(bg, 0, palette)
        people = {k: reduce(v, 0, palette) for k, v in people.items()}
    bg = bg.convert("RGBA")
    for npc_id, tx, ty, _, _ in sorted(S.RESIDENTS, key=lambda r: r[1] + r[2]):
        sprite = people[npc_id]
        ax, ay = sprites[npc_id]["anchor"]
        x, y = tile_px(meta, tx, ty)
        bg.alpha_composite(sprite, (round(x - ax), round(y - ay)))
    return bg.convert("RGB")


def crop_box(unit: float, region: dict = S.CROP) -> tuple[int, int, int, int]:
    (vx0, _), (vy0, _) = S.VIEW["sx"], S.VIEW["sy"]
    (cx0, cx1), (cy0, cy1) = region["sx"], region["sy"]
    return (
        round((cx0 - vx0) * unit),
        round((cy0 - vy0) * unit),
        round((cx1 - vx0) * unit),
        round((cy1 - vy0) * unit),
    )


def save(im: Image.Image, name: str, quality: int = 86, folder=S.IMAGES) -> None:
    folder.mkdir(exist_ok=True)
    path = folder / name
    if name.endswith(".jpg"):
        im.convert("RGB").save(path, quality=quality, optimize=True, progressive=True)
    else:
        im.save(path, optimize=True)
    print(
        f"{path.relative_to(S.HERE)}  {im.size[0]}x{im.size[1]}  {path.stat().st_size // 1024} KB"
    )


def upscale(im: Image.Image, k: int) -> Image.Image:
    return im if k == 1 else im.resize((im.width * k, im.height * k), Image.Resampling.NEAREST)


def scene_images(level: str) -> None:
    full = composite(level)
    meta = json.loads((S.OUT / level / "scene.json").read_text())
    unit = (meta["ex"][0] - meta["ey"][0]) / 2
    show = POST[level]["show"]
    crop = full.crop(crop_box(unit))
    lossless = POST[level]["colours"] is not None
    ext = "png" if lossless else "jpg"
    scaled = (
        full
        if full.width <= 1200
        else full.resize((1200, round(full.height * 1200 / full.width)), Image.Resampling.LANCZOS)
    )
    save(reduce(scaled, 256) if lossless else scaled, f"{PREFIX[level]}-scene.{ext}")
    save(upscale(crop, show) if lossless else crop, f"{PREFIX[level]}-crop.{ext}", quality=90)
    (S.OUT / level / "composite.png").parent.mkdir(exist_ok=True)
    full.save(S.OUT / level / "composite.png")


def walk_images(level: str) -> None:
    out = S.OUT / level
    info = json.loads((out / "walk.json").read_text())
    frames = {
        (d, f): painterly(Image.open(out / "walk" / f"{d}_{f}.png").convert("RGBA"), level, True)
        for d in info["dirs"]
        for f in range(info["frames"])
    }
    if POST[level]["colours"]:
        palette = shared_palette([(list(frames.values()), 96)])
        frames = {k: reduce(v, 0, palette) for k, v in frames.items()}
    box = None
    for im in frames.values():
        b = im.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox()
        box = (
            b
            if box is None
            else (min(box[0], b[0]), min(box[1], b[1]), max(box[2], b[2]), max(box[3], b[3]))
        )
    pad = 2
    box = (box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad)
    fw, fh = box[2] - box[0], box[3] - box[1]
    label = 22
    ground = (196, 186, 170, 255)
    cols, rows = info["frames"], len(info["dirs"])
    sheet = Image.new("RGBA", (label + cols * fw, rows * fh), ground)
    draw = ImageDraw.Draw(sheet)
    for r, d in enumerate(info["dirs"]):
        draw.text((3, r * fh + fh // 2 - 6), d.upper(), fill=(40, 40, 50, 255))
        for c in range(cols):
            tile = Image.new("RGBA", (fw, fh), ground)
            tile.alpha_composite(frames[(d, c)].crop(box))
            sheet.paste(tile, (label + c * fw, r * fh))
    show = POST[level]["show"]
    save(reduce(upscale(sheet, show), 256), f"{PREFIX[level]}-walk.png")
    gif = []
    for c in range(cols):
        strip = Image.new("RGBA", (rows * fw, fh), ground)
        for r, d in enumerate(info["dirs"]):
            strip.alpha_composite(frames[(d, c)].crop(box), (r * fw, 0))
        gif.append(upscale(strip, show).convert("RGB").quantize(128))
    path = S.IMAGES / f"{PREFIX[level]}-walk.gif"
    gif[0].save(
        path, save_all=True, append_images=gif[1:], duration=1000 // cols, loop=0, optimize=True
    )
    print(f"{path.relative_to(S.HERE)}  {path.stat().st_size // 1024} KB")


def compare() -> None:
    """The same crop from each approach, side by side; the pixel art at an exact 2×."""
    crops = [
        ("1-xcom-crop.jpg", "1  pre-rendered 3D, XCOM 2 level"),
        ("1b-fallout-crop.png", "1b  pre-rendered 3D, Fallout 2 level"),
        ("2-pixel-crop.png", "2  isometric pixel art (A1 reprojected)"),
    ]
    if not all((S.IMAGES / name).exists() for name, _ in crops):
        return
    w, h, label = 704, 448, 20
    sheet = Image.new("RGB", (w * len(crops), h + label), (24, 20, 37))
    draw = ImageDraw.Draw(sheet)
    for i, (name, title) in enumerate(crops):
        im = Image.open(S.IMAGES / name).convert("RGB")
        if name.startswith("2-"):
            native = im.resize((im.width // 3, im.height // 3), Image.Resampling.NEAREST)
            im = upscale(native, 2)
        else:
            im = im.resize((w, h), Image.Resampling.LANCZOS)
        sheet.paste(im, (i * w, label))
        draw.text((i * w + 6, 4), title, fill=(234, 212, 170))
    save(sheet, "compare.png")


LIGHT_LEVEL = "xcom"
GLOW_BY_TIME = {"night": 1.0, "morning": 0.25, "afternoon": 0.25, "evening": 0.85}
FADE_HOUR = 17.0
GROUP = {"sx": (3.0, 27.0), "sy": (19.5, 28.5)}


def lit(time: str) -> dict:
    """A lighting set from out/: its background, its sprites, the neutral ones and its light map."""
    base = S.OUT / LIGHT_LEVEL
    radius, strength = POST[LIGHT_LEVEL]["glow"]
    scene = Image.open(base / time / "scene.png").convert("RGB")
    return {
        "time": time,
        "bg": glow(scene, radius, strength * GLOW_BY_TIME[time]),
        "meta": json.loads((base / time / "scene.json").read_text()),
        "baked": _sprites(base / time),
        "neutral": _sprites(base / "neutral"),
        "map": LightMap(base / time, S.TIMES[time]["elevation"]),
    }


def _sprites(folder) -> dict:
    info = json.loads((folder / "sprites.json").read_text())
    return {
        npc_id: (
            Image.open(folder / f"sprite_{npc_id}.png").convert("RGBA"),
            info[npc_id]["anchor"],
        )
        for npc_id, *_ in S.RESIDENTS
    }


def _linear(path) -> np.ndarray:
    c = np.asarray(Image.open(path).convert("RGB")).astype(np.float64) / 255
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _luma(rgb: np.ndarray) -> np.ndarray:
    return rgb @ np.array([0.2126, 0.7152, 0.0722])


class LightMap:
    """The light a resident standing on each spot gets, relative to standing in the open."""

    def __init__(self, folder, elevation: float) -> None:
        self.px = json.loads((folder / "lightmap.json").read_text())["px_per_tile"]
        sunsky, sun = _linear(folder / "light_sunsky.png"), _linear(folder / "light_sun.png")
        sky, lamps = sunsky - sun, _linear(folder / "light_lights.png")
        e = math.radians(elevation)
        # An upright figure gets cos(e)/π of a sun that gives the ground sin(e), and half the sky.
        upright = math.cos(e) / (math.pi * math.sin(e))
        self.figure = sun * upright + 0.5 * (sky + lamps)
        self.sun = sun
        open_ground = _luma(sunsky) >= np.percentile(_luma(sunsky), 99)
        self.open_sun = sun[open_ground].mean(axis=0)
        self.open = self.open_sun * upright + 0.5 * sky[open_ground].mean(axis=0)

    def at(self, tx: float, ty: float) -> tuple[np.ndarray, float]:
        """How much more light than in the open a resident gets here, and how much of the sun."""
        r = 0.35 * self.px
        cx, cy = tx * self.px, ty * self.px
        ys, xs = np.mgrid[0 : self.sun.shape[0], 0 : self.sun.shape[1]]
        disc = (xs + 0.5 - cx) ** 2 + (ys + 0.5 - cy) ** 2 <= r * r
        sun = _luma(self.sun[disc].mean(axis=0)) / max(_luma(self.open_sun), 1e-6)
        return self.figure[disc].mean(axis=0) / self.open, float(min(sun, 1.0))


def runtime_light(s: dict) -> dict:
    """What a runtime needs per set: a tint and a shadow strength, measured against neutral."""
    lit_sum, neutral_sum, shadow = np.zeros(3), np.zeros(3), []
    for npc_id in s["neutral"]:
        n_im, (nax, nay) = s["neutral"][npc_id]
        b_im, (bax, bay) = s["baked"][npc_id]
        n, b = np.asarray(n_im).astype(np.float64), np.asarray(b_im).astype(np.float64)
        ys, xs = np.nonzero(n[..., 3] > 250)
        by, bx = ys - nay + bay, xs - nax + bax
        solid = b[by, bx, 3] > 250
        lit_sum += b[by[solid], bx[solid], :3].sum(axis=0)
        neutral_sum += n[ys[solid], xs[solid], :3].sum(axis=0)
        body = np.zeros(b.shape[:2], bool)
        body[by, bx] = True
        body = np.asarray(Image.fromarray(body).filter(ImageFilter.MaxFilter(9)))
        alpha = b[..., 3][~body] / 255
        shadow += list(alpha[alpha > 0.03])
    sun = S.TIMES[s["time"]]
    return {
        "tint": [round(float(c), 3) for c in np.clip(lit_sum / neutral_sum, 0, 1)],
        "shadow": round(float(np.percentile(shadow, 95)), 3) if shadow else 0.0,
        "azimuth": sun["azimuth"],
        "elevation": sun["elevation"],
    }


def light_here(light: dict, light_map: LightMap | None, tx: float, ty: float):
    """A resident's tint and shadow strength: the set's, or the set's moved by the local light."""
    tint, shadow = np.array(light["tint"]), light["shadow"]
    if light_map is None:
        return tint, shadow
    ratio, sun = light_map.at(tx, ty)
    tint = tint * ratio ** (1 / 2.2)
    return tint / max(tint.max(), 1.0), shadow * sun


def drop_shadow(meta, tx, ty, azimuth, elevation, opacity) -> tuple[Image.Image, tuple]:
    """The runtime shadow, an ellipse on the ground from the feet away from the sun, and where."""
    east, north, _ = S.to_sun(azimuth, elevation)
    flat = math.hypot(east, north)
    dx, dy = -east / flat, north / flat
    length = S.FIGURE_M / math.tan(math.radians(elevation)) / S.TILE_M
    half_w = 0.2 / S.TILE_M
    shapes = []
    for centre, along, across, strength in (
        (length / 2, length / 2 + half_w, half_w, opacity),
        (0.0, 0.3, 0.26, 0.35),
    ):
        pts = []
        for i in range(48):
            a = math.tau * i / 48
            u, v = centre + along * math.cos(a), across * math.sin(a)
            pts.append(tile_px(meta, tx + u * dx - v * dy, ty + u * dy + v * dx))
        shapes.append((pts, strength))
    blur = min(1.0 + length * 0.4, 5.0)
    pad = math.ceil(blur * 3) + 2
    xs = [x for pts, _ in shapes for x, _ in pts]
    ys = [y for pts, _ in shapes for _, y in pts]
    x0, y0 = math.floor(min(xs)) - pad, math.floor(min(ys)) - pad
    size = (math.ceil(max(xs)) + pad - x0, math.ceil(max(ys)) + pad - y0)
    k = 4
    mask = np.zeros((size[1] * k, size[0] * k), np.uint8)
    for pts, strength in shapes:
        layer = Image.new("L", (size[0] * k, size[1] * k), 0)
        local = [((x - x0) * k, (y - y0) * k) for x, y in pts]
        ImageDraw.Draw(layer).polygon(local, fill=round(255 * strength))
        mask = np.maximum(mask, np.asarray(layer))
    small = Image.fromarray(mask).resize(size, Image.Resampling.BOX)
    return small.filter(ImageFilter.GaussianBlur(blur)), (x0, y0)


def darken(bg: Image.Image, mask: Image.Image, at: tuple[int, int]) -> Image.Image:
    full = Image.new("L", bg.size, 0)
    full.paste(mask, at)
    a = np.asarray(bg.convert("RGB")).astype(np.float32)
    m = np.asarray(full).astype(np.float32)[..., None] / 255
    return Image.fromarray((a * (1 - m)).astype(np.uint8))


def place(bg: Image.Image, meta, sprites: dict, tints: dict | None = None) -> Image.Image:
    out = bg.convert("RGBA")
    for npc_id, tx, ty, _, _ in sorted(S.RESIDENTS, key=lambda r: r[1] + r[2]):
        sprite, (ax, ay) = sprites[npc_id]
        if tints:
            rgba = np.asarray(sprite).astype(np.float32)
            rgba[..., :3] *= np.asarray(tints[npc_id], np.float32)
            sprite = Image.fromarray(rgba.astype(np.uint8), "RGBA")
        x, y = tile_px(meta, tx, ty)
        out.alpha_composite(sprite, (round(x - ax), round(y - ay)))
    return out.convert("RGB")


def baked(s: dict) -> Image.Image:
    """(a) Each resident rendered under this set's light, shadow included."""
    return place(s["bg"], s["meta"], s["baked"])


def tinted(bg, meta, neutral, lights: list[tuple[dict, LightMap | None, float]]) -> Image.Image:
    """(b) One neutral sprite, a runtime tint, and a drop shadow per set weighted as the fade."""
    tints = {}
    for npc_id, tx, ty, _, _ in S.RESIDENTS:
        tints[npc_id] = np.zeros(3)
        for light, light_map, weight in lights:
            tint, shadow = light_here(light, light_map, tx, ty)
            tints[npc_id] += tint * weight
            mask, at = drop_shadow(
                meta, tx, ty, light["azimuth"], light["elevation"], shadow * weight
            )
            bg = darken(bg, mask, at)
    return place(bg, meta, neutral, tints)


def lighting() -> None:
    folder = S.HERE / "lighting"
    sets = {t: lit(t) for t in S.TIMES}
    lights = {t: runtime_light(s) for t, s in sets.items()}
    meta = sets["night"]["meta"]
    unit = (meta["ex"][0] - meta["ey"][0]) / 2
    crop, group = crop_box(unit), crop_box(unit, GROUP)
    shots = {}
    for i, (t, s) in enumerate(sets.items(), 1):
        flat = tinted(s["bg"], meta, s["neutral"], [(lights[t], None, 1.0)])
        full = tinted(s["bg"], meta, s["neutral"], [(lights[t], s["map"], 1.0)])
        save(half_width(full), f"{i}-{t}.jpg", folder=folder)
        save(full.crop(crop), f"{i}-{t}-crop.jpg", quality=90, folder=folder)
        shots[t] = [baked(s).crop(group), flat.crop(group), full.crop(group)]
    (a, _), (b, w) = S.blend(FADE_HOUR)
    mid = Image.blend(sets[a]["bg"], sets[b]["bg"], w)
    pair = [(lights[t], sets[t]["map"], weight) for t, weight in S.blend(FADE_HOUR)]
    fade = tinted(mid, meta, sets[a]["neutral"], pair)
    save(half_width(fade), f"5-crossfade-{a}-{b}.jpg", folder=folder)
    save(fade.crop(crop), f"5-crossfade-{a}-{b}-crop.jpg", quality=90, folder=folder)
    characters(shots, folder)
    (S.OUT / LIGHT_LEVEL / "runtime_light.json").write_text(json.dumps(lights, indent=2))
    print(json.dumps(lights))


def half_width(im: Image.Image) -> Image.Image:
    return im.resize((1200, round(im.height * 1200 / im.width)), Image.Resampling.LANCZOS)


def characters(shots: dict, folder) -> None:
    """The residents under each set: (a), then (b) without and with the light map."""
    titles = (
        "(a) sprites rendered per set",
        "(b) neutral sprite, set tint, drop shadow",
        "(b) + light map: tint and shadow from where they stand",
    )
    w, h = shots["night"][0].size
    label = 22
    sheet = Image.new("RGB", (len(titles) * w, len(shots) * (h + label)), (24, 20, 37))
    draw = ImageDraw.Draw(sheet)
    for r, (t, row) in enumerate(shots.items()):
        y = r * (h + label)
        for c, (im, title) in enumerate(zip(row, titles, strict=True)):
            sheet.paste(im, (c * w, y + label))
            draw.text((c * w + 6, y + 5), f"{t.upper()}  {title}", fill=(234, 212, 170))
    save(sheet, "6-characters.jpg", quality=88, folder=folder)


def atlas_mb(folder) -> float:
    """A walk cycle's frames on one sheet at their shared trimmed size, 256 colours with alpha."""
    frames = [Image.open(p).convert("RGBA") for p in sorted((folder / "walk").glob("*.png"))]
    boxes = [im.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox() for im in frames]
    box = (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )
    fw, fh = box[2] - box[0], box[3] - box[1]
    cols = 8
    sheet = Image.new("RGBA", (cols * fw, -(-len(frames) // cols) * fh), (0, 0, 0, 0))
    for i, im in enumerate(frames):
        sheet.paste(im.crop(box), ((i % cols) * fw, (i // cols) * fh))
    path = S.OUT / LIGHT_LEVEL / f"atlas_{folder.name}.png"
    sheet.quantize(256, method=Image.Quantize.FASTOCTREE).save(path, optimize=True)
    return path.stat().st_size / 1e6


def objects_mb(folder) -> float:
    total = 0
    for p in (folder / "objects").glob("*.png"):
        im = Image.open(p).convert("RGBA")
        im = im.crop(im.getchannel("A").getbbox())
        im.quantize(256, method=Image.Quantize.FASTOCTREE).save(S.OUT / "object.png", optimize=True)
        total += (S.OUT / "object.png").stat().st_size
    return total / 1e6


def costs() -> None:
    """Measured render times per set, and the full asset set they extrapolate to."""
    base = S.OUT / LIGHT_LEVEL
    residents, frames = 11, 72
    print(
        "| Set | Mock-up scene | 32 object sprites | Light map | Scenery set | Scenery on disk "
        "| One walk frame | 11 residents | Atlas per resident |"
    )
    print("|---|--:|--:|--:|--:|--:|--:|--:|--:|")
    total = {"a": 0.0, "b": 0.0}
    disk = {"a": 0.0, "b": 0.0}
    for t in (*S.TIMES, "neutral"):
        tm = json.loads((base / t / "timings.json").read_text())
        frame = tm["walk_render_s"] / tm["walk_frames"]
        atlas = atlas_mb(base / t) * frames / tm["walk_frames"]
        people, people_mb = residents * frames * frame, residents * atlas
        size = f"{frame:.2f} s at {tm['walk_frame_size'][0]}×{tm['walk_frame_size'][1]} px"
        if t == "neutral":
            total["b"] += people
            disk["b"] += people_mb
            print(f"| neutral, once | | | | | | {size} | {people / 60:.1f} min | {atlas:.2f} MB |")
            continue
        jpg = base / t / "scene.jpg"
        Image.open(base / t / "scene.png").convert("RGB").save(jpg, quality=86)
        scenery = tm["scene_render_s"] * 4.9 + tm["object_render_s"] + tm["lightmap_render_s"]
        scenery_mb = jpg.stat().st_size / 1e6 * 4.9 + objects_mb(base / t)
        total["a"] += scenery + people
        total["b"] += scenery
        disk["a"] += scenery_mb + people_mb
        disk["b"] += scenery_mb
        print(
            f"| {t} | {tm['scene_render_s']} s | {tm['object_render_s']} s | "
            f"{tm['lightmap_render_s']} s | {scenery / 60:.1f} min | {scenery_mb:.1f} MB | "
            f"{size} | {people / 60:.1f} min | {atlas:.2f} MB |"
        )
    for k in total:
        print(f"({k}) all four sets: {total[k] / 60:.0f} min, {disk[k]:.1f} MB")


def main(args: list[str]) -> None:
    levels = [a for a in args if a in POST]
    for level in levels:
        scene_images(level)
        walk_images(level)
    if levels:
        compare()
    if "lighting" in args:
        lighting()
    if "costs" in args:
        costs()


if __name__ == "__main__":
    main(sys.argv[1:] or ["xcom", "fallout"])
