"""Paths, the four residents, the grimy cartoon's words, FLUX in both modes, and the colour check
every approach is measured by."""

import gc
import json
import sys
import tempfile
import time
from functools import cache
from pathlib import Path
from types import TracebackType
from typing import Self

import numpy as np
from PIL import Image

STUDY = Path(__file__).resolve().parent
OUT = STUDY / "out"
IMAGES = STUDY / "images"
FULL = OUT / "previews"
REPO = STUDY.parents[1]
STYLE_STUDY = STUDY.parent / "style-study-2"
sys.path.insert(0, str(STYLE_STUDY))

from common import NO_TEXT, REFS, busy  # noqa: E402

WHO = ("lachlan", "odalys", "ingrid", "henrietta")
"""Broad, average and slim; pale, golden, light brown and deep brown skin; a cap over silver
buzzed hair, curls, a ponytail and a grey bun; a cap, an apron, a backpack and a scarf."""
HEAD = 1.6
"""#329's recommended head size, about the neck, against #310's."""
RESIDENTS_REF = REFS / "grimy" / "residents.jpg"
BUILD_WORDS = {"slim": "slim", "average": "medium build", "broad": "broad and stocky"}
LOOK = (
    "hand-drawn 2D cartoon game art: thick dark brown ink outlines that are scratchy, uneven and "
    "slightly broken, as if drawn with a worn dip pen, flat colour fills with simple soft "
    "shading, a few light smudges and scuffs on the clothes, a slightly dirty, muted palette, "
    "chunky rounded simplified shapes, bold readable silhouettes"
)
"""#329's grimy look, with its grime kept to the clothes: the reviewer found it heavy on faces."""
FACE = "The face is clean, with simple dot eyes and a small smile, and no smudges on it."


def styled(subject: str) -> str:
    return f"{subject} Art style: {LOOK}.{NO_TEXT}"


@cache
def people() -> dict:
    from simile.dolls.build import people as everyone

    return everyone()


def look_of(who: str):
    from simile.dolls.look import Look

    return Look.of(people()[who], who)


def described(who: str) -> str:
    """The resident in words: #310's skin, hair and accessories, and their clothes and build."""
    from simile.dolls.paint import CLOTH, an, named, person

    appearance = people()[who]
    top = named(appearance.top_colour, CLOTH)
    bottom = named(appearance.bottom_colour, CLOTH)
    shoes = (
        "white"
        if appearance.shoe_colour.lower() == "#ffffff"
        else named(appearance.shoe_colour, CLOTH)
    )
    build = BUILD_WORDS[appearance.build.value]
    return (
        f"{person(appearance, who)} They are {build}, in {an(top)} t-shirt, {bottom} trousers and "
        f"{shoes} sneakers."
    )


REGIONS = ("skin", "hair", "top", "bottom", "shoe", "accent", "apron")
"""The `Look`'s colours, which every approach is measured against."""


def targets(who: str) -> dict[str, np.ndarray]:
    """The colours each region should be: #310's `Look`, skin exact and the rest muted, as its
    flat pieces are drawn."""
    look = look_of(who)
    wanted = {"skin", "hair", "top", "bottom", "shoe"}
    if look.accessories & {"cap", "beanie", "headphones", "scarf", "backpack"}:
        wanted.add("accent")
    if "apron" in look.accessories:
        wanted.add("apron")
    return {r: np.array(getattr(look, r), dtype=np.float64) for r in REGIONS if r in wanted}


def measure(painted: Image.Image, labels: np.ndarray, who: str, least: int = 12) -> dict:
    """Each region's median painted colour against its `Look` colour, CIEDE2000, as
    `dolls.matched` checks a region: `labels` names each pixel's region by its index in
    `REGIONS`, or -1."""
    from simile.dolls.colour import delta_e, hex_of

    p = np.asarray(painted.convert("RGBA"), dtype=np.float64)
    out = {}
    for name, colour in targets(who).items():
        region = (labels == REGIONS.index(name)) & (p[..., 3] > 200)
        if region.sum() < least:
            out[name] = {"pixels": int(region.sum()), "delta_e": None}
            continue
        got = np.median(p[..., :3][region], axis=0)
        out[name] = {
            "pixels": int(region.sum()),
            "want": hex_of(colour),
            "got": hex_of(got),
            "delta_e": round(float(delta_e(got, colour)), 1),
        }
    return out


def flat_labels(flat: Image.Image, who: str, erode: int = 1) -> np.ndarray:
    """A label map from a picture drawn in the `Look`'s exact colours, eroded `erode` pixels so
    antialiased edges and a few pixels' misregistration don't count."""
    import cv2

    f = np.asarray(flat.convert("RGBA"), dtype=np.int32)
    labels = np.full(f.shape[:2], -1, dtype=np.int32)
    kernel = np.ones((2 * erode + 1, 2 * erode + 1), np.uint8)
    for name, colour in targets(who).items():
        hit = (np.abs(f[..., :3] - colour).max(axis=2) <= 1) & (f[..., 3] == 255)
        if erode:
            hit = cv2.erode(hit.astype(np.uint8), kernel) > 0
        labels[hit & (labels == -1)] = REGIONS.index(name)
    return labels


