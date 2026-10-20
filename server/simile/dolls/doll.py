"""A doll as the client loads it: its pieces packed into a flat and a painted atlas that share one
frame table, and a manifest of frames, pivots and joints. `content/dolls/README.md` documents it."""

import base64
import io
from dataclasses import dataclass
from typing import Any

import numpy as np
from PIL import Image, ImageFilter

from simile.dolls.look import Look
from simile.dolls.pieces import Piece, flat_pieces
from simile.dolls.shapes import PIECES, STANDING_HEIGHT

UNIT = 5.0
"""Atlas pixels a unit, so a standing doll is about 500 px: twice its size on the street."""
VERSION = 2
PAD = 2
ATLAS_WIDTH = 512
RIM = 0.3
"""How far the cut edge of each piece is lightened towards the card's core."""
CARD = (246, 240, 228)
QUALITY = 88


@dataclass
class Doll:
    flat: dict[str, Piece]
    painted: dict[str, Piece] | None = None


def flat_doll(look: Look) -> Doll:
    return Doll({name: rimmed(piece) for name, piece in flat_pieces(look, UNIT).items()})


def aligned(painted: Image.Image, sheet_piece: Piece, sheet_scale: float, flat: Piece) -> Piece:
    """A painted sheet piece scaled to the atlas and laid exactly over `flat`, with its outline."""
    factor = UNIT / sheet_scale
    w, h = painted.size
    small = painted.resize((max(1, round(w * factor)), max(1, round(h * factor))), Image.LANCZOS)
    fx, fy = small.width / w, small.height / h
    dx = sheet_piece.pivot[0] * fx - flat.pivot[0]
    dy = sheet_piece.pivot[1] * fy - flat.pivot[1]
    rgb = small.transform(
        flat.image.size, Image.Transform.AFFINE, (1, 0, dx, 0, 1, dy), Image.Resampling.BICUBIC
    )
    rgb.putalpha(flat.image.getchannel("A"))
    return rimmed(Piece(rgb, flat.pivot, flat.joints))


def rimmed(piece: Piece) -> Piece:
    """The piece with its cut edge catching the light, as card does."""
    a = np.asarray(piece.image, dtype=np.float64)
    alpha = piece.image.getchannel("A")
    inner = np.asarray(alpha.filter(ImageFilter.MinFilter(3)), dtype=np.float64) / 255
    edge = np.clip(a[..., 3] / 255 - inner, 0, 1)[..., None]
    a[..., :3] += (np.array(CARD) - a[..., :3]) * edge * RIM
    return Piece(
        Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGBA"), piece.pivot, piece.joints
    )


def pack(pieces: dict[str, Piece]) -> tuple[tuple[int, int], dict[str, tuple[int, int, int, int]]]:
    """Shelves, tallest first: the atlas's size and each piece's frame."""
    order = sorted(PIECES, key=lambda n: (-pieces[n].image.height, n))
    frames: dict[str, tuple[int, int, int, int]] = {}
    x = y = shelf = 0
    width = max(ATLAS_WIDTH, max(p.image.width for p in pieces.values()) + PAD)
    for name in order:
        w, h = pieces[name].image.size
        if x + w + PAD > width:
            x, y, shelf = 0, y + shelf + PAD, 0
        frames[name] = (x, y, w, h)
        x += w + PAD
        shelf = max(shelf, h)
    return (width, y + shelf), frames


def atlas(pieces: dict[str, Piece], size: tuple[int, int], frames: dict) -> Image.Image:
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    for name, (x, y, _, _) in frames.items():
        out.paste(pieces[name].image, (x, y))
    return out


def webp(image: Image.Image, lossless: bool, quick: bool = False) -> bytes:
    """`quick` trades a quarter more bytes for a twentieth of the time, for a preview."""
    data = io.BytesIO()
    if lossless:
        effort = {"quality": 50, "method": 4} if quick else {"quality": 100, "method": 6}
        image.save(data, "WEBP", lossless=True, exact=False, **effort)
    else:
        image.save(data, "WEBP", quality=QUALITY, alpha_quality=90, method=6)
    return data.getvalue()


def manifest(
    doll: Doll, frames: dict[str, tuple[int, int, int, int]], images: dict[str, str], **extra: Any
) -> dict[str, Any]:
    def point(p: tuple[float, float]) -> list[float]:
        return [round(p[0], 2), round(p[1], 2)]

    return {
        **extra,
        "version": VERSION,
        "unit": UNIT,
        "height": round(STANDING_HEIGHT, 2),
        **images,
        "pieces": {
            name: {
                "frame": list(frames[name]),
                "pivot": point(doll.flat[name].pivot),
                "joints": {k: point(v) for k, v in doll.flat[name].joints.items()},
            }
            for name in PIECES
        },
    }


def flat_manifest(look: Look) -> dict[str, Any]:
    """A flat doll with its atlas inline, for the creator to show at once."""
    doll = flat_doll(look)
    size, frames = pack(doll.flat)
    data = base64.b64encode(webp(atlas(doll.flat, size, frames), True, quick=True)).decode()
    return manifest(doll, frames, {"flat": f"data:image/webp;base64,{data}"})
