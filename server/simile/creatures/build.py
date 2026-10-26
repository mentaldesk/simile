"""Paints the creatures into `content/creatures/`, repainting only those whose catalogue entry
or pipeline changed."""

import hashlib
import json
import time
import zlib
from collections.abc import Callable, Iterable
from contextlib import AbstractContextManager, ExitStack
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageDraw, ImageFilter, ImageOps

from simile.creatures.catalogue import CREATURES, Box, Creature, Edit
from simile.dolls.flux import Painter
from simile.dolls.sprites import PAD, atlas, cut_out, scaled

REPO = Path(__file__).resolve().parents[3]
CONTENT = REPO / "content" / "creatures"
PAINTINGS = REPO / "server" / "data" / "creatures" / "paintings"
"""Every painting as FLUX returned it, by what it was painted from. Ignored by git."""
REFERENCE = "cartoon/street"
SIZE = (1024, 768)
PPM = 80
"""Atlas pixels a metre, as the dolls'."""
VERSION = 1
SOLID = 128
APART = 0.05
"""The share of a frame's figure that may be in pieces apart from its body."""
SPECK = 0.02
"""A piece this much smaller than the body is cut away."""
OFF_COLOUR = 10.0
"""How far, CIEDE2000, a frame's average colour may be from the first frame's."""
SIZES = (0.5, 2.0)
"""How much smaller or bigger than the first frame a frame's figure may be, by area."""

Cut = Callable[[Image.Image], Image.Image]


def seed(creature: str, frame: str, reroll: int = 0) -> int:
    return zlib.crc32(f"{creature}/{frame}/{reroll}".encode()) % 2**31


def fingerprint(creature: Creature) -> str:
    """What a creature is painted from: a new one means it's painted again."""
    inputs = {
        "version": VERSION,
        "creature": asdict(creature),
        "prompts": {frame: creature.prompt(frame) for frame in creature.frames},
        "reference": REFERENCE,
    }
    return hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()[:16]


class Cached:
    """Paints through `painter`, keeping each painting in `folder` by everything it was painted
    from, and loading the painter only for one that isn't there."""

    def __init__(
        self, painter: Callable[[], AbstractContextManager[Painter]], folder: Path | None
    ) -> None:
        self.factory, self.folder = painter, folder
        self.stack = ExitStack()
        self.model: Painter | None = None

    def paint(
        self, prompt: str, seed: int, images: list[Image.Image]
    ) -> tuple[Image.Image, float | None]:
        key = hashlib.sha256(prompt.encode() + str(seed).encode())
        for image in images:
            key.update(image.tobytes())
        path = None if self.folder is None else self.folder / f"{key.hexdigest()[:20]}.png"
        if path is not None and path.exists():
            return Image.open(path).convert("RGB"), None
        if self.model is None:
            self.model = self.stack.enter_context(self.factory())
        start = time.perf_counter()
        painting = self.model.paint(prompt, SIZE, seed, images)
        seconds = round(time.perf_counter() - start, 1)
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            painting.save(path)
        return painting, seconds


@dataclass
class Try:
    seed: int
    problems: list[str]
    off: float
    """CIEDE2000 from the first frame's average colour."""
    seconds: float | None


@dataclass
class Painted:
    creature: Creature
    paintings: dict[str, Image.Image] = field(default_factory=dict)
    figures: dict[str, Image.Image] = field(default_factory=dict)
    """Each frame cut out, the size of its painting."""
    guides: dict[str, Image.Image] = field(default_factory=dict)
    tries: dict[str, list[Try]] = field(default_factory=dict)
    """Every painting of each frame, the one kept last."""

    @property
    def seconds(self) -> float:
        return sum(t.seconds or 0 for tries in self.tries.values() for t in tries)


def solid(figure: Image.Image) -> NDArray[np.bool_]:
    return np.asarray(figure.getchannel("A")) >= SOLID


