"""Paths, the two styles, the period, and FLUX.2 Klein 4B in text mode for the references."""

import gc
import json
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Self

from PIL import Image

STUDY = Path(__file__).resolve().parent
OUT = STUDY / "out"
REFS = STUDY / "references"
IMAGES = STUDY / "images"
os.environ.setdefault("HF_HUB_OFFLINE", "1")

NO_TEXT = " No text, no lettering, no logos, no words on signs."


@dataclass(frozen=True)
class Style:
    name: str
    look: str
    """The art style, as `styled()` appends it."""
    made: str
    """How a thing is made in this style, for the leads and redraws."""
    finish: str
    """The surface every redraw asks for."""
    whole: str
    """How everything in a reference scene is made, so nothing in it comes out realistic."""


PAPERCRAFT = Style(
    "papercraft",
    "papercraft diorama made of cut coloured paper and cardboard layers, visible paper edges and "
    "fibres, soft drop shadows between layers, handmade crafty look",
    "made of cut paper and card in the papercraft style",
    "matt paper with visible fibres and cut edges",
    "Everything in the picture, the buildings, the glass towers, the trees, the vehicles and the "
    "people, is cut from coloured paper and card.",
)
CARTOON = Style(
    "cartoon",
    "hand-drawn 2D cartoon game art: very thick bold dark brown outlines around every shape, "
    "flat colour fills with simple soft shading, chunky rounded simplified shapes with slightly "
    "wobbly hand-drawn lines, bold readable silhouettes, slightly exaggerated cartoon "
    "proportions, a faint painted grain",
    "hand-drawn in the cartoon style",
    "very thick dark outlines around every shape and flat colours with simple soft shading",
    "Everything in the picture, the buildings, the glass towers, the trees, the vehicles and the "
    "people, is drawn as a simple chunky cartoon with very thick dark outlines, and the people "
    "have big round heads and short sturdy bodies.",
)
STYLES = {s.name: s for s in (PAPERCRAFT, CARTOON)}

PERIOD = (
    "a near-future neighbourhood of a southern Chinese tech city like Shenzhen, today: low-rise "
    "three-storey shop buildings with big glass shopfronts, glowing LED light panels and neon "
    "tubes that show only simple pictograms, air-conditioning units and balconies full of "
    "plants, slim glass skyscrapers rising behind, electric scooters and e-bikes, a small "
    "delivery drone in the sky, banyan trees and lush greenery everywhere"
)
CLOTHES = "contemporary casual clothes: t-shirts, hoodies, light jackets, jeans and sneakers"


def styled(subject: str, style: Style) -> str:
    """`subject` in `style`, with the ban on lettering, as #309's `styled()` does."""
    return f"{subject} Art style: {style.look}.{NO_TEXT}"


def reference(style: Style, name: str) -> Path:
    return REFS / style.name / f"{name}.jpg"


def busy() -> list[str]:
    """Other image or language models running on this Mac: mflux, a simile build, or Ollama."""
    found = []
    for pattern in ("mflux", "simile (papercraft|dolls)"):
        run = subprocess.run(["pgrep", "-fl", pattern], capture_output=True, text=True)
        found += [line for line in run.stdout.splitlines() if str(os.getpid()) not in line]
    try:
        ollama = subprocess.run(["ollama", "ps"], capture_output=True, text=True).stdout
        found += [f"ollama: {line}" for line in ollama.splitlines()[1:] if line.strip()]
    except FileNotFoundError:
        pass
    return found


def wait_for_gpu() -> None:
    """Waits until nothing else is using the model memory, checked before every load."""
    while others := busy():
        print(f"Waiting for {others}", flush=True)
        time.sleep(60)


def log(entry: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "timings.jsonl").open("a") as f:
        f.write(json.dumps({"at": round(time.time()), **entry}) + "\n")


class TextPainter:
    """FLUX.2 Klein 4B from a prompt alone, at #309's 8 bits. Loads on entry, frees on exit."""

    def __init__(self, bits: int | None = 8) -> None:
        self.bits = bits
        self._flux = None

    def __enter__(self) -> Self:
        from mflux.models.flux2.variants import Flux2Klein

        from simile.works.config import DEFAULT_CONFIG
        from simile.works.flux import downloaded

        wait_for_gpu()
        start = time.perf_counter()
        path = downloaded(DEFAULT_CONFIG.image_model)
        self._flux = Flux2Klein(quantize=self.bits, model_path=str(path))
        log({"event": "load", "mode": "text", "seconds": round(time.perf_counter() - start, 1)})
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

    def paint(self, prompt: str, size: tuple[int, int], seed: int) -> Image.Image:
        import mlx.core as mx

        try:
            return self._flux.generate_image(
                seed=seed, prompt=prompt, num_inference_steps=4, width=size[0], height=size[1]
            ).image.convert("RGB")
        finally:
            mx.clear_cache()
