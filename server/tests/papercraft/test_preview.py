import copy

import numpy as np
import pytest

from simile.papercraft import preview
from simile.papercraft.village import TILE

VIEWS = preview.read_views()
WIDTH = 480


@pytest.fixture
def with_city(monkeypatch: pytest.MonkeyPatch) -> dict:
    m = copy.deepcopy(preview.manifest())
    m["streets"]["high_street"]["city"] = "layers/far-hills"
    middle = WIDTH / 2 / (VIEWS["high_street"].width * TILE * preview.SCENE_PPM)
    m["landmarks"] = {
        "apex": {
            "piece": "fronts/coffee_shop",
            "glow": "glow/coffee_shop",
            "at": {"high_street": middle},
        }
    }
    monkeypatch.setattr(preview, "manifest", lambda: m)
    return m


def scene(when: str = "afternoon", ppm: float = preview.SCENE_PPM) -> np.ndarray:
    image = preview.street_scene(VIEWS["high_street"], when, 0, WIDTH, ppm)
    return np.asarray(image, dtype=np.int16)


def test_a_street_is_drawn_at_the_pixels_a_metre_asked_for() -> None:
    assert scene(ppm=2 * preview.SCENE_PPM).shape[0] == 2 * preview.H


def test_a_street_with_a_city_draws_it_and_its_landmark(with_city: dict) -> None:
    city = scene()
    del with_city["landmarks"]
    skyline = scene()
    del with_city["streets"]["high_street"]["city"]
    plain = scene()

    assert np.abs(city - skyline).max() > 40
    assert np.abs(skyline - plain).max() > 40
