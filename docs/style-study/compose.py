"""Turns the Blender renders in out/ into the committed mock-ups in images/.

uv run --no-project --with pillow --with numpy python compose.py xcom fallout
"""

import json
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


def crop_box(unit: float) -> tuple[int, int, int, int]:
    (vx0, _), (vy0, _) = S.VIEW["sx"], S.VIEW["sy"]
    (cx0, cx1), (cy0, cy1) = S.CROP["sx"], S.CROP["sy"]
    return (
        round((cx0 - vx0) * unit),
        round((cy0 - vy0) * unit),
        round((cx1 - vx0) * unit),
        round((cy1 - vy0) * unit),
    )


def save(im: Image.Image, name: str, quality: int = 86) -> None:
    S.IMAGES.mkdir(exist_ok=True)
    path = S.IMAGES / name
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
    """The same 1:1 crop from each approach, side by side at half size."""
    crops = [
        ("1-xcom-crop.jpg", "1  pre-rendered 3D, XCOM 2 level"),
        ("1b-fallout-crop.png", "1b  pre-rendered 3D, Fallout 2 level"),
        ("2-pixel-crop.png", "2  isometric pixel art (A1 reprojected)"),
    ]
    if not all((S.IMAGES / name).exists() for name, _ in crops):
        return
    w, h, label = 528, 336, 20
    sheet = Image.new("RGB", (w * len(crops), h + label), (24, 20, 37))
    draw = ImageDraw.Draw(sheet)
    for i, (name, title) in enumerate(crops):
        im = Image.open(S.IMAGES / name).convert("RGB").resize((w, h), Image.Resampling.LANCZOS)
        sheet.paste(im, (i * w, label))
        draw.text((i * w + 6, 4), title, fill=(234, 212, 170))
    save(sheet, "compare.jpg", quality=88)


def main(levels: list[str]) -> None:
    for level in levels:
        scene_images(level)
        walk_images(level)
    compare()


if __name__ == "__main__":
    main(sys.argv[1:] or ["xcom", "fallout"])
