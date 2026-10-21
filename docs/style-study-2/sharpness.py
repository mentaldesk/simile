"""Why #295's pictures look sharper than #326's: a few pieces painted at 8 bits and at bf16, at
1.5 times the size, and from text alone, then cut, stored and shown each way.

`python sharpness.py paint` paints them into out/sharpness/, and `python sharpness.py compose`
makes the pictures and numbers.
"""

import dataclasses
import json
import shutil
import sys
import tempfile
import time
from contextlib import contextmanager
from functools import partial
from pathlib import Path

import numpy as np
from common import CARTOON, OUT, PAPERCRAFT, TextPainter, log, wait_for_gpu
from PIL import Image

from simile.papercraft.painter import EditPainter

HERE = OUT / "sharpness"
VARIANTS = ("8-bit", "bf16", "large", "text")
KEYS = {
    CARTOON: (
        "fronts/corner_shop",
        "fronts/coffee_shop",
        "furniture/espresso_machine",
        "furniture/sofa",
        "layers/mid-shophouses",
    ),
    PAPERCRAFT: ("furniture/sofa", "furniture/espresso_machine"),
}
"""The pieces painted each way, in #326's styles."""
LARGE = 1.5
WHO = "odalys"


def bits(variant: str) -> int | None:
    return None if variant == "bf16" else 8


class Measured(EditPainter):
    """#309's painter that waits for the GPU, and logs each load and each painting's peak
    memory."""

    def __enter__(self):
        import mlx.core as mx

        wait_for_gpu()
        start = time.perf_counter()
        out = super().__enter__()
        mx.eval(self._flux.parameters())
        seconds = round(time.perf_counter() - start, 1)
        log(
            {
                "event": "load",
                "mode": "edit",
                "bits": self.bits,
                "seconds": seconds,
                "memory": mx.get_active_memory(),
            }
        )
        return out

    def paint(self, prompt, size, seed, images):
        import mlx.core as mx

        mx.reset_peak_memory()
        start = time.perf_counter()
        picture = super().paint(prompt, size, seed, images)
        log(
            {
                "event": "sharpness",
                "bits": self.bits,
                "size": list(size),
                "seconds": round(time.perf_counter() - start, 1),
                "peak": mx.get_peak_memory(),
            }
        )
        return picture


class FromText(TextPainter):
    """The text-mode painter behind #309's painter interface: the style images are dropped."""

    def __enter__(self):
        import mlx.core as mx

        out = super().__enter__()
        mx.eval(self._flux.parameters())
        return out

    def paint(self, prompt, size, seed, images=()):
        import mlx.core as mx

        from simile.works.flux import size as paint_size

        mx.reset_peak_memory()
        start = time.perf_counter()
        picture = super().paint(prompt, paint_size(*size), seed)
        log(
            {
                "event": "sharpness",
                "bits": self.bits,
                "text": True,
                "size": list(size),
                "seconds": round(time.perf_counter() - start, 1),
                "peak": mx.get_peak_memory(),
            }
        )
        return picture.resize(size, Image.LANCZOS) if picture.size != size else picture


def variant_pieces(style, variant: str):
    from scenery import leads, pieces

    chosen = [p for p in pieces(style) if p.key in KEYS[style]]
    if variant == "large":
        grown = []
        for p in chosen:
            if p.kind == "front":
                grown.append(p)
                continue
            size = tuple(round(v * LARGE / 16) * 16 for v in p.size)
            grown.append(dataclasses.replace(p, size=size))
        return grown
    if variant == "text":
        lead = leads(style)["lead"]
        return [
            dataclasses.replace(p, prompt=p.prompt.replace(lead, ""), refs=())
            for p in chosen
            if p.kind == "sprite"
        ]
    return chosen


def builder(style, variant: str):
    from scenery import builder as study_builder

    build = study_builder(style)
    folder = HERE / variant / style.name
    build.pieces = {p.key: p for p in variant_pieces(style, variant)}
    build.content = folder / "papercraft"
    build.cache = folder / "cache"
    build.front_pixels = LARGE if variant == "large" else 1.0
    if variant == "text":
        build.painter = FromText
    else:
        build.painter = partial(Measured, bits=bits(variant))
    return build