def bounds(figure: Image.Image) -> tuple[int, int, int, int]:
    """The figure's opaque box: left, top, right and bottom, inclusive."""
    a = solid(figure)
    rows, cols = np.flatnonzero(a.any(axis=1)), np.flatnonzero(a.any(axis=0))
    return int(cols[0]), int(rows[0]), int(cols[-1]), int(rows[-1])


def boxed(figure: Image.Image, box: Box) -> tuple[int, int, int, int]:
    """`box` in pixels of the painting, from shares of `figure`'s opaque box."""
    left, top, right, bottom = bounds(figure)
    w, h = right - left, bottom - top
    x0, y0, x1, y1 = box
    return round(left + x0 * w), round(top + y0 * h), round(left + x1 * w), round(top + y1 * h)


def backdrop(painting: Image.Image) -> tuple[int, int, int]:
    a = np.asarray(painting.convert("RGB"))
    border = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
    return tuple(int(v) for v in np.median(border, axis=0))


def guide(painting: Image.Image, figure: Image.Image, edit: Edit) -> Image.Image:
    """What `edit` is painted over: its base frame's painting, made into a rough guide."""
    out = painting.convert("RGB").copy()
    plain = backdrop(painting)
    if edit.mirror:
        x0, y0, x1, y1 = boxed(figure, edit.mirror)
        part = figure.crop((x0, y0, x1, y1))
        reflected = ImageOps.flip(part)
        ImageDraw.Draw(out).rectangle((x0, y0, x1, y1), plain)
        out.paste(reflected.convert("RGB"), (x0, y1), reflected.getchannel("A"))
    draw = ImageDraw.Draw(out)
    for box in edit.rub:
        draw.rectangle(boxed(figure, box), plain)
    if edit.turn:
        left, top, right, bottom = bounds(figure)
        centre = ((left + right) / 2, (top + bottom) / 2)
        out = out.rotate(-edit.turn, Image.Resampling.BICUBIC, center=centre, fillcolor=plain)
    return out


