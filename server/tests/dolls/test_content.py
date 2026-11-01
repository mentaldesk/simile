import json
from functools import cache

import numpy as np
import pytest
from PIL import Image

from simile.dolls import bionics
from simile.dolls.bionics import COMBINATIONS, SHORTS, figure_id, missing, spared
from simile.dolls.build import (
    CONTENT,
    LONG,
    MISSES,
    fingerprint,
    fitted_fingerprint,
    people,
    personas,
)
from simile.dolls.figure import EDITS, FRAMES, POSES
from simile.dolls.measure import CLOSE, CORES, MARKS, face_marks, hidden, swatches
from simile.dolls.sprites import (
    HEAD,
    HEIGHT_M,
    PPM,
    SOLES,
    climber,
    head,
    lower_edge,
    scale,
    seat,
    underside,
    upright,
)
from simile.schema import PLAYER_ID
from simile.schema.player import Bionic

BUDGET = 3 * 1024 * 1024
EVERYONE = people()
FITTED = {figure_id(c): c for c in COMBINATIONS}
FIGURES = EVERYONE | dict.fromkeys(FITTED, EVERYONE[PLAYER_ID])
"""Every resident, and the player with each combination of bionics."""
SAME_SIZE = 0.03
"""How much bigger or smaller the player's head may be drawn with bionics, once scaled."""
SHOWN = 0.7
"""The share of `bionics.LEAST` a part must cover once the atlas has shrunk it, lossily."""
EYE_SIZES = 2
"""How many atlas pixels wider the eye's lens may be in one frame than another."""
FEET_PX = 2.5
"""How far a frame's feet may be from under the middle of its head and its lowest row, after
the atlas's lossy WebP."""
INTERIOR = 0.002
"""The share of a figure that may be see-through away from its edge, after the lossy WebP."""
SCALE_OFF = 0.1
"""How far a frame may be drawn bigger or smaller than the standing figure, once scaled."""
FROM_APPEARANCE = CLOSE + 1.5
"""The build matches within `CLOSE`; the atlas is smaller and lossy."""
ON_SEAT = 0.03
"""Metres a sitting figure's seat may be from the bottom of its thighs as painted."""
LYING = [f for f, pose in EDITS.items() if pose.lying]


def manifest(who: str) -> dict:
    return json.loads((CONTENT / f"{who}.json").read_text())


@cache
def atlas(who: str) -> Image.Image:
    return Image.open(CONTENT / manifest(who)["painted"]).convert("RGBA")


def frame(who: str, name: str, laid: bool = False) -> Image.Image:
    """A frame as measured: lying ones turned head up, unless `laid`."""
    x, y, w, h = manifest(who)["frames"][name]["frame"]
    found = atlas(who).crop((x, y, x + w, y + h))
    return upright(found) if name in LYING and not laid else found


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


@pytest.mark.parametrize("who", FIGURES)
def test_each_frame_stands_under_the_middle_of_its_head(who: str) -> None:
    depth = HEAD * HEIGHT_M * PPM
    hands_up = [f for f, pose in EDITS.items() if pose.bands == "climb"]
    lifted = [f for f, pose in EDITS.items() if pose.lifted]
    for name, entry in manifest(who)["frames"].items():
        picture = frame(who, name)
        x, y, w, h = entry["frame"]
        assert x + w <= atlas(who).width and y + h <= atlas(who).height, name
        if name in LYING:
            continue
        solid = np.asarray(picture.getchannel("A")) >= 128
        lowest = np.flatnonzero(solid.any(axis=1))[-1] + 1
        feet_x, feet_y = entry["feet"]
        if name in lifted:
            assert feet_y >= lowest - FEET_PX, name
        else:
            assert feet_y == pytest.approx(lowest, abs=FEET_PX), name
        middle = climber(picture)[0] if name in hands_up else head(picture, depth)[0]
        assert feet_x == pytest.approx(middle, abs=FEET_PX), name


@pytest.mark.parametrize("who", FIGURES)
def test_lying_figures_lie_on_the_middle_of_their_underside_and_fit_a_bed(who: str) -> None:
    for name in LYING:
        entry = manifest(who)["frames"][name]
        laid = frame(who, name, laid=True)
        assert laid.width > laid.height, name
        assert entry["bed"] == entry["feet"], name
        assert entry["bed"] == pytest.approx(underside(laid), abs=FEET_PX), name
        if (who.split("_")[0], name, "length") not in MISSES:
            assert np.ptp(np.flatnonzero(np.asarray(laid.getchannel("A")).any(axis=0))) < LONG * PPM


@pytest.mark.parametrize("who", FIGURES)
def test_standing_figures_keep_the_appearances_colours(who: str) -> None:
    fitted = FITTED.get(who, ())
    cores = CORES | {"bottom": SHORTS} if bionics.LEGS_PART in fitted else CORES
    found = swatches(frame(who, "stand"), FIGURES[who], cores=cores)

    for name, swatch in found.items():
        unseen = hidden(FIGURES[who]) | bionics.hides(fitted)
        if name in unseen or (who, "stand", name) in MISSES:
            continue
        assert swatch.delta_e < FROM_APPEARANCE, f"{name}: {swatch}"


@pytest.mark.parametrize("who", FIGURES)
def test_every_frame_is_drawn_to_the_standing_figures_scale(who: str) -> None:
    stand = frame(who, "stand")
    for name, pose in EDITS.items():
        drawn = scale(frame(who, name), stand, pose.bands == "climb")
        assert drawn == pytest.approx(1, abs=SCALE_OFF), name