class DollPainter:
    """#310's sheet painter at `bits`."""

    def __init__(self, bits: int | None) -> None:
        self._painter = Measured(bits=bits)

    def __enter__(self):
        self._painter.__enter__()
        return self

    def __exit__(self, *exc) -> None:
        self._painter.__exit__(*exc)

    def paint(self, prompt, images, size, seed):
        pictures = [Image.open(path).convert("RGB") for path in images]
        return self._painter.paint(prompt, size, seed, pictures)


def paint_dolls(variant: str) -> None:
    from dolls import matched, styled_pipeline

    from simile.dolls import build as dolls

    folder = HERE / variant / CARTOON.name / "dolls"
    model = dolls.Lazy(partial(DollPainter, bits(variant)))
    with styled_pipeline(CARTOON.name), model.stack, tempfile.TemporaryDirectory() as scratch:
        everyone = dolls.people()
        painted = dolls.paint(WHO, everyone[WHO], model, Path(scratch), folder / "paintings")
        matched(painted.doll)
        appearance = everyone[WHO].model_dump(mode="json")
        dolls.write(folder, dolls.files(WHO, painted.doll, appearance=appearance))


def paint() -> None:
    for variant in VARIANTS:
        for style in KEYS:
            build = builder(style, variant)
            if not build.pieces:
                continue
            report = build.run()
            print(variant, style.name, report.painted, flush=True)
    for variant in ("8-bit", "bf16"):
        paint_dolls(variant)


LUMA = np.array([0.299, 0.587, 0.114])
PLAY = 40
"""Pixels a metre at play size, as #326's previews draw the street."""
SCALES = (PLAY, 2 * PLAY)
"""Play size, and play size on a retina screen, where the client draws twice the pixels."""
CELL = (300, 220)
BACK = (226, 220, 208)
TESTS = [
    (CARTOON, "fronts/coffee_shop", ("8-bit", "bf16", "large"), (0.42, 0.3)),
    (CARTOON, "furniture/espresso_machine", VARIANTS, (0.5, 0.45)),
    (PAPERCRAFT, "furniture/sofa", VARIANTS, (0.5, 0.5)),
    (CARTOON, "layers/mid-shophouses", ("8-bit", "bf16", "large"), (0.3, 0.6)),
]
"""Each test piece, how it's painted, and where to look at it."""
NAMES = {
    "8-bit": "8-bit",
    "bf16": "bf16",
    "large": "8-bit at 1.5x the pixels",
    "text": "8-bit from text",
}


def crispness(image: Image.Image) -> float:
    """Mean gradient magnitude of the luminance inside the opaque pixels: higher is crisper, for
    pictures of the same thing at the same scale."""
    a = np.asarray(image.convert("RGBA"), dtype=np.float64)
    gy, gx = np.gradient(a[..., :3] @ LUMA)
    solid = a[..., 3] > 250
    for axis in (0, 1):
        solid = solid & np.roll(solid, 1, axis) & np.roll(solid, -1, axis)
    return round(float(np.hypot(gx, gy)[solid].mean()), 2) if solid.any() else 0.0


def error(image: Image.Image, truth: Image.Image) -> float:
    """Mean CIEDE2000 from `truth`, over the opaque pixels."""
    from simile.dolls.colour import delta_e

    a = np.asarray(on(image), dtype=np.float64).reshape(-1, 3)
    b = np.asarray(on(truth), dtype=np.float64).reshape(-1, 3)
    return round(float(delta_e(a, b).mean()), 2)


def at(image: Image.Image, height_m: float, ppm: float) -> Image.Image:
    h = max(1, round(height_m * ppm))
    return image.resize((max(1, round(image.width * h / image.height)), h), Image.LANCZOS)


def on(image: Image.Image, back=BACK) -> Image.Image:
    out = Image.new("RGBA", image.size, (*back, 255))
    out.alpha_composite(image.convert("RGBA"))
    return out.convert("RGB")