def wait_for_gpu() -> None:
    """Waits until no other FLUX, simile build or Ollama model is running, as #329's check does
    before every load."""
    while others := busy():
        print(f"Waiting for {others}", flush=True)
        time.sleep(30)


def log(entry: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "timings.jsonl").open("a") as f:
        f.write(json.dumps({"at": round(time.time()), **entry}) + "\n")


class Painter:
    """FLUX.2 Klein 4B at #309's 8 bits, from a prompt alone or, if `edit`, from images too.
    Loaded on entry once this study's lock is free and nothing else holds the GPU, and freed on
    exit."""

    def __init__(self, approach: str, edit: bool = True) -> None:
        self.approach = approach
        self.edit = edit
        self._flux = None

    def __enter__(self) -> Self:
        import fcntl

        from mflux.models.flux2.variants import Flux2Klein, Flux2KleinEdit

        from simile.works.config import DEFAULT_CONFIG
        from simile.works.flux import downloaded

        OUT.mkdir(parents=True, exist_ok=True)
        self._lock = (OUT / "flux.lock").open("w")
        fcntl.flock(self._lock, fcntl.LOCK_EX)
        wait_for_gpu()
        start = time.perf_counter()
        model = Flux2KleinEdit if self.edit else Flux2Klein
        self._flux = model(quantize=8, model_path=str(downloaded(DEFAULT_CONFIG.image_model)))
        seconds = round(time.perf_counter() - start, 1)
        log({"event": "load", "approach": self.approach, "edit": self.edit, "seconds": seconds})
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        trace: TracebackType | None,
    ) -> None:
        import mlx.core as mx

        self._flux = None
        gc.collect()
        mx.clear_cache()
        self._lock.close()

    def paint(
        self,
        key: str,
        prompt: str,
        size: tuple[int, int],
        seed: int,
        images: list[Image.Image] = (),
    ) -> Image.Image:
        import mlx.core as mx

        start = time.perf_counter()
        with tempfile.TemporaryDirectory() as folder:
            paths = []
            for i, image in enumerate(images):
                paths.append(Path(folder) / f"{i}.png")
                image.convert("RGB").save(paths[-1])
            extra = {"image_paths": paths} if self.edit else {}
            try:
                picture = self._flux.generate_image(
                    seed=seed,
                    prompt=prompt,
                    num_inference_steps=4,
                    width=size[0],
                    height=size[1],
                    **extra,
                ).image.convert("RGB")
            finally:
                mx.clear_cache()
        seconds = round(time.perf_counter() - start, 1)
        log(
            {
                "event": "paint",
                "approach": self.approach,
                "key": key,
                "seed": seed,
                "size": list(size),
                "images": len(images),
                "seconds": seconds,
                "prompt": prompt,
            }
        )
        print(f"{key} seed {seed}: {seconds} s", flush=True)
        return picture


def cut_out(painting: Image.Image) -> Image.Image:
    """The figure on its plain background as RGBA, with #309's IS-Net and colour key."""
    from simile.papercraft.cutout import hybrid, unmix

    return unmix(painting, hybrid(painting))


def trimmed(image: Image.Image, pad: int = 4) -> Image.Image:
    box = image.getchannel("A").point(lambda v: 255 if v > 24 else 0).getbbox()
    if box is None:
        return image
    x0, y0, x1, y1 = box
    return image.crop((max(0, x0 - pad), max(0, y0 - pad), x1 + pad, y1 + pad))


NEAR = 20.0
"""How far, CIEDE2000, a painted pixel may be from its region's typical colour and still be
restored with it."""


def restored(painted: Image.Image, flat: Image.Image) -> Image.Image:
    """#310's `restore`, for a map that only roughly lines up with the painting: each region's
    gain moves only the pixels painted near its typical colour, fading out by `NEAR`, so a face
    that falls where the map has hair isn't tinted like the hair."""
    from simile.dolls.colour import delta_e
    from simile.dolls.sheet import regions

    p = np.asarray(painted.convert("RGB"), dtype=np.float64)
    f = np.asarray(flat.convert("RGB"), dtype=np.float64)
    nearest, main, opaque = regions(flat)
    out = p.copy()
    for i, target in enumerate(main):
        region = opaque & (nearest == i)
        core = region & (np.abs(f - target).max(axis=2) < 1)
        if core.sum() < 10:
            continue
        typical = np.median(p[core], axis=0)
        gain = np.clip(np.maximum(target, 8) / np.maximum(typical, 8), 0.15, 4.0)
        weight = np.clip(1 - delta_e(p[region], typical) / NEAR, 0, 1)[:, None]
        out[region] = p[region] * (1 + (gain - 1) * weight)
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))


def save(image: Image.Image, name: str, width: int | None = 1600, quality: int = 86) -> None:
    """The full picture to out/previews/, and one `width` wide to images/ as JPEG 4:4:4, as #329
    found keeps thin lines crisp."""
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
