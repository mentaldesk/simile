"""Depth keys: sprites in diagonal slices, keyed by the far end of the footprint's front edge."""

import math

from simile.art.iso.camera import TILE_H, TILE_W

SLICE_PX = TILE_W // 2


def front(footprint: tuple[float, float, float, float], diagonal: float) -> float:
    """Screen y of the footprint's nearest point on the line x − y = diagonal (clamped to it)."""
    x0, y0, x1, y1 = footprint
    d = min(max(diagonal, x0 - y1), x1 - y0)
    return min(2 * x1 - d, 2 * y1 + d) * TILE_H / 2


def slices(
    footprint: tuple[float, float, float, float], left: int, width: int
) -> list[dict[str, float]]:
    """A sprite's slices: x and width within the sprite, and the depth key of each."""
    out: list[dict[str, float]] = []
    first, last = math.floor(left / SLICE_PX), math.ceil((left + width) / SLICE_PX)
    for c in range(first, last):
        x0 = max(c * SLICE_PX, left) - left
        x1 = min((c + 1) * SLICE_PX, left + width) - left
        depth = round(min(front(footprint, c), front(footprint, c + 1)), 1)
        if out and out[-1]["depth"] == depth:
            out[-1]["width"] += x1 - x0
        else:
            out.append({"x": x0, "width": x1 - x0, "depth": depth})
    return out
