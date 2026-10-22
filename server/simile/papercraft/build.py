"""Paints, cuts out and scales every piece into content/papercraft/, and keeps its manifest.

Each piece keeps a hash of its inputs, so a run repaints only what changed. Paintings are cached
by their own hash outside the repo, so changing how pieces are cut doesn't repaint them.
"""

import dataclasses
import hashlib
import inspect
import json
import time
from collections.abc import Callable, Iterable, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

from simile.papercraft import cutout, fronts, sketches
from simile.papercraft.catalogue import Painting, index, paintings
from simile.papercraft.fronts import EAVES, Front, Plan, draw, unit_plans, units
from simile.papercraft.layout import Layout, load_layout
from simile.papercraft.painter import REFERENCES, EditPainter, Painter, reference
from simile.papercraft.sketches import SKETCHES
from simile.papercraft.village import LOOKS, front

CONTENT = Path(__file__).resolve().parents[3] / "content" / "papercraft"
MANIFEST = "manifest.json"
PPM = 120
"""Pixels per metre of every scaled piece."""
PAINTING = 1
"""Bump when what a painting is made from changes in a way its inputs don't show."""
PIPELINE = 19
"""Bump when cutting, scaling or saving changes."""
NIGHT_SIDE = 768
NIGHT_TINT = (0.3, 0.36, 0.6)
WEBP_METHOD = 6
QUALITY = {
    "sprite": 85,
    "front": 85,
    "layer": 82,
    "strip": 82,
    "ground": 82,
    "paper": 80,
    "glow": 80,
}

type Mask = Callable[[Image.Image], Image.Image]


def digest(*parts: object) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update(part if isinstance(part, bytes) else json.dumps(part, sort_keys=True).encode())
        h.update(b"\0")
    return h.hexdigest()[:20]


@cache
def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fit(image: Image.Image, side: int) -> Image.Image:
    s = side / max(image.size)
    if s >= 1:
        return image
    size = (round(image.width * s), round(image.height * s))
    return image.resize(size, Image.Resampling.LANCZOS)


@cache
def _whole(f: Front, ppm: float) -> Plan:
    return draw(f, ppm)


def _fields(f: Front) -> dict:
    """A front's fields that differ from their defaults, so a new field leaves other fronts'
    hashes alone."""
    return {
        k.name: getattr(f, k.name)
        for k in dataclasses.fields(f)
        if k.default is dataclasses.MISSING or getattr(f, k.name) != k.default
    }


@cache
def _sketch_source(name: str) -> str:
    return inspect.getsource(sketches.Sheet) + inspect.getsource(SKETCHES[name])


@cache
def _sketch_shape(name: str) -> np.ndarray:
    """What a sketch covers: everything not its backdrop."""
    a = np.asarray(_sketch(name), dtype=np.int16)
    return np.abs(a - a[0, 0]).max(axis=2) > 6


@cache
def _sketch(name: str) -> Image.Image:
    return SKETCHES[name]()


@dataclass
class Report:
    painted: dict[str, float] = field(default_factory=dict)
    """Seconds each painting took."""
    written: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)