@pytest.mark.parametrize("who", FIGURES)
def test_no_face_is_painted_over(who: str) -> None:
    eye = Bionic.INFRARED_EYE in FITTED.get(who, ())
    for name in ["stand", *(name for name, pose in EDITS.items() if pose.face)]:
        picture = frame(who, name)
        assert face_marks(picture, FIGURES[who], spared(picture) if eye else None) <= MARKS, name


@pytest.mark.parametrize("who", FITTED)
def test_the_player_has_a_current_figure_for_each_combination_of_bionics(who: str) -> None:
    found = manifest(who)

    player = fingerprint(PLAYER_ID, EVERYONE[PLAYER_ID])
    assert found["hash"] == fitted_fingerprint(FITTED[who], player, EVERYONE[PLAYER_ID])
    assert found["fitted"] == [b.value for b in FITTED[who]]
    assert found["appearance"] == EVERYONE[PLAYER_ID].model_dump(mode="json")
    assert found["poses"] == POSES
    assert set(found["frames"]) == set(FRAMES)
    assert found["ppm"] == PPM and found["height"] == pytest.approx(HEIGHT_M * PPM, abs=0.1)


@pytest.mark.parametrize("who", FITTED)
def test_every_frame_shows_the_bionics_fitted(who: str) -> None:
    for name in FRAMES:
        assert missing(frame(who, name), FITTED[who], name, SHOWN) == [], name


def test_the_whole_player_shows_no_bionics() -> None:
    for name in FRAMES:
        found = missing(frame(PLAYER_ID, name), bionics.FITTED, name, SHOWN)

        assert found == [bionics.NAMES[b] for b in bionics.FITTED if bionics.shows(b, name)], name


@pytest.mark.parametrize("who", [who for who, parts in FITTED.items() if bionics.EYE in parts])
def test_the_eye_is_one_size_in_every_frame(who: str) -> None:
    def width(name: str) -> int:
        lens = bionics.patches(bionics.parts(frame(who, name))[bionics.EYE])[0]
        return int(np.ptp(np.flatnonzero(lens.any(axis=0)))) + 1

    widths = {name: width(name) for name in FRAMES if bionics.shows(bionics.EYE, name)}

    assert max(widths.values()) - min(widths.values()) <= EYE_SIZES, widths


@pytest.mark.parametrize("who", FITTED)
def test_the_player_is_the_same_size_whatever_is_fitted(who: str) -> None:
    drawn = scale(frame(who, "stand"), frame(PLAYER_ID, "stand"))

    assert drawn == pytest.approx(1, abs=SAME_SIZE)


@pytest.mark.parametrize("who", FIGURES)
def test_the_head_stays_level_through_the_run(who: str) -> None:
    def crown(name: str) -> float:
        solid = np.asarray(frame(who, name).getchannel("A")) >= 128
        return manifest(who)["frames"][name]["feet"][1] - np.flatnonzero(solid.any(axis=1))[0]

    for name, pose in EDITS.items():
        if pose.lifted:
            assert crown(name) >= crown(pose.lifted) - FEET_PX, name


@pytest.mark.parametrize("who", FIGURES)
def test_sitting_sits_on_its_thighs_with_its_feet_below(who: str) -> None:
    for name, pose in EDITS.items():
        if pose.seated:
            x, y = manifest(who)["frames"][name]["seat"]
            feet = manifest(who)["frames"][name]["feet"]
            assert x == feet[0]
            assert 0.1 < (feet[1] - y) / (HEIGHT_M * PPM) < 0.35, name


def thigh_line(solid: np.ndarray) -> int:
    """The bottom of the longest flat stretch of the lower edge behind the heels."""
    rows = np.flatnonzero(solid.any(axis=1))
    soles = solid[rows[-1] + 1 - round(SOLES * (rows[-1] - rows[0] + 1)) :]
    heel = int(np.flatnonzero(soles.any(axis=0))[0])
    edge = lower_edge(solid)[:heel]
    span, best = 2 * ON_SEAT * PPM, (0, 0)
    for start in range(len(edge)):
        end = start
        while end < len(edge) and edge[end] >= 0 and np.ptp(edge[start : end + 1]) <= span:
            end += 1
        if end - start > best[1] - best[0]:
            best = (start, end)
    return int(edge[best[0] : best[1]].max() + 1)


@pytest.mark.parametrize("who", FIGURES)
def test_sitting_sits_on_the_bottom_of_its_thighs_as_painted(who: str) -> None:
    for name, pose in EDITS.items():
        if pose.seated:
            entry = manifest(who)["frames"][name]
            picture = frame(who, name)
            solid = np.asarray(picture.getchannel("A")) >= 128
            measured = list(seat(picture, entry["feet"][0]))
            assert entry["seat"] == measured, "run `uv run simile dolls seats`"
            assert abs(entry["seat"][1] - thigh_line(solid)) / PPM <= ON_SEAT, name


@pytest.mark.parametrize("who", FIGURES)
def test_figures_are_opaque_inside_their_outline(who: str) -> None:
    alpha = np.asarray(atlas(who).getchannel("A")).astype(int)
    clear = alpha < 8
    edge = clear.copy()
    for dy in range(-3, 4):
        for dx in range(-3, 4):
            edge |= np.roll(clear, (dy, dx), axis=(0, 1))
    see_through = (alpha >= 8) & (alpha < 200)
    assert (see_through & ~edge).sum() <= INTERIOR * (alpha >= 8).sum()
