import json
from functools import cache

import numpy as np
import pytest
from PIL import Image

from simile.dolls.build import CONTENT, MISSES, fingerprint, people, personas
from simile.dolls.figure import EDITS, FRAMES, POSES
from simile.dolls.measure import CLOSE, MARKS, face_marks, hidden, swatches
from simile.dolls.sprites import HEAD, HEIGHT_M, PPM, climber, head, scale

BUDGET = 3 * 1024 * 1024
EVERYONE = people()
FEET_PX = 2.5
"""How far a frame's feet may be from under the middle of its head and its lowest row, after
the atlas's lossy WebP."""
SCALE_OFF = 0.1
"""How far a frame may be drawn bigger or smaller than the standing figure, once scaled."""
FROM_APPEARANCE = CLOSE + 1.5
"""The build matches within `CLOSE`; the atlas is smaller and lossy."""


def manifest(who: str) -> dict:
    return json.loads((CONTENT / f"{who}.json").read_text())


@cache
def atlas(who: str) -> Image.Image:
    return Image.open(CONTENT / manifest(who)["painted"]).convert("RGBA")


def frame(who: str, name: str) -> Image.Image:
    x, y, w, h = manifest(who)["frames"][name]["frame"]
    return atlas(who).crop((x, y, x + w, y + h))


def test_content_dolls_stay_within_budget() -> None:
    assert sum(path.stat().st_size for path in CONTENT.rglob("*") if path.is_file()) < BUDGET


@pytest.mark.parametrize("who", EVERYONE)
def test_every_resident_and_the_player_has_a_current_figure(who: str) -> None:
    found = manifest(who)

    said = personas().get(who, "")
    assert found["hash"] == fingerprint(who, EVERYONE[who], said), "run `uv run simile dolls paint`"
    assert found["appearance"] == EVERYONE[who].model_dump(mode="json")
    assert found["poses"] == POSES
    assert set(found["frames"]) == set(FRAMES)
    assert found["ppm"] == PPM and found["height"] == pytest.approx(HEIGHT_M * PPM, abs=0.1)


@pytest.mark.parametrize("who", EVERYONE)
def test_each_frame_stands_under_the_middle_of_its_head(who: str) -> None:
    depth = HEAD * HEIGHT_M * PPM
    hands_up = [f for f, pose in EDITS.items() if pose.bands == "climb"]
    for name, entry in manifest(who)["frames"].items():
        picture = frame(who, name)
        x, y, w, h = entry["frame"]
        assert x + w <= atlas(who).width and y + h <= atlas(who).height, name
        solid = np.asarray(picture.getchannel("A")) >= 128
        lowest = np.flatnonzero(solid.any(axis=1))[-1] + 1
        feet_x, feet_y = entry["feet"]
        assert feet_y == pytest.approx(lowest, abs=FEET_PX), name
        middle = climber(picture)[0] if name in hands_up else head(picture, depth)[0]
        assert feet_x == pytest.approx(middle, abs=FEET_PX), name


@pytest.mark.parametrize("who", EVERYONE)
def test_standing_figures_keep_the_appearances_colours(who: str) -> None:
    found = swatches(frame(who, "stand"), EVERYONE[who])

    for name, swatch in found.items():
        if name in hidden(EVERYONE[who]) or (who, name) in MISSES:
            continue
        assert swatch.delta_e < FROM_APPEARANCE, f"{name}: {swatch}"


@pytest.mark.parametrize("who", EVERYONE)
def test_every_frame_is_drawn_to_the_standing_figures_scale(who: str) -> None:
    stand = frame(who, "stand")
    for name, pose in EDITS.items():
        drawn = scale(frame(who, name), stand, pose.bands == "climb")
        assert drawn == pytest.approx(1, abs=SCALE_OFF), name


@pytest.mark.parametrize("who", EVERYONE)
def test_no_face_is_painted_over(who: str) -> None:
    for name in ["stand", *(name for name, pose in EDITS.items() if pose.face)]:
        assert face_marks(frame(who, name), EVERYONE[who]) <= MARKS, name