def crop(image: Image.Image, box=CELL, spot=(0.5, 0.5)) -> Image.Image:
    """`box` of `image` around `spot`, padded with the backdrop if it's smaller."""
    w, h = min(box[0], image.width), min(box[1], image.height)
    x, y = round((image.width - w) * spot[0]), round((image.height - h) * spot[1])
    cell = Image.new("RGB", box, BACK)
    part = on(image.convert("RGBA").crop((x, y, x + w, y + h)))
    cell.paste(part, ((box[0] - w) // 2, (box[1] - h) // 2))
    return cell


def raw_of(style, variant: str, key: str) -> Image.Image:
    build = builder(style, variant)
    return build.raw(build.pieces[key], 0 if key.startswith("fronts/") else None)


def recut(style, variant: str, key: str, lossless: bool) -> tuple[Image.Image, float]:
    """The piece cut from its painting again, and its height: saved as #309 saves it, or
    lossless."""
    from simile.papercraft import build as pipeline

    build = builder(style, variant)
    original = pipeline.save_webp
    with tempfile.TemporaryDirectory() as scratch:
        build.content = Path(scratch)
        if lossless:
            pipeline.save_webp = lambda image, path, q: image.save(path, "WEBP", lossless=True)
        try:
            entry = build.finish(build.pieces[key])
            image = Image.open(Path(scratch) / entry["file"]).convert("RGBA")
        finally:
            pipeline.save_webp = original
    if key.startswith("layers/"):
        image = image.crop((0, 0, min(image.width, 3 * image.height), image.height))
    return image, entry["height"]


def hard(image: Image.Image) -> Image.Image:
    a = np.asarray(image.convert("RGBA"), dtype=np.uint8).copy()
    a[..., 3] = np.where(a[..., 3] > 127, 255, 0)
    return Image.fromarray(a, "RGBA")


def step_paintings(numbers: dict) -> None:
    """Each test piece painted each way: a 1:1 crop of the painting, then the piece as stored,
    at play size and at retina play size."""
    from compose import label, save, stack

    rows = []
    for style, key, variants, spot in TESTS:
        row = []
        for variant in variants:
            raw = raw_of(style, variant, key)
            piece, height = recut(style, variant, key, lossless=False)
            shown = [at(piece, height, ppm) for ppm in SCALES]
            numbers.setdefault(f"{style.name} {key}", {})[variant] = {
                "painting px": list(raw.size),
                "painted px/m": round(raw.height / height, 0)
                if key.startswith("fronts/")
                else None,
                **{f"{ppm} px/m": crispness(s) for ppm, s in zip(SCALES, shown, strict=True)},
            }
            cells = [crop(raw, spot=spot)] + [crop(s, spot=spot) for s in shown]
            row.append(label(stack(cells, gap=4), NAMES[variant], 16))
        title = f"{style.name} {key}: the painting 1:1, then 40 and 80 px/m"
        rows.append(label(stack(row, across=True, gap=10), title, 20))
    save(stack(rows, gap=20), "sharpness-paintings", 1600, quality=88)


def zoom(image: Image.Image, factor: int) -> Image.Image:
    return image.resize((image.width * factor, image.height * factor), Image.NEAREST)


def jpeg(image: Image.Image, **settings) -> tuple[Image.Image, int]:
    import io

    data = io.BytesIO()
    image.convert("RGB").save(data, "JPEG", **settings)
    return Image.open(io.BytesIO(data.getvalue())).convert("RGB"), len(data.getvalue())


@contextmanager
def swapped_front(variant: str):
    """#326's cartoon scenery with its coffee shop front from `variant`'s painting."""
    from simile.papercraft import preview

    with tempfile.TemporaryDirectory() as scratch:
        folder = Path(scratch)
        source = OUT / "cartoon" / "papercraft"
        shutil.copytree(source, folder, dirs_exist_ok=True)
        theirs = HERE / variant / "cartoon" / "papercraft"
        key = "fronts/coffee_shop"
        manifest = json.loads((folder / "manifest.json").read_text())
        entry = json.loads((theirs / "manifest.json").read_text())["pieces"][key]
        shutil.copy(theirs / entry["file"], folder / entry["file"])
        manifest["pieces"][key] = entry
        (folder / "manifest.json").write_text(json.dumps(manifest))
        saved = preview.CONTENT
        preview.CONTENT = folder
        preview.manifest.cache_clear()
        preview.piece.cache_clear()
        try:
            yield
        finally:
            preview.CONTENT = saved
            preview.manifest.cache_clear()
            preview.piece.cache_clear()


def step_display(numbers: dict) -> None:
    """What happens after the painting: how big the client draws the street, fronts painted at
    more pixels, storing pieces lossy or lossless, soft or hard cut-out edges, the README's
    JPEG, and the dolls at 8 bits and bf16."""
    import scaled
    from compose import CAMERA, label, save, stack, street, views
    from dolls import Doll, Drawn

    rows = []
    wide = street("cartoon", CAMERA, 1600).crop((140, 420, 520, 630))
    close = street("cartoon", CAMERA, 1600, scale=2).crop((280, 840, 1040, 1260))
    cells = [
        label(
            wide.resize(close.size, Image.LANCZOS), "40 px/m, as #326 showed it, enlarged 2x", 18
        ),
        label(close, "80 px/m, as the client draws it on a retina screen", 18),
    ]
    rows.append(label(stack(cells, across=True, gap=10), "The camera: the same pieces", 22))

    view = views()["high_street"]
    cells = []
    for variant in ("8-bit", "large"):
        with swapped_front(variant):
            frame = scaled.street_scene(view, "afternoon", 30.0, 1600, 2)
        cells.append(
            label(frame.crop((0, 760, 760, 1180)), f"Coffee shop front, {NAMES[variant]}", 18)
        )
    rows.append(label(stack(cells, across=True, gap=10), "Fronts at 80 px/m", 22))

    style, key = CARTOON, "furniture/espresso_machine"
    lossy, height = recut(style, "8-bit", key, lossless=False)
    lossless, _ = recut(style, "8-bit", key, lossless=True)
    truth = at(lossless, height, 2 * PLAY)
    cells = []
    for name, piece in (
        ("WebP q85, as #309 stores it", lossy),
        ("lossless", lossless),
        ("lossless, hard edge", hard(lossless)),
    ):
        shown = at(piece, height, 2 * PLAY)
        numbers.setdefault("storage", {})[name] = {"ΔE from lossless": error(shown, truth)}
        cells.append(label(zoom(crop(shown, (160, 130), (0.5, 0.2)), 3), name, 18))
    rows.append(label(stack(cells, across=True, gap=10), "Stored and cut, 80 px/m, zoomed 3x", 22))

    frame = street(style.name, CAMERA, 1600, scale=2).crop((0, 700, 1600, 1600))
    part = frame.crop((560, 520, 720, 650))
    cells = []
    for name, settings in (
        ("JPEG q82, 4:2:0, as #326's README", {"quality": 82, "subsampling": 2}),
        ("JPEG q86, 4:4:4", {"quality": 86, "subsampling": 0}),
        ("lossless", None),
    ):
        image, _ = jpeg(part, **settings) if settings else (part, 0)
        size = jpeg(frame, **settings)[1] if settings else 0
        numbers.setdefault("jpeg", {})[name] = {
            "ΔE from lossless": error(image, part),
            "bytes": size,
        }
        cells.append(label(zoom(image, 3), name, 18))
    rows.append(label(stack(cells, across=True, gap=10), "The README's JPEG, zoomed 3x", 22))

    cells = []
    for variant in ("8-bit", "bf16"):
        folder = HERE / variant / CARTOON.name / "dolls"
        figure = Doll.load(folder, WHO, Drawn("cartoon", outline=0.9, head=1.22))
        strip = Image.new("RGBA", (420, 230), (*BACK, 255))
        for i, facing in enumerate(("south", "east", "north")):
            image, (ox, oy) = figure.draw("standing", facing, 0, 164)
            strip.alpha_composite(image, (round(70 + i * 140 - ox), round(205 - oy)))
        cells.append(label(strip.convert("RGB"), f"Odalys's sheets painted at {variant}", 18))
    rows.append(label(stack(cells, across=True, gap=10), "Dolls at 164 px, twice street size", 22))
    save(stack(rows, gap=20), "sharpness-display", 1600, quality=90)


def compose() -> None:
    numbers: dict = {}
    step_paintings(numbers)
    step_display(numbers)
    peaks = {}
    for line in (OUT / "timings.jsonl").read_text().splitlines():
        entry = json.loads(line)
        if entry.get("event") == "sharpness":
            name = "text" if entry.get("text") else "bf16" if entry["bits"] is None else "8-bit"
            peaks.setdefault(name, []).append((entry["size"], entry["seconds"], entry["peak"]))
    numbers["runs"] = peaks
    (OUT / "sharpness.json").write_text(json.dumps(numbers, indent=1))
    print(json.dumps({k: v for k, v in numbers.items() if k != "runs"}, indent=1))


STEPS = {"paint": paint, "compose": compose}

if __name__ == "__main__":
    for step in sys.argv[1:] or ["paint", "compose"]:
        STEPS[step]()
