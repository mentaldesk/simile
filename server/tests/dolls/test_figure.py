import numpy as np
import pytest

from simile.characters.palette import PLAYER
from simile.dolls.colour import rgb
from simile.dolls.figure import (
    BODY,
    EDITS,
    FACE,
    FRAMES,
    POSES,
    edit_prompt,
    legs_guide,
    stand_prompt,
)
from simile.dolls.flux import FakePainter

from .keyed import keyed


def test_the_standing_painting_asks_for_the_clean_style_the_big_head_and_who_they_are() -> None:
    words = stand_prompt(PLAYER, "player", "A woman of 30.")

    assert "three-quarter view turned to the right" in words
    assert "A woman of 30. The person has golden tan skin" in words
    assert BODY in words and FACE in words
    assert "smooth, even dark brown ink outlines" in words
    assert "no smudges, stains or grime" in words
    assert "scratchy" not in words


@pytest.mark.parametrize("frame", EDITS)
def test_every_other_pose_redraws_the_same_character(frame: str) -> None:
    words = edit_prompt(frame, PLAYER, "player")

    assert words.startswith("Redraw image 1")
    assert "unchanged in every detail and the same size" in words
    assert "golden tan skin" in words
    assert (FACE in words) == (frame != "climb")


def test_every_pose_plays_only_painted_frames() -> None:
    assert {frame for frames in POSES.values() for frame in frames} == set(FRAMES)
    assert all(EDITS[frame].base in FRAMES for frame in EDITS)


def test_the_passing_step_is_painted_over_its_legs_redrawn() -> None:
    painting = FakePainter().paint("", (300, 400), 1)
    alpha = np.asarray(keyed(painting).getchannel("A"))

    guide = np.asarray(legs_guide(painting, alpha, PLAYER, "pass"), dtype=np.int16)

    before = np.asarray(painting, dtype=np.int16)
    rows = np.flatnonzero((alpha >= 128).any(axis=1))
    head = slice(rows[0], rows[0] + (rows[-1] - rows[0]) // 2)
    assert np.array_equal(guide[head], before[head])
    trousers = np.all(guide == rgb(PLAYER.bottom_colour), axis=2)
    assert trousers[rows[0] + (rows[-1] - rows[0]) * 3 // 4 :].sum() > 200
    assert not np.array_equal(guide, before)
