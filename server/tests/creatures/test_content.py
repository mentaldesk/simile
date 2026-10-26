import json
from functools import cache

import numpy as np
import pytest
from PIL import Image

from simile.creatures.build import CONTENT, PPM, components, fingerprint
from simile.creatures.catalogue import CREATURES

BUDGET = 2 * 1024 * 1024
APART = 0.06
"""The share of a frame that may be in pieces apart from its body, after the lossy WebP."""


def manifest(name: str) -> dict:
    return json.loads((CONTENT / f"{name}.json").read_text())


@cache
def atlas(name: str) -> Image.Image:
    return Image.open(CONTENT / manifest(name)["painted"]).convert("RGBA")


def frame(name: str, which: str) -> Image.Image:
    x, y, w, h = manifest(name)["frames"][which]["frame"]
    return atlas(name).crop((x, y, x + w, y + h))


def test_content_creatures_stay_within_budget() -> None:
    assert sum(path.stat().st_size for path in CONTENT.rglob("*") if path.is_file()) < BUDGET


def test_only_the_catalogues_creatures_are_there() -> None:
    found = {path.stem for path in CONTENT.glob("*.json")}

    assert found == set(CREATURES)


@pytest.mark.parametrize("name", CREATURES)
def test_every_creature_is_painted_from_its_catalogue_entry(name: str) -> None:
    creature = CREATURES[name]
    found = manifest(name)

    assert found["hash"] == fingerprint(creature), "run `uv run simile creatures paint`"
    assert found["id"] == name
    assert found["ppm"] == PPM
    assert found["moves"] == creature.moves
    assert set(found["frames"]) == set(creature.frames)
    assert found["poses"] == creature.poses


@pytest.mark.parametrize("name", CREATURES)
def test_every_frame_is_in_the_atlas_and_whole(name: str) -> None:
    width, height = atlas(name).size
    for which, entry in manifest(name)["frames"].items():
        x, y, w, h = entry["frame"]
        assert x + w <= width and y + h <= height, which
        solid = np.asarray(frame(name, which).getchannel("A")) >= 128
        _, sizes = components(solid)
        assert 1 - sizes.max() / sizes.sum() <= APART, which


@pytest.mark.parametrize("name", CREATURES)
def test_the_first_frame_is_as_long_as_the_catalogue_says(name: str) -> None:
    creature = CREATURES[name]
    first = frame(name, creature.first)
    solid = np.asarray(first.getchannel("A")) >= 128
    cols = np.flatnonzero(solid.any(axis=0))

    assert (cols[-1] - cols[0] + 1) / PPM == pytest.approx(creature.length, abs=0.03)
    assert manifest(name)["size"][0] == pytest.approx(creature.length, abs=0.1)


@pytest.mark.parametrize("name", CREATURES)
def test_a_walker_stands_on_its_anchor(name: str) -> None:
    creature = CREATURES[name]
    if creature.moves != "walk":
        pytest.skip("flies")
    entry = manifest(name)["frames"][creature.first]
    solid = np.asarray(frame(name, creature.first).getchannel("A")) >= 128
    bottom = np.flatnonzero(solid.any(axis=1))[-1] + 1

    assert entry["anchor"][1] == pytest.approx(bottom, abs=2)


def test_the_preview_sheet_and_cycles_are_there() -> None:
    for name in ("preview.webp", "cycles.webp"):
        with Image.open(CONTENT / name) as image:
            assert image.width > 0
