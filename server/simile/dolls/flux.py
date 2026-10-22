"""The painter the figures are painted with: FLUX.2 Klein 4B through mflux at 8 bits, from text
alone or, given pictures, in edit mode. Never imports MLX until it loads."""

import gc
import tempfile
from collections.abc import Callable, Sequence
from importlib.util import find_spec
from pathlib import Path
from typing import Protocol, Self

from PIL import Image

from simile.dolls.paint import NoPainter


class Painter(Protocol):
    """Paints `prompt` at `size`, redrawing `images[0]` if there are any."""

    def paint(
        self, prompt: str, size: tuple[int, int], seed: int, images: Sequence[Image.Image] = ()
    ) -> Image.Image: ...


class Flux:
    """Loads the text model or the edit model as each painting needs it, never both, and frees
    it on leaving. `before_load` runs before each load, to wait for the GPU."""

    def __init__(self, before_load: Callable[[], None] = lambda: None) -> None:
        if find_spec("mflux") is None:
            raise NoPainter(
                "Painting dolls needs FLUX: on Apple Silicon, `uv sync --extra images`."
            )
        self.before_load = before_load
        self._model = None
        self._edit: bool | None = None

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._free()

    def _free(self) -> None:
        import mlx.core as mx

        self._model, self._edit = None, None
        gc.collect()
        mx.clear_cache()

    def _load(self, edit: bool) -> None:
        if self._edit == edit:
            return
        if self._model is not None:
            self._free()
        from mflux.models.flux2.variants import Flux2Klein, Flux2KleinEdit

        from simile.works.config import DEFAULT_CONFIG
        from simile.works.flux import download, downloaded

        self.before_load()
        model = DEFAULT_CONFIG.image_model
        path = downloaded(model) or download(model)
        kind = Flux2KleinEdit if edit else Flux2Klein
        self._model = kind(quantize=DEFAULT_CONFIG.image_bits, model_path=str(path))
        self._edit = edit

    def paint(
        self, prompt: str, size: tuple[int, int], seed: int, images: Sequence[Image.Image] = ()
    ) -> Image.Image:
        import mlx.core as mx

        from simile.works.config import DEFAULT_CONFIG
        from simile.works.flux import size as paint_size

        self._load(bool(images))
        across, up = paint_size(*size)
        with tempfile.TemporaryDirectory() as folder:
            paths = []
            for i, image in enumerate(images):
                paths.append(Path(folder) / f"{i}.png")
                image.convert("RGB").save(paths[-1])
            extra = {"image_paths": paths} if images else {}
            try:
                picture = self._model.generate_image(
                    seed=seed,
                    prompt=prompt,
                    num_inference_steps=DEFAULT_CONFIG.image_steps,
                    width=across,
                    height=up,
                    **extra,
                ).image.convert("RGB")
            finally:
                mx.clear_cache()
        if picture.size != size:
            picture = picture.resize(size, Image.Resampling.LANCZOS)
        return picture


class FakePainter:
    """Draws a figure in the colours the prompt names, without a model: for tests and dry runs.
    An edit redraws `images[0]` a little darker."""

    BACKGROUND = (214, 214, 216)

    def __init__(self) -> None:
        self.calls: list[tuple[str, int, int]] = []

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> None:
        pass

    def paint(
        self, prompt: str, size: tuple[int, int], seed: int, images: Sequence[Image.Image] = ()
    ) -> Image.Image:
        import numpy as np

        self.calls.append((prompt, seed, len(images)))
        if images:
            base = np.asarray(images[0].convert("RGB").resize(size), dtype=np.float64)
            return Image.fromarray(np.clip(base * 0.98, 0, 255).astype(np.uint8))
        return figure(size, named_colours(prompt))


def named_colours(prompt: str) -> dict[str, str]:
    """The colours `words.described` names in `prompt`, as hex."""
    import re

    from simile.characters.palette import PALETTE
    from simile.dolls.words import COLOURS, HAIR, SKIN

    def hex_of(word: str, names: dict[str, str]) -> str:
        keys = [k for k, name in names.items() if name == word]
        keys = keys or [k for k, name in COLOURS.items() if name == word]
        return PALETTE[keys[0]] if keys else "#808080"

    found = dict.fromkeys(("skin", "hair", "top", "bottom", "shoe"), "#808080")
    if match := re.search(r"has (.+?) skin", prompt):
        found["skin"] = hex_of(match[1], SKIN)
    for word in sorted(set(HAIR.values()) | set(COLOURS.values()), key=len, reverse=True):
        if f"{word} hair" in prompt:
            found["hair"] = hex_of(word, HAIR)
            break
    clothes = r", in an? ([^,]+?) t-shirt, ([^,]+?) trousers and ([^,.]+?) sneakers"
    if match := re.search(clothes, prompt):
        for name, word in zip(("top", "bottom", "shoe"), match.groups(), strict=True):
            found[name] = hex_of(word, COLOURS)
    return found


def figure(size: tuple[int, int], colours: dict[str, str]) -> Image.Image:
    """A rough upright figure, its head about a third of its height."""
    from PIL import ImageDraw

    w, h = size
    out = Image.new("RGB", size, FakePainter.BACKGROUND)
    draw = ImageDraw.Draw(out)
    ink = (40, 26, 20)
    top, tall = 0.08 * h, 0.84 * h
    x = w / 2

    def box(left: float, upper: float, right: float, lower: float) -> tuple[float, ...]:
        return (x + left * tall, top + upper * tall, x + right * tall, top + lower * tall)

    for side in (-1, 1):
        legs = sorted((side * 0.01, side * 0.1))
        draw.rectangle(box(legs[0], 0.6, legs[1], 0.95), colours["bottom"], ink, 4)
        shoes = sorted((side * 0.0, side * 0.13))
        draw.rectangle(box(shoes[0], 0.93, shoes[1], 1.0), colours["shoe"], ink, 4)
    draw.rounded_rectangle(box(-0.14, 0.36, 0.14, 0.66), 12, colours["top"], ink, 4)
    draw.ellipse(box(-0.17, 0.02, 0.17, 0.36), colours["skin"], ink, 4)
    draw.chord(box(-0.17, 0.0, 0.17, 0.3), 180, 360, colours["hair"], ink, 4)
    return out
