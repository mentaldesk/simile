"""Shared paths, prompts and the FLUX.2 Klein 4B painter for the side-view study."""

import gc
import json
import os
import sys
import time
from pathlib import Path

from PIL import Image

STUDY = Path(__file__).resolve().parent
OUT = STUDY / "out"
RAW = OUT / "raw"
REFS = STUDY / "references"
IMAGES = STUDY / "images"
SERVER = STUDY.parents[1] / "server"
sys.path.insert(0, str(STUDY))

from references.gen import NO_TEXT, STYLE  # noqa: E402

os.environ.setdefault("HF_HUB_OFFLINE", "1")


def styled(subject: str) -> str:
    return f"{subject} Art style: {STYLE}.{NO_TEXT}"


def residents() -> dict:
    """The eleven residents from content/npcs, read only."""
    sys.path.insert(0, str(SERVER))
    from simile.npc.content import NPCS_DIR, load_npcs

    return {npc.id: npc for npc in load_npcs(NPCS_DIR)}


def player_appearance():
    from simile.art.characters import PLAYER

    return PLAYER


def small_reference(name: str, width: int = 768) -> Path:
    """A reference picture scaled to `width`, so conditioning on it stays cheap."""
    out = OUT / "refs" / f"{name}-{width}.png"
    if not out.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
        image = Image.open(REFS / f"{name}.jpg").convert("RGB")
        height = round(image.height * width / image.width / 16) * 16
        image.resize((width, height), Image.Resampling.LANCZOS).save(out)
    return out


class Painter:
    """FLUX.2 Klein 4B through mflux, loaded once per mode: plain (text and img2img) or edit
    (reference images). Paintings are cached in out/raw and timed in out/timings.jsonl."""

    def __init__(self, bits: int | None = None) -> None:
        self.bits = bits
        self.mode: str | None = None
        self.model = None

    def _load(self, mode: str) -> None:
        if self.mode == mode:
            return
        self.unload()
        import mlx.core as mx
        from mflux.models.common.config import ModelConfig
        from mflux.models.flux2.variants import Flux2Klein, Flux2KleinEdit

        start = time.time()
        kind = Flux2KleinEdit if mode == "edit" else Flux2Klein
        self.model = kind(model_config=ModelConfig.flux2_klein_4b(), quantize=self.bits)
        mx.eval(self.model.parameters())
        self.mode = mode
        from mlx.utils import tree_flatten

        size = sum(v.nbytes for _, v in tree_flatten(self.model.parameters()))
        log(
            {
                "event": "load",
                "mode": mode,
                "bits": self.bits,
                "seconds": time.time() - start,
                "bytes": size,
            }
        )

    def unload(self) -> None:
        if self.model is None:
            return
        import mlx.core as mx

        self.model = None
        self.mode = None
        gc.collect()
        mx.clear_cache()

    def paint(
        self,
        name: str,
        prompt: str,
        size: tuple[int, int],
        seed: int = 42,
        refs: list[Path] | None = None,
        init: Path | None = None,
        strength: float | None = None,
        steps: int = 4,
    ) -> Image.Image:
        path = RAW / f"{name}.png"
        if path.exists():
            return Image.open(path).convert("RGB")
        path.parent.mkdir(parents=True, exist_ok=True)
        self._load("edit" if refs else "plain")
        start = time.time()
        args = {"seed": seed, "prompt": prompt, "num_inference_steps": steps}
        args |= {"width": size[0], "height": size[1]}
        if refs:
            image = self.model.generate_image(**args, image_paths=[str(r) for r in refs])
        elif init:
            image = self.model.generate_image(**args, image_path=str(init), image_strength=strength)
        else:
            image = self.model.generate_image(**args)
        image.image.save(path)
        seconds = time.time() - start
        log(
            {
                "event": "paint",
                "name": name,
                "mode": self.mode,
                "bits": self.bits,
                "size": list(size),
                "steps": steps,
                "refs": len(refs or []),
                "img2img": init is not None,
                "seconds": round(seconds, 2),
                "prompt": prompt,
            }
        )
        print(f"{name} {seconds:.1f}s", flush=True)
        return image.image.convert("RGB")


def log(entry: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "timings.jsonl").open("a") as f:
        f.write(json.dumps(entry) + "\n")
