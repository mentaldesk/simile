import numpy as np
from PIL import Image

from simile.dolls.flux import FakePainter


def keyed(painting: Image.Image) -> Image.Image:
    """The fake painter's figure off its plain background, without IS-Net or OpenCV."""
    rgb = np.asarray(painting.convert("RGB"), dtype=np.int16)
    away = np.abs(rgb - np.array(FakePainter.BACKGROUND)).max(axis=2) > 12
    alpha = (away * 255).astype(np.uint8)
    return Image.fromarray(np.dstack([rgb.astype(np.uint8), alpha]), "RGBA")
