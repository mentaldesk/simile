"""FLUX.2 [klein] 4B in edit mode through mflux, on Apple Silicon with the `images` extra."""

import gc
import time
from pathlib import Path
from types import TracebackType
from typing import Self

from PIL import Image

MODEL = "black-forest-labs/FLUX.2-klein-4B"
BITS = 8
STEPS = 4


class FluxEdit:
    """Loads once on entering and unloads on leaving. Never downloads."""

    def __init__(self, model: str = MODEL, bits: int | None = BITS, steps: int = STEPS) -> None:
        self.model_name = model
        self.bits = bits
        self.steps = steps
        self.seconds: list[float] = []

    def __enter__(self) -> Self:
        from mflux.models.flux2.variants import Flux2KleinEdit

        from simile.works.flux import downloaded

        path = downloaded(self.model_name)
        if path is None:
            raise RuntimeError(
                f"{self.model_name} isn't downloaded. Run `uv run simile works download`."
            )
        start = time.perf_counter()
        self._model = Flux2KleinEdit(quantize=self.bits, model_path=str(path))
        self.load_seconds = time.perf_counter() - start
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        import mlx.core as mx

        del self._model
        gc.collect()
        mx.clear_cache()

    def paint(
        self, prompt: str, images: list[Path], size: tuple[int, int], seed: int
    ) -> Image.Image:
        import mlx.core as mx

        start = time.perf_counter()
        try:
            return self._model.generate_image(
                seed=seed,
                prompt=prompt,
                num_inference_steps=self.steps,
                width=size[0],
                height=size[1],
                image_paths=[str(path) for path in images],
            ).image.convert("RGB")
        finally:
            self.seconds.append(time.perf_counter() - start)
            mx.clear_cache()
