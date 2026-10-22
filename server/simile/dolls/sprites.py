"""Painted figures as the client draws them: cut out, scaled to the street, stood on their feet
under the middle of their head, and packed into one WebP atlas with a manifest."""

import io
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray
from PIL import Image

PPM = 80
"""Atlas pixels a metre: a retina screen's, so a figure draws 1:1 at play size."""
HEIGHT_M = 2.04
"""A standing figure, sole to crown: the client's `DOLL_M`."""
VERSION = 3
QUALITY = 85
PAD = 2
ATLAS_WIDTH = 1024
SOLID = 128
CLEAR = 8
EDGE = 3
"""How far in from the clear around it an edge stays soft."""
GAP = 12
"""How far from the background's colour, the most any channel differs, a clear patch inside the
outline must be, typically, to be the figure's own: pale hair is about 18, a gap 6 to 8."""
HEAD = 0.25
"""The share of a standing figure's height measured as its head, from the top: above the chin,
the shoulders and swinging arms."""
CROWN = 0.6
"""The share of the head measured for its width: above the ears, where raised arms stay clear."""
FIT = (0.6, 1.6)
"""How far a frame is rescaled to match the standing figure."""
SOLES = 0.08
"""The share of a sitting figure's height measured up from its lowest row as its feet."""
CLIMB = 3
"""Columns looked back along the backs of the calves, so a short flat step doesn't end them."""


@dataclass
class Frame:
    image: Image.Image
    feet: tuple[float, float]
    """The ground under the middle of the head, from the frame's top-left in pixels."""
    seat: tuple[float, float] | None = None
    """Where a sitting figure sits, under the middle of its head: the bottom of what's behind
    its calves."""


def solid(image: Image.Image) -> NDArray[np.bool_]:
    return np.asarray(image.getchannel("A")) >= SOLID


def cut_out(painting: Image.Image) -> Image.Image:
    """The figure off its plain background, with #309's IS-Net and key, and without the shadow
    FLUX paints on the floor: shadow-grey reached from outside, not grey inside the outline.
    Pale hair close to the background's grey is kept wherever the outline encloses it, only the
    background itself shows through a gap, such as between an arm and the body, and nothing is
    see-through but the antialiased edge."""
    import cv2

    from simile.papercraft.cutout import background, hybrid, shadows, unmix

    mask = np.asarray(hybrid(painting)).copy()
    plain = np.abs(np.asarray(painting, dtype=np.float32) - background(painting)).max(axis=2)
    count, labels = cv2.connectedComponents(enclosed(mask < SOLID).astype(np.uint8), 4)
    for i in range(1, count):
        if np.median(plain[labels == i]) >= GAP:
            mask[labels == i] = 255
    edge = cv2.dilate((mask < CLEAR).astype(np.uint8), np.ones((2 * EDGE + 1,) * 2, np.uint8))
    mask[(mask >= CLEAR) & (edge == 0)] = 255
    shade = shadows(painting)
    rows = np.flatnonzero((mask >= SOLID).any(axis=1))
    if len(rows):
        shade[: rows[0] + int(0.8 * (rows[-1] - rows[0]))] = False
    open_ = ((mask < SOLID) | shade).astype(np.uint8)
    _, labels = cv2.connectedComponents(open_, connectivity=4)
    border = np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]]))
    mask[shade & np.isin(labels, border[border > 0])] = 0
    return unmix(painting, Image.fromarray(mask))


def enclosed(clear: NDArray[np.bool_]) -> NDArray[np.bool_]:
    """The clear pixels that can't reach the picture's edge without crossing the figure."""
    import cv2

    _, labels = cv2.connectedComponents(clear.astype(np.uint8), connectivity=4)
    border = np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]]))
    return clear & ~np.isin(labels, border)


def trimmed(image: Image.Image, pad: int = PAD) -> Image.Image:
    box = image.getchannel("A").point(lambda v: 255 if v > 8 else 0).getbbox()
    if box is None:
        return image
    x0, y0, x1, y1 = box
    return image.crop((max(0, x0 - pad), max(0, y0 - pad), x1 + pad, y1 + pad))


