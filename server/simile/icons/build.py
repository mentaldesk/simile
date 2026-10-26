"""Paints the icons into `content/icons/`, repainting only those whose catalogue entry or
pipeline changed."""

import hashlib
import io
import json
import zlib
from collections.abc import Callable, Iterable
from contextlib import AbstractContextManager
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image

from simile.creatures.build import (
    SIZE,
    Cached,
    Try,
    bounds,
    boxed,
    components,
    solid,
    tidied,
    write,
)
from simile.dolls.flux import Painter
from simile.dolls.sprites import PAD, QUALITY, cut_out, scaled
from simile.icons.catalogue import ICONS, WHOLE, Box, Icon

REPO = Path(__file__).resolve().parents[3]
CONTENT = REPO / "content" / "icons"
MANIFEST = "icons.json"
PAINTINGS = REPO / "server" / "data" / "icons" / "paintings"
"""Every painting as FLUX returned it, by what it was painted from. Ignored by git."""
REFERENCE = "cartoon/street"
VERSION = 1
SIDE = 256
"""The longest an icon is, in pixels: sharp at the panel's size on a 5K screen."""
APART = 0.05
"""The share of an icon that may be in pieces apart from its `pieces` biggest."""
PAIRED = 0.3
"""How big each of an icon's `pieces` must be, against the biggest."""

Cut = Callable[[Image.Image], Image.Image]


def seed(icon: Icon, reroll: int = 0) -> int:
    return zlib.crc32(f"icon/{icon.id}/{reroll}".encode()) % 2**31


def fingerprint(icon: Icon) -> str:
    """What an icon is painted from: a new one means it's painted again."""
    inputs = {
        "version": VERSION,
        "icon": asdict(icon),
        "prompt": icon.prompt(),
        "reference": REFERENCE,
        "size": SIZE,
        "side": SIDE,
    }
    return hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()[:16]


@dataclass
class Painted:
    icon: Icon
    painting: Image.Image | None = None
    figure: Image.Image | None = None
    """Cut out, the size of its painting."""
    tries: list[Try] = field(default_factory=list)
    """Every painting of it, the one kept last."""

    @property
    def seconds(self) -> float:
        return sum(t.seconds or 0 for t in self.tries)


def problems(figure: Image.Image, pieces: int = 1) -> list[str]:
    a = solid(figure)
    if not a.any():
        return ["empty"]
    found = []
    if a[0].any() or a[-1].any() or a[:, 0].any() or a[:, -1].any():
        found.append("cut off by the edge")
    _, sizes = components(a)
    biggest = np.sort(sizes)[::-1][:pieces]
    if 1 - biggest.sum() / sizes.sum() > APART:
        found.append("in pieces")
    if len(biggest) < pieces or biggest[-1] < PAIRED * biggest[0]:
        found.append(f"not in {pieces} pieces")
    return found


def finished(figure: Image.Image, keep: Box = WHOLE) -> Image.Image:
    """Cropped to the `keep` share of the icon, at most `SIDE` pixels long."""
    x0, y0, x1, y1 = boxed(figure, keep)
    figure = figure.crop((x0, y0, x1 + 1, y1 + 1))
    left, top, right, bottom = bounds(figure)
    width, height = right - left + 1, bottom - top + 1
    small = scaled(
        figure.crop((left, top, right + 1, bottom + 1)), min(1, SIDE / max(width, height))
    )
    out = Image.new("RGBA", (small.width + 2 * PAD, small.height + 2 * PAD), (0, 0, 0, 0))
    out.paste(small, (PAD, PAD))
    return out


def paint(
    icon: Icon, painter: Cached, cut: Cut = cut_out, log: Callable[[str], None] = print
) -> Painted:
    """Paints `icon` in the style of the tunnels' reference until nothing's wrong with it, at most
    `tries` times, keeping the one with fewest problems."""
    from simile.papercraft.painter import reference

    style = [reference(REFERENCE)]
    made = []
    for n in range(icon.reroll, icon.reroll + icon.tries):
        number = seed(icon, n)
        painting, seconds = painter.paint(icon.prompt(), number, style)
        figure = tidied(cut(painting))
        wrong = problems(figure, icon.pieces)
        made.append((Try(number, wrong, 0.0, seconds), painting, figure))
        if not wrong:
            break
    best = min(made, key=lambda m: len(m[0].problems))
    said = "; ".join(best[0].problems) or "fine"
    log(f"{icon.id}: {said} after {len(made)} {'try' if len(made) == 1 else 'tries'}")
    return Painted(icon, best[1], best[2], [m[0] for m in made if m is not best] + [best[0]])


def webp(image: Image.Image) -> bytes:
    data = io.BytesIO()
    image.save(data, "WEBP", quality=QUALITY, alpha_quality=100, method=6)
    return data.getvalue()


def manifest(directory: Path) -> dict:
    path = directory / MANIFEST
    return json.loads(path.read_text()) if path.exists() else {"version": VERSION, "icons": {}}


def current(directory: Path, icon: Icon, entries: dict) -> bool:
    entry = entries.get(icon.id)
    return (
        entry is not None
        and entry["hash"] == fingerprint(icon)
        and (directory / entry["file"]).is_file()
    )


def build(
    painter: Callable[[], AbstractContextManager[Painter]],
    directory: Path = CONTENT,
    only: Iterable[str] = (),
    force: bool = False,
    cache: Path | None = PAINTINGS,
    cut: Cut = cut_out,
    log: Callable[[str], None] = print,
) -> list[Painted]:
    """Paints each icon whose fingerprint changed, loading the painter only if a painting isn't in
    `cache`, and lists every icon in the catalogue in the manifest, dropping any that's gone."""
    wanted = list(only) or list(ICONS)
    if unknown := [name for name in wanted if name not in ICONS]:
        raise KeyError(f"No icon called {', '.join(unknown)}: {', '.join(ICONS)}")
    entries = manifest(directory)["icons"]
    done = []
    model = Cached(painter, cache)
    with model.stack:
        for name in wanted:
            icon = ICONS[name]
            if not force and current(directory, icon, entries):
                log(f"{name}: up to date")
                continue
            painted = paint(icon, model, cut, log)
            image = finished(painted.figure, icon.keep)
            file = f"{name}.webp"
            write(directory, {file: webp(image)})
            entries[name] = {"file": file, "size": list(image.size), "hash": fingerprint(icon)}
            log(f"{name}: painted in {painted.seconds:.0f} s of FLUX")
            done.append(painted)
    for gone in set(entries) - set(ICONS):
        (directory / entries.pop(gone)["file"]).unlink(missing_ok=True)
    listed = {name: entries[name] for name in ICONS if name in entries}
    body = {"version": VERSION, "icons": listed}
    write(directory, {MANIFEST: (json.dumps(body, indent=2) + "\n").encode()})
    return done
