import math
from collections.abc import Callable
from pathlib import Path
from typing import Any

import mlx.core as mx
from huggingface_hub import snapshot_download
from huggingface_hub.errors import LocalEntryNotFoundError
from mflux.models.common.resolution.model_revisions import ModelRevisions
from mflux.models.flux2 import Flux2Klein
from mflux.models.flux2.weights.flux2_weight_definition import Flux2KleinWeightDefinition
from PIL import Image

LEAST_SIDE = 256
"""FLUX paints poorly much below this, so smaller pictures are painted bigger and scaled down."""


def downloaded(model: str) -> Path | None:
    """`model`'s weights on disk: a directory, or a Hugging Face repo's snapshot in the local
    cache at the revision mflux pins. None if they aren't all there."""
    if (path := Path(model).expanduser()).is_dir():
        return path
    try:
        return Path(
            snapshot_download(
                model,
                revision=ModelRevisions.get(model),
                allow_patterns=Flux2KleinWeightDefinition.get_download_patterns(),
                local_files_only=True,
            )
        )
    except LocalEntryNotFoundError:
        return None


def download(model: str) -> Path:
    """`model` from its Hugging Face repo, at the revision mflux pins, into the local cache."""
    return Path(
        snapshot_download(
            model,
            revision=ModelRevisions.get(model),
            allow_patterns=Flux2KleinWeightDefinition.get_download_patterns(),
        )
    )


def size(width: int, height: int) -> tuple[int, int]:
    """The size to paint a `width` × `height` picture at: multiples of 16, at least
    `LEAST_SIDE` across its shorter side."""
    scale = max(1.0, LEAST_SIDE / min(width, height))
    return math.ceil(width * scale / 16) * 16, math.ceil(height * scale / 16) * 16


class FluxKlein:
    """FLUX.2 [klein] 4B through mflux, on MLX, so Apple Silicon only. Distilled to paint in 4
    steps. `bits` quantizes its weights as it loads."""

    def __init__(self, path: Path, *, bits: int | None, steps: int) -> None:
        self.path = path
        self.bits = bits
        self.steps = steps
        self._step: Callable[[], None] = lambda: None

    def load(self) -> None:
        self._model = Flux2Klein(quantize=self.bits, model_path=str(self.path))
        self._model.callbacks.register(self)

    def paint(
        self, prompt: str, width: int, height: int, seed: int, step: Callable[[], None]
    ) -> Image.Image:
        self._step = step
        step()
        across, up = size(width, height)
        try:
            return self._model.generate_image(
                seed=seed,
                prompt=prompt,
                num_inference_steps=self.steps,
                width=across,
                height=up,
            ).image
        finally:
            self._step = lambda: None
            mx.clear_cache()

    def call_in_loop(self, *args: Any, **kwargs: Any) -> None:
        self._step()