class Build:
    def __init__(
        self,
        pieces: Sequence[Painting] | None = None,
        content: Path = CONTENT,
        cache_dir: Path | None = None,
        painter: Callable[[], AbstractContextManager[Painter]] = EditPainter,
        mask: Mask | None = None,
        key: Mask | None = None,
        layout: Layout | None = None,
    ) -> None:
        self.layout = layout or load_layout()
        chosen = pieces if pieces is not None else paintings(self.layout)
        self.pieces = {p.key: p for p in chosen}
        self.content = content
        self.cache = cache_dir or cutout.cache_dir() / "papercraft"
        self.painter = painter
        self.mask = mask or cutout.hybrid
        self.key = key or (lambda image: cutout.clean(cutout.key(image)))

    def front(self, piece: Painting) -> Front:
        building = piece.building or ""
        return front(self.layout.facades[building], LOOKS[building])

    def units(self, piece: Painting) -> tuple[tuple[float, Plan], ...]:
        """The units a front is painted in, each with where it starts and its plan."""
        return unit_plans(self.front(piece))

    def plan(self, piece: Painting) -> Plan:
        """The whole front's plan, at its units' scale, which they're put together on."""
        f = self.front(piece)
        return _whole(f, unit_plans(f)[0][1].ppm)

    def paint_hash(self, piece: Painting, unit: int | None = None) -> str:
        """The hash of what a painting is made from. A front or glow map is painted a unit at a
        time, and its own hash covers every unit's."""
        if piece.kind in ("front", "glow") and unit is None:
            count = len(self.units(piece))
            return digest(*(self.paint_hash(piece, i) for i in range(count)))
        prompt = self.prompt(piece, unit)
        inputs: list[object] = [PAINTING, prompt, list(self.size(piece, unit)), piece.seed]
        inputs += [_file_hash(REFERENCES / f"{name}.jpg") for name in piece.refs]
        if piece.kind == "front":
            unit_front = units(self.front(piece))[unit or 0][1]
            inputs += [unit, fronts.PLAN, _fields(unit_front)]
        if piece.sketch:
            inputs += [piece.sketch, _sketch_source(piece.sketch)]
        if piece.base:
            inputs.append(self.paint_hash(self.pieces[piece.base], unit))
        return digest(*inputs)

    def out_hash(self, piece: Painting) -> str:
        inputs: list[object] = [PIPELINE, PPM, piece.kind, piece.height, self.paint_hash(piece)]
        if piece.cut:
            inputs.append(list(piece.cut))
        if piece.kind in ("front", "glow"):
            inputs += [fronts.PLAN, _fields(self.front(piece))]
        return digest(*inputs)

    def prompt(self, piece: Painting, unit: int | None = None) -> str:
        return piece.prompts[unit] if unit is not None and piece.prompts else piece.prompt

    def size(self, piece: Painting, unit: int | None = None) -> tuple[int, int]:
        if piece.kind in ("front", "glow"):
            return self.units(piece)[unit or 0][1].image.size
        return piece.size

    def raw_path(self, piece: Painting, unit: int | None = None) -> Path:
        return self.cache / "raw" / f"{self.paint_hash(piece, unit)}.png"

    def jobs(self, piece: Painting) -> list[int | None]:
        """The paintings a piece is made from: one per unit for a front or glow map."""
        if piece.kind in ("front", "glow"):
            return list(range(len(self.units(piece))))
        return [None]

    def read_manifest(self) -> dict:
        path = self.content / MANIFEST
        return json.loads(path.read_text()) if path.exists() else {}

    def stale(self, manifest: dict, keys: Iterable[str]) -> list[Painting]:
        pieces = manifest.get("pieces", {})
        out = []
        for key in keys:
            piece = self.pieces[key]
            entry = pieces.get(key)
            if (
                entry is None
                or entry.get("hash") != self.out_hash(piece)
                or not (self.content / entry["file"]).exists()
            ):
                out.append(piece)
        return out

    def run(self, only: Callable[[str], bool] = lambda key: True, log=print) -> Report:
        report = Report()
        manifest = self.read_manifest()
        stale = self.stale(manifest, [k for k in self.pieces if only(k)])
        unpainted = self.unpainted(stale)
        if unpainted:
            log(f"Painting {len(unpainted)} for {len(stale)} stale pieces")
            with self.painter() as painter:
                for piece, unit in unpainted:
                    start = time.perf_counter()
                    size = self.size(piece, unit)
                    seed = piece.seed + (unit or 0)
                    images = self.images(piece, unit)
                    prompt = self.prompt(piece, unit)
                    picture = painter.paint(prompt, size, seed, images)
                    path = self.raw_path(piece, unit)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    picture.save(path)
                    name = piece.key if unit is None else f"{piece.key}#{unit}"
                    report.painted[name] = round(time.perf_counter() - start, 1)
                    log(f"  {name} {report.painted[name]}s")
                    self._time(name, piece, size, report.painted[name])
        entries = dict(manifest.get("pieces", {}))
        for piece in stale:
            entries[piece.key] = self.finish(piece)
            report.written.append(piece.key)
            log(f"  wrote {entries[piece.key]['file']}")
        if all(only(k) for k in entries):
            for key in sorted(set(entries) - set(self.pieces)):
                (self.content / entries.pop(key)["file"]).unlink(missing_ok=True)
                report.removed.append(key)
        self.write_manifest({k: entries[k] for k in sorted(entries)})
        return report

    def unpainted(self, stale: list[Painting]) -> list[tuple[Painting, int | None]]:
        """Every painting `stale` needs that isn't cached, bases first."""
        need: dict[tuple[str, int | None], tuple[Painting, int | None]] = {}

        def visit(piece: Painting) -> None:
            if piece.base:
                visit(self.pieces[piece.base])
            for unit in self.jobs(piece):
                if not self.raw_path(piece, unit).exists():
                    need.setdefault((piece.key, unit), (piece, unit))

        for piece in stale:
            visit(piece)
        return list(need.values())

    def _time(self, name: str, piece: Painting, size: tuple, seconds: float) -> None:
        with (self.cache / "timings.jsonl").open("a") as f:
            entry = {"key": name, "kind": piece.kind, "size": list(size), "seconds": seconds}
            f.write(json.dumps(entry) + "\n")

    def raw(self, piece: Painting, unit: int | None = None) -> Image.Image:
        return Image.open(self.raw_path(piece, unit)).convert("RGB")

    def images(self, piece: Painting, unit: int | None = None) -> list[Image.Image]:
        """What a painting is painted from: its plan, sketch or base first, then its
        references."""
        images = []
        if piece.kind == "front":
            images.append(self.units(piece)[unit or 0][1].image)
        if piece.sketch:
            images.append(_sketch(piece.sketch))
        if piece.base:
            images.append(_fit(self.raw(self.pieces[piece.base], unit), NIGHT_SIDE))
        for name in piece.refs:
            images.append(reference(name, 512 if name == "furniture" else 768))
        return images

    def finish(self, piece: Painting) -> dict:
        """Cut, scale and save `piece` from its painting, and its manifest entry."""
        entry: dict = {"kind": piece.kind}
        if piece.kind in ("front", "glow"):
            image, extra = self.finish_front(piece)
            entry.update(extra)
            height = image.height / PPM
        else:
            raw = self.raw(piece)
            if piece.kind == "paper":
                sky, slab = piece.key == "layers/sky", piece.key == "papers/slab"
                image = tileable(raw, both=not (sky or slab), plain=sky)
                if slab:
                    image = band_rows(image)
                height = piece.height or image.height / PPM
            elif piece.kind in ("layer", "strip", "ground"):
                if "above" in piece.cut:
                    mask = cutout.clean(cutout.key(raw, bg=top_backdrop(raw)))
                else:
                    mask = self.key(raw) if piece.kind == "ground" else self.mask(raw)
                if piece.kind != "strip":
                    mask = cutout.skyline(mask)
                image = tileable(trim_rows(cutout.unmix(raw, mask)))
                height = piece.height or image.height / PPM
            else:
                if piece.sketch and "outline" in piece.cut:
                    shape = _sketch_shape(piece.sketch)
                    mask = outline_mask(raw, shape, round(0.012 * raw.width) | 1, 5)
                else:
                    mask = self.mask(raw)
                if piece.cut:
                    mask = cutout.tidy(raw, mask, piece.cut)
                image = cutout.unmix(raw, mask)
                image = image.crop(image.getchannel("A").getbbox() or (0, 0, *image.size))
                image = scaled(image, round((piece.height or 1) * PPM))
                height = piece.height or 1
                entry["anchor"] = [0.5, 1.0]
        file = f"{piece.key}.webp"
        path = self.content / file
        path.parent.mkdir(parents=True, exist_ok=True)
        save_webp(image, path, QUALITY[piece.kind])
        return {
            "file": file,
            "size": list(image.size),
            "height": round(height, 3),
            **entry,
            "hash": self.out_hash(piece),
        }

    def finish_front(self, piece: Painting) -> tuple[Image.Image, dict]:
        """A front, or its glow map, put together from its units' paintings side by side, cut
        to the front and scaled."""
        whole, f = self.plan(piece), self.front(piece)
        glow = piece.kind == "glow"
        image = Image.new("RGB" if glow else "RGBA", whole.image.size, (0, 0, 0, 0))
        for i, (x, plan) in enumerate(self.units(piece)):
            raw = self.raw(piece, i)
            if glow:
                part = glow_map(self.raw(self.pieces[piece.base or ""], i), raw, plan)
            else:
                part = cutout.unmix(raw, front_mask(raw, plan), top_backdrop(raw))
            at = (round(whole.left + x * whole.ppm - plan.left), round(whole.ground - plan.ground))
            layer = Image.new(image.mode, image.size, (0, 0, 0, 0))
            layer.paste(part, at)
            if glow:
                image = Image.fromarray(np.maximum(np.asarray(image), np.asarray(layer)))
            else:
                image = Image.alpha_composite(image, layer)
        box = front_box(whole, f)
        image = image.crop(tuple(round(v) for v in box))
        s = PPM / whole.ppm
        image = image.resize(
            (round(image.width * s), round(image.height * s)), Image.Resampling.LANCZOS
        )
        middle = whole.left + f.width * whole.ppm / 2
        anchor = [
            round((middle - box[0]) / (box[2] - box[0]), 4),
            round((whole.ground - box[1]) / (box[3] - box[1]), 4),
        ]
        extra = {"anchor": anchor, "width": round(f.width, 3), "eaves": round(f.wall_height, 3)}
        return image, extra

    def write_manifest(self, pieces: dict) -> None:
        manifest = {"version": 1, "ppm": PPM, **index(self.layout), "pieces": pieces}
        text = json.dumps(manifest, indent=1) + "\n"
        path = self.content / MANIFEST
        if not path.exists() or path.read_text() != text:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)