def widest_run(row: NDArray[np.bool_]) -> tuple[int, int]:
    """The longest stretch of opaque pixels in a row, as (start, end)."""
    padded = np.concatenate([[False], row, [False]]).astype(np.int8)
    edges = np.flatnonzero(np.diff(padded))
    starts, ends = edges[::2], edges[1::2]
    if not len(starts):
        return 0, 0
    i = int(np.argmax(ends - starts))
    return int(starts[i]), int(ends[i])


def head(image: Image.Image, depth: float | None = None) -> tuple[float, float]:
    """The head's middle column and its width across its crown: the top `depth` pixels of the
    figure (by default `HEAD` of its height)."""
    a = solid(image)
    rows = np.flatnonzero(a.any(axis=1))
    top, bottom = int(rows[0]), int(rows[-1])
    depth = int(depth or HEAD * (bottom - top + 1))
    runs = [widest_run(a[y]) for y in range(top, min(bottom, top + depth) + 1)]
    middles = [(s + e) / 2 for s, e in runs if e > s]
    crown = runs[: max(1, round(CROWN * len(runs)))]
    return float(np.median(middles)), float(max(e - s for s, e in crown))


def climber(image: Image.Image) -> tuple[float, int]:
    """A figure seen from behind with its hands up: the middle of its body, which it mirrors
    about, and the top of its head, the first row opaque there, between the arms."""
    a = solid(image)
    rows = np.flatnonzero(a.any(axis=1))
    top, bottom = int(rows[0]), int(rows[-1])
    tall = bottom - top + 1
    body = np.argwhere(a[top + int(0.45 * tall) : top + int(0.75 * tall)])
    middle = float(body[:, 1].mean())
    column = a[:, max(0, round(middle) - 2) : round(middle) + 3].any(axis=1)
    return middle, int(np.flatnonzero(column)[0])


def feet(image: Image.Image, depth: float | None = None, hands_up: bool = False) -> tuple:
    """Under the middle of the head, or the body with `hands_up`, on the lowest opaque row."""
    rows = np.flatnonzero(solid(image).any(axis=1))
    middle = climber(image)[0] if hands_up else head(image, depth)[0]
    return middle, float(rows[-1] + 1)


def height(image: Image.Image) -> int:
    rows = np.flatnonzero(solid(image).any(axis=1))
    return int(rows[-1] - rows[0] + 1)


def scaled(image: Image.Image, factor: float) -> Image.Image:
    size = (max(1, round(image.width * factor)), max(1, round(image.height * factor)))
    return image.resize(size, Image.Resampling.LANCZOS)


def scale(figure: Image.Image, stand: Image.Image, hands_up: bool = False) -> float:
    """How much bigger `figure` is drawn than the standing figure: its head as wide, or, seen
    from behind with its hands up, a head narrower than from the front, as tall from the top of
    its head."""
    figure, stand = trimmed(figure), trimmed(stand)
    tall = height(stand)
    if hands_up:
        return (np.flatnonzero(solid(figure).any(axis=1))[-1] + 1 - climber(figure)[1]) / tall
    depth = HEAD * tall
    return head(figure, depth)[1] / max(head(stand, depth)[1], 1)


