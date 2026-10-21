"""The one texture FLUX paints for approach 3: grime for the 3D models' clothes, so they wear the
same smudges as #329's scenery.

`python textures.py` paints out/model/grime.png if it's missing.
"""

import numpy as np
from PIL import Image
from study import NO_TEXT, OUT, Painter

PATH = OUT / "model" / "grime.png"
PROMPT = (
    "A flat square texture for a 2D cartoon game, seen straight on: light smudges, scuffs, small "
    "stains, faint dirt specks and dry-brush grime marks scattered unevenly on plain off-white, "
    "in a scratchy, grimy hand-drawn cartoon style with a slightly dirty, muted palette. No "
    "objects, no shapes, no shadows, no border." + NO_TEXT
)


def paint() -> None:
    if PATH.exists():
        return
    with Painter("model", edit=False) as painter:
        image = painter.paint("grime", PROMPT, (1024, 1024), 1)
    PATH.parent.mkdir(parents=True, exist_ok=True)
    image.save(PATH.with_name("grime-raw.png"))
    grey = np.asarray(image.convert("L"), np.float32)
    level = grey / np.percentile(grey, 90)
    Image.fromarray((np.clip(level, 0, 1) * 255).astype(np.uint8)).save(PATH)


if __name__ == "__main__":
    paint()