def front_box(plan: Plan, f: Front) -> tuple[float, float, float, float]:
    """The part of a front's painting that's kept: its walls and roof with the eaves, from a
    little above the roof down to just under the ground line."""
    side = (EAVES + 0.25) * plan.ppm
    return (
        max(0, plan.left - side),
        max(0, plan.ground - (f.total_height + 0.3) * plan.ppm),
        min(plan.image.width, plan.left + f.width * plan.ppm + side),
        min(plan.image.height, plan.ground + 0.12 * plan.ppm),
    )


def top_backdrop(image: Image.Image) -> np.ndarray:
    """The backdrop's colour, from the picture's top row, which a slice's sides aren't."""
    return np.median(np.asarray(image.convert("RGB"), dtype=np.float32)[0], axis=0)


def silhouette(plan: Plan) -> np.ndarray:
    return np.asarray(plan.shape) > 0


def front_mask(painted: Image.Image, plan: Plan) -> Image.Image:
    reach, grain = round(0.3 * plan.ppm) | 1, round(0.05 * plan.ppm) | 1
    return outline_mask(painted, silhouette(plan), reach, grain)


def outline_mask(
    painted: Image.Image, shape: np.ndarray, reach: int, grain: int, lo: float = 28, hi: float = 60
) -> Image.Image:
    """Solid inside the drawing's `shape`, and beyond it, out to `reach` px, wherever the
    painting differs clearly from the backdrop: so roof edges painted past the plan stay, and
    painted ground, shadows and paper margins go. Specks of backdrop grain outside are opened
    away."""
    inside = shape.astype(np.float32) * 255
    solid = -dilate(-inside, 5)
    near = dilate(inside, reach)
    a = np.asarray(painted, dtype=np.float32)
    d = np.abs(a - top_backdrop(painted)).max(axis=2)
    keyed = np.minimum(np.clip((d - lo) / (hi - lo), 0, 1) * 255, near)
    keyed = dilate(-dilate(-keyed, grain), grain)
    m = np.maximum(keyed, solid)
    return Image.fromarray(m.astype(np.uint8)).filter(ImageFilter.MedianFilter(3))