def components(mask: NDArray[np.bool_]) -> tuple[NDArray[np.int_], NDArray[np.int_]]:
    """Each pixel's piece of `mask`, corners joining, 0 for none, and each piece's size from 1:
    runs along each row joined to the runs they touch in the row above."""
    parent: list[int] = [0]

    def root(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    runs: list[tuple[int, int, int, int]] = []
    above: list[tuple[int, int, int]] = []
    for y, row in enumerate(mask):
        edges = np.flatnonzero(np.diff(np.concatenate([[0], row.astype(np.int8), [0]])))
        here = []
        for start, end in zip(edges[::2], edges[1::2], strict=True):
            label = len(parent)
            parent.append(label)
            for s, e, other in above:
                if s <= end and e >= start:
                    parent[root(label)] = root(other)
            here.append((int(start), int(end), label))
            runs.append((y, int(start), int(end), label))
        above = here
    labels = np.zeros(mask.shape, dtype=np.int_)
    roots = sorted({root(i) for i in range(1, len(parent))})
    number = {r: n for n, r in enumerate(roots, 1)}
    for y, start, end, label in runs:
        labels[y, start:end] = number[root(label)]
    return labels, np.bincount(labels.ravel(), minlength=len(roots) + 1)[1:]


def tidied(figure: Image.Image) -> Image.Image:
    """`figure` without opaque specks apart from its body: a painted shadow, a stray stone."""
    a = np.asarray(figure).copy()
    labels, sizes = components(a[..., 3] >= SOLID)
    if len(sizes) > 1:
        small = 1 + np.flatnonzero(sizes < SPECK * sizes.max())
        near = np.asarray(
            Image.fromarray((np.isin(labels, small) * 255).astype(np.uint8)).filter(
                ImageFilter.MaxFilter(5)
            )
        )
        a[near > 0, 3] = 0
    return Image.fromarray(a, "RGBA")


def average(figure: Image.Image) -> NDArray[np.float64]:
    from simile.dolls.colour import cielab

    rgb = np.asarray(figure.convert("RGB"), dtype=np.float64)[solid(figure)]
    return cielab(rgb).mean(axis=0)


def problems(figure: Image.Image, first: Image.Image | None) -> tuple[list[str], float]:
    """What's wrong with a frame, and how far its average colour is from the first frame's."""
    from simile.dolls.colour import delta_e_lab

    a = solid(figure)
    found = []
    if not a.any():
        return ["empty"], 0.0
    if a[0].any() or a[-1].any() or a[:, 0].any() or a[:, -1].any():
        found.append("cut off by the edge")
    _, sizes = components(a)
    if 1 - sizes.max() / sizes.sum() > APART:
        found.append("in pieces")
    off = 0.0
    if first is not None:
        off = float(delta_e_lab(average(figure), average(first)))
        if off > OFF_COLOUR:
            found.append(f"off colour by ΔE {off:.1f}")
        ratio = a.sum() / max(solid(first).sum(), 1)
        if not SIZES[0] <= ratio <= SIZES[1]:
            found.append(f"{ratio:.2f} times the first frame's size")
    return found, off


def paint_frame(
    painter: Cached,
    painted: Painted,
    frame: str,
    images: list[Image.Image],
    cut: Cut,
    log: Callable[[str], None],
) -> None:
    """Paints `frame` until nothing's wrong with it, at most `tries` times, keeping the best."""
    creature = painted.creature
    first = painted.figures.get(creature.first)
    prompt = creature.prompt(frame)
    start = creature.rerolls.get(frame, 0)
    made = []
    for n in range(start, start + creature.tries):
        number = seed(creature.id, frame, n)
        painting, seconds = painter.paint(prompt, number, images)
        figure = tidied(cut(painting))
        wrong, off = problems(figure, first)
        made.append((Try(number, wrong, round(off, 1), seconds), painting, figure))
        if not wrong:
            break
    best = min(made, key=lambda m: (len(m[0].problems), m[0].off))
    painted.tries[frame] = [m[0] for m in made if m is not best] + [best[0]]
    painted.paintings[frame], painted.figures[frame] = best[1], best[2]
    said = "; ".join(best[0].problems) or "fine"
    log(f"{creature.id} {frame}: {said} after {len(made)} {'try' if len(made) == 1 else 'tries'}")


def paint(
    creature: Creature,
    painter: Cached,
    cut: Cut = cut_out,
    log: Callable[[str], None] = print,
) -> Painted:
    """The first frame from words in the style of the tunnels' reference, then each other as an
    edit of its base frame over a guide drawn from it."""
    from simile.papercraft.painter import reference

    painted = Painted(creature)
    paint_frame(painter, painted, creature.first, [reference(REFERENCE)], cut, log)
    for frame, edit in creature.edits.items():
        base = painted.paintings[edit.base]
        painted.guides[frame] = guide(base, painted.figures[edit.base], edit)
        paint_frame(painter, painted, frame, [painted.guides[frame]], cut, log)
    return painted


@dataclass
class Placed:
    image: Image.Image
    anchor: tuple[float, float]


def anchor(creature: Creature, figure: Image.Image) -> tuple[float, float]:
    """In the first frame's painting: the ground under its middle, or for a flier its middle."""
    left, top, right, bottom = bounds(figure)
    if creature.moves == "fly":
        return (left + right + 1) / 2, (top + bottom + 1) / 2
    return (left + right + 1) / 2, float(bottom + 1)


def hung(figure: Image.Image) -> tuple[float, float]:
    """Where a hanging figure holds on: the middle of its top rows."""
    a = solid(figure)
    rows = np.flatnonzero(a.any(axis=1))
    top = int(rows[0])
    cols = np.flatnonzero(a[top : top + max(2, (rows[-1] - top) // 10)].any(axis=0))
    return float(cols.mean()), float(top)


def placed(creature: Creature, figures: dict[str, Image.Image]) -> dict[str, Placed]:
    """Every frame at `PPM`, each scaled as the first is, `length` metres wide. Edits keep the
    first frame where it was painted, so each frame's anchor is the first's, at the same place in
    its painting, but for one hanging from its own."""
    first = figures[creature.first]
    left, _, right, _ = bounds(first)
    factor = creature.length * PPM / (right - left + 1)
    at = anchor(creature, first)
    out = {}
    for name in creature.frames:
        edit = creature.edits.get(name)
        point = hung(figures[name]) if edit and edit.hangs else at
        small = scaled(figures[name], factor)
        x0, y0, x1, y1 = bounds(small)
        x0, y0 = max(0, x0 - PAD), max(0, y0 - PAD)
        image = small.crop(
            (x0, y0, min(small.width, x1 + 1 + PAD), min(small.height, y1 + 1 + PAD))
        )
        out[name] = Placed(image, (point[0] * factor - x0, point[1] * factor - y0))
    return out


def files(creature: Creature, figures: dict[str, Image.Image], **extra: Any) -> dict[str, bytes]:
    """The manifest and the atlas, by file name."""
    made = placed(creature, figures)
    data, places = atlas(made)
    left, top, right, bottom = bounds(made[creature.first].image)
    name = f"{creature.id}.webp"
    body = {
        "id": creature.id,
        **extra,
        "version": VERSION,
        "ppm": PPM,
        "moves": creature.moves,
        "size": [round((right - left + 1) / PPM, 2), round((bottom - top + 1) / PPM, 2)],
        "painted": name,
        "frames": {
            frame: {
                "frame": list(places[frame]),
                "anchor": [round(made[frame].anchor[0], 1), round(made[frame].anchor[1], 1)],
                **(
                    {"hangs": True}
                    if frame in creature.edits and creature.edits[frame].hangs
                    else {}
                ),
            }
            for frame in creature.frames
        },
        "poses": creature.poses,
    }
    return {name: data, f"{creature.id}.json": (json.dumps(body, indent=2) + "\n").encode()}


def write(directory: Path, named: dict[str, bytes]) -> list[Path]:
    """Writes only the files whose bytes changed."""
    directory.mkdir(parents=True, exist_ok=True)
    written = []
    for name, data in named.items():
        path = directory / name
        if not path.exists() or path.read_bytes() != data:
            path.write_bytes(data)
            written.append(path)
    return written


def current(directory: Path, creature: Creature) -> bool:
    path = directory / f"{creature.id}.json"
    if not path.exists():
        return False
    found = json.loads(path.read_text())
    return found.get("hash") == fingerprint(creature) and (directory / found["painted"]).is_file()


def build(
    painter: Callable[[], AbstractContextManager[Painter]],
    directory: Path = CONTENT,
    only: Iterable[str] = (),
    force: bool = False,
    cache: Path | None = PAINTINGS,
    cut: Cut = cut_out,
    log: Callable[[str], None] = print,
) -> list[Painted]:
    """Paints each creature whose fingerprint changed, loading the painter only if a painting
    isn't in `cache`."""
    wanted = list(only) or list(CREATURES)
    if unknown := [name for name in wanted if name not in CREATURES]:
        raise KeyError(f"No creature called {', '.join(unknown)}: {', '.join(CREATURES)}")
    done = []
    model = Cached(painter, cache)
    with model.stack:
        for name in wanted:
            creature = CREATURES[name]
            if not force and current(directory, creature):
                log(f"{name}: up to date")
                continue
            painted = paint(creature, model, cut, log)
            changed = write(directory, files(creature, painted.figures, hash=fingerprint(creature)))
            log(f"{name}: painted in {painted.seconds:.0f} s of FLUX, wrote {len(changed)} files")
            done.append(painted)
    return done