def frames(
    figures: Mapping[str, Image.Image],
    standing: str = "stand",
    hands_up: Iterable[str] = (),
    lifted: Mapping[str, str] | None = None,
    seated: Iterable[str] = (),
    reference: Image.Image | None = None,
) -> dict[str, Frame]:
    """Every cut-out figure at `PPM`: the standing one `HEIGHT_M` tall, and each other one by
    the same factor over its `scale`, since FLUX may redraw a pose a little bigger or smaller.
    A frame `lifted` to another is in the air: its feet go below its lowest row, so its head is
    as high as the other's. A `seated` frame says where it sits."""
    stand = trimmed(figures[standing] if reference is None else reference)
    factor = HEIGHT_M * PPM / height(stand)
    depth = HEAD * height(stand)
    out = {}
    for name, figure in figures.items():
        up = name in hands_up
        fit = float(np.clip(1 / scale(figure, stand, up), *FIT))
        small = trimmed(scaled(trimmed(figure), factor * fit))
        out[name] = Frame(small, feet(small, depth * factor * fit, up))
        if name in seated:
            out[name].seat = seat(small, out[name].feet[0])
    for name, other in (lifted or {}).items():
        x, y = out[name].feet
        lift = max(0.0, crown(out[other]) - crown(out[name]))
        out[name] = Frame(out[name].image, (x, y + lift))
    return out


def seat(image: Image.Image, middle: float) -> tuple[float, float]:
    """Under the middle of the head, at the bottom of the thighs, up the calves from the heels."""
    a = solid(image)
    rows = np.flatnonzero(a.any(axis=1))
    tall = int(rows[-1] - rows[0] + 1)
    low = a[rows[-1] + 1 - max(1, round(SOLES * tall)) :]
    knee = int(np.flatnonzero(low.any(axis=0))[0])
    edge = lower_edge(a)
    while knee > 0 and climbs(edge[max(0, knee - CLIMB) : knee], edge[knee]):
        knee -= 1
    return middle, float(edge[: knee + 1].max() + 1)


def climbs(back: NDArray[np.int_], here: int) -> bool:
    found = back[back >= 0]
    return bool(found.size) and int(found.min()) < here


def lower_edge(a: NDArray[np.bool_]) -> NDArray[np.int_]:
    """Each column's lowest opaque row, or -1 where it has none."""
    lowest = a.shape[0] - 1 - np.argmax(a[::-1], axis=0)
    return np.where(a.any(axis=0), lowest, -1)


def crown(frame: Frame) -> float:
    """How high the top of the head is over the feet, in pixels."""
    return frame.feet[1] - float(np.flatnonzero(solid(frame.image).any(axis=1))[0])


def pack(images: Mapping[str, Image.Image]) -> tuple[tuple[int, int], dict[str, tuple]]:
    """Shelves, tallest first: the atlas's size and each frame's place."""
    order = sorted(images, key=lambda n: (-images[n].height, n))
    places: dict[str, tuple[int, int, int, int]] = {}
    x = y = shelf = 0
    width = max(ATLAS_WIDTH, max(i.width for i in images.values()) + PAD)
    for name in order:
        w, h = images[name].size
        if x + w + PAD > width:
            x, y, shelf = 0, y + shelf + PAD, 0
        places[name] = (x, y, w, h)
        x += w + PAD
        shelf = max(shelf, h)
    used = max(x + w for x, _, w, _ in places.values())
    return (used, y + shelf), places


def atlas(made: Mapping[str, Frame]) -> tuple[bytes, dict[str, tuple]]:
    size, places = pack({name: frame.image for name, frame in made.items()})
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    for name, (x, y, _, _) in places.items():
        out.paste(made[name].image, (x, y))
    data = io.BytesIO()
    out.save(data, "WEBP", quality=QUALITY, alpha_quality=100, method=6)
    return data.getvalue(), places


def manifest(
    made: Mapping[str, Frame],
    places: Mapping[str, tuple],
    poses: Mapping[str, list[str]],
    painted: str,
    **extra: Any,
) -> dict[str, Any]:
    return {
        **extra,
        "version": VERSION,
        "ppm": PPM,
        "height": round(HEIGHT_M * PPM, 1),
        "painted": painted,
        "frames": {
            name: {
                "frame": list(places[name]),
                "feet": [round(made[name].feet[0], 1), round(made[name].feet[1], 1)],
                **(
                    {"seat": [round(made[name].seat[0], 1), round(made[name].seat[1], 1)]}
                    if made[name].seat
                    else {}
                ),
            }
            for name in sorted(made)
        },
        "poses": {pose: list(names) for pose, names in poses.items()},
    }
