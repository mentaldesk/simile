"""How iso renders are stored. Each kind of asset has one format setting, here."""

import io
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from PIL import Image


@dataclass(frozen=True)
class Format:
    name: str
    ext: str
    options: tuple[tuple[str, Any], ...]

    def encode(self, image: Image.Image) -> bytes:
        buffer = io.BytesIO()
        image.save(buffer, format="PNG" if self.ext == "png" else "WEBP", **dict(self.options))
        return buffer.getvalue()


LOSSY_WEBP = Format("lossy-webp", "webp", (("quality", 82), ("method", 6), ("alpha_quality", 100)))
LOSSLESS_WEBP = Format(
    "lossless-webp", "webp", (("lossless", True), ("quality", 100), ("method", 6))
)
PNG = Format("png", "png", (("optimize", True),))
FORMATS = (LOSSY_WEBP, PNG, LOSSLESS_WEBP)

GROUND = LOSSY_WEBP
SPRITES = LOSSLESS_WEBP
LIGHT_MAP = LOSSLESS_WEBP
CHARACTERS = LOSSLESS_WEBP


def sizes(images: Iterable[Image.Image], formats: Iterable[Format] = FORMATS) -> dict[str, int]:
    """Total bytes of these images in each format, to choose a format by measurement."""
    images, totals = list(images), {}
    for f in formats:
        totals[f.name] = sum(len(f.encode(im)) for im in images)
    return totals
