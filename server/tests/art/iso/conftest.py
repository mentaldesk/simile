import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from PIL import Image

from simile.art.iso.scenery import CONTENT_DIR

VILLAGE = CONTENT_DIR / "map" / "village.tmj"
WINDOW = (36, 2, 52, 17)


def crop_map(source: Path, target: Path, window: tuple[int, int, int, int] = WINDOW) -> None:
    """The village cut down to two buildings, trees on grass, a lamp and a few small props."""
    data = json.loads(source.read_text())
    x0, y0, x1, y1 = window
    width = data["width"]
    for layer in data["layers"]:
        if layer["type"] == "tilelayer":
            rows = [layer["data"][y * width : (y + 1) * width][x0:x1] for y in range(y0, y1)]
            layer["data"] = [g for row in rows for g in row]
            layer["width"], layer["height"] = x1 - x0, y1 - y0
    data["layers"] = [layer for layer in data["layers"] if layer["type"] == "tilelayer"]
    data["width"], data["height"] = x1 - x0, y1 - y0
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data))


@pytest.fixture
def content(tmp_path: Path) -> Path:
    crop_map(VILLAGE, tmp_path / "content" / "map" / "village.tmj")
    return tmp_path / "content"


class FakeBlender:
    """Writes renders shaped like Blender's, instantly, and remembers what it was asked for."""

    def __init__(self) -> None:
        self.jobs: list[dict[str, Any]] = []

    def __call__(self, job: dict[str, Any], work: Path) -> dict[str, Any]:
        self.jobs.append(job)
        work.mkdir(parents=True, exist_ok=True)
        sprites = {}
        for task in job["sprites"]:
            (work / "sprites").mkdir(exist_ok=True)
            image = Image.new("RGBA", (24, 40), (0, 0, 0, 0))
            image.paste((200, 120, 60, 255), (4, 2, 20, 38))
            image.save(work / "sprites" / f"{task['key']}.png")
            sprites[task["key"]] = {"rect": [-12, -36, 24, 40], "seconds": 0.0}
        if task := job.get("ground"):
            _, _, w, h = task["rect"]
            Image.new("RGBA", (w, h), (90, 100, 110, 255)).save(work / "ground.png")
            Image.new("RGBA", (w, h), (150, 160, 170, 255)).save(work / "ground_open.png")
        if task := job.get("lightmap"):
            px, town = task["px_per_tile"], job["town"]
            shape = (town["height"] * px, town["width"] * px, 3)
            sun = np.full(shape, 0.8, np.float32)
            sun[: shape[0] // 2, : shape[1] // 3] = 0.0
            np.save(work / "light_sun.npy", sun)
            np.save(work / "light_sunsky.npy", sun + 0.2)
            np.save(work / "light_lights.npy", np.zeros(shape, np.float32))
        return {"seconds": {"total": 0.0}, "sprites": sprites}

    def rendered(self) -> set[str]:
        out = set()
        for job in self.jobs:
            out |= {t["key"] for t in job["sprites"]}
            out |= {f"{job['light']['name']}:ground"} if job.get("ground") else set()
        return out


@pytest.fixture
def fake_blender() -> FakeBlender:
    return FakeBlender()


@pytest.fixture
def add_room(content: Path) -> Callable[[str], Path]:
    """Copy one of the repo's interiors into the test content."""

    def add(name: str) -> Path:
        target = content / "map" / "interiors" / f"{name}.tmj"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text((CONTENT_DIR / "map" / "interiors" / f"{name}.tmj").read_text())
        return target

    return add