def dilate(a: np.ndarray, size: int) -> np.ndarray:
    """A square max filter `size` across, as two passes."""
    pad = size // 2
    for axis in (0, 1):
        widths = [(0, 0), (0, 0)]
        widths[axis] = (pad, pad)
        padded = np.pad(a, widths, mode="edge")
        a = np.lib.stride_tricks.sliding_window_view(padded, size, axis=axis).max(axis=-1)
    return a


def glow_map(day: Image.Image, night: Image.Image, plan: Plan) -> Image.Image:
    """The light a building gives off at night: what's warm and bright in its night picture and
    not in its day one, only where its plan has windows and lamps."""
    d = np.asarray(day, dtype=np.float32)
    n = np.asarray(night.resize(day.size, Image.Resampling.LANCZOS), dtype=np.float32)
    grown = dilate(np.asarray(plan.glow, dtype=np.float32), round(0.08 * plan.ppm) | 1)
    where = Image.fromarray(grown.astype(np.uint8)).filter(ImageFilter.GaussianBlur(2))
    m = np.asarray(where, dtype=np.float32)[..., None] / 255
    warm = np.clip((n.mean(axis=2) - 100) / 90, 0, 1) * (n[..., 0] > n[..., 2] + 15)
    light = np.clip(n - d * np.array(NIGHT_TINT), 0, 255) * warm[..., None] * m
    return Image.fromarray(light.astype(np.uint8))


