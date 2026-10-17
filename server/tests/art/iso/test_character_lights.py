import json
import math

import pytest

from simile.art.iso import camera
from simile.art.iso.lighting import SETS, shadow_direction
from simile.art.iso.scenery import CONTENT_DIR

CHARACTERS = CONTENT_DIR / "art" / "iso" / "characters"
LIGHTS = json.loads((CHARACTERS / "lights.json").read_text())


def test_only_the_light_constants_are_left() -> None:
    assert [p.name for p in CHARACTERS.iterdir() if not p.name.startswith(".")] == ["lights.json"]


def test_there_are_constants_for_every_lighting_set() -> None:
    assert list(LIGHTS["sets"]) == list(SETS)


@pytest.mark.parametrize("name", list(SETS))
def test_the_shadow_follows_the_sets_sun(name: str) -> None:
    light, s = SETS[name], LIGHTS["sets"][name]
    dx, dy = shadow_direction(light.azimuth)
    length = LIGHTS["figure_m"] / math.tan(math.radians(light.elevation)) / camera.TILE_M

    assert s["sun"] == {"azimuth": light.azimuth, "elevation": light.elevation}
    assert s["shadow"]["direction"] == pytest.approx([dx, dy], abs=1e-4)
    assert s["shadow"]["length"] == pytest.approx(length, abs=1e-3)
    assert s["shadow"]["tip"] == pytest.approx(camera.project(dx * length, dy * length), abs=0.1)


@pytest.mark.parametrize("name", list(SETS))
def test_the_measured_tint_and_strength_are_in_range(name: str) -> None:
    s = LIGHTS["sets"][name]
    assert len(s["tint"]) == 3 and all(0 < c <= 1 for c in s["tint"])
    assert 0 < s["shadow"]["strength"] < 1
