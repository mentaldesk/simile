import numpy as np
import pytest
from PIL import Image, ImageDraw

from simile.characters.palette import PLAYER
from simile.dolls.bionics import (
    COMBINATIONS,
    FITTED,
    changed,
    edit_prompt,
    figure_id,
    laid,
    missing,
    patches,
    shows,
    spared,
)
from simile.dolls.figure import FRAMES, stand_prompt
from simile.dolls.flux import FakePainter, figure, fitted, named_colours
from simile.dolls.measure import face_marks
from simile.schema.player import Bionic, Body

from .keyed import keyed

LEGS, DATAJACK, EYE = FITTED
SIZE = (300, 400)


def whole() -> Image.Image:
    return figure(SIZE, named_colours(stand_prompt(PLAYER, "player")))


def with_parts(*parts: Bionic) -> Image.Image:
    painting = whole()
    for part in parts:
        painting = fitted(painting, edit_prompt("stand", part, PLAYER))
    return keyed(painting)


def test_every_combination_once_fewest_first() -> None:
    assert len(COMBINATIONS) == 7 == len(set(COMBINATIONS))
    assert [len(c) for c in COMBINATIONS] == [1, 1, 1, 2, 2, 2, 3]
    assert all(list(c) == sorted(c, key=FITTED.index) for c in COMBINATIONS)


@pytest.mark.parametrize(
    ("fitted_", "id_"),
    [
        ((), "player"),
        ((LEGS,), "player_legs"),
        ((EYE, LEGS), "player_legs_eye"),
        ((EYE, DATAJACK, LEGS), "player_legs_datajack_eye"),
    ],
)
def test_names_the_figure_for_whatever_is_fitted(fitted_: tuple, id_: str) -> None:
    assert figure_id(fitted_) == id_


def test_a_body_names_its_figure_by_its_bionics_whichever_eye() -> None:
    left = Body(left_eye=EYE, vertebra=DATAJACK)
    right = Body(right_eye=EYE, vertebra=DATAJACK, left_kidney="sold")

    assert figure_id(left.bionics) == figure_id(right.bionics) == "player_datajack_eye"


def test_the_eye_isnt_seen_from_behind() -> None:
    assert [f for f in FRAMES if not shows(EYE, f)] == ["climb"]
    assert all(shows(LEGS, f) and shows(DATAJACK, f) for f in FRAMES)


def test_each_part_is_asked_for_alone_over_the_whole_player() -> None:
    legs, eye = edit_prompt("run", LEGS, PLAYER), edit_prompt("run", EYE, PLAYER)

    assert "now with both legs replaced" in legs and "eye nearer the ear" not in legs
    assert " shorts and " in legs and " trousers and " not in legs
    assert "now with the eye nearer the ear" in eye and " trousers and " in eye
    assert "one bright red bionic eye" in eye and "simple dot eyes" in legs


def test_climbing_asks_for_no_face() -> None:
    climb = edit_prompt("climb", DATAJACK, PLAYER)

    assert "datajack" in climb and "eye" not in climb


def test_finds_each_part_painted() -> None:
    assert missing(with_parts(), FITTED, "stand") == ["legs", "datajack", "eye"]
    assert missing(with_parts(LEGS, DATAJACK, EYE), FITTED, "stand") == []
    assert missing(with_parts(DATAJACK), FITTED, "climb") == ["legs"]


def test_both_eyes_painted_red_is_one_too_many() -> None:
    painting = with_parts(EYE)
    w, h = SIZE
    ImageDraw.Draw(painting).ellipse((0.47 * w, 0.21 * h, 0.5 * w, 0.24 * h), (222, 30, 30))

    assert missing(painting, (EYE,), "stand") == ["two eyes"]


def test_the_face_check_spares_the_eye_and_nothing_else() -> None:
    eyed = with_parts(EYE)
    w, h = SIZE
    marked = eyed.copy()
    ImageDraw.Draw(marked).ellipse((0.53 * w, 0.27 * h, 0.6 * w, 0.32 * h), (139, 155, 180))

    assert face_marks(eyed, PLAYER, spared(eyed)) == 0
    assert face_marks(marked, PLAYER, spared(marked)) > 0


def test_counts_patches_biggest_first() -> None:
    mask = np.zeros((10, 10), dtype=bool)
    mask[1:3, 1:3] = True
    mask[5:9, 5:9] = True

    assert [int(p.sum()) for p in patches(mask)] == [16, 4]


def test_a_part_is_where_painting_it_changed_the_frame_near_it() -> None:
    player = with_parts()
    eye = with_parts(EYE)
    w, h = SIZE
    ImageDraw.Draw(eye).rectangle((0.45 * w, 0.8 * h, 0.55 * w, 0.85 * h), (139, 155, 180))

    where = changed(player, eye, EYE)

    lens = np.argwhere(np.asarray(eye.convert("RGB")) == (222, 30, 30))
    assert where[lens[:, 0], lens[:, 1]].all()
    assert not where[int(0.82 * h), int(0.5 * w)]
    assert where.sum() < 0.05 * where.size


def test_parts_are_laid_over_the_player_and_nothing_else_changes() -> None:
    player = with_parts()
    legs, eye = with_parts(LEGS), with_parts(EYE)
    w, h = SIZE

    both = laid(player, [(legs, changed(player, legs, LEGS)), (eye, changed(player, eye, EYE))])

    assert missing(both, (LEGS, EYE), "stand") == []
    before, after = np.asarray(player), np.asarray(both)
    assert (before[: int(0.12 * h)] == after[: int(0.12 * h)]).all()
    assert (before[:, : int(0.2 * w)] == after[:, : int(0.2 * w)]).all()


def test_the_fake_painter_paints_what_an_edit_asks_for() -> None:
    painter = FakePainter()
    base = painter.paint(stand_prompt(PLAYER, "player"), SIZE, 1)

    edited = painter.paint(edit_prompt("stand", EYE, PLAYER), SIZE, 1, [base])

    assert missing(keyed(edited), FITTED, "stand") == ["legs", "datajack"]
