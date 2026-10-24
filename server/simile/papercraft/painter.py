"""The edit-mode painter: FLUX.2 Klein 4B through mflux, painting from a prompt and style images.

mflux and MLX are imported only when the model loads, so this module imports anywhere.
"""

import gc
import tempfile
from collections.abc import Sequence
from pathlib import Path
from types import TracebackType
from typing import Protocol, Self

from PIL import Image

from simile.works.config import DEFAULT_CONFIG

REFERENCES = Path(__file__).resolve().parents[3] / "content" / "papercraft" / "references"
STYLE = (
    "papercraft diorama made of cut coloured paper and cardboard layers, visible paper edges and "
    "fibres, soft drop shadows between layers, handmade crafty look"
)
CARTOON = (
    "hand-drawn 2D cartoon game art: thick dark brown ink outlines that are scratchy, uneven and "
    "slightly broken, as if drawn with a worn dip pen, flat colour fills with simple soft "
    "shading, a little worn and dirty with a few smudges, scuffs and stains, a slightly muted "
    "palette, chunky rounded simplified shapes, bold readable silhouettes"
)
"""#329's revised cartoon, a little dirty: the tunnels' style."""
GRIMY = (
    "hand-drawn 2D cartoon game art: thick dark brown ink outlines that are scratchy, uneven and "
    "slightly broken, as if drawn with a worn dip pen, flat colour fills with simple soft "
    "shading, heavy grime, damp stains, slime, rust streaks, smudges and scuffs on every "
    "surface, a dirty, muted palette, chunky rounded simplified shapes, bold readable silhouettes"
)
"""#329's properly grimy cartoon: the sewers' style."""
NO_TEXT = " No text, no lettering, no logos, no words on signs."
REFERENCE_WIDTH = 768


def styled(subject: str) -> str:
    """`subject` with the references' art style and the ban on lettering."""
    return f"{subject} Art style: {STYLE}.{NO_TEXT}"


def cartoon(subject: str) -> str:
    """`subject` in the tunnels' cartoon, with the ban on lettering."""
    return f"{subject} Art style: {CARTOON}.{NO_TEXT}"


def grimy(subject: str) -> str:
    """`subject` in the sewers' grimy cartoon, with the ban on lettering."""
    return f"{subject} Art style: {GRIMY}.{NO_TEXT}"


def reference(name: str, width: int = REFERENCE_WIDTH) -> Image.Image:
    """A reference picture from `references/`, scaled to `width` to keep conditioning cheap."""
    image = Image.open(REFERENCES / f"{name}.jpg").convert("RGB")
    height = round(image.height * width / image.width / 16) * 16
    return image.resize((width, height), Image.Resampling.LANCZOS)


class Painter(Protocol):
    def paint(
        self, prompt: str, size: tuple[int, int], seed: int, images: Sequence[Image.Image]
    ) -> Image.Image: ...


class EditPainter:
    """FLUX.2 Klein 4B in edit mode: each painting follows the prompt in the style of `images`,
    or redraws the first of them. Apple Silicon only, with the `images` extra. Use it as a
    context manager, which loads the model on entry and frees it on exit."""

    def __init__(
        self,
        model: str = DEFAULT_CONFIG.image_model,
        *,
        bits: int | None = DEFAULT_CONFIG.image_bits,
        steps: int = DEFAULT_CONFIG.image_steps,
    ) -> None:
        self.model = model
        self.bits = bits
        self.steps = steps
        self._flux = None

    def __enter__(self) -> Self:
        from mflux.models.flux2.variants import Flux2KleinEdit

        from simile.works.flux import download, downloaded

        path = downloaded(self.model) or download(self.model)
        self._flux = Flux2KleinEdit(quantize=self.bits, model_path=str(path))
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

    def paint(
        self, prompt: str, size: tuple[int, int], seed: int, images: Sequence[Image.Image]
    ) -> Image.Image:
        """A `size` painting, at least 256 px across and in multiples of 16 as FLUX needs, scaled
        to `size` exactly."""
        if not images:
            raise ValueError("edit mode paints from at least one image")
        if self._flux is None:
            raise RuntimeError("load the painter with `with EditPainter() as painter:` first")
        import mlx.core as mx

        from simile.works.flux import size as paint_size

        across, up = paint_size(*size)
        with tempfile.TemporaryDirectory() as folder:
            paths = []
            for i, image in enumerate(images):
                paths.append(Path(folder) / f"{i}.png")
                image.convert("RGB").save(paths[-1])
            try:
                picture = self._flux.generate_image(
                    seed=seed,
                    prompt=prompt,
                    num_inference_steps=self.steps,
                    width=across,
                    height=up,
                    image_paths=paths,
                ).image
            finally:
                mx.clear_cache()
        picture = picture.convert("RGB")
        if picture.size != size:
            picture = picture.resize(size, Image.Resampling.LANCZOS)
        return picture