def band_rows(image: Image.Image, share: float = 0.97) -> Image.Image:
    """`image` cut to its longest run of rows that are almost all painting, not backdrop: a
    band painted across a picture, without the backdrop above it or its ragged edge."""
    a = np.asarray(image.convert("RGB"), dtype=np.float32)
    painted = (np.abs(a - top_backdrop(image)).max(axis=2) > 30).mean(axis=1) >= share
    edges = np.flatnonzero(np.diff(np.r_[0, painted.astype(int), 0]))
    runs = list(zip(edges[::2], edges[1::2], strict=True))
    if not runs:
        return image
    top, bottom = max(runs, key=lambda r: r[1] - r[0])
    return image.crop((0, int(top), image.width, int(bottom)))


def trim_rows(image: Image.Image) -> Image.Image:
    """`image` without the fully transparent rows above and below it, keeping its width."""
    alpha = np.asarray(image.getchannel("A")) > 8
    rows = np.flatnonzero(alpha.any(axis=1))
    if not len(rows):
        return image
    return image.crop((0, int(rows[0]), image.width, int(rows[-1]) + 1))


def tileable(
    image: Image.Image, both: bool = False, plain: bool = False, overlap: int = 32
) -> Image.Image:
    """`image` made to repeat without a seam: cut at a gap near each end if it has one, or else
    cut where its two ends look most alike and crossfaded there. `both` does top and bottom
    too. `plain` joins it only where it's plain, for things on a plain ground, like clouds in a
    sky, so none is cut in two."""
    a = np.asarray(image, dtype=np.float32)
    if a.shape[2] == 4:
        cover = (a[..., 3] > 8).sum(axis=0)
        w = a.shape[1]
        reach = w // 5
        left = int(np.argmin(cover[:reach]))
        right = w - reach + int(np.argmin(cover[w - reach :]))
        if cover[left] == 0 and cover[right] == 0:
            return image.crop((left, 0, right, image.height))
    a = _seamless(a, overlap, plain)
    if both:
        a = _seamless(a.transpose(1, 0, 2), overlap, plain).transpose(1, 0, 2)
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), image.mode)


