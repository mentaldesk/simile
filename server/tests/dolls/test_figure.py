import numpy as np
import pytest

from simile.characters.palette import PLAYER
from simile.dolls.colour import rgb
from simile.dolls.figure import (
    ASLEEP,
    BODY,
    EDITS,
    FACE,
    FRAMES,
    POSES,
    edit_prompt,
    legs_guide,
    stand_prompt,
    touching,
)
from simile.dolls.flux import FakePainter
from simile.schema.npc import Accessory

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
    assert (FACE in words) == (frame not in ("climb", "lie"))


def test_lying_asks_for_closed_eyes_head_to_the_left_and_no_bed() -> None:
    words = edit_prompt("lie", PLAYER, "player")

    assert ASLEEP in words and FACE not in words
    assert "the head on the left and the feet on the right" in words
    assert "no bed, no pillow, no blanket" in words
    assert EDITS["lie"].lying and not EDITS["sit"].lying


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


def test_an_apron_over_the_legs_is_kept_as_painted() -> None:
    painting = FakePainter().paint("", (300, 400), 1)
    alpha = np.asarray(keyed(painting).getchannel("A"))
    aproned = PLAYER.model_copy(update={"accessories": [Accessory.APRON]})

    plain = np.asarray(legs_guide(painting, alpha, PLAYER, "pass"))
    kept = np.asarray(legs_guide(painting, alpha, aproned, "pass"))

    changed = np.any(kept != plain, axis=2)
    assert changed.sum() > 100
    assert np.array_equal(kept[changed], np.asarray(painting.convert("RGB"))[changed])


def test_a_patch_is_every_pixel_joined_to_it_corners_included() -> None:
    mask = np.zeros((6, 6), dtype=bool)
    mask[1, 1] = mask[2, 2] = mask[3, 2] = mask[5, 5] = True

    patch = touching(mask, 1, 1)

    assert patch.sum() == 3 and not patch[5, 5]
    assert not touching(mask, 0, 0).any()