def _seamless(a: np.ndarray, overlap: int, plain: bool, step: int = 4) -> np.ndarray:
    """`a` cropped from column `i` to `j`, where the stretch after `j` most resembles the one
    after `i`, with the two crossfaded: a plain crossfade of unlike ends ghosts both. If
    `plain`, the pair is also kept to stretches where nothing strays from its row's usual
    colour, so the join falls in clear sky rather than through a cloud."""
    w = a.shape[1]
    overlap = min(overlap, w // 6)
    reach = w // 6
    small = a[::step, ::step]
    band = overlap // step
    starts = range(0, reach // step)
    ends = range((w - reach - overlap) // step, (w - overlap) // step)
    detail = _detail(small, band) if plain else np.zeros(small.shape[1])
    cost = np.array(
        [
            [
                np.abs(small[:, i : i + band] - small[:, j : j + band]).mean()
                + detail[i]
                + detail[j]
                for j in ends
            ]
            for i in starts
        ]
    )
    bi, bj = np.unravel_index(int(np.argmin(cost)), cost.shape)
    i, j = starts[bi] * step, ends[bj] * step
    after, start = a[:, j : j + overlap], a[:, i : i + overlap]
    t = np.linspace(0, 1, overlap)[None, :, None]
    out = a[:, i:j].copy()
    out[:, :overlap] = after * (1 - t) + start * t
    return _level(out, after, start)


LUMA = np.array([0.299, 0.587, 0.114])


def _level(tile: np.ndarray, after: np.ndarray, start: np.ndarray) -> np.ndarray:
    """`tile` lightened or darkened so that its two joined stretches meet at the brightness
    halfway between them, row by row and smoothed: where the painting's light falls off, the
    join shows no step, and the tile keeps its mean brightness. Each pixel's channels move by
    the same amount, which keeps its hue, and near-white isn't darkened, so clouds stay white."""
    overlap = after.shape[1]
    both = np.ones(after.shape[:2], bool)
    opaque = np.ones(tile.shape[:2], bool)
    if tile.shape[2] == 4:
        both = (after[..., 3] > 128) & (start[..., 3] > 128)
        opaque = tile[..., 3] > 128
    diff = np.where(both, (after[..., :3] - start[..., :3]) @ LUMA, 0.0)
    rows = diff.sum(axis=1) / np.maximum(both.sum(axis=1), 1)
    sigma = max(2.0, len(rows) / 12)
    x = np.arange(-round(3 * sigma), round(3 * sigma) + 1)
    kernel = np.exp(-(x**2) / (2 * sigma**2))
    smooth = np.convolve(np.pad(rows, len(x) // 2, mode="edge"), kernel / kernel.sum(), "valid")
    w = tile.shape[1]
    ramp = np.clip(1 - np.arange(w) / (w - 1), 0, 1)
    ramp[:overlap] *= np.linspace(0, 1, overlap)
    shift = smooth[:, None] * ramp[None, :]
    weight = np.where(opaque, 1.0, 0.0)
    total = np.maximum(weight.sum(axis=1, keepdims=True), 1)
    shift -= (shift * weight).sum(axis=1, keepdims=True) / total
    highlight = np.clip((250 - tile[..., :3] @ LUMA) / 40, 0, 1)
    shift = np.where(shift < 0, shift * highlight, shift)
    out = tile.copy()
    out[..., :3] += shift[..., None]
    return out


def _detail(small: np.ndarray, band: int) -> np.ndarray:
    """For each column, how far the stretch `band` wide from it strays, at its most, from the
    usual colour of its rows: low in clear sky, high through a cloud, even inside a big one."""
    rgb = small[..., :3]
    strays = np.abs(rgb - np.median(rgb, axis=1, keepdims=True)).sum(axis=2)
    total = np.cumsum(np.pad(strays, ((0, 0), (1, 0))), axis=1)
    means = (total[:, band:] - total[:, :-band]) / band
    means = np.pad(means, ((0, 0), (0, small.shape[1] - means.shape[1])), mode="edge")
    return means.max(axis=0)


def scaled(image: Image.Image, height: int) -> Image.Image:
    h = max(1, height)
    return image.resize(
        (max(1, round(image.width * h / image.height)), h), Image.Resampling.LANCZOS
    )


def save_webp(image: Image.Image, path: Path, quality: int) -> None:
    if image.mode == "RGBA" and image.getchannel("A").getextrema()[0] == 255:
        image = image.convert("RGB")
    image.save(path, "WEBP", quality=quality, method=WEBP_METHOD)
